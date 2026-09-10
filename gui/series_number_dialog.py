"""
gui/series_number_dialog.py

Number Series: assigns sequential Series # values to the selected books,
in their current table order (top to bottom). A plain bulk-edit can't do
this -- applying one value to every selected book is the opposite of
what you want when numbering an entire series at once. Modeled on
mp3tag's "auto-number tracks" feature.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.epub_metadata import EpubBook
from redactor_common.core.series_numbering import DEFAULT_START, DEFAULT_STEP, generate_series_numbers

BOOK_COL, CURRENT_COL, NEW_COL = range(3)


class SeriesNumberDialog(QDialog):
    def __init__(self, books: list[EpubBook], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Number Series")
        self.resize(520, 480)
        self.books = books  # already in current table (visual, top-to-bottom) order
        self._new_values: list[str] = []

        self._build_ui()
        self._refresh_preview()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        info = QLabel(
            f"Assigns sequential Series # values to {len(self.books)} selected book(s), "
            "in their current order in the table (top to bottom) -- sort or select them "
            "in the order you want numbered first."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        row = QHBoxLayout()
        row.addWidget(QLabel("Start at:"))
        self.start_edit = QLineEdit(DEFAULT_START)
        self.start_edit.setMaximumWidth(80)
        self.start_edit.textChanged.connect(self._refresh_preview)
        row.addWidget(self.start_edit)
        row.addSpacing(16)
        row.addWidget(QLabel("Step:"))
        self.step_edit = QLineEdit(DEFAULT_STEP)
        self.step_edit.setMaximumWidth(80)
        self.step_edit.textChanged.connect(self._refresh_preview)
        row.addWidget(self.step_edit)
        row.addStretch(1)
        layout.addLayout(row)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Book", "Current Series #", "New Series #"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Apply")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _refresh_preview(self) -> None:
        self._new_values = generate_series_numbers(
            len(self.books), self.start_edit.text(), self.step_edit.text()
        )
        self.table.setRowCount(len(self.books))
        for row, (book, new_val) in enumerate(zip(self.books, self._new_values)):
            self.table.setItem(row, BOOK_COL, self._readonly_item(os.path.basename(book.path)))
            self.table.setItem(row, CURRENT_COL, self._readonly_item(book.metadata.series_index or ""))
            self.table.setItem(row, NEW_COL, self._readonly_item(new_val))
        self.table.resizeColumnsToContents()

    @staticmethod
    def _readonly_item(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    # ------------------------------------------------------------------
    # Result accessor, read by the caller after exec() returns Accepted

    def result_values(self) -> dict[int, str]:
        """book index (into the `books` list passed to the constructor)
        -> new series_index value."""
        return dict(enumerate(self._new_values))
