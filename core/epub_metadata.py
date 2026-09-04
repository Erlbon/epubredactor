"""
core/epub_metadata.py

Pure-logic EPUB metadata engine. No GUI dependencies.

Handles reading and writing the standard Dublin Core metadata fields from
an EPUB's OPF (package) document, plus:

- Series information written in BOTH of the two conventions readers use
  in the wild:
    1. Calibre-style:   <meta name="calibre:series" content="..."/>
                         <meta name="calibre:series_index" content="..."/>
    2. EPUB3 collection: <meta property="belongs-to-collection" id="c01">Name</meta>
                          <meta refines="#c01" property="collection-type">series</meta>
                          <meta refines="#c01" property="group-position">1</meta>
  Writing both maximizes compatibility across Calibre, Kobo firmware of
  different vintages, and other reading apps.

- ISBN as a second <dc:identifier opf:scheme="ISBN">, kept separate from
  the book's primary/unique identifier (usually a UUID).

- Publication date as <dc:date>, split into year/month/day for editing
  and reassembled with only as much precision as was actually provided
  (a book with just a year won't get a fake "-01-01" bolted on).

- DDC (Dewey Decimal) classification as a <dc:subject opf:authority="DDC">,
  kept separate from ordinary tags/genre <dc:subject> elements.

- Cover image: located via the EPUB3 `properties="cover-image"` manifest
  attribute or the EPUB2 `<meta name="cover" content="...">` convention.
  Replacing/removing a cover is staged in memory (like every other edit)
  and only actually written into the zip -- including manifest changes --
  on save().

Design notes:
- We rewrite the OPF file (and, if the cover changed, the cover image
  file) in place inside a fresh zip, copying every other archive member
  byte-for-byte. The `mimetype` file is always written first, uncompressed
  (STORED), per the EPUB spec.
- All other members preserve their original compression type.
"""

from __future__ import annotations

import mimetypes
import posixpath
import re
import shutil
import uuid
import zipfile
import zlib
from dataclasses import dataclass, field
from typing import Optional

from lxml import etree

from core.validation_issue import (
    SEVERITY_ERROR,
    SEVERITY_LOCKED,
    SEVERITY_WARNING,
    ValidationIssue,
    status_for_issues,
)

NS = {
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
    "container": "urn:oasis:names:tc:opendocument:xmlns:container",
}

# Matches an ISBN embedded in a URN-style identifier, e.g. "urn:isbn:9780141439518".
_URN_ISBN_RE = re.compile(r"urn:isbn:(.+)", re.IGNORECASE)


class EpubError(Exception):
    """Raised for any problem reading or writing an EPUB's metadata."""


@dataclass
class EpubMetadata:
    """Plain-data snapshot of the text fields this tool edits. Cover image
    bytes are NOT part of this class -- they live on EpubBook directly,
    since they're binary and handled through their own add/replace/delete
    actions rather than the generic text-field edit flow.

    `authors` and `tags` are stored as lists internally but the GUI
    presents/edits them as a single semicolon-separated string, matching
    the mp3tag convention for multi-value fields (e.g. multiple genres).
    """

    title: str = ""
    isbn: str = ""
    authors: list[str] = field(default_factory=list)
    author_sort: list[str] = field(default_factory=list)  # "Last, First" per author, aligned by index
    series: str = ""
    series_index: str = ""
    collection: str = ""  # EPUB3 belongs-to-collection with collection-type="set"
    tags: list[str] = field(default_factory=list)
    publisher: str = ""
    pub_year: str = ""
    pub_month: str = ""
    pub_day: str = ""
    ddc: str = ""
    language: str = ""
    description: str = ""

    # ---- convenience string <-> list helpers used by the GUI layer ----

    @property
    def authors_str(self) -> str:
        return "; ".join(a for a in self.authors if a)

    @authors_str.setter
    def authors_str(self, value: str) -> None:
        self.authors = _split_multi(value)

    @property
    def author_sort_str(self) -> str:
        # Deliberately NOT filtering out blank entries here (unlike
        # authors_str/tags_str): author_sort is positionally aligned with
        # authors by index, so a blank in the middle (2nd of 3 authors has
        # no sort-name set) needs to stay visible as a gap, not collapse
        # and silently shift a later author's sort-name onto the wrong
        # author. A book with only its first author's sort-name set (by
        # far the common case) just shows that one value, no trailing
        # separators.
        while self.author_sort and not self.author_sort[-1]:
            self.author_sort = self.author_sort[:-1]
        return "; ".join(self.author_sort)

    @author_sort_str.setter
    def author_sort_str(self, value: str) -> None:
        self.author_sort = [p.strip() for p in value.split(";")] if value.strip() else []

    @property
    def tags_str(self) -> str:
        return "; ".join(t for t in self.tags if t)

    @tags_str.setter
    def tags_str(self, value: str) -> None:
        self.tags = _split_multi(value)

    def as_dict(self) -> dict:
        return {
            "title": self.title,
            "isbn": self.isbn,
            "authors_str": self.authors_str,
            "author_sort_str": self.author_sort_str,
            "series": self.series,
            "series_index": self.series_index,
            "collection": self.collection,
            "tags_str": self.tags_str,
            "publisher": self.publisher,
            "pub_year": self.pub_year,
            "pub_month": self.pub_month,
            "pub_day": self.pub_day,
            "ddc": self.ddc,
            "language": self.language,
            "description": self.description,
        }


