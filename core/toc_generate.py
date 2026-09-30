"""
core/toc_generate.py

Builds a table of contents for a book that has none (validation issue
NO_TOC: neither an EPUB3 nav document nor an NCX) -- typical of badly
converted scanned-PDF EPUBs -- from what the spine documents themselves
say: their h1-h3 headings, else their <title>.

Like core/content_scan.py this is a best-guess heuristic, so nothing is
applied silently: generate_toc_entries() only PROPOSES entries (the
Repair dialog shows them first), and stage_generated_toc_for() stages
the rendered files on the book, which writes nothing until save().

Content documents are never modified: a heading without an id can't be
linked to, so only the first heading of a file (which is just "the top of
the file") gets a fragment-less entry; later id-less headings are dropped.

Qt-free; all paths are zip-member names with forward slashes.
"""

from __future__ import annotations

import math
import posixpath
import re
import uuid
import zipfile
from dataclasses import dataclass
from urllib.parse import quote
from xml.sax.saxutils import escape

import lxml.html

from core.epub_metadata import NS, EpubBook, href_to_archive_path

HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3}
_XHTML_TYPES = {"application/xhtml+xml", "text/html"}

# A heading (or <title>) text counts as a running page header -- and is
# ignored -- when it appears in at least this share of the book's content
# documents AND in at least MIN_REPEAT_DOCS of them, in a book with at
# least MIN_DOCS_FOR_REPEAT_CHECK documents (tiny books legitimately
# repeat things).
REPEAT_FRACTION = 0.30
MIN_REPEAT_DOCS = 3
MIN_DOCS_FOR_REPEAT_CHECK = 6

# More entries than this and the TOC is collapsed to the first entry of
# each document (hundreds of sub-headings are noise, not navigation).
COLLAPSE_ABOVE = 300

# The "Section N" last resort (no headings or titles anywhere) emits at
# most about this many entries, sampling documents evenly.
MAX_FALLBACK_SECTIONS = 40

MAX_TITLE_CHARS = 200
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
_FILENAME_LIKE = re.compile(r"\.(x?html?|xml)$|^(untitled|unknown|document|index|page\s*\d*)$", re.IGNORECASE)


@dataclass
class TocEntry:
    title: str
    archive_path: str
    fragment: str = ""  # "" = the document itself
    level: int = 1


@dataclass
class _Doc:
    ordinal: int  # 1-based position among the spine's content documents
    archive_path: str
    item_id: str
    headings: list  # [(level, text, id)] in document order
    title: str


def _clean(text: str) -> str:
    return _CONTROL_CHARS.sub("", " ".join((text or "").split()))[:MAX_TITLE_CHARS].strip()


def _key(text: str) -> str:
    return text.casefold()


def _heading_id(el) -> str:
    if el.get("id"):
        return el.get("id")
    # <h2><a id="x"></a>Title</h2> -- the anchor is the real link target.
    for child in el.iter():
        if child is not el and child.get("id"):
            return child.get("id")
    return ""


def _parse_doc(raw: bytes) -> tuple[list, str]:
    """([(level, text, id)], <title> text) for one content document;
    ([], "") for anything unparseable."""
    try:
        doc = lxml.html.document_fromstring(raw)
    except Exception:  # noqa: BLE001 - malformed/empty markup must never abort a scan
        return [], ""
    headings = []
    try:
        for el in doc.iter():
            tag = el.tag if isinstance(el.tag, str) else ""
            level = HEADING_TAGS.get(tag.lower())
            if not level:
                continue
            text = _clean(el.text_content())
            if text:
                headings.append((level, text, _heading_id(el)))
        title_el = doc.find(".//title")
        title = _clean(title_el.text_content()) if title_el is not None else ""
    except Exception:  # noqa: BLE001
        return [], ""
    return headings, title


def _spine_docs(book: EpubBook) -> list[_Doc]:
    root = book._opf_tree.getroot()  # noqa: SLF001 -- same package
    manifest = root.find("opf:manifest", namespaces=NS)
    spine = root.find("opf:spine", namespaces=NS)
    if manifest is None or spine is None:
        return []
    items = {i.get("id"): i for i in manifest.findall("opf:item", namespaces=NS)}
    opf_dir = posixpath.dirname(book.opf_path)

    docs: list[_Doc] = []
    try:
        with zipfile.ZipFile(book.path, "r") as zf:
            names = set(zf.namelist())
            for itemref in spine.findall("opf:itemref", namespaces=NS):
                item = items.get(itemref.get("idref"))
                if item is None or (item.get("media-type") or "").lower() not in _XHTML_TYPES:
                    continue
                if "nav" in (item.get("properties") or "").split():
                    continue
                archive_path = href_to_archive_path(opf_dir, item.get("href") or "")
                if not archive_path or archive_path not in names or book.is_path_encrypted(archive_path):
                    continue
                try:
                    raw = zf.read(archive_path)
                except (KeyError, OSError, RuntimeError, zipfile.BadZipFile):
                    continue
                headings, title = _parse_doc(raw)
                docs.append(_Doc(len(docs) + 1, archive_path, item.get("id") or "", headings, title))
    except (zipfile.BadZipFile, OSError):
        return []
    return docs


