"""
core/google_books_lookup.py

Looks up metadata AND a cover image for a book from its title/author
using the Google Books API (https://www.googleapis.com/books/v1/volumes)
-- free, no API key required for this volume of use. Replaces the
narrower isbn_lookup.py, which threw away everything from each result
except the ISBN even though Google Books already returns title,
authors, publisher, year, categories (genre-like), description,
language, and a cover thumbnail in the same response.

The actual HTTP call is injected via the `fetch` parameter so the JSON
-parsing logic can be unit-tested with canned responses, independent of
having real network access.
"""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import quote

from core.isbn import best_isbn13

API_URL = "https://www.googleapis.com/books/v1/volumes"
DEFAULT_TIMEOUT = 8.0
# A couple of short backoff attempts specifically for HTTP 429 (rate
# limited) -- Google's unauthenticated quota for this endpoint is
# fairly easy to trip when searching several books in a row (this app's
# own "Import Metadata from Google Books" dialog does exactly that),
# and the limit is typically short-lived enough that a brief wait and
# retry clears it without the person needing to do anything.
RATE_LIMIT_RETRY_DELAYS = (1.0, 2.0)


class GoogleBooksLookupError(Exception):
    """Raised for any problem searching for, parsing, or downloading
    Google Books results."""


@dataclass
class GoogleBooksCandidate:
    title: str = ""
    authors_str: str = ""
    publisher: str = ""
    pub_year: str = ""
    isbn13: str = ""
    isbn10: str = ""
    tags_str: str = ""
    language: str = ""
    description: str = ""
    cover_url: str = ""

    @property
    def best_isbn(self) -> str:
        return self.isbn13 or self.isbn10

    def display_label(self) -> str:
        bits = [self.title or "(untitled)"]
        if self.authors_str:
            bits.append(f"by {self.authors_str}")
        if self.pub_year:
            bits.append(f"({self.pub_year})")
        if self.publisher:
            bits.append(f"— {self.publisher}")
        return " ".join(bits)

    def as_dict(self) -> dict:
        """Only the fields that actually came back, with keys already
        safe to pass straight to EpubBook.apply_metadata(). Deliberately
        excludes cover_url -- the cover isn't a plain text metadata
        field, it needs a separate download step, so the caller handles
        it via download_cover_image() instead."""
        raw = {
            "title": self.title,
            "authors_str": self.authors_str,
            "publisher": self.publisher,
            "pub_year": self.pub_year,
            "isbn": best_isbn13(self.best_isbn) or self.best_isbn,
            "tags_str": self.tags_str,
            "language": self.language,
            "description": self.description,
        }
        return {k: v for k, v in raw.items() if v}


def _default_fetch(url: str, timeout: float = DEFAULT_TIMEOUT) -> bytes:
    request = urllib.request.Request(
        url, headers={"User-Agent": "EpubRedactor/1.0"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def build_query_url(title: str, authors_str: str = "", max_results: int = 5) -> str:
    title = (title or "").strip()
    if not title:
        raise GoogleBooksLookupError("A title is required to search Google Books.")

    query_parts = [f"intitle:{title}"]
    first_author = ""
    if authors_str:
        first_author = authors_str.split(";")[0].strip()
    if first_author:
        query_parts.append(f"inauthor:{first_author}")

    query = "+".join(query_parts)
    return f"{API_URL}?q={quote(query)}&maxResults={max_results}"


def _cover_url_from_image_links(image_links: dict) -> str:
    """Google Books commonly returns cover thumbnail URLs as plain
    http://, not https:// -- normalized here for consistency with the
    rest of this app, which fetches everything over https."""
    url = image_links.get("thumbnail") or image_links.get("smallThumbnail") or ""
    if url.startswith("http://"):
        url = "https://" + url[len("http://"):]
    return url


def parse_response(raw: bytes) -> list[GoogleBooksCandidate]:
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise GoogleBooksLookupError("Received an unreadable response from Google Books.") from exc

    candidates: list[GoogleBooksCandidate] = []
    for item in data.get("items", []) or []:
        info = item.get("volumeInfo", {}) or {}

        isbn13 = isbn10 = ""
        for ident in info.get("industryIdentifiers", []) or []:
            id_type = ident.get("type", "")
            value = ident.get("identifier", "")
            if id_type == "ISBN_13":
                isbn13 = value
            elif id_type == "ISBN_10":
                isbn10 = value

        candidates.append(
            GoogleBooksCandidate(
                title=info.get("title", "") or "",
                authors_str="; ".join(info.get("authors", []) or []),
                publisher=info.get("publisher", "") or "",
                pub_year=(info.get("publishedDate", "") or "")[:4],
                isbn13=isbn13,
                isbn10=isbn10,
                tags_str="; ".join(info.get("categories", []) or []),
                language=info.get("language", "") or "",
                description=info.get("description", "") or "",
                cover_url=_cover_url_from_image_links(info.get("imageLinks", {}) or {}),
            )
        )
    return candidates


def search_google_books(
    title: str,
    authors_str: str = "",
    fetch=None,
    max_results: int = 5,
    sleep_fn=time.sleep,
) -> list[GoogleBooksCandidate]:
    """Search for candidates matching the given title/author(s).

    Raises GoogleBooksLookupError on missing title, network failure, or
    an unparseable response. Returns an empty list (not an error) when
    the search succeeds but simply finds nothing. An HTTP 429 (rate
    limited) is retried a couple of times with a short backoff before
    giving up -- see RATE_LIMIT_RETRY_DELAYS -- since this is usually a
    transient, short-lived limit, not a real failure."""
    fetch = fetch or _default_fetch
    url = build_query_url(title, authors_str, max_results)

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
                raise GoogleBooksLookupError(
                    "Google Books is rate-limiting requests right now (HTTP 429) -- "
                    "this usually clears up on its own after a minute or two. Try "
                    "again shortly, or search fewer books at once."
                ) from exc
            raise GoogleBooksLookupError(
                f"Google Books returned an error (HTTP {exc.code}): {exc.reason}"
            ) from exc
        except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as exc:
            raise GoogleBooksLookupError(
                f"Could not reach Google Books (check your internet connection): {exc}"
            ) from exc

    return parse_response(raw)


def download_cover_image(candidate: GoogleBooksCandidate, fetch=None) -> bytes:
    """Download the actual cover image bytes for a chosen candidate.
    Raises GoogleBooksLookupError if the candidate has no cover_url, the
    download fails, or comes back empty."""
    if not candidate.cover_url:
        raise GoogleBooksLookupError("This result has no cover image available.")
    fetch = fetch or _default_fetch
    try:
        data = fetch(candidate.cover_url)
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise GoogleBooksLookupError(
                "Google Books is rate-limiting requests right now (HTTP 429) -- "
                "wait a minute or two and try again."
            ) from exc
        raise GoogleBooksLookupError(
            f"Could not download the cover image (HTTP {exc.code}): {exc.reason}"
        ) from exc
    except (urllib.error.URLError, OSError) as exc:
        raise GoogleBooksLookupError(f"Could not download the cover image: {exc}") from exc
    if not data:
        raise GoogleBooksLookupError("Cover image download returned no data.")
    return data
