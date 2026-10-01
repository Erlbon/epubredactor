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
COVER_BY_ID_URL = "https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"  # same as OpenLibraryCandidate.image_url()
USER_AGENT = f"EpubRedactor/{APP_VERSION} (https://github.com/Erlbon/epubredactor)"
TIMEOUT = 20
MAX_COVER_BYTES = 10 * 1024 * 1024  # a cover is never anywhere near this; don't buffer a runaway response


class IsbnCoverError(Exception):
    """Open Library couldn't be reached or sent something unusable."""


class IsbnCoverLimitError(IsbnCoverError):
    """Open Library refused: its per-IP limit on ISBN cover lookups."""


def _default_get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        data = response.read(MAX_COVER_BYTES + 1)
    if len(data) > MAX_COVER_BYTES:
        raise IsbnCoverError("Open Library sent an unreasonably large cover image")
    return data


def _get_cover(url: str, get: Optional[Callable[[str], bytes]]) -> Optional[bytes]:
    """One GET of a cover URL with the policy shared by both lookups: 404 is
    "none" (None), 403/429 the per-IP limit, anything else IsbnCoverError."""
    try:
        data = (get or _default_get)(url)
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


def fetch_cover_by_isbn(isbn: str, get: Optional[Callable[[str], bytes]] = None) -> Optional[bytes]:
    """The cover image Open Library has for this ISBN, or None when it
    has none (or the ISBN is empty)."""
    digits = normalize_isbn(isbn or "")
    if not digits:
        return None
    return _get_cover(COVER_BY_ISBN_URL.format(isbn=digits), get)


def fetch_cover_by_id(cover_id: int, get: Optional[Callable[[str], bytes]] = None) -> Optional[bytes]:
    """The cover image for an Open Library cover id (what the local database
    records for an edition), through the same GET, size cap and error policy
    as the ISBN lookup; None when the id is not positive or has no image."""
    if not isinstance(cover_id, int) or isinstance(cover_id, bool) or cover_id <= 0:
        return None
    return _get_cover(COVER_BY_ID_URL.format(cover_id=cover_id), get)


def fetch_cover_for_isbn(
    isbn: str, local_path: str = "", get: Optional[Callable[[str], bytes]] = None, local_search=None
) -> Optional[bytes]:
    """The cover for `isbn`: when the local Open Library database (`local_path`)
    has the edition with a cover id, that id is fetched directly; otherwise,
    or when that finds nothing, the by-ISBN lookup. Only the per-IP limit
    error is raised out of the id attempt (the ISBN lookup would hit it too)."""
    if local_path:
        from core.openlibrary_local import OpenLibraryLocalError, local_search_by_isbn

        try:
            found = (local_search or local_search_by_isbn)(local_path, isbn)
        except OpenLibraryLocalError:
            found = []
        for candidate in found:
            if candidate.cover_id > 0:
                try:
                    data = fetch_cover_by_id(candidate.cover_id, get)
                except IsbnCoverLimitError:
                    raise
                except IsbnCoverError:
                    break
                if data:
                    return data
                break
    return fetch_cover_by_isbn(isbn, get)
