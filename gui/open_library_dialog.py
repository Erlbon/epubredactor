"""
gui/open_library_dialog.py

Import Metadata from Open Library: for each selected book, searches
Open Library (openlibrary.org) using that book's own title/author and
shows the best match -- title, authors, publisher, year, ISBN, genre
tags (subjects), and cover, all from the same lookup.

One checkbox per book (not per field) -- ticking a row applies
everything found for that book, cover included, matching Calibre Lookup
and Google Books. Nothing is written until you click Apply.

Built on redactor_common's LookupDialogBase since 2026-09-23: current vs
found cover side by side, and per-row title/author correction with
"Search This Item".
"""

from __future__ import annotations

import os
from typing import Optional

from core.epub_metadata import EpubBook
from core.isbn import best_isbn13
from gui.cover_quality import image_size
from core.open_library_lookup import (
    OpenLibraryLookupError,
    download_cover_image,
    search_open_library,
)
from core.openlibrary_local import (
    OpenLibraryLocalError,
    local_search_by_isbn,
    local_search_by_title,
)
from redactor_common.gui.lookup_dialog import LookupDialogBase, LookupResult

QUERY_FIELDS = [("title", "Title"), ("authors", "Author(s)")]


class OpenLibraryDialog(LookupDialogBase):
    """`local_path`: the offline Open Library database (Tools > Open Library
    Database). With it the same dialog searches that file instead of the
    network: a book's own ISBN first, else title/author. The cover, when
    the edition has a cover id, is the only thing fetched online."""

    cover_fetch = None  # tests inject a fake fetch(url) -> bytes; None = the real network fetch

    def __init__(self, books: list[EpubBook], parent=None, local_path: str = ""):
        self.books = books
        self.local_path = local_path
        if local_path:
            window_title = "Import Metadata from Open Library (Local Database)"
            info_text = (
                f"Searching the local Open Library database for {len(books)} book(s): by ISBN where the "
                "book has one, else by title/author. Each match brings in title, authors, publisher, "
                "date, ISBN, language and (when Open Library has one) the cover together -- untick anything you don't trust, then Apply."
            )
            search_label = "Searching the local Open Library database…"
        else:
            window_title = "Import Metadata from Open Library"
            info_text = (
                f"Searching Open Library for {len(books)} book(s) by title/author. Each "
                "match brings in title, authors, publisher, year, ISBN, genre and cover "
                "together -- untick anything you don't trust, then Apply."
            )
            search_label = "Searching Open Library…"
        super().__init__(
            books, parent,
            window_title=window_title,
            info_text=info_text,
            search_label=search_label,
            item_label=lambda book: os.path.basename(book.path),
            search_one=self._search_one,
            query_fields=QUERY_FIELDS,
            get_local_cover=lambda book: book.cover_bytes,
            progress_threshold=1,
        )

    def _search_one(self, book: EpubBook, query_override: dict) -> LookupResult:
        title = query_override.get("title") or book.metadata.title.strip()
        authors = query_override.get("authors") or book.metadata.authors_str
        used = {"title": title, "authors": authors}
        if self.local_path:
            return self._search_local(book, query_override, title, authors, used)
        if not title:
            return LookupResult(error="no title set -- can't search", used_query=used)
        try:
            candidates = search_open_library(title, authors)
        except OpenLibraryLookupError as exc:
            return LookupResult(error=str(exc), used_query=used)
        if not candidates:
            return LookupResult(used_query=used)

        best = candidates[0]
        cover_bytes = None
        if best.cover_id:
            try:
                cover_bytes = download_cover_image(best)
            except OpenLibraryLookupError:
                cover_bytes = None  # metadata still usable without the cover
        return LookupResult(fields=best.as_dict(), cover_bytes=cover_bytes, used_query=used)

    def _search_local(self, book: EpubBook, query_override: dict, title: str, authors: str, used: dict) -> LookupResult:
        try:
            candidates = []
            isbn = best_isbn13(book.metadata.isbn)
            if isbn and not query_override:  # a typed-in correction means "search by this text instead"
                candidates = local_search_by_isbn(self.local_path, isbn)
            if not candidates:
                if not title:
                    return LookupResult(error="no title set -- can't search", used_query=used)
                candidates = local_search_by_title(self.local_path, title, authors, book.metadata.pub_year)
        except OpenLibraryLocalError as exc:
            return LookupResult(error=str(exc), used_query=used)
        if not candidates:
            return LookupResult(used_query=used)
        best = candidates[0]
        return LookupResult(fields=best.as_dict(), cover_bytes=self._local_cover(best), used_query=used)

    def _local_cover(self, candidate) -> Optional[bytes]:
        """The cover for a local match's Open Library cover id, fetched like the online
        path's (download_cover_image: same URL, size cap and errors). This runs on the
        lookup's worker thread; any failure -- or bytes that aren't an image -- is silent
        (the metadata is still usable without the cover). Nothing for cover id <= 0."""
        if candidate.cover_id <= 0:
            return None
        try:
            data = download_cover_image(candidate, fetch=self.cover_fetch)
        except OpenLibraryLookupError:
            return None
        return data if image_size(data) else None

    # accepted_metadata() comes from LookupDialogBase.

    def accepted_covers(self) -> dict[int, tuple[bytes, str]]:
        """book index -> (image_bytes, mime), for every checked row that
        has a downloaded cover. Open Library covers are JPEG."""
        return {
            row: (result.cover_bytes, "image/jpeg")
            for row, result in self.accepted_rows().items()
            if result.cover_bytes
        }
