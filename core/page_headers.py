"""
core/page_headers.py

Finds and removes the page furniture a scan-and-OCR conversion leaves in an EPUB's text: the running headers
("30 BRAZILIAN GOLD MINE MYSTERY" on a left page, "THE SAFARI STARTS 33" on a right one), bare page numbers, and
the empty paragraphs around them -- and puts back together the sentences a page break cut in two (a paragraph
that stops mid-sentence, a header, then a paragraph that carries on in lower case; a word split with a hyphen at
the page end).

Nothing in an ordinary book looks like this, so the detection wants EVIDENCE rather than a pattern match:

  * a numbered header is a short paragraph that is a number plus a heading (or a heading plus a number), whose
    heading text repeats at least MIN_REPEATS times in the book, and the numbers read through the whole book form a
    rising sequence (page numbers do; a stray "3 BLIND MICE" does not);
  * a heading with no number (the OCR lost it) counts only when the same heading was proved as a numbered one,
    and only after the first proved header (the title page is front matter and stays);
  * a bare number counts only when it fits between the page numbers of the headers around it;
  * a book with fewer than MIN_HEADERS proved headers is left alone.

The text is edited as text, paragraph by paragraph, never re-serialised, so everything else in a content document is
kept byte for byte. Only <p> paragraphs are looked at. Nothing is written here: find_page_furniture() returns a plan
(what would go, what would be joined, the evidence) and apply_page_furniture() stages the new documents on the book,
which writes them on save() like every other staged change. Qt-free.
"""

from __future__ import annotations

import difflib
import html
import posixpath
import re
import zipfile
from dataclasses import dataclass, field

from core.epub_metadata import NS, EpubBook, href_to_archive_path

MIN_REPEATS = 3  # a header's heading appears at least this often
MIN_HEADERS = 6  # proved numbered headers needed before anything is removed
MIN_RISING_SHARE = 0.85  # of consecutive header numbers, how many must go up
MAX_NUMBER_STEP = 60  # a jump bigger than this between two headers is not a page sequence
MAX_HEADING_CHARS = 70
MAX_HEADING_WORDS = 10
STRONG_EVIDENCE_HEADERS = 20  # at or above this the plan is high confidence
HIGH_CONFIDENCE = 0.95
MEDIUM_CONFIDENCE = 0.85
MAX_EMPTY_AROUND = 2
CAPITALS_SHARE = 0.8  # of a header's letters that are capitals, when it is printed in capitals
SIMILAR_HEADING = 0.85  # how alike an OCR-damaged heading is to a proved one
EXAMPLES = 6

_PARAGRAPH = re.compile(r"<p\b[^>]*?(?<!/)>(.*?)</p\s*>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")
_NUMBER_FIRST = re.compile(r"(\d{1,4})\s+(\D.{2,%d})" % MAX_HEADING_CHARS, re.S)
_NUMBER_LAST = re.compile(r"(\D.{2,%d}?)\s+(\d{1,4})" % MAX_HEADING_CHARS, re.S)
_BARE_NUMBER = re.compile(r"\[?(\d{1,4})\]?")
_ENDS_A_SENTENCE = re.compile(r"[.!?:…\"'”’»)\]]$")
_XHTML_TYPES = {"application/xhtml+xml", "text/html"}

KIND_LEFT = "header with page number (left)"
KIND_RIGHT = "header with page number (right)"
KIND_TITLE = "header without a page number"
KIND_NUMBER = "page number"
KIND_EMPTY = "empty paragraph at a page break"


@dataclass
class Block:
    start: int
    end: int
    inner: str
    text: str


@dataclass
class DocPlan:
    path: str
    new_text: str
    removed: list[tuple[str, str]] = field(default_factory=list)  # (kind, text)
    joins: int = 0
    hyphen_joins: int = 0


