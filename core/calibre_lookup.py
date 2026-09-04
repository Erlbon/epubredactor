"""
core/calibre_lookup.py

Integrates with the user's own Calibre installation via its bundled
`fetch-ebook-metadata` command-line tool. That tool runs whatever
metadata source plugins the user has installed and enabled in Calibre
itself -- including third-party plugins like Goodreads-replacement
scrapers or FantasticFiction, which Calibre does NOT ship by default
(Goodreads shut down its public API in 2020; both are commonly added
back in by users via Calibre's own Plugin manager).

This deliberately does NOT reimplement or load Calibre's plugin system
directly:
- Security: a "plugin" is arbitrary Python code. Shelling out to
  Calibre's own tool as a separate process means this app never
  executes third-party plugin code inside itself.
- Licensing: Calibre is GPLv3. Invoking its CLI as a subprocess doesn't
  link against or embed its code, so there's no copyleft entanglement
  the way there would be importing its internals directly.
- Maintenance: Calibre's plugin API is internal and shifts between
  versions. Its own CLI tool is the stable, documented surface.

Which plugins actually get used is entirely up to the user's own
Calibre configuration -- this module has no say in it beyond running
the fetch (no --allowed-plugin is passed, so Calibre uses everything
the user has enabled).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

from lxml import etree

from core.calibre_tools import no_console_window_kwargs
from core.epub_metadata import parse_date_parts

DEFAULT_TIMEOUT_SECONDS = 30
# Calibre's fetch-ebook-metadata can be extremely chatty on stderr when
# nothing is found -- logging every plugin's search attempts, URLs
# queried, and intermediate results, sometimes hundreds of lines. This
# bounds how much of that ends up in a raised CalibreLookupError's
# message, so a single failed lookup can't balloon this app's own
# results table/status area to an unusable size. The full log is still
# Calibre's own to inspect if genuinely needed; this app doesn't try to
# parse or interpret it, just avoids drowning in it.
MAX_STDERR_CHARS = 500


class CalibreLookupError(Exception):
    """Raised for any problem locating or running Calibre's metadata tool,
    or for a search with nothing to search on."""


@dataclass
class CalibreLookupResult:
    title: str = ""
    authors_str: str = ""
    author_sort_str: str = ""
    series: str = ""
    series_index: str = ""
    tags_str: str = ""
    publisher: str = ""
    pub_year: str = ""
    pub_month: str = ""
    pub_day: str = ""
    isbn: str = ""
    language: str = ""
    description: str = ""

    def as_dict(self) -> dict:
        """Only the fields that actually came back, with keys already
        safe to pass straight to EpubBook.apply_metadata()."""
        raw = {
            "title": self.title,
            "authors_str": self.authors_str,
            "author_sort_str": self.author_sort_str,
            "series": self.series,
            "series_index": self.series_index,
            "tags_str": self.tags_str,
            "publisher": self.publisher,
            "pub_year": self.pub_year,
            "pub_month": self.pub_month,
            "pub_day": self.pub_day,
            "isbn": self.isbn,
            "language": self.language,
            "description": self.description,
        }
        return {k: v for k, v in raw.items() if v}


def _localname(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def parse_calibre_opf(opf_bytes: bytes) -> CalibreLookupResult:
    """Parse the OPF Calibre's fetch-ebook-metadata --opf prints to
    stdout. Matches elements by local tag name rather than strict
    namespace-prefixed XPath, since exactly how the namespace gets
    declared can vary and this is more robust to that. Never raises --
    malformed input just yields an empty result."""
    result = CalibreLookupResult()
    if not opf_bytes:
        return result
    try:
        root = etree.fromstring(opf_bytes)
    except etree.XMLSyntaxError:
        return result

    authors: list[str] = []
    author_sort: list[str] = []
    tags: list[str] = []
    isbn = ""

    for el in root.iter():
        local = _localname(el.tag) if isinstance(el.tag, str) else ""
        text = (el.text or "").strip()

        if local == "title" and not result.title:
            result.title = text
        elif local == "creator":
            if text:
                authors.append(text)
                file_as = ""
                for attr_name, attr_val in el.attrib.items():
                    if _localname(attr_name) == "file-as":
                        file_as = attr_val.strip()
                author_sort.append(file_as)
        elif local == "subject":
            if text:
                tags.append(text)
        elif local == "publisher" and not result.publisher:
            result.publisher = text
        elif local == "language" and not result.language:
            result.language = text
        elif local == "description" and not result.description:
            result.description = text
        elif local == "date" and not result.pub_year:
            year, month, day = parse_date_parts(text)
            result.pub_year, result.pub_month, result.pub_day = year, month, day
        elif local == "identifier":
            scheme = ""
            for attr_name, attr_val in el.attrib.items():
                if _localname(attr_name) == "scheme":
                    scheme = attr_val
            if scheme.upper() == "ISBN" and not isbn and text:
                isbn = text
        elif local == "meta":
            name = el.get("name", "")
            if name == "calibre:series":
                result.series = el.get("content", "")
            elif name == "calibre:series_index":
                result.series_index = el.get("content", "")

    result.authors_str = "; ".join(authors)
    while author_sort and not author_sort[-1]:
        author_sort.pop()
    result.author_sort_str = "; ".join(author_sort)
    result.tags_str = "; ".join(tags)
    result.isbn = isbn
    return result


def fetch_metadata(
    exe_path: str,
    title: str = "",
    authors: str = "",
    isbn: str = "",
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    run_fn=subprocess.run,
) -> CalibreLookupResult:
    """Run Calibre's fetch-ebook-metadata for one book and parse its OPF
    output. `run_fn` is injectable (defaults to subprocess.run) so this
    is testable without a real Calibre install -- see test_calibre_lookup.py."""
    if not (title or authors or isbn):
        raise CalibreLookupError("Need at least a title, author, or ISBN to search with.")

    args = [exe_path, "--opf", "--timeout", str(timeout)]
    if title:
        args += ["--title", title]
    if authors:
        args += ["--authors", authors]
    if isbn:
        args += ["--isbn", isbn]

    try:
        proc = run_fn(args, capture_output=True, timeout=timeout + 15, **no_console_window_kwargs())
    except subprocess.TimeoutExpired as exc:
        raise CalibreLookupError(
            f"Calibre metadata lookup timed out after {timeout + 15}s."
        ) from exc
    except OSError as exc:
        raise CalibreLookupError(f"Could not run Calibre's fetch-ebook-metadata: {exc}") from exc

    if proc.returncode != 0:
        stderr_text = _decode(proc.stderr).strip()
        if len(stderr_text) > MAX_STDERR_CHARS:
            stderr_text = stderr_text[:MAX_STDERR_CHARS].rstrip() + "\u2026"
        raise CalibreLookupError(stderr_text or "Calibre metadata lookup found nothing or failed.")

    return parse_calibre_opf(proc.stdout if isinstance(proc.stdout, bytes) else _encode(proc.stdout))


def _decode(data) -> str:
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data or ""


def _encode(data) -> bytes:
    if isinstance(data, str):
        return data.encode("utf-8")
    return data or b""
