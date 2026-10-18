"""
core/open_library_lookup.py

Looks up metadata AND a cover image for a book from its title/author
using the Open Library search + covers API (https://openlibrary.org,
free, no API key required). Replaces the narrower cover_search.py,
which only ever extracted a cover image even though Open Library's
search endpoint already returns title, authors, publisher, first
publish year, ISBN, and subjects (genre-like) in the same response.

Deliberately does NOT map Open Library's `language` field into this
app's Language metadata field: Open Library returns 3-letter codes
(e.g. "eng"), while this app's Language field expects 2-letter ISO
639-1 codes (see core/languages.py) -- importing the 3-letter code
directly would just write something that doesn't match what the rest
of the app expects, and a full conversion table is more than this
warrants right now.

Same "find, review, apply" pattern as everywhere else that fetches
external data -- here "review" means actually seeing the cover image.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from urllib.parse import quote

from core.author_sort import space_initials
from core.isbn import normalize_isbn
from redactor_common.core.lookup_client import fetch_bytes, fetch_json, make_default_fetch

SEARCH_URL = "https://openlibrary.org/search.json"
COVER_URL_TEMPLATE = "https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
DEFAULT_TIMEOUT = 8.0
# A couple of short backoff attempts specifically for HTTP 429 (rate
# limited) -- same reasoning as core/google_books_lookup.py: usually a
# short-lived limit that clears up after a brief wait, especially when
# searching several books in a row.
RATE_LIMIT_RETRY_DELAYS = (1.0, 2.0)

# Open Library's `subject` list on a popular work can run into the
# hundreds of entries (fan-curated tags, not a controlled vocabulary) --
# capped here so a single import doesn't dump an unusably long tag list
# into Genre.
MAX_SUBJECTS = 6


class OpenLibraryLookupError(Exception):
    """Raised for any problem searching for, parsing, or downloading
    Open Library results."""


@dataclass
class OpenLibraryCandidate:
    title: str = ""
    authors_str: str = ""
    publisher: str = ""
    pub_year: str = ""
    isbn: str = ""
    tags_str: str = ""
    cover_id: int = 0
    # Only the local database (core/openlibrary_local.py) fills these in;
    # the online search leaves them empty, so as_dict() is unchanged for it.
    language: str = ""
    pub_month: str = ""
    pub_day: str = ""
    subtitle: str = ""  # shown/compared, but there is no Subtitle field to apply it to
    pages: int = 0  # likewise
    score: float = 0.0  # how well a title/author search matched (0..1); ISBN matches don't set it

    def image_url(self) -> str:
        return COVER_URL_TEMPLATE.format(cover_id=self.cover_id)

    def display_label(self) -> str:
        bits = [self.title or "(untitled)"]
        if self.authors_str:
            bits.append(f"by {self.authors_str}")
        if self.pub_year:
            bits.append(f"({self.pub_year})")
        return " ".join(bits)

    def as_dict(self) -> dict:
        """Only the fields that actually came back, with keys already
        safe to pass straight to EpubBook.apply_metadata(). Deliberately
        excludes the cover -- that's handled separately via
        download_cover_image(), since it needs its own download step."""
        raw = {
            "title": self.title,
            "authors_str": self.authors_str,
            "publisher": self.publisher,
            "pub_year": self.pub_year,
            "isbn": self.isbn,
            "tags_str": self.tags_str,
            "language": self.language,
            "pub_month": self.pub_month,
            "pub_day": self.pub_day,
        }
        return {k: v for k, v in raw.items() if v}


# redactor_common's fixed-User-Agent fetch (same request this module
# used to build by hand); injectable via each function's `fetch` arg.
_default_fetch = make_default_fetch("EpubRedactor/1.0", timeout=DEFAULT_TIMEOUT)


def build_search_url(title: str, author: str = "", max_results: int = 6, publisher: str = "") -> str:
    title = (title or "").strip()
    if not title:
        raise OpenLibraryLookupError("A title is required to search Open Library.")
    params = [f"title={quote(title)}"]
    first_author = author.split(";")[0].strip() if author else ""
    if first_author:
        params.append(f"author={quote(first_author)}")
    if (publisher or "").strip():
        params.append(f"publisher={quote(publisher.strip())}")
    params.append(f"limit={max_results}")
    return f"{SEARCH_URL}?{'&'.join(params)}"


def parse_search_response(raw: bytes) -> list[OpenLibraryCandidate]:
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise OpenLibraryLookupError("Received an unreadable response from Open Library.") from exc
    return _candidates_from(data)


def _candidates_from(data) -> list[OpenLibraryCandidate]:
    candidates: list[OpenLibraryCandidate] = []
    for doc in (data or {}).get("docs", []) or []:
        authors = doc.get("author_name") or []
        publishers = doc.get("publisher") or []
        isbns = doc.get("isbn") or []
        subjects = (doc.get("subject") or [])[:MAX_SUBJECTS]
        candidates.append(OpenLibraryCandidate(
            title=doc.get("title", "") or "",
            authors_str=space_initials("; ".join(authors)),
            publisher=publishers[0] if publishers else "",
            pub_year=str(doc.get("first_publish_year") or ""),
            isbn=isbns[0] if isbns else "",
            tags_str="; ".join(subjects),
            cover_id=doc.get("cover_i") or 0,
        ))
    return candidates


def build_isbn_search_url(isbn: str, max_results: int = 3) -> str:
    isbn = normalize_isbn(isbn or "")
    if not isbn:
        raise OpenLibraryLookupError("An ISBN is required to search Open Library by ISBN.")
    return f"{SEARCH_URL}?isbn={quote(isbn)}&limit={max_results}"


def _fetch_search(url: str, fetch, sleep_fn) -> list[OpenLibraryCandidate]:
    """One search GET via redactor_common's fetch_json, with the
    rate-limit policy shared by both searches: an HTTP 429 is retried a
    couple of times with a short backoff before giving up -- see
    RATE_LIMIT_RETRY_DELAYS."""
    return _candidates_from(fetch_json(
        url, fetch or _default_fetch, OpenLibraryLookupError, "Open Library",
        unreachable_message="Could not reach Open Library (check your internet connection): {detail}",
        status_messages={429: (
            "Open Library is rate-limiting requests right now (HTTP 429) -- "
            "this usually clears up on its own after a minute or two. Try "
            "again shortly, or search fewer books at once."
        )},
        retry_429=RATE_LIMIT_RETRY_DELAYS, sleep=sleep_fn,
    ))


def search_open_library(
    title: str, author: str = "", fetch=None, max_results: int = 6, sleep_fn=time.sleep, publisher: str = ""
) -> list[OpenLibraryCandidate]:
    """Search for candidates. Raises OpenLibraryLookupError on missing
    title, network failure, or an unparseable response. Returns an
    empty list (not an error) when the search succeeds but finds
    nothing. With a `publisher` the search first asks for that publisher
    (a reprint's own edition ranks first), then, if nothing came back,
    again without it."""
    if (publisher or "").strip():
        found = _fetch_search(build_search_url(title, author, max_results, publisher), fetch, sleep_fn)
        if found:
            return found
    return _fetch_search(build_search_url(title, author, max_results), fetch, sleep_fn)


def search_open_library_by_isbn(
    isbn: str, fetch=None, max_results: int = 3, sleep_fn=time.sleep
) -> list[OpenLibraryCandidate]:
    """Works Open Library lists for exactly this ISBN (used by the Redact
    recipe). Same errors and retry policy as search_open_library()."""
    url = build_isbn_search_url(isbn, max_results)
    return _fetch_search(url, fetch, sleep_fn)


def download_cover_image(candidate: OpenLibraryCandidate, fetch=None) -> bytes:
    """Download the actual cover image bytes for a chosen candidate.
    Raises OpenLibraryLookupError if the candidate has no cover_id, the
    download fails, or comes back empty."""
    if not candidate.cover_id:
        raise OpenLibraryLookupError("This result has no cover image available.")
    return fetch_bytes(
        candidate.image_url(), fetch or _default_fetch, OpenLibraryLookupError, what="the cover image",
        status_messages={429: (
            "Open Library is rate-limiting requests right now (HTTP 429) -- "
            "wait a minute or two and try again."
        )},
        require_data=True,
    )
