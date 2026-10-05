"""
gui/isfdb_dialog.py

Metadata > Look Up > ISFDB (Local Database): for each selected book,
searches the offline ISFDB database (Tools > ISFDB Database) by the book's
own ISBN where it has one, else by title/author, and shows the best match --
title, authors, publisher, date, language and above all the book's SERIES
and number.

One checkbox per book (not per field) -- ticking a row applies everything
found for that book. Nothing is written until you click Apply, and the
overwrite review still asks before a differing value is replaced.

Built on redactor_common's LookupDialogBase, like the Open Library dialog:
per-row title/author correction with "Search This Item". ISFDB has no
covers, so there is no cover column.
"""

from __future__ import annotations

import os

from core.epub_metadata import EpubBook
from core.isbn import best_isbn13
from core.isfdb_local import IsfdbLocalError, local_search_by_isbn, local_search_by_title
from redactor_common.gui.lookup_dialog import LookupDialogBase, LookupResult

QUERY_FIELDS = [("title", "Title"), ("authors", "Author(s)")]


class IsfdbDialog(LookupDialogBase):
    """`local_path`: the offline ISFDB database (Tools > ISFDB Database)."""

    def __init__(self, books: list[EpubBook], parent=None, local_path: str = ""):
        self.books = books
        self.local_path = local_path
        super().__init__(
            books, parent,
            window_title="Import Metadata from ISFDB (Local Database)",
            info_text=(
                f"Searching the local ISFDB database for {len(books)} book(s): by ISBN where the book has "
                "one, else by title/author. Each match brings in the series and its number, authors, "
                "publisher, date and language together -- untick anything you don't trust, then Apply. "
                "(ISFDB covers science fiction, fantasy and horror.)"
            ),
            search_label="Searching the local ISFDB database…",
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
        try:
            candidates = []
            isbn = best_isbn13(book.metadata.isbn)
            if isbn and not query_override:  # a typed-in correction means "search by this text instead"
                candidates = local_search_by_isbn(self.local_path, isbn)
            if not candidates:
                if not title:
                    return LookupResult(error="no title set -- can't search", used_query=used)
                candidates = local_search_by_title(self.local_path, title, authors, book.metadata.pub_year)
        except IsfdbLocalError as exc:
            return LookupResult(error=str(exc), used_query=used)
        if not candidates:
            return LookupResult(used_query=used)
        return LookupResult(fields=candidates[0].as_dict(), used_query=used)

    # accepted_metadata() comes from LookupDialogBase.