def _repeated_texts(docs: list[_Doc], per_doc_texts) -> set[str]:
    """Casefolded texts found in enough documents to be running headers."""
    if len(docs) < MIN_DOCS_FOR_REPEAT_CHECK:
        return set()
    counts: dict[str, int] = {}
    for doc in docs:
        for text in set(per_doc_texts(doc)):
            counts[text] = counts.get(text, 0) + 1
    threshold = max(MIN_REPEAT_DOCS, math.ceil(REPEAT_FRACTION * len(docs)))
    return {text for text, n in counts.items() if n >= threshold}


def _is_cover(doc: _Doc) -> bool:
    stem = posixpath.splitext(posixpath.basename(doc.archive_path))[0].lower()
    return "cover" in stem or "cover" in doc.item_id.lower()


def _normalize_levels(entries: list[TocEntry]) -> None:
    """In place: re-derives each level from the heading tags' nesting, so
    the first entry is level 1, no entry is more than one level deeper
    than the one before it, and same-tag entries stay siblings even when
    a higher heading (e.g. the h1 above an h2) was dropped."""
    open_tags: list[int] = []  # the original levels of the currently open ancestors
    for entry in entries:
        while open_tags and open_tags[-1] >= entry.level:
            open_tags.pop()
        original = entry.level
        entry.level = len(open_tags) + 1
        open_tags.append(original)


def generate_toc_entries(book: EpubBook) -> list[TocEntry]:
    """Proposed TOC entries for `book` in reading order, [] if the spine
    holds nothing usable. Read-only (opens the archive, changes nothing)."""
    if book.load_error or book._opf_tree is None:  # noqa: SLF001
        return []
    docs = _spine_docs(book)
    if not docs:
        return []

    book_title = _key(_clean(book.metadata.title))
    repeated_headings = _repeated_texts(docs, lambda d: [_key(t) for _l, t, _i in d.headings])
    repeated_titles = _repeated_texts(docs, lambda d: [_key(d.title)] if d.title else [])

    def meaningful_title(title: str) -> bool:
        k = _key(title)
        return bool(title) and k != book_title and k not in repeated_titles and not _FILENAME_LIKE.search(title)

    entries: list[TocEntry] = []
    first_entry_of_doc: list[int] = []  # index into entries, one per document that has any
    real_entries = 0  # entries from headings/titles, i.e. not the "Cover" label
    for doc in docs:
        start = len(entries)
        linkable_top = True  # the file's top is only a fair link target until a heading is kept
        for level, text, ident in doc.headings:
            if _key(text) in repeated_headings:
                continue
            if not ident and not linkable_top:
                continue  # can't link to it without editing the content
            linkable_top = False
            if entries[start:] and entries[-1].title == text and entries[-1].fragment == ident:
                continue
            entries.append(TocEntry(text, doc.archive_path, ident, level))
        if len(entries) > start:
            real_entries += 1
        elif meaningful_title(doc.title):
            entries.append(TocEntry(doc.title, doc.archive_path, "", 1))
            real_entries += 1
        elif doc.ordinal == 1 and _is_cover(doc):
            entries.append(TocEntry("Cover", doc.archive_path, "", 1))
        if len(entries) > start:
            first_entry_of_doc.append(start)

    if len(entries) > COLLAPSE_ABOVE:
        entries = [entries[i] for i in first_entry_of_doc]

    if not real_entries:
        # Nothing but (at most) a cover: the only way to give the book any
        # navigation is one "Section N" per document, sampled when the
        # book is hundreds of page-files long.
        step = max(1, math.ceil(len(docs) / MAX_FALLBACK_SECTIONS))
        entries = [
            TocEntry(f"Section {doc.ordinal}", doc.archive_path, "", 1)
            for doc in docs[::step]
        ]
        if _is_cover(docs[0]):
            entries[0] = TocEntry("Cover", docs[0].archive_path, "", 1)

    _normalize_levels(entries)
    return entries


# ----------------------------------------------------------------------
# Rendering: nav.xhtml (EPUB3) and toc.ncx, hrefs percent-encoded


def _href(from_dir: str, entry: TocEntry) -> str:
    rel = posixpath.relpath(entry.archive_path, from_dir or ".")
    href = quote(rel, safe="/")
    return f"{href}#{quote(entry.fragment, safe='')}" if entry.fragment else href


def _tree(entries: list[TocEntry]) -> list[list]:
    """Nests a flat, level-normalized entry list: [[entry, children], ...]."""
    roots: list[list] = []
    stack: list[list] = []  # stack[k] = the open node at level k + 1
    for entry in entries:
        node = [entry, []]
        del stack[entry.level - 1:]
        (stack[-1][1] if stack else roots).append(node)
        stack.append(node)
    return roots


def _attr(value: str) -> str:
    return escape(value, {'"': "&quot;"})


