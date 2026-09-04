"""
core/content_scan.py

Scans the first few content documents of an EPUB (typically the title
page and copyright page) for text patterns that commonly carry metadata:
"Copyright (c) 2020 by Jane Doe", "Published by Acme Press", "ISBN
978-...", "Dewey Decimal 823.912", and so on.

This is inherently a best-guess heuristic tool, NOT a reliable parser --
real book front matter varies enormously in wording and layout. Every
result is a suggestion for the user to review, never applied
automatically (same "find candidates, human decides" pattern as the
ISBN lookup feature).
"""

from __future__ import annotations

import posixpath
import re
import zipfile
from dataclasses import dataclass, field

import lxml.html

from core.epub_metadata import EpubBook
from core.isbn import best_isbn13, is_valid_isbn

DEFAULT_MAX_DOCS = 4
DEFAULT_MAX_CHARS = 20000

_NS = {"opf": "http://www.idpf.org/2007/opf"}

_ISBN_RE = re.compile(
    r"ISBN(?:-1[03])?\s*[:#]?\s*([0-9][0-9\- ]{8,18}[0-9Xx])", re.IGNORECASE
)
_DDC_RE = re.compile(
    r"(?:Dewey\s*Decimal(?:\s*Classification)?|DDC)\s*[:#]?\s*(\d{3}(?:\.\d+)?)",
    re.IGNORECASE,
)
_COPYRIGHT_YEAR_RE = re.compile(r"Copyright\s*(?:\u00a9|\(c\))?\s*(\d{4})", re.IGNORECASE)
_FIRST_PUBLISHED_YEAR_RE = re.compile(
    r"First published(?:\s+in)?\s+(\d{4})", re.IGNORECASE
)
_COPYRIGHT_AUTHOR_RE = re.compile(
    r"Copyright\s*(?:\u00a9|\(c\))?\s*\d{4}\s*by[ \t]+"
    r"((?:[A-Z]\.|[A-Z][a-z'\-]+)(?:[ \t]+(?:[A-Z]\.|[A-Z][a-z'\-]+)){0,4})"
)
_PUBLISHED_BY_RE = re.compile(
    r"Published by\s+([A-Z][A-Za-z0-9&,'.\s]{2,60}?)(?:[.\n]|$)"
)
_PUBLISHER_SUFFIX_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9&'.\s]{2,50}?(?:Press|Publishing|Publications|Books))\b"
)


@dataclass
class ContentScanResult:
    title: str = ""
    authors_str: str = ""
    publisher: str = ""
    pub_year: str = ""
    isbn: str = ""
    ddc: str = ""
    source_snippets: dict = field(default_factory=dict)  # field -> matched text, for review

    def as_dict(self) -> dict:
        return {
            k: v for k, v in {
                "title": self.title,
                "authors_str": self.authors_str,
                "publisher": self.publisher,
                "pub_year": self.pub_year,
                "isbn": self.isbn,
                "ddc": self.ddc,
            }.items() if v
        }


def extract_text_from_epub(
    book: EpubBook, max_docs: int = DEFAULT_MAX_DOCS, max_chars: int = DEFAULT_MAX_CHARS
) -> str:
    """Plain text from the first few spine documents, in reading order."""
    if book.load_error or book._opf_tree is None:  # noqa: SLF001 -- same package
        return ""

    root = book._opf_tree.getroot()  # noqa: SLF001
    manifest = root.find("opf:manifest", namespaces=_NS)
    spine = root.find("opf:spine", namespaces=_NS)
    if manifest is None or spine is None:
        return ""

    id_to_href = {item.get("id"): item.get("href") for item in manifest.findall("opf:item", namespaces=_NS)}
    opf_dir = posixpath.dirname(book.opf_path)

    text_parts: list[str] = []
    total_chars = 0
    docs_read = 0

    try:
        with zipfile.ZipFile(book.path, "r") as zf:
            for itemref in spine.findall("opf:itemref", namespaces=_NS):
                if docs_read >= max_docs or total_chars >= max_chars:
                    break
                href = id_to_href.get(itemref.get("idref"))
                if not href:
                    continue
                archive_path = posixpath.normpath(posixpath.join(opf_dir, href)) if opf_dir else href
                try:
                    raw = zf.read(archive_path)
                except KeyError:
                    continue
                try:
                    doc = lxml.html.fromstring(raw)
                    text = " ".join(doc.itertext())
                except Exception:  # noqa: BLE001 - malformed content shouldn't crash a scan
                    continue
                text_parts.append(text)
                total_chars += len(text)
                docs_read += 1
    except (zipfile.BadZipFile, KeyError, OSError):
        return ""

    return " ".join(text_parts)[:max_chars]


def guess_metadata_from_text(text: str) -> ContentScanResult:
    result = ContentScanResult()
    if not text:
        return result

    isbn_match = _ISBN_RE.search(text)
    if isbn_match:
        candidate = isbn_match.group(1)
        if is_valid_isbn(candidate):
            result.isbn = best_isbn13(candidate) or candidate
            result.source_snippets["isbn"] = isbn_match.group(0).strip()

    ddc_match = _DDC_RE.search(text)
    if ddc_match:
        result.ddc = ddc_match.group(1)
        result.source_snippets["ddc"] = ddc_match.group(0).strip()

    year_match = _COPYRIGHT_YEAR_RE.search(text) or _FIRST_PUBLISHED_YEAR_RE.search(text)
    if year_match:
        result.pub_year = year_match.group(1)
        result.source_snippets["pub_year"] = year_match.group(0).strip()

    author_match = _COPYRIGHT_AUTHOR_RE.search(text)
    if author_match:
        result.authors_str = author_match.group(1).strip()
        result.source_snippets["authors_str"] = author_match.group(0).strip()

    publisher_match = _PUBLISHED_BY_RE.search(text) or _PUBLISHER_SUFFIX_RE.search(text)
    if publisher_match:
        result.publisher = publisher_match.group(1).strip().rstrip(".,")
        result.source_snippets["publisher"] = publisher_match.group(0).strip()

    return result


def scan_book(
    book: EpubBook, max_docs: int = DEFAULT_MAX_DOCS, max_chars: int = DEFAULT_MAX_CHARS
) -> ContentScanResult:
    text = extract_text_from_epub(book, max_docs, max_chars)
    return guess_metadata_from_text(text)
