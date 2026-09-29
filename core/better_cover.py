"""
core/better_cover.py

Looks up a book's cover by ISBN on Open Library's covers service, for
Operations > Find Better Covers... (gui/better_cover_dialog.py): a
low-resolution or missing cover can be replaced by the larger image
Open Library has for the same ISBN.

  https://covers.openlibrary.org/b/isbn/<ISBN>-L.jpg?default=false

answers 404 when it has no cover for that ISBN (without default=false it
would send a 1x1 placeholder instead). Open Library limits cover
lookups BY ISBN per IP address; when it refuses (403/429),
IsbnCoverLimitError says so and the caller stops asking for the rest.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from typing import Callable, Optional

from core.isbn import normalize_isbn
from core.version import APP_VERSION

COVER_BY_ISBN_URL = "https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg?default=false"
USER_AGENT = f"EpubRedactor/{APP_VERSION} (https://github.com/Erlbon/epubredactor)"
TIMEOUT = 20


class IsbnCoverError(Exception):
    """Open Library couldn't be reached or sent something unusable."""


class IsbnCoverLimitError(IsbnCoverError):
    """Open Library refused: its per-IP limit on ISBN cover lookups."""


def _default_get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read()


def fetch_cover_by_isbn(isbn: str, get: Optional[Callable[[str], bytes]] = None) -> Optional[bytes]:
    """The cover image Open Library has for this ISBN, or None when it
    has none (or the ISBN is empty)."""
    digits = normalize_isbn(isbn or "")
    if not digits:
        return None
    try:
        data = (get or _default_get)(COVER_BY_ISBN_URL.format(isbn=digits))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        if exc.code in (403, 429):
            raise IsbnCoverLimitError(
                "Open Library is refusing more cover lookups by ISBN for now (it limits how many one "
                "computer may make in a few minutes) -- try the rest again later."
            ) from exc
        raise IsbnCoverError(f"Open Library answered {exc.code}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise IsbnCoverError(f"Open Library couldn't be reached: {exc}") from exc
    return data or None