@dataclass
class PageFurniturePlan:
    docs: list[DocPlan] = field(default_factory=list)
    headers: int = 0  # proved numbered headers in the whole book
    headings: list[str] = field(default_factory=list)  # the repeated heading texts that were proved
    examples: list[str] = field(default_factory=list)
    reason: str = ""  # why nothing was found, when nothing was

    @property
    def removed(self) -> int:
        return sum(len(d.removed) for d in self.docs)

    @property
    def joins(self) -> int:
        return sum(d.joins for d in self.docs)

    @property
    def hyphen_joins(self) -> int:
        return sum(d.hyphen_joins for d in self.docs)

    @property
    def changed(self) -> bool:
        return any(d.removed or d.joins for d in self.docs)

    @property
    def confidence(self) -> float:
        return HIGH_CONFIDENCE if self.headers >= STRONG_EVIDENCE_HEADERS else MEDIUM_CONFIDENCE

    def summary(self) -> str:
        if not self.changed:
            return self.reason or "no running headers or page numbers found"
        bits = [f"{self.removed} header / page number line(s) removed"]
        if self.joins:
            bits.append(f"{self.joins} split sentence(s) rejoined" + (f" ({self.hyphen_joins} hyphenated)" if self.hyphen_joins else ""))
        return ", ".join(bits)

    def __str__(self) -> str:
        return self.summary()


# --- reading the paragraphs ------------------------------------------------------------------------------------


def _clean(text: str) -> str:
    return " ".join(html.unescape(_TAG.sub("", text)).replace("\xa0", " ").split())


def paragraph_blocks(text: str) -> list[Block]:
    return [Block(m.start(), m.end(), m.group(1), _clean(m.group(1))) for m in _PARAGRAPH.finditer(text)]


def _norm_heading(text: str) -> str:
    return re.sub(r"[\W_]+", " ", text.casefold()).strip()


def _capitals_share(text: str) -> float:
    letters = [ch for ch in text if ch.isalpha()]
    return sum(ch.isupper() for ch in letters) / len(letters) if letters else 0.0


def _heading_like(text: str) -> bool:
    words = text.split()
    if not words or len(text) > MAX_HEADING_CHARS or len(words) > MAX_HEADING_WORDS:
        return False
    # a sentence end inside ("It was late. He left.") says it is text; capitals ("MR. BREWSTER ARRIVES") do not
    return _capitals_share(text) >= CAPITALS_SHARE or not re.search(r"[.!?]\s+\S", text)


def content_paths(book: EpubBook) -> list[str]:
    """The archive paths of the book's readable content documents, in reading order."""
    root = book._opf_tree.getroot()  # noqa: SLF001 -- same package, like core/toc_generate.py
    manifest = root.find("opf:manifest", namespaces=NS)
    spine = root.find("opf:spine", namespaces=NS)
    if manifest is None or spine is None:
        return []
    items = {i.get("id"): i for i in manifest.findall("opf:item", namespaces=NS)}
    opf_dir = posixpath.dirname(book.opf_path)
    try:
        with zipfile.ZipFile(book.path, "r") as zf:
            names = set(zf.namelist())
    except (zipfile.BadZipFile, OSError):
        return []
    paths: list[str] = []
    for itemref in spine.findall("opf:itemref", namespaces=NS):
        item = items.get(itemref.get("idref"))
        if item is None or (item.get("media-type") or "").lower() not in _XHTML_TYPES:
            continue
        if "nav" in (item.get("properties") or "").split():
            continue
        path = href_to_archive_path(opf_dir, item.get("href") or "")
        if path and path in names and not book.is_path_encrypted(path) and path not in paths:
            paths.append(path)
    return paths


def _decode(data: bytes) -> tuple[str, bool] | None:
    bom = data.startswith(b"\xef\xbb\xbf")
    try:
        return data[3:].decode("utf-8") if bom else data.decode("utf-8"), bom
    except UnicodeDecodeError:
        return None


# --- finding the headers ---------------------------------------------------------------------------------------


@dataclass
class _Candidate:
    doc: int
    block: int
    kind: str
    number: int | None
    heading: str  # normalised
    text: str
    raw: str = ""  # the heading as printed (case and punctuation kept), without the page number


def _candidates(docs: list[tuple[str, list[Block]]]) -> list[_Candidate]:
    found: list[_Candidate] = []
    for d, (_path, blocks) in enumerate(docs):
        for b, block in enumerate(blocks):
            text = block.text
            if not text:
                continue
            if m := _BARE_NUMBER.fullmatch(text):
                found.append(_Candidate(d, b, KIND_NUMBER, int(m.group(1)), "", text))
                continue
            if m := _NUMBER_FIRST.fullmatch(text):
                if _heading_like(m.group(2)):
                    found.append(_Candidate(d, b, KIND_LEFT, int(m.group(1)), _norm_heading(m.group(2)), text, m.group(2).strip()))
                    continue
            if m := _NUMBER_LAST.fullmatch(text):
                if _heading_like(m.group(1)):
                    found.append(_Candidate(d, b, KIND_RIGHT, int(m.group(2)), _norm_heading(m.group(1)), text, m.group(1).strip()))
                    continue
            if _heading_like(text) and not text[-1] in ".,;":
                found.append(_Candidate(d, b, KIND_TITLE, None, _norm_heading(text), text))
    return found


