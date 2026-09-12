"""
gui/author_sort_dialog.py

Batch mode for the Author(s) <-> Author Sort conversion the Tag panel
already offers per book (see core/author_sort.py for the exact rule
and its caveats) -- one of the most repeated single-book actions, so
this runs it across many books at once. Preview shows only books that
would actually change, each with its own checkbox before Apply -- same
UX as Case Conversion.
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

from core.author_sort import author_sort_to_authors, authors_to_author_sort
from core.epub_metadata import EpubBook

BOOK_COL, OLD_COL, NEW_COL, APPLY_COL = range(4)

# label -> (source field, target field, conversion fn). The dialog only
# ever writes the target field -- the source is read-only input.
DIRECTIONS = {
    "Author(s) → Author Sort": ("authors_str", "author_sort_str", authors_to_author_sort),
    "Author Sort → Author(s)": ("author_sort_str", "authors_str", author_sort_to_authors),
}


class AuthorSortDialog(QDialog):
    def __init__(self, books: list[EpubBook], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Author ↔ Author Sort Conversion")
        self.resize(760, 480)
        self.books = books
        self._checkboxes: dict[int, QCheckBox] = {}
        self._new_values: dict[int, str] = {}

        self._build_ui()
        self._refresh_preview()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Applies to {len(self.books)} book(s)."))

        caveat = QLabel(
            "Naive guess, per semicolon-separated author -- splits each name on "
            "its last space (or each entry on its first comma, in reverse). "
            "Review before applying: compound surnames, single names, and "
            "non-Western name order will come out wrong."
        )
        caveat.setWordWrap(True)
        caveat.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(caveat)

        row = QHBoxLayout()
        row.addWidget(QLabel("Direction:"))
        self.direction_combo = QComboBox()
        self.direction_combo.addItems(list(DIRECTIONS.keys()))
        self.direction_combo.currentIndexChanged.connect(self._refresh_preview)
        row.addWidget(self.direction_combo, 1)
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
        _source_key, target_key, _convert = DIRECTIONS[self.direction_combo.currentText()]
        return target_key

    def _refresh_preview(self) -> None:
        source_key, target_key, convert = DIRECTIONS[self.direction_combo.currentText()]
        self._checkboxes = {}
        self._new_values = {}

        rows_to_show: list[tuple[int, str, str]] = []
        for i, book in enumerate(self.books):
            if book.load_error:
                continue
            source_value = getattr(book.metadata, source_key, "") or ""
            old_value = getattr(book.metadata, target_key, "") or ""
            new_value = convert(source_value)
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