def _split_multi(value: str) -> list[str]:
    parts = [p.strip() for p in value.split(";")]
    return [p for p in parts if p]


def parse_date_parts(text: str) -> tuple[str, str, str]:
    """Split a dc:date value into (year, month, day). Tolerates plain
    years ("2020"), year-month ("2020-05"), full dates ("2020-05-14"),
    and full datetimes ("2020-05-14T00:00:00Z") -- anything past the
    date portion is ignored. Missing/unparseable pieces come back "" ."""
    text = (text or "").strip()
    if not text:
        return "", "", ""
    date_part = text.split("T")[0]
    parts = date_part.split("-")
    year = parts[0].strip() if len(parts) >= 1 and parts[0].strip().isdigit() else ""
    month = parts[1].strip() if len(parts) >= 2 and parts[1].strip().isdigit() else ""
    day = parts[2].strip() if len(parts) >= 3 and parts[2].strip().isdigit() else ""
    if not year:  # a date with no valid year isn't usable in any granularity
        return "", "", ""
    return year, month, day


def format_date_parts(year: str, month: str, day: str) -> str:
    """Reassemble year/month/day into a dc:date value with only as much
    precision as was actually supplied -- a year-only book stays
    "2020", it doesn't silently gain a fabricated "-01-01"."""
    year = (year or "").strip()
    month = (month or "").strip()
    day = (day or "").strip()
    if not year:
        return ""
    if not month:
        return year
    if not day:
        return f"{year}-{month.zfill(2)}"
    return f"{year}-{month.zfill(2)}-{day.zfill(2)}"


def _find_opf_path(zf: zipfile.ZipFile) -> str:
    try:
        container_data = zf.read("META-INF/container.xml")
    except KeyError as exc:
        raise EpubError("Not a valid EPUB: missing META-INF/container.xml") from exc

    tree = etree.fromstring(container_data)
    rootfile = tree.find(".//container:rootfile", namespaces=NS)
    if rootfile is None:
        raise EpubError("Not a valid EPUB: no <rootfile> in container.xml")
    full_path = rootfile.get("full-path")
    if not full_path:
        raise EpubError("Not a valid EPUB: <rootfile> missing full-path")
    return full_path


