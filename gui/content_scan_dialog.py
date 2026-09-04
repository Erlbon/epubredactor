"""
gui/content_scan_dialog.py

Scans each selected book's first few pages for metadata patterns
(publisher, author, ISBN, year, DDC -- see core/content_scan.py) and
lets you review and selectively apply the results. Same "find
candidates, human decides" pattern as the Google Books/Open Library
lookups -- this is a heuristic best-guess tool, not a reliable parser,
so nothing is applied without review.

Runs synchronously but pumps the Qt event loop between books (via a
QProgressDialog), same technique used by those lookup dialogs.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QProgressDialog,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.content_scan import scan_book
from core.epub_metadata import EpubBook

BOOK_COL, FOUND_COL, APPLY_COL = range(3)


class ContentScanDialog(QDialog):
    def __init__(self, books: list[EpubBook], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Scan Content for Metadata")
        self.resize(820, 480)
        self.books = books
        self._checkboxes: dict[int, QCheckBox] = {}
        self._results: dict[int, dict[str, str]] = {}  # row -> {field_key: value}

        self._build_ui()
        self._run_scan()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        info = QLabel(
            f"Scanning the first few pages of {len(self.books)} book(s) for publisher, "
            "author, ISBN, year, and DDC classification.\n"
            "This is a best guess from the book's own text, not a reliable parser -- "
            "review before applying."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Book", "Found", "Apply"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(FOUND_COL, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

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

    def _run_scan(self) -> None:
        self.table.setRowCount(len(self.books))
        progress = QProgressDialog("Scanning book content…", "Cancel", 0, len(self.books), self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)

        found_count = 0
        for row, book in enumerate(self.books):
            if progress.wasCanceled():
                self.table.setRowCount(row)
                break
            progress.setValue(row)
            progress.setLabelText(f"Scanning: {os.path.basename(book.path)}")
            QApplication.processEvents()

            self.table.setItem(row, BOOK_COL, self._readonly_item(os.path.basename(book.path)))

            try:
                result = scan_book(book)
            except Exception:  # noqa: BLE001 - a scan failure shouldn't crash the dialog
                result = None

            fields = result.as_dict() if result else {}
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
        self.status_label.setText(f"Found something in {found_count} of {len(self.books)} book(s).")

    @staticmethod
    def _readonly_item(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

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
