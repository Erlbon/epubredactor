"""
gui/strip_description_html_dialog.py

Strip HTML from Description (Repair menu): converts a book's
Description from raw HTML (tags and all -- common for an EPUB whose
dc:description was literally copy-pasted from a publisher's marketing
page) into clean plain text via core/description_html.py. Same
"preview only books that would actually change, each with its own
checkbox before Apply" shape as Case Conversion.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.description_html import strip_html
from core.epub_metadata import EpubBook
from redactor_common.gui.progress import run_with_progress

BOOK_COL, OLD_COL, NEW_COL, APPLY_COL = range(4)


class StripDescriptionHtmlDialog(QDialog):
    def __init__(self, books: list[EpubBook], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Strip HTML from Description")
        self.resize(880, 480)
        self.books = books
        self._checkboxes: dict[int, QCheckBox] = {}
        self._new_values: dict[int, str] = {}

        self._build_ui()
        self._refresh_preview()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            f"Applies to {len(self.books)} book(s). Only books whose Description actually "
            "contains HTML markup are listed -- a plain-text description is never touched."
        ))

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Book", "Current value", "New value", "Apply"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(OLD_COL, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(NEW_COL, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self.status_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Apply")
        self._ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _refresh_preview(self) -> None:
        self._checkboxes = {}
        self._new_values = {}

        rows_to_show: list[tuple[int, str, str]] = []

        def _step(book: EpubBook, i: int) -> None:
            if book.load_error:
                return
            old_value = book.metadata.description or ""
            new_value = strip_html(old_value)
            if new_value != old_value:
                rows_to_show.append((i, old_value, new_value))

        run_with_progress(
            self, self.books, _step, "Scanning descriptions…",
            cancellable=False, update_every=25,
        )

        self.table.setRowCount(len(rows_to_show))
        for row, (book_index, old_value, new_value) in enumerate(rows_to_show):
            book = self.books[book_index]
            self.table.setItem(row, BOOK_COL, self._readonly_item(os.path.basename(book.path)))
            self.table.setItem(row, OLD_COL, self._readonly_item(old_value))
            self.table.setItem(row, NEW_COL, self._readonly_item(new_value))

            cb = QCheckBox()
            cb.setChecked(True)
            self._checkboxes[book_index] = cb
            self.table.setCellWidget(row, APPLY_COL, cb)
            self._new_values[book_index] = new_value

        self.table.resizeColumnsToContents()

        if not rows_to_show:
            self.status_label.setText("No book's Description contains HTML markup.")
            self._ok_button.setEnabled(False)
        else:
            self.status_label.setText(f"{len(rows_to_show)} book(s) would be changed.")
            self._ok_button.setEnabled(True)

    @staticmethod
    def _readonly_item(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    # ------------------------------------------------------------------
    # Result accessor, read by the caller after exec() returns Accepted

    def accepted_changes(self) -> dict[int, str]:
        """book index -> new (stripped) description, for every row whose
        checkbox is checked."""
        return {i: self._new_values[i] for i, cb in self._checkboxes.items() if cb.isChecked()}