class EpubBook:
    """Represents one EPUB file loaded for metadata editing."""

    def __init__(self, path: str):
        self.path = path
        self.opf_path: str = ""
        self._opf_tree: Optional[etree._ElementTree] = None
        self.metadata = EpubMetadata()
        self.dirty = False
        self.load_error: Optional[str] = None
        # Set when the most recent attempt to write this book's file to
        # disk failed (permission denied, file locked by another
        # program, etc.) -- distinct from load_error (a problem with the
        # file's own content) and from validation_status (the EPUB's
        # structural validity), since a perfectly valid, freshly-edited
        # book can still fail to save for reasons that have nothing to
        # do with the book itself. Cleared on the next successful save.
        self.save_error: str = ""

        # Cover image state. cover_bytes/cover_mime always reflect the
        # CURRENT state (on disk, or staged-but-unsaved). cover_changed
        # and cover_removed track whether that current state still needs
        # to be written to the actual file.
        self.cover_bytes: Optional[bytes] = None
        self.cover_mime: str = ""
        self.cover_changed = False
        self.cover_removed = False

        # Validation state, recomputed on load and after apply_fixes().
        self.validation_issues: list[ValidationIssue] = []
        self.validation_status: str = "OK"

        self._load()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load(self) -> None:
        try:
            with zipfile.ZipFile(self.path, "r") as zf:
                self.opf_path = _find_opf_path(zf)
                opf_data = zf.read(self.opf_path)
                self._opf_tree = etree.fromstring(
                    opf_data, parser=etree.XMLParser(remove_blank_text=False)
                ).getroottree()
                self.metadata = self._read_metadata()
                self._load_cover(zf)
                self._validate(zf)
        except (zipfile.BadZipFile, KeyError, etree.XMLSyntaxError, EpubError, OSError, zlib.error) as exc:
            # zlib.error specifically: raised when a zip ENTRY's own
            # compressed bytes are corrupted (truncated download, bit
            # rot, a bad write) -- distinct from zipfile.BadZipFile,
            # which is about the zip's own structure/header being
            # malformed. Neither is a subclass of the other, so both
            # need to be listed here explicitly; a file hit by this
            # previously crashed the entire load operation outright
            # (every other file in the same batch included) instead of
            # just failing gracefully on its own, the same as every
            # other kind of corruption already handled here.
            self.load_error = str(exc)
            self.validation_issues = [
                ValidationIssue("LOAD_FAILED", SEVERITY_ERROR, str(exc), fixable=False)
            ]
            self.validation_status = status_for_issues(self.validation_issues)


    def _metadata_el(self) -> etree._Element:
        root = self._opf_tree.getroot()
        md = root.find("opf:metadata", namespaces=NS)
        if md is None:
            raise EpubError("OPF has no <metadata> element")
        return md

    def _manifest_el(self) -> Optional[etree._Element]:
        root = self._opf_tree.getroot()
        return root.find("opf:manifest", namespaces=NS)

    @staticmethod
    def _iter_collections(md: etree._Element):
        """Yields (meta_el, coll_id, collection_type) for every
        belongs-to-collection meta. Per the EPUB3 spec, collection-type
        defaults to "series" when not explicitly refined -- this matters
        now that Series (collection-type="series") and Collection
        (collection-type="set") are both written as belongs-to-collection
        entries and must not be confused for each other."""
        for meta_el in md.findall("opf:meta", namespaces=NS):
            if meta_el.get("property") != "belongs-to-collection":
                continue
            coll_id = meta_el.get("id")
            coll_type = "series"
            if coll_id:
                type_el = md.find(
                    f'opf:meta[@refines="#{coll_id}"][@property="collection-type"]',
                    namespaces=NS,
                )
                if type_el is not None and (type_el.text or "").strip():
                    coll_type = (type_el.text or "").strip().lower()
            yield meta_el, coll_id, coll_type

    def _read_metadata(self) -> EpubMetadata:
        md = self._metadata_el()

        def first_text(tag: str) -> str:
            el = md.find(f"dc:{tag}", namespaces=NS)
            return (el.text or "").strip() if el is not None else ""

        title = first_text("title")
        publisher = first_text("publisher")
        language = first_text("language")
        description = first_text("description")
        pub_year, pub_month, pub_day = parse_date_parts(first_text("date"))

        opf_file_as_attr = f"{{{NS['opf']}}}file-as"
        authors: list[str] = []
        author_sort: list[str] = []
        for el in md.findall("dc:creator", namespaces=NS):
            name = (el.text or "").strip()
            if not name:
                continue
            authors.append(name)
            author_sort.append((el.get(opf_file_as_attr) or "").strip())
        while author_sort and not author_sort[-1]:
            author_sort.pop()

        opf_authority_attr = f"{{{NS['opf']}}}authority"
        tags: list[str] = []
        ddc = ""
        for el in md.findall("dc:subject", namespaces=NS):
            text = (el.text or "").strip()
            if not text:
                continue
            authority = (el.get(opf_authority_attr) or el.get("authority") or "").strip()
            if authority.upper() == "DDC":
                ddc = text
            else:
                tags.append(text)

        series = ""
        series_index = ""
        for meta_el in md.findall("opf:meta", namespaces=NS):
            name = meta_el.get("name")
            if name == "calibre:series":
                series = meta_el.get("content", "")
            elif name == "calibre:series_index":
                series_index = meta_el.get("content", "")

        if not series:
            # Fall back to EPUB3 collection metadata if calibre-style absent.
            for meta_el, coll_id, coll_type in self._iter_collections(md):
                if coll_type != "series":
                    continue
                series = (meta_el.text or "").strip()
                if coll_id:
                    pos_el = md.find(
                        f'opf:meta[@refines="#{coll_id}"][@property="group-position"]',
                        namespaces=NS,
                    )
                    if pos_el is not None:
                        series_index = (pos_el.text or "").strip()
                break

        collection = ""
        for meta_el, _coll_id, coll_type in self._iter_collections(md):
            if coll_type == "set":
                collection = (meta_el.text or "").strip()
                break

        isbn = self._read_isbn(md)

        return EpubMetadata(
            title=title,
            isbn=isbn,
            authors=authors,
            author_sort=author_sort,
            series=series,
            series_index=series_index,
            collection=collection,
            tags=tags,
            publisher=publisher,
            pub_year=pub_year,
            pub_month=pub_month,
            pub_day=pub_day,
            ddc=ddc,
            language=language,
            description=description,
        )

    @staticmethod
    def _read_isbn(md: etree._Element) -> str:
        """Find the ISBN among possibly-several dc:identifier elements.
        A book typically has its own primary identifier (a UUID), tracked
        by <package unique-identifier="...">, plus optionally an ISBN as a
        second one. We look for the ISBN specifically rather than assuming
        it's the primary identifier."""
        opf_scheme_attr = f"{{{NS['opf']}}}scheme"
        for el in md.findall("dc:identifier", namespaces=NS):
            text = (el.text or "").strip()
            if not text:
                continue
            scheme = el.get(opf_scheme_attr, "")
            if scheme.strip().upper() == "ISBN":
                m = _URN_ISBN_RE.match(text)
                return m.group(1).strip() if m else text
            m = _URN_ISBN_RE.match(text)
            if m:
                return m.group(1).strip()
        return ""

    # ------------------------------------------------------------------
    # Cover image
    # ------------------------------------------------------------------

    def _find_cover_item(self) -> Optional[etree._Element]:
        manifest = self._manifest_el()
        if manifest is None:
            return None
        # EPUB3 convention: item with properties="cover-image"
        for item in manifest.findall("opf:item", namespaces=NS):
            props = (item.get("properties") or "").split()
            if "cover-image" in props:
                return item
        # EPUB2 convention: <meta name="cover" content="<manifest id>">
        md = self._metadata_el()
        for meta_el in md.findall("opf:meta", namespaces=NS):
            if meta_el.get("name") == "cover":
                cover_id = meta_el.get("content")
                if cover_id:
                    for item in manifest.findall("opf:item", namespaces=NS):
                        if item.get("id") == cover_id:
                            return item
        return None

    def _cover_archive_path(self, href: str) -> str:
        opf_dir = posixpath.dirname(self.opf_path)
        return posixpath.normpath(posixpath.join(opf_dir, href)) if opf_dir else href

    def _load_cover(self, zf: zipfile.ZipFile) -> None:
        item = self._find_cover_item()
        if item is None:
            return
        href = item.get("href")
        if not href:
            return
        archive_path = self._cover_archive_path(href)
        try:
            self.cover_bytes = zf.read(archive_path)
        except KeyError:
            self.cover_bytes = None
            return
        media_type = item.get("media-type") or mimetypes.guess_type(href)[0] or ""
        self.cover_mime = media_type

    def set_cover(self, image_bytes: bytes, mime: str) -> None:
        """Stage a new cover image (add, or replace the existing one).
        Not written to disk until save()."""
        self.cover_bytes = image_bytes
        self.cover_mime = mime
        self.cover_changed = True
        self.cover_removed = False
        self.dirty = True

    def remove_cover(self) -> None:
        """Stage removal of the cover image. Not written to disk until
        save(). A no-op (but still marks dirty, harmlessly) if there was
        never a cover to begin with."""
        had_cover = self.cover_bytes is not None
        self.cover_bytes = None
        self.cover_mime = ""
        self.cover_changed = False
        self.cover_removed = True
        if had_cover:
            self.dirty = True

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    #
    # Deliberately NOT a full EPUB spec/accessibility validator (that's
    # what epubcheck is for) -- this covers the structural problems that
    # matter most for a bulk metadata-editing tool: things that could
    # make a book fail to open, lose its cover/TOC, or silently resist
    # having its metadata edited correctly. Content-document (chapter
    # XHTML) well-formedness is deliberately NOT checked, to keep loading
    # fast even for large batches of books.

    def _validate(self, zf: zipfile.ZipFile) -> None:
        issues: list[ValidationIssue] = []
        names = set(zf.namelist())
        root = self._opf_tree.getroot()
        md = self._metadata_el()
        manifest = self._manifest_el()

        # --- mimetype: informational only. We always write this file
        # correctly ourselves on every save() regardless of what the
        # source had, so there's nothing for the user to "fix" here.
        if "mimetype" not in names:
            issues.append(ValidationIssue(
                "MIMETYPE_MISSING", SEVERITY_WARNING,
                "The required 'mimetype' file is missing (will be added automatically on next save).",
            ))
        else:
            if zf.read("mimetype") != b"application/epub+zip":
                issues.append(ValidationIssue(
                    "MIMETYPE_CONTENT", SEVERITY_WARNING,
                    "'mimetype' file content isn't exactly 'application/epub+zip' "
                    "(will be corrected automatically on next save).",
                ))
            first_name = zf.namelist()[0] if zf.namelist() else ""
            if first_name != "mimetype" or zf.getinfo("mimetype").compress_type != zipfile.ZIP_STORED:
                issues.append(ValidationIssue(
                    "MIMETYPE_POSITION", SEVERITY_WARNING,
                    "'mimetype' isn't the first, uncompressed entry, as the EPUB spec requires "
                    "(will be corrected automatically on next save).",
                ))

        # --- primary unique-identifier must point at a real dc:identifier
        primary_id = root.get("unique-identifier")
        id_elements = {el.get("id") for el in md.findall("dc:identifier", namespaces=NS) if el.get("id")}
        if not primary_id or primary_id not in id_elements:
            issues.append(ValidationIssue(
                "PRIMARY_ID_MISSING", SEVERITY_ERROR,
                "The package's unique-identifier doesn't point to any actual <dc:identifier> element.",
                fixable=True,
            ))

        # --- required metadata presence
        title_el = md.find("dc:title", namespaces=NS)
        if title_el is None or not (title_el.text or "").strip():
            issues.append(ValidationIssue("TITLE_MISSING", SEVERITY_WARNING, "No title is set.", fixable=False))
        lang_el = md.find("dc:language", namespaces=NS)
        if lang_el is None or not (lang_el.text or "").strip():
            issues.append(ValidationIssue(
                "LANGUAGE_MISSING", SEVERITY_WARNING, "No language is set.", fixable=True
            ))

        # --- manifest: files that should exist actually exist, ids are unique
        opf_dir = posixpath.dirname(self.opf_path)
        manifest_items = manifest.findall("opf:item", namespaces=NS) if manifest is not None else []
        seen_ids: set[str] = set()
        dup_ids: set[str] = set()
        for item in manifest_items:
            item_id = item.get("id")
            if item_id:
                if item_id in seen_ids:
                    dup_ids.add(item_id)
                seen_ids.add(item_id)
        missing_entries = self._missing_manifest_entries(names, opf_dir, manifest_items)
        if missing_entries:
            missing_hrefs = [href for _item_id, href in missing_entries]
            preview = ", ".join(missing_hrefs[:3]) + (", ..." if len(missing_hrefs) > 3 else "")
            issues.append(ValidationIssue(
                "MANIFEST_FILE_MISSING", SEVERITY_ERROR,
                f"{len(missing_hrefs)} file(s) referenced in the manifest are missing from "
                f"the archive: {preview}. Use Operations \u2192 Rebuild Manifest to review and "
                f"remove the broken references (not offered here as a one-click fix, since it "
                f"can affect reading-order content if the missing file is a spine document).",
                fixable=False,
            ))
        if dup_ids:
            issues.append(ValidationIssue(
                "DUPLICATE_MANIFEST_ID", SEVERITY_ERROR,
                f"Duplicate manifest id(s): {', '.join(sorted(dup_ids))}",
                fixable=False,
            ))

        # --- spine entries should reference a real manifest id
        spine = root.find("opf:spine", namespaces=NS)
        dangling: list[str] = []
        if spine is not None:
            for itemref in spine.findall("opf:itemref", namespaces=NS):
                idref = itemref.get("idref")
                if idref not in seen_ids:
                    dangling.append(idref or "(no idref)")
        if dangling:
            noun = "entry" if len(dangling) == 1 else "entries"
            issues.append(ValidationIssue(
                "DANGLING_SPINE_ITEMREF", SEVERITY_WARNING,
                f"{len(dangling)} spine {noun} reference a missing manifest id: "
                f"{', '.join(dangling[:3])}",
                fixable=True,
            ))

        # --- table of contents present (either flavor)
        has_nav = any("nav" in (item.get("properties") or "").split() for item in manifest_items)
        has_ncx = spine is not None and bool(spine.get("toc"))
        if not has_nav and not has_ncx:
            issues.append(ValidationIssue(
                "NO_TOC", SEVERITY_WARNING, "No table of contents (nav or NCX) found.", fixable=False
            ))

        # --- DRM detection (detection only -- this tool will never
        # attempt to remove or work around DRM). SEVERITY_LOCKED, not
        # SEVERITY_ERROR: a DRM-protected book isn't broken or corrupt --
        # it's a perfectly valid EPUB, just off-limits to editing here.
        if "META-INF/encryption.xml" in names:
            issues.append(ValidationIssue(
                "DRM_DETECTED", SEVERITY_LOCKED,
                "This book appears to be DRM-protected (META-INF/encryption.xml present). "
                "Editing or saving may not work correctly, and this tool cannot and will not "
                "remove DRM.",
                fixable=False,
            ))

        self.validation_issues = issues
        self.validation_status = status_for_issues(issues)

    def apply_fixes(self, issue_codes: Optional[set[str]] = None) -> list[str]:
        """Apply whichever currently-fixable validation issues are
        requested (or ALL fixable ones if issue_codes is None). Mutates
        the in-memory OPF tree and marks the book dirty -- nothing is
        written to disk until save(). Returns human-readable descriptions
        of what was fixed.

        Deliberately NOT covered by the app's Undo stack: these fixes
        resolve broken/missing structural data rather than changing
        user-authored content, and "undoing" a repaired dangling spine
        reference back to a broken one isn't a meaningful action."""
        if self.load_error:
            return []
        applicable = [
            issue for issue in self.validation_issues
            if issue.fixable and (issue_codes is None or issue.code in issue_codes)
        ]
        if not applicable:
            return []

        md = self._metadata_el()
        manifest = self._manifest_el()
        root = self._opf_tree.getroot()
        fixed: list[str] = []

        for issue in applicable:
            if issue.code == "PRIMARY_ID_MISSING":
                target = None
                for el in md.findall("dc:identifier", namespaces=NS):
                    if el.get("id"):
                        target = el
                        break
                if target is None:
                    target = etree.SubElement(md, f"{{{NS['dc']}}}identifier")
                    target.set("id", "BookId")
                    target.text = f"urn:uuid:{uuid.uuid4()}"
                root.set("unique-identifier", target.get("id"))
                fixed.append("Repaired the package's unique-identifier reference")

            elif issue.code == "LANGUAGE_MISSING":
                el = md.find("dc:language", namespaces=NS)
                if el is None:
                    el = etree.SubElement(md, f"{{{NS['dc']}}}language")
                el.text = "en"
                self.metadata.language = "en"
                fixed.append('Set language to "en" (please verify this is correct)')

            elif issue.code == "DANGLING_SPINE_ITEMREF":
                spine = root.find("opf:spine", namespaces=NS)
                valid_ids = (
                    {item.get("id") for item in manifest.findall("opf:item", namespaces=NS)}
                    if manifest is not None else set()
                )
                removed = 0
                if spine is not None:
                    for itemref in list(spine.findall("opf:itemref", namespaces=NS)):
                        if itemref.get("idref") not in valid_ids:
                            spine.remove(itemref)
                            removed += 1
                if removed:
                    noun = "reference" if removed == 1 else "references"
                    fixed.append(f"Removed {removed} broken spine {noun}")

        self.dirty = True
        self.revalidate()
        return fixed

    def revalidate(self) -> None:
        """Re-run validation against the file as it exists on disk right
        now, combined with the current in-memory OPF tree. Used both
        right after apply_fixes() (to confirm which tree-based issues
        just got resolved) and after save() (to confirm what's actually
        on disk now matches expectations -- e.g. that a "will be
        corrected automatically on next save" mimetype issue really was
        corrected this time, not just promised). A no-op, leaving
        whatever validation state already existed, if the file can't be
        reopened for some reason."""
        try:
            with zipfile.ZipFile(self.path, "r") as zf:
                self._validate(zf)
        except (zipfile.BadZipFile, KeyError, EpubError, OSError):
            pass

    @staticmethod
    def _missing_manifest_entries(
        names: set[str], opf_dir: str, manifest_items: list
    ) -> list[tuple[str, str]]:
        """Pure logic (given the archive's file listing and the manifest
        items already found): (item_id, href) for every manifest item
        whose file doesn't actually exist in the archive. Shared by
        _validate() and the public find_missing_manifest_files(), so
        there's exactly one place this matching logic lives."""
        missing = []
        for item in manifest_items:
            href = item.get("href")
            if not href:
                continue
            archive_path = posixpath.normpath(posixpath.join(opf_dir, href)) if opf_dir else href
            if archive_path not in names:
                missing.append((item.get("id") or "", href))
        return missing

    def find_missing_manifest_files(self) -> list[tuple[str, str]]:
        """Public, read-only: (item_id, href) for every manifest item
        whose referenced file doesn't exist in the archive right now.
        Opens the archive fresh, so it reflects current on-disk state
        even outside a validation pass. Used by the standalone "Rebuild
        Manifest" action (gui/manifest_rebuild_dialog.py) to show
        exactly what would be removed before anything happens."""
        try:
            with zipfile.ZipFile(self.path, "r") as zf:
                names = set(zf.namelist())
        except (zipfile.BadZipFile, KeyError, OSError):
            return []
        root = self._opf_tree.getroot()
        manifest = root.find("opf:manifest", namespaces=NS)
        if manifest is None:
            return []
        opf_dir = posixpath.dirname(self.opf_path)
        manifest_items = manifest.findall("opf:item", namespaces=NS)
        return self._missing_manifest_entries(names, opf_dir, manifest_items)

    def rebuild_manifest(self, item_ids: set[str] | None = None) -> list[str]:
        """Removes manifest <item> entries for item_ids -- or, if None,
        every entry find_missing_manifest_files() currently reports --
        plus any spine <itemref> referencing them. Returns the hrefs
        actually removed. Marks the book dirty and re-validates against
        the file as it exists on disk right now.

        Deliberately separate from apply_fixes()/Validate & Fix Issues'
        one-click flow: unlike those fixes, removing a manifest entry
        can affect actual reading-order content if the missing file was
        a spine document, not just an orphaned image -- so this is only
        ever triggered by an explicit, standalone action that shows
        exactly what it's about to remove first. Not pushed to Undo,
        same reasoning and same convention as apply_fixes(): this is a
        structural repair, not user-authored content, and the dialog's
        own upfront confirmation is the safeguard here instead."""
        root = self._opf_tree.getroot()
        manifest = root.find("opf:manifest", namespaces=NS)
        if manifest is None:
            return []

        if item_ids is None:
            item_ids = {item_id for item_id, _href in self.find_missing_manifest_files() if item_id}
        if not item_ids:
            return []

        removed_hrefs = []
        removed_ids = set()
        for item in list(manifest.findall("opf:item", namespaces=NS)):
            item_id = item.get("id")
            if item_id and item_id in item_ids:
                removed_hrefs.append(item.get("href", ""))
                removed_ids.add(item_id)
                manifest.remove(item)

        if removed_ids:
            spine = root.find("opf:spine", namespaces=NS)
            if spine is not None:
                for itemref in list(spine.findall("opf:itemref", namespaces=NS)):
                    if itemref.get("idref") in removed_ids:
                        spine.remove(itemref)
            self.dirty = True
            self.revalidate()

        return removed_hrefs

    # ------------------------------------------------------------------
    # Writing metadata back into the in-memory OPF tree
    # ------------------------------------------------------------------

    def apply_metadata(self, new_values: dict) -> None:
        """Apply a dict of field_name -> value onto this book's metadata
        and mark it dirty. Only keys present in new_values are changed."""
        changed = False
        for key, value in new_values.items():
            if key in ("authors_str", "author_sort_str", "tags_str"):
                setattr(self.metadata, key, value)
                changed = True
            elif hasattr(self.metadata, key):
                if getattr(self.metadata, key) != value:
                    setattr(self.metadata, key, value)
                    changed = True
        if changed:
            self.dirty = True

    def _rebuild_opf(self) -> tuple[bytes, dict]:
        """Returns (new_opf_bytes, file_ops), where file_ops describes any
        non-OPF archive changes needed (currently: cover image add/replace
        /remove): {"add": {archive_path: bytes}, "remove": {archive_path}}."""
        md = self._metadata_el()
        nsmap_dc = NS["dc"]
        nsmap_opf = NS["opf"]
        file_ops = {"add": {}, "remove": set()}

        def set_dc_single(tag: str, value: str) -> None:
            el = md.find(f"dc:{tag}", namespaces=NS)
            if not value:
                if el is not None:
                    md.remove(el)
                return
            if el is None:
                el = etree.SubElement(md, f"{{{nsmap_dc}}}{tag}")
            el.text = value

        def set_dc_multi(tag: str, values: list[str]) -> None:
            for el in md.findall(f"dc:{tag}", namespaces=NS):
                md.remove(el)
            for v in values:
                el = etree.SubElement(md, f"{{{nsmap_dc}}}{tag}")
                el.text = v

        def set_creators(authors: list[str], author_sort: list[str]) -> None:
            for el in md.findall("dc:creator", namespaces=NS):
                md.remove(el)
            opf_file_as_attr = f"{{{nsmap_opf}}}file-as"
            for i, name in enumerate(authors):
                el = etree.SubElement(md, f"{{{nsmap_dc}}}creator")
                el.text = name
                if i < len(author_sort) and author_sort[i]:
                    el.set(opf_file_as_attr, author_sort[i])

        set_dc_single("title", self.metadata.title)
        set_creators(self.metadata.authors, self.metadata.author_sort)
        set_dc_single("publisher", self.metadata.publisher)
        set_dc_single("language", self.metadata.language)
        set_dc_single("description", self.metadata.description)
        set_dc_single("date", format_date_parts(
            self.metadata.pub_year, self.metadata.pub_month, self.metadata.pub_day
        ))

        # --- subjects: tags/genre (plain dc:subject) and DDC classification
        # (dc:subject with opf:authority="DDC") share the same element type,
        # so they're rebuilt together to avoid clobbering one when writing
        # the other.
        for el in md.findall("dc:subject", namespaces=NS):
            md.remove(el)
        for tag_value in self.metadata.tags:
            el = etree.SubElement(md, f"{{{nsmap_dc}}}subject")
            el.text = tag_value
        if self.metadata.ddc.strip():
            el = etree.SubElement(md, f"{{{nsmap_dc}}}subject")
            el.set(f"{{{nsmap_opf}}}authority", "DDC")
            el.text = self.metadata.ddc.strip()

        # --- series & collection: strip ALL existing belongs-to-collection
        # meta (both series-type and other-type, e.g. "set"), then rewrite
        # fresh so we never leave stale/duplicate entries behind. Removal
        # is type-agnostic since both use the same element shapes; writing
        # is not, since Series and Collection are independent fields with
        # their own collection-type.
        for meta_el in md.findall("opf:meta", namespaces=NS):
            name = meta_el.get("name")
            prop = meta_el.get("property")
            refines = meta_el.get("refines")
            if name in ("calibre:series", "calibre:series_index"):
                md.remove(meta_el)
            elif prop == "belongs-to-collection":
                md.remove(meta_el)
            elif refines and prop in ("collection-type", "group-position"):
                md.remove(meta_el)

        if self.metadata.series:
            cal_series = etree.SubElement(md, f"{{{nsmap_opf}}}meta")
            cal_series.set("name", "calibre:series")
            cal_series.set("content", self.metadata.series)

            if self.metadata.series_index:
                cal_idx = etree.SubElement(md, f"{{{nsmap_opf}}}meta")
                cal_idx.set("name", "calibre:series_index")
                cal_idx.set("content", self.metadata.series_index)

            coll_id = "bookmeta-series"
            coll_el = etree.SubElement(md, f"{{{nsmap_opf}}}meta")
            coll_el.set("id", coll_id)
            coll_el.set("property", "belongs-to-collection")
            coll_el.text = self.metadata.series

            type_el = etree.SubElement(md, f"{{{nsmap_opf}}}meta")
            type_el.set("refines", f"#{coll_id}")
            type_el.set("property", "collection-type")
            type_el.text = "series"

            if self.metadata.series_index:
                pos_el = etree.SubElement(md, f"{{{nsmap_opf}}}meta")
                pos_el.set("refines", f"#{coll_id}")
                pos_el.set("property", "group-position")
                pos_el.text = self.metadata.series_index

        if self.metadata.collection:
            set_id = "bookmeta-collection"
            set_el = etree.SubElement(md, f"{{{nsmap_opf}}}meta")
            set_el.set("id", set_id)
            set_el.set("property", "belongs-to-collection")
            set_el.text = self.metadata.collection

            set_type_el = etree.SubElement(md, f"{{{nsmap_opf}}}meta")
            set_type_el.set("refines", f"#{set_id}")
            set_type_el.set("property", "collection-type")
            set_type_el.text = "set"

        self._write_isbn(md)
        self._write_cover(md, file_ops)

        new_opf_bytes = etree.tostring(
            self._opf_tree, xml_declaration=True, encoding="UTF-8", standalone=True
        )
        return new_opf_bytes, file_ops

    def _write_isbn(self, md: etree._Element) -> None:
        """Update or create the ISBN dc:identifier, without ever touching
        the package's primary/unique identifier element (referenced by
        <package unique-identifier="...">) -- removing or repurposing that
        one would make the EPUB invalid."""
        root = self._opf_tree.getroot()
        primary_id = root.get("unique-identifier")
        opf_scheme_attr = f"{{{NS['opf']}}}scheme"

        isbn_el = None
        for el in md.findall("dc:identifier", namespaces=NS):
            text = (el.text or "").strip()
            scheme = el.get(opf_scheme_attr, "")
            if scheme.strip().upper() == "ISBN" or _URN_ISBN_RE.match(text):
                isbn_el = el
                break

        new_isbn = self.metadata.isbn.strip()
        urn_match = _URN_ISBN_RE.match(new_isbn)
        if urn_match:  # tidy up an accidentally-pasted "urn:isbn:" prefix
            new_isbn = urn_match.group(1).strip()

        if not new_isbn:
            if isbn_el is not None and isbn_el.get("id") != primary_id:
                md.remove(isbn_el)
            return

        if isbn_el is not None:
            isbn_el.text = new_isbn
            isbn_el.set(opf_scheme_attr, "ISBN")
        else:
            new_el = etree.SubElement(md, f"{{{NS['dc']}}}identifier")
            new_el.set(opf_scheme_attr, "ISBN")
            new_el.text = new_isbn
            existing_ids = {e.get("id") for e in md.iter() if e.get("id")}
            candidate_id, n = "isbn-id", 2
            while candidate_id in existing_ids:
                candidate_id = f"isbn-id-{n}"
                n += 1
            new_el.set("id", candidate_id)

    def _write_cover(self, md: etree._Element, file_ops: dict) -> None:
        """Apply any staged cover add/replace/removal to the manifest (and
        record the corresponding raw-file change in file_ops for save() to
        act on). A no-op when the cover wasn't touched."""
        if not self.cover_changed and not self.cover_removed:
            return

        manifest = self._manifest_el()
        existing_item = self._find_cover_item()

        if self.cover_removed:
            if existing_item is not None:
                href = existing_item.get("href")
                if href:
                    file_ops["remove"].add(self._cover_archive_path(href))
                cover_id = existing_item.get("id")
                manifest.remove(existing_item)
                # epub2-style pointer meta, if present
                for meta_el in md.findall("opf:meta", namespaces=NS):
                    if meta_el.get("name") == "cover" and meta_el.get("content") == cover_id:
                        md.remove(meta_el)
            return

        # cover_changed: add or replace
        assert self.cover_bytes is not None
        if existing_item is not None:
            # Reuse the same href/id -- just overwrite the bytes and
            # correct the media-type, no manifest structure changes needed.
            href = existing_item.get("href")
            existing_item.set("media-type", self.cover_mime or "image/jpeg")
            file_ops["add"][self._cover_archive_path(href)] = self.cover_bytes
            return

        # No existing cover item: create one from scratch.
        ext = mimetypes.guess_extension(self.cover_mime or "image/jpeg") or ".jpg"
        href = f"cover-image{ext}"
        archive_path = self._cover_archive_path(href)

        existing_ids = {e.get("id") for e in md.iter() if e.get("id")}
        for e in manifest.iter():
            if e.get("id"):
                existing_ids.add(e.get("id"))
        cover_id, n = "cover-image", 2
        while cover_id in existing_ids:
            cover_id = f"cover-image-{n}"
            n += 1

        new_item = etree.SubElement(manifest, f"{{{NS['opf']}}}item")
        new_item.set("id", cover_id)
        new_item.set("href", href)
        new_item.set("media-type", self.cover_mime or "image/jpeg")
        new_item.set("properties", "cover-image")  # EPUB3 readers

        # Also add the EPUB2-style pointer for older readers/Calibre.
        cover_meta = etree.SubElement(md, f"{{{NS['opf']}}}meta")
        cover_meta.set("name", "cover")
        cover_meta.set("content", cover_id)

        file_ops["add"][archive_path] = self.cover_bytes

    # ------------------------------------------------------------------
    # Saving
    # ------------------------------------------------------------------

    def save(self, output_path: Optional[str] = None) -> None:
        """Write the updated metadata (and cover, if changed) back into an
        EPUB file.

        If output_path is None, overwrites self.path in place (via a
        temp file + atomic replace, so a crash mid-write can't corrupt
        the original). Otherwise writes a new file at output_path,
        leaving the source untouched.
        """
        if self.load_error:
            raise EpubError(f"Cannot save, file failed to load: {self.load_error}")

        new_opf_bytes, file_ops = self._rebuild_opf()
        target = output_path or self.path
        tmp_fd_path = target + ".tmp_write"

        with zipfile.ZipFile(self.path, "r") as src:
            names = src.namelist()
            infos = {i.filename: i for i in src.infolist()}

            with zipfile.ZipFile(tmp_fd_path, "w") as dst:
                written: set[str] = set()

                # Always write a spec-correct mimetype entry -- first,
                # uncompressed, exact required content -- regardless of
                # what the source had (even if it was missing entirely).
                # This is what validation's MIMETYPE_* issues refer to
                # when they say "corrected automatically on next save".
                dst.writestr(
                    zipfile.ZipInfo("mimetype"),
                    b"application/epub+zip",
                    compress_type=zipfile.ZIP_STORED,
                )
                written.add("mimetype")

                for name in names:
                    if name == "mimetype" or name in file_ops["remove"]:
                        continue
                    if name == self.opf_path:
                        data = new_opf_bytes
                    elif name in file_ops["add"]:
                        data = file_ops["add"][name]
                    else:
                        data = src.read(name)
                    info = infos[name]
                    new_info = zipfile.ZipInfo(name, date_time=info.date_time)
                    new_info.compress_type = info.compress_type
                    new_info.external_attr = info.external_attr
                    dst.writestr(new_info, data)
                    written.add(name)

                # Brand-new files not present in the original archive
                # (e.g. a cover added to a book that had none before).
                for path, data in file_ops["add"].items():
                    if path not in written:
                        dst.writestr(path, data)

        shutil.move(tmp_fd_path, target)
        # Only treat this as "saved" (clear dirty, adopt new path) when we
        # actually overwrote this book's own file. Saving to a *different*
        # path is a copy -- the original book is still exactly as dirty
        # (or not) as it was before, and still lives at its original path.
        if output_path is None or output_path == self.path:
            self.path = target
            self.dirty = False
            self.cover_changed = False
            self.cover_removed = False