def render_nav(entries: list[TocEntry], nav_dir: str, language: str = "") -> bytes:
    def ol(nodes) -> str:
        items = []
        for entry, children in nodes:
            link = f'<a href="{_attr(_href(nav_dir, entry))}">{escape(entry.title)}</a>'
            items.append(f"<li>{link}{ol(children) if children else ''}</li>")
        return "<ol>" + "".join(items) + "</ol>"

    lang = f' xml:lang="{_attr(language)}" lang="{_attr(language)}"' if language else ""
    return "\n".join([
        '<?xml version="1.0" encoding="utf-8"?>',
        "<!DOCTYPE html>",
        f'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"{lang}>',
        '<head><meta charset="utf-8"/><title>Table of Contents</title></head>',
        "<body>",
        f'<nav epub:type="toc" id="toc"><h1>Table of Contents</h1>{ol(_tree(entries))}</nav>',
        "</body>",
        "</html>",
        "",
    ]).encode("utf-8")


def render_ncx(entries: list[TocEntry], ncx_dir: str, uid: str, title: str = "") -> bytes:
    counter = [0]

    def points(nodes) -> str:
        out = []
        for entry, children in nodes:
            counter[0] += 1
            n = counter[0]  # playOrder follows document order, parent before children
            out.append(
                f'<navPoint id="navpoint-{n}" playOrder="{n}">'
                f"<navLabel><text>{escape(entry.title)}</text></navLabel>"
                f'<content src="{_attr(_href(ncx_dir, entry))}"/>'
                f"{points(children)}</navPoint>"
            )
        return "".join(out)

    depth = max(e.level for e in entries) if entries else 1
    return "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">',
        f'<head><meta name="dtb:uid" content="{_attr(uid)}"/>'
        f'<meta name="dtb:depth" content="{depth}"/>'
        '<meta name="dtb:totalPageCount" content="0"/>'
        '<meta name="dtb:maxPageNumber" content="0"/></head>',
        f"<docTitle><text>{escape(_clean(title) or 'Table of Contents')}</text></docTitle>",
        f"<navMap>{points(_tree(entries))}</navMap>",
        "</ncx>",
        "",
    ]).encode("utf-8")


def _primary_identifier(book: EpubBook) -> str:
    root = book._opf_tree.getroot()  # noqa: SLF001
    md = root.find("opf:metadata", namespaces=NS)
    if md is not None:
        idents = md.findall("dc:identifier", namespaces=NS)
        wanted = root.get("unique-identifier")
        for el in idents:
            if wanted and el.get("id") == wanted and (el.text or "").strip():
                return el.text.strip()
        for el in idents:
            if (el.text or "").strip():
                return el.text.strip()
    return f"urn:uuid:{uuid.uuid4()}"


def _free_path(book: EpubBook, opf_dir: str, stem: str, ext: str) -> str:
    """An archive path next to the OPF that collides with no archive
    member and no manifest href (case-insensitively, for zips that are
    unpacked on case-insensitive file systems)."""
    taken: set[str] = set()
    try:
        with zipfile.ZipFile(book.path, "r") as zf:
            taken.update(n.casefold() for n in zf.namelist())
    except (zipfile.BadZipFile, OSError):
        pass
    manifest = book._manifest_el()  # noqa: SLF001
    if manifest is not None:
        for item in manifest.findall("opf:item", namespaces=NS):
            if item.get("href"):
                taken.add(href_to_archive_path(opf_dir, item.get("href")).casefold())
    n = 1
    while True:
        name = f"{stem}{'' if n == 1 else '-' + str(n)}{ext}"
        path = posixpath.join(opf_dir, name) if opf_dir else name
        if path.casefold() not in taken:
            return path
        n += 1


def render_toc_files(book: EpubBook, entries: list[TocEntry]) -> dict[str, tuple[str, bytes]]:
    """{"nav"/"ncx": (archive_path, bytes)} in the form
    EpubBook.stage_generated_toc() takes: an EPUB3 book gets both a nav
    document and an NCX (older readers, Calibre), an EPUB2 book just the
    NCX. Raises ValueError for an empty entry list."""
    if not entries:
        raise ValueError("no TOC entries to write")
    opf_dir = posixpath.dirname(book.opf_path)
    version = (book._opf_tree.getroot().get("version") or "").strip()  # noqa: SLF001
    files: dict[str, tuple[str, bytes]] = {}
    if version.startswith("3"):
        nav_path = _free_path(book, opf_dir, "nav", ".xhtml")
        files["nav"] = (nav_path, render_nav(entries, posixpath.dirname(nav_path), book.metadata.language))
    ncx_path = _free_path(book, opf_dir, "toc", ".ncx")
    files["ncx"] = (
        ncx_path,
        render_ncx(entries, posixpath.dirname(ncx_path), _primary_identifier(book), book.metadata.title),
    )
    return files


def needs_toc(book: EpubBook) -> bool:
    """True for a loaded book with the NO_TOC validation issue."""
    return not book.load_error and any(i.code == "NO_TOC" for i in book.validation_issues)


def stage_generated_toc_for(book: EpubBook, entries: list[TocEntry]) -> None:
    """Renders `entries` and stages them on the book (written on save())."""
    book.stage_generated_toc(render_toc_files(book, entries))
