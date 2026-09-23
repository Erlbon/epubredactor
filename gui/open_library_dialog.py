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

from core.epub_metadata import EpubBook
from core.open_library_lookup import (
    OpenLibraryLookupError,
    download_cover_image,
    search_open_library,
)
from redactor_common.gui.lookup_dialog import LookupDialogBase, LookupResult

QUERY_FIELDS = [("title", "Title"), ("authors", "Author(s)")]


class OpenLibraryDialog(LookupDialogBase):
    def __init__(self, books: list[EpubBook], parent=None):
        self.books = books
        super().__init__(
            books, parent,
            window_title="Import Metadata from Open Library",
            info_text=(
                f"Searching Open Library for {len(books)} book(s) by title/author. Each "
                "match brings in title, authors, publisher, year, ISBN, genre and cover "
                "together -- untick anything you don't trust, then Apply."
            ),
            search_label="Searching Open Library…",
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

    # accepted_metadata() comes from LookupDialogBase.

    def accepted_covers(self) -> dict[int, tuple[bytes, str]]:
        """book index -> (image_bytes, mime), for every checked row that
        has a downloaded cover. Open Library covers are JPEG."""
        return {
            row: (result.cover_bytes, "image/jpeg")
            for row, result in self.accepted_rows().items()
            if result.cover_bytes
        }