def _rising(numbers: list[int]) -> bool:
    if len(numbers) < MIN_HEADERS:
        return False
    steps = list(zip(numbers, numbers[1:]))
    up = sum(1 for a, b in steps if 0 < b - a <= MAX_NUMBER_STEP)
    return up / len(steps) >= MIN_RISING_SHARE


def _prove(candidates: list[_Candidate]) -> tuple[list[_Candidate], set[str], set[str]]:
    """The numbered headers that are really page headers, the headings that were proved, and those headings exactly
    as printed (a chapter title in Title Case is not the running header in capitals)."""
    numbered = [c for c in candidates if c.kind in (KIND_LEFT, KIND_RIGHT) and c.heading]
    counts: dict[str, int] = {}
    for c in numbered:
        counts[c.heading] = counts.get(c.heading, 0) + 1
    repeated = [c for c in numbered if counts[c.heading] >= MIN_REPEATS]
    if len(repeated) < MIN_HEADERS or not _rising([c.number for c in repeated]):
        return [], set(), set()
    return repeated, {c.heading for c in repeated}, {c.raw for c in repeated}


# --- editing the documents -------------------------------------------------------------------------------------


def _join(a_inner: str, b_inner: str) -> tuple[str, bool]:
    """(the joined paragraph's inner HTML, whether a hyphen was dropped)."""
    hyphen = re.search(r"([^\W\d_])-(\s*(?:</[^>]+>\s*)*)$", a_inner)
    if hyphen:
        return a_inner[: hyphen.start()] + hyphen.group(1) + hyphen.group(2) + b_inner.lstrip(), True
    return a_inner.rstrip() + " " + b_inner.lstrip(), False


_CHAPTER_MARKER = re.compile(r"(chapter|part|book|section)\b.*|[IVXLC]{1,7}\.?|\d{1,3}\.?", re.I)


def _after_chapter_marker(blocks: list[Block], index: int, removed: dict[int, str]) -> bool:
    """True when the paragraph before this one (skipping empty ones) is a chapter marker ("CHAPTER IV"): the line
    after it is the chapter's own title, never a running header. A paragraph that is itself being removed (a page
    number) is not a marker."""
    for i in range(index - 1, -1, -1):
        if blocks[i].text and i not in removed:
            return bool(_CHAPTER_MARKER.fullmatch(blocks[i].text))
    return False


def _printed_like_a_header(raw: str, printed: set[str]) -> bool:
    if _capitals_share(raw) >= CAPITALS_SHARE:
        return True
    return any(difflib.SequenceMatcher(None, raw.casefold(), known.casefold()).ratio() >= SIMILAR_HEADING for known in printed)


def _rewrite_document(text: str, blocks: list[Block], remove: dict[int, str], join_sentences: bool = True) -> tuple[str, DocPlan]:
    plan = DocPlan(path="", new_text=text)
    inner = {b: blk.inner for b, blk in enumerate(blocks)}
    texts = {b: blk.text for b, blk in enumerate(blocks)}
    dropped: set[int] = set()
    for b, kind in remove.items():
        dropped.add(b)
        plan.removed.append((kind, blocks[b].text))
    # the empty paragraphs right beside a removed header belong to the page break
    for b in sorted(remove):
        for step in (-1, 1):
            n, i = 0, b + step
            while 0 <= i < len(blocks) and n < MAX_EMPTY_AROUND and (not texts[i] or i in dropped):
                if not texts[i] and i not in dropped:
                    dropped.add(i)
                    plan.removed.append((KIND_EMPTY, ""))
                    n += 1
                i += step
    # put the sentences a page break cut back together
    removed_at = sorted(remove)
    previous_kept: int | None = None
    for b in range(len(blocks)):
        if b in dropped:
            continue
        if not texts[b]:
            continue
        cut_between = join_sentences and previous_kept is not None and any(previous_kept < r < b for r in removed_at)
        if cut_between and not _ENDS_A_SENTENCE.search(texts[previous_kept]) and texts[b][0].islower():
            joined, hyphen = _join(inner[previous_kept], inner[b])
            inner[previous_kept] = joined
            texts[previous_kept] = _clean(joined)
            dropped.add(b)
            plan.joins += 1
            plan.hyphen_joins += hyphen
            continue
        previous_kept = b
    out, cursor = [], 0
    for b, blk in enumerate(blocks):
        out.append(text[cursor: blk.start])
        cursor = blk.end
        if b in dropped:
            continue
        if inner[b] != blk.inner:
            open_tag_end = text.index(">", blk.start) + 1
            out.append(text[blk.start: open_tag_end] + inner[b] + "</p>")
        else:
            out.append(text[blk.start: blk.end])
    out.append(text[cursor:])
    plan.new_text = "".join(out)
    return plan.new_text, plan


