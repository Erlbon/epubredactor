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
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import quote

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
        }
        return {k: v for k, v in raw.items() if v}


def _default_fetch(url: str, timeout: float = DEFAULT_TIMEOUT) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "EpubRedactor/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def build_search_url(title: str, author: str = "", max_results: int = 6) -> str:
    title = (title or "").strip()
    if not title:
        raise OpenLibraryLookupError("A title is required to search Open Library.")
    params = [f"title={quote(title)}"]
    first_author = author.split(";")[0].strip() if author else ""
    if first_author:
        params.append(f"author={quote(first_author)}")
    params.append(f"limit={max_results}")
    return f"{SEARCH_URL}?{'&'.join(params)}"


def parse_search_response(raw: bytes) -> list[OpenLibraryCandidate]:
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise OpenLibraryLookupError("Received an unreadable response from Open Library.") from exc

    candidates: list[OpenLibraryCandidate] = []
    for doc in data.get("docs", []) or []:
        authors = doc.get("author_name") or []
        publishers = doc.get("publisher") or []
        isbns = doc.get("isbn") or []
        subjects = (doc.get("subject") or [])[:MAX_SUBJECTS]
        candidates.append(OpenLibraryCandidate(
            title=doc.get("title", "") or "",
            authors_str="; ".join(authors),
            publisher=publishers[0] if publishers else "",
            pub_year=str(doc.get("first_publish_year") or ""),
            isbn=isbns[0] if isbns else "",
            tags_str="; ".join(subjects),
            cover_id=doc.get("cover_i") or 0,
        ))
    return candidates


def search_open_library(
    title: str, author: str = "", fetch=None, max_results: int = 6, sleep_fn=time.sleep
) -> list[OpenLibraryCandidate]:
    """Search for candidates. Raises OpenLibraryLookupError on missing
    title, network failure, or an unparseable response. Returns an
    empty list (not an error) when the search succeeds but finds
    nothing. An HTTP 429 (rate limited) is retried a couple of times
    with a short backoff before giving up -- see
    RATE_LIMIT_RETRY_DELAYS."""
    fetch = fetch or _default_fetch
    url = build_search_url(title, author, max_results)

    remaining_delays = list(RATE_LIMIT_RETRY_DELAYS)
    while True:
        try:
            raw = fetch(url)
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and remaining_delays:
                sleep_fn(remaining_delays.pop(0))
                continue
            if exc.code == 429:
                raise OpenLibraryLookupError(
                    "Open Library is rate-limiting requests right now (HTTP 429) -- "
                    "this usually clears up on its own after a minute or two. Try "
                    "again shortly, or search fewer books at once."
                ) from exc
            raise OpenLibraryLookupError(
                f"Open Library returned an error (HTTP {exc.code}): {exc.reason}"
            ) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise OpenLibraryLookupError(
                f"Could not reach Open Library (check your internet connection): {exc}"
            ) from exc

    return parse_search_response(raw)


def download_cover_image(candidate: OpenLibraryCandidate, fetch=None) -> bytes:
    """Download the actual cover image bytes for a chosen candidate.
    Raises OpenLibraryLookupError if the candidate has no cover_id, the
    download fails, or comes back empty."""
    if not candidate.cover_id:
        raise OpenLibraryLookupError("This result has no cover image available.")
    fetch = fetch or _default_fetch
    try:
        data = fetch(candidate.image_url())
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise OpenLibraryLookupError(
                "Open Library is rate-limiting requests right now (HTTP 429) -- "
                "wait a minute or two and try again."
            ) from exc
        raise OpenLibraryLookupError(
            f"Could not download the cover image (HTTP {exc.code}): {exc.reason}"
        ) from exc
    except (urllib.error.URLError, OSError) as exc:
        raise OpenLibraryLookupError(f"Could not download the cover image: {exc}") from exc
    if not data:
        raise OpenLibraryLookupError("Cover image download returned no data.")
    return data
