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
"""

from __future__ import annotations

import os
import webbrowser

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.calibre_lookup import CalibreLookupError, fetch_metadata
from core.calibre_tools import DOWNLOAD_URL, find_tool
from core.epub_metadata import EpubBook
from core.error_summary import summarize_errors
from gui import app_settings

BOOK_COL, FOUND_COL, APPLY_COL = range(3)

# Above this many books, warn before starting -- each lookup can take up
# to Calibre's own ~30s timeout, so a big batch adds up fast.
WARN_BATCH_SIZE = 5


class CalibreLookupDialog(QDialog):
    def __init__(self, books: list[EpubBook], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Look Up via Calibre")
        self.resize(820, 520)
        self.books = books
        self._checkboxes: dict[int, QCheckBox] = {}
        self._results: dict[int, dict[str, str]] = {}
        self._tool_path = ""

        self._build_ui()
        self._resolve_tool_and_run()

    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self.info_label = QLabel(
            f"Looking up {len(self.books)} book(s) via your Calibre installation's own "
            "metadata plugins (Google, Amazon, Open Library, or any others you have "
            "enabled -- e.g. a Goodreads-replacement or FantasticFiction plugin).\n"
            "This can take a while for more than a few books."
        )
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Book", "Found", "Apply"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(FOUND_COL, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

        btn_row = QHBoxLayout()
        self.retry_btn = QPushButton("Search Again")
        self.retry_btn.clicked.connect(self._resolve_tool_and_run)
        btn_row.addWidget(self.retry_btn)
        self.change_tool_btn = QPushButton("Change Calibre Location…")
        self.change_tool_btn.clicked.connect(self._browse_for_tool)
        btn_row.addWidget(self.change_tool_btn)
        self.download_btn = QPushButton("Download Calibre…")
        self.download_btn.clicked.connect(lambda: webbrowser.open(DOWNLOAD_URL))
        self.download_btn.setVisible(False)  # only shown once Calibre genuinely can't be found
        btn_row.addWidget(self.download_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self.status_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Apply")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _readonly_item(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

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
        self._run_lookup()

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
    # Running the lookup

    def _run_lookup(self) -> None:
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

        self.table.setRowCount(len(self.books))
        self._checkboxes = {}
        self._results = {}
        progress = QProgressDialog("Looking up metadata via Calibre…", "Cancel", 0, len(self.books), self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)

        found_count = 0
        errors: list[str] = []
        for row, book in enumerate(self.books):
            if progress.wasCanceled():
                self.table.setRowCount(row)
                break
            progress.setValue(row)
            progress.setLabelText(f"Looking up: {os.path.basename(book.path)}")
            QApplication.processEvents()

            self.table.setItem(row, BOOK_COL, self._readonly_item(os.path.basename(book.path)))

            fields = {}
            try:
                result = fetch_metadata(
                    self._tool_path,
                    title=book.metadata.title,
                    authors=book.metadata.authors_str,
                    isbn=book.metadata.isbn,
                )
                fields = result.as_dict()
            except CalibreLookupError as exc:
                errors.append(f"{os.path.basename(book.path)}: {exc}")

            cb = QCheckBox()
            if fields:
                summary = "; ".join(f"{k}: {v}" for k, v in fields.items())
                self.table.setItem(row, FOUND_COL, self._readonly_item(summary))
                cb.setChecked(True)
                self._results[row] = fields
                found_count += 1
            else:
                self.table.setItem(row, FOUND_COL, self._readonly_item("(nothing found)"))
                cb.setEnabled(False)
            self._checkboxes[row] = cb
            self.table.setCellWidget(row, APPLY_COL, cb)

        progress.setValue(len(self.books))
        self.table.resizeColumnsToContents()

        msg = f"Found something for {found_count} of {len(self.books)} book(s)."
        if errors:
            msg += f" {len(errors)} error(s): {summarize_errors(errors)}"
        self.status_label.setText(msg)

    # ------------------------------------------------------------------
    # Result accessor, read by the caller after exec() returns Accepted

    def accepted_changes(self) -> dict[int, dict[str, str]]:
        """book index -> {field_key: value}, for every row whose checkbox
        is checked and which found something."""
        return {
            row: self._results[row]
            for row, cb in self._checkboxes.items()
            if cb.isChecked() and cb.isEnabled() and row in self._results
        }
