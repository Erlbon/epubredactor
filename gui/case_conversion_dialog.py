"""
gui/case_conversion_dialog.py

Case Conversion (mp3tag's feature of the same name): pick a column and
a conversion mode, preview shows only books that would actually change,
each with its own checkbox before Apply.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.case_conversion import CASE_CONVERSIONS, apply_case_conversion
from core.epub_metadata import EpubBook
from core.fields import FIELDS

BOOK_COL, OLD_COL, NEW_COL, APPLY_COL = range(4)


class CaseConversionDialog(QDialog):
    def __init__(self, books: list[EpubBook], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Case Conversion")
        self.resize(760, 480)
        self.books = books
        self._checkboxes: dict[int, QCheckBox] = {}
        self._new_values: dict[int, str] = {}

        self._build_ui()
        self._refresh_preview()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Applies to {len(self.books)} book(s)."))

        row = QHBoxLayout()
        row.addWidget(QLabel("Column:"))
        self.field_combo = QComboBox()
        for key, label, _multiline in FIELDS:
            self.field_combo.addItem(label, key)
        self.field_combo.currentIndexChanged.connect(self._refresh_preview)
        row.addWidget(self.field_combo, 1)

        row.addWidget(QLabel("Convert to:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(list(CASE_CONVERSIONS.keys()))
        self.mode_combo.currentIndexChanged.connect(self._refresh_preview)
        row.addWidget(self.mode_combo)
        layout.addLayout(row)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Book", "Current value", "New value", "Apply"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
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

    def result_field_key(self) -> str:
        return self.field_combo.currentData()

    def _refresh_preview(self) -> None:
        field_key = self.result_field_key()
        mode = self.mode_combo.currentText()
        self._checkboxes = {}
        self._new_values = {}

        rows_to_show: list[tuple[int, str, str]] = []
        for i, book in enumerate(self.books):
            if book.load_error:
                continue
            old_value = getattr(book.metadata, field_key, "") or ""
            new_value = apply_case_conversion(old_value, mode)
            if new_value != old_value:
                rows_to_show.append((i, old_value, new_value))

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
            self.status_label.setText("No books would be changed.")
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
        """book index -> new value, for every row whose checkbox is checked."""
        return {i: self._new_values[i] for i, cb in self._checkboxes.items() if cb.isChecked()}