def find_page_furniture(book: EpubBook, join_sentences: bool = True) -> PageFurniturePlan:
    """What removing the running headers and page numbers (and rejoining the split sentences) would do to the book.
    Reads the documents as they currently stand (a staged change counts); changes nothing. `join_sentences=False`
    only removes the headers and leaves the cut sentences as they are."""
    plan = PageFurniturePlan()
    documents: list[tuple[str, str, bool]] = []  # path, text, had a BOM
    for path in content_paths(book):
        data = book.read_archive_file(path)
        decoded = _decode(data) if data else None
        if decoded:
            documents.append((path, decoded[0], decoded[1]))
    if not documents:
        plan.reason = "the book has no readable text documents"
        return plan
    parsed = [(path, paragraph_blocks(text)) for path, text, _bom in documents]
    candidates = _candidates(parsed)
    proved, headings, printed = _prove(candidates)
    if not proved:
        plan.reason = "no running headers or page numbers found"
        return plan
    plan.headers, plan.headings = len(proved), sorted(headings)
    first = min((c.doc, c.block) for c in proved)
    order = {c.doc * 1_000_000 + c.block: c for c in proved}
    remove: dict[int, dict[int, str]] = {}
    for c in proved:
        remove.setdefault(c.doc, {})[c.block] = c.kind
    proved_keys = sorted(order)
    for c in candidates:
        key = c.doc * 1_000_000 + c.block
        if key in order or (c.doc, c.block) <= first:
            continue
        if c.kind in (KIND_LEFT, KIND_RIGHT):
            # a short chapter, or an OCR slip in the heading ("RINO", "BANDITS1"), leaves a header the repeat count
            # does not prove; it still counts when its number fits the proved sequence and it is printed like the
            # others (capitals, or nearly the same text as a proved heading)
            before = [order[k].number for k in proved_keys if k < key]
            after = [order[k].number for k in proved_keys if k > key]
            fits = bool(before) and before[-1] < c.number and (c.number < after[0] if after else c.number - before[-1] <= MAX_NUMBER_STEP)
            if fits and _printed_like_a_header(c.raw, printed):
                remove.setdefault(c.doc, {})[c.block] = c.kind
        elif c.kind == KIND_TITLE and c.text in printed and not _after_chapter_marker(parsed[c.doc][1], c.block, remove.get(c.doc, {})):
            remove.setdefault(c.doc, {})[c.block] = c.kind
        elif c.kind == KIND_NUMBER:
            before = [order[k].number for k in proved_keys if k < key]
            after = [order[k].number for k in proved_keys if k > key]
            if before and after and before[-1] <= c.number <= after[0]:
                remove.setdefault(c.doc, {})[c.block] = c.kind
    for d, (path, text, bom) in enumerate(documents):
        if d not in remove:
            continue
        _new, doc_plan = _rewrite_document(text, parsed[d][1], remove[d], join_sentences)
        doc_plan.path = path
        if bom:
            doc_plan.new_text = "﻿" + doc_plan.new_text
        plan.docs.append(doc_plan)
        for kind, shown in doc_plan.removed:
            if shown and len(plan.examples) < EXAMPLES:
                plan.examples.append(f"{kind}: {shown}")
    return plan


def apply_page_furniture(book: EpubBook, plan: PageFurniturePlan) -> int:
    """Stages the plan's new documents on the book (written on save()). Returns how many documents changed."""
    count = 0
    for doc in plan.docs:
        if doc.removed or doc.joins:
            book.stage_content_replacement(doc.path, doc.new_text.encode("utf-8"))
            count += 1
    return count
