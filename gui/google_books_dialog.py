"""
gui/google_books_dialog.py

Import Metadata from Google Books: for each selected book, searches
Google Books using that book's own title/author and shows the best
match -- title, authors, publisher, year, ISBN, genre tags, language,
description, and cover, all from the same lookup.

One checkbox per book (not per field) -- ticking a row applies
everything found for that book, cover included. Nothing is written
until you click Apply, and you can untick any row you don't trust first.

Built on redactor_common's LookupDialogBase since 2026-09-23 (the shared
dialog was generalized from this one and cbz's lookups): the selected
row's current cover sits next to the found one at a readable size, and a
wrong guess can be corrected -- edit the title/author for that row and
"Search This Item" re-runs just it.
"""

from __future__ import annotations

import os

from core.epub_metadata import EpubBook
from core.google_books_lookup import (
    GoogleBooksLookupError,
    download_cover_image,
    search_google_books,
)
from redactor_common.gui.lookup_dialog import LookupDialogBase, LookupResult

QUERY_FIELDS = [("title", "Title"), ("authors", "Author(s)")]


class GoogleBooksDialog(LookupDialogBase):
    def __init__(self, books: list[EpubBook], parent=None):
        self.books = books
        super().__init__(
            books, parent,
            window_title="Import Metadata from Google Books",
            info_text=(
                f"Searching Google Books for {len(books)} book(s) by title/author. Each "
                "match brings in title, authors, publisher, year, ISBN, genre, language, "
                "description, and cover together -- untick anything you don't trust, then Apply."
            ),
            search_label="Searching Google Books…",
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
            candidates = search_google_books(title, authors)
        except GoogleBooksLookupError as exc:
            return LookupResult(error=str(exc), used_query=used)
        if not candidates:
            return LookupResult(used_query=used)

        best = candidates[0]
        cover_bytes = None
        cover_error = None
        if best.cover_url:
            try:
                cover_bytes = download_cover_image(best)
            except GoogleBooksLookupError as exc:
                cover_error = f"cover: {exc}"
        result = LookupResult(fields=best.as_dict(), cover_bytes=cover_bytes, used_query=used)
        if cover_error and not result.fields:
            result.error = cover_error
        return result

    # ------------------------------------------------------------------
    # Result accessors, read by the caller after exec() returns Accepted
    # (accepted_metadata() comes from LookupDialogBase)

    def accepted_covers(self) -> dict[int, tuple[bytes, str]]:
        """book index -> (image_bytes, mime), for every checked row that
        has a downloaded cover. Google Books thumbnails are JPEG."""
        return {
            row: (result.cover_bytes, "image/jpeg")
            for row, result in self.accepted_rows().items()
            if result.cover_bytes
        }
