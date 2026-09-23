"""
gui/calibre_lookup_dialog.py

Looks up metadata for each selected book via the user's own Calibre
installation, using its bundled fetch-ebook-metadata command-line tool
(see core/calibre_lookup.py for why this shells out rather than loading
Calibre plugins directly). Whichever metadata source plugins actually
get used -- Google, Amazon, Open Library, or third-party ones like a
Goodreads-replacement or FantasticFiction scraper the user has added
themselves -- is entirely up to the user's own Calibre configuration.

Before anything can be searched, Calibre's tool has to be located. If
it isn't found automatically, the dialog asks the user to browse to it
once and remembers that choice.

Each lookup can take up to Calibre's own timeout (30s by default) since
it may be querying several online sources in sequence -- for anything
more than a handful of books, this can take a while, so the dialog
warns before starting a large batch.

Built on redactor_common's LookupDialogBase since 2026-09-23 (with
auto_search=False, since Calibre has to be located first): current vs
found cover side by side, and per-row title/author/ISBN correction with
"Search This Item".
"""

from __future__ import annotations

import os
import webbrowser

from PyQt6.QtWidgets import QFileDialog, QMessageBox, QPushButton

from core.calibre_lookup import CalibreLookupError, fetch_metadata
from core.calibre_tools import DOWNLOAD_URL, find_tool
from core.epub_metadata import EpubBook
from gui import app_settings
from redactor_common.gui.lookup_dialog import LookupDialogBase, LookupResult

# Above this many books, warn before starting -- each lookup can take up
# to Calibre's own ~30s timeout, so a big batch adds up fast.
WARN_BATCH_SIZE = 5

QUERY_FIELDS = [("title", "Title"), ("authors", "Author(s)"), ("isbn", "ISBN")]


class CalibreLookupDialog(LookupDialogBase):
    def __init__(self, books: list[EpubBook], parent=None):
        self.books = books
        self._tool_path = ""
        super().__init__(
            books, parent,
            window_title="Look Up via Calibre",
            info_text=(
                f"Looking up {len(books)} book(s) via your Calibre installation's own "
                "metadata plugins (Google, Amazon, Open Library, or any others you have "
                "enabled -- e.g. a Goodreads-replacement or FantasticFiction plugin).\n"
                "This can take a while for more than a few books."
            ),
            search_label="Looking up metadata via Calibre…",
            item_label=lambda book: os.path.basename(book.path),
            search_one=self._search_one,
            query_fields=QUERY_FIELDS,
            get_local_cover=lambda book: book.cover_bytes,
            progress_threshold=1,
            auto_search=False,
        )
        self.retry_btn.clicked.disconnect()
        self.retry_btn.clicked.connect(self._resolve_tool_and_run)

        self.change_tool_btn = QPushButton("Change Calibre Location…")
        self.change_tool_btn.clicked.connect(self._browse_for_tool)
        self.add_toolbar_button(self.change_tool_btn)
        self.download_btn = QPushButton("Download Calibre…")
        self.download_btn.clicked.connect(lambda: webbrowser.open(DOWNLOAD_URL))
        self.download_btn.setVisible(False)  # only shown once Calibre genuinely can't be found
        self.add_toolbar_button(self.download_btn)

        self._resolve_tool_and_run()

    # ------------------------------------------------------------------
    # Locating Calibre's tool

    def _resolve_tool_and_run(self) -> None:
        self.download_btn.setVisible(False)
        configured_dir = app_settings.load_calibre_install_dir()
        found = find_tool("fetch-ebook-metadata", configured_install_dir=configured_dir)
        if found is None:
            self._prompt_for_tool()
            return
        self._tool_path = found
        if len(self.books) > WARN_BATCH_SIZE:
            reply = QMessageBox.question(
                self,
                "Large batch",
                f"Looking up {len(self.books)} books via Calibre can take a while "
                "(each one may take up to Calibre's own timeout, ~30s). Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.run_search()

    def _prompt_for_tool(self) -> None:
        self.status_label.setText(
            "Couldn't find Calibre automatically. If you have it installed, click "
            "\"Change Calibre Location…\" and pick your install folder (this only needs "
            "doing once -- it's reused for both metadata lookup and format conversion). "
            "If you don't have it, it's free -- click \"Download Calibre…\"."
        )
        self.download_btn.setVisible(True)
        self.table.setRowCount(0)

    def _browse_for_tool(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Locate Your Calibre Install Folder")
        if not folder:
            return
        app_settings.save_calibre_install_dir(folder)
        self._resolve_tool_and_run()

    # ------------------------------------------------------------------
    # One lookup

    def _search_one(self, book: EpubBook, query_override: dict) -> LookupResult:
        used = {
            "title": query_override.get("title") or book.metadata.title,
            "authors": query_override.get("authors") or book.metadata.authors_str,
            "isbn": query_override.get("isbn") or book.metadata.isbn,
        }
        try:
            result = fetch_metadata(
                self._tool_path, title=used["title"], authors=used["authors"], isbn=used["isbn"],
            )
        except CalibreLookupError as exc:
            return LookupResult(error=str(exc), used_query=used)
        return LookupResult(fields=result.as_dict(), used_query=used)

    # ------------------------------------------------------------------
    # Result accessor, read by the caller after exec() returns Accepted

    def accepted_changes(self) -> dict[int, dict[str, str]]:
        """book index -> {field_key: value}, for every row whose checkbox
        is checked and which found something."""
        return self.accepted_metadata()
