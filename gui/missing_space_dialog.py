"""
gui/missing_space_dialog.py

Detect Missing Spaces: flags a common metadata-quality problem (a
missing space right after punctuation, e.g. "Hello.World") in the
Title and Series fields, with a preview of the suggested fix before
anything is applied.

Scoped to just these two fields for now -- a broader "lowercase letter
directly followed by an uppercase one" heuristic would catch more real
issues, but also false-positives constantly on legitimate names with an
internal capital (McDonald, DiCaprio, MacArthur), so it's deliberately
left out rather than shipped as a noisy check. See core/missing_space.py.
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

from core.epub_metadata import EpubBook
from core.missing_space import find_missing_spaces, suggest_fix

SCANNED_FIELDS = [("title", "Title"), ("series", "Series")]
BOOK_COL, FIELD_COL, CURRENT_COL, SUGGESTED_COL, APPLY_COL = range(5)


class MissingSpaceDialog(QDialog):
    def __init__(self, books: list[EpubBook], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Detect Missing Spaces")
        self.resize(680, 480)
        self.books = [b for b in books if not b.load_error]
        self._checkboxes: dict[int, QCheckBox] = {}
        # row -> (book, field_key, suggested_value)
        self._rows: dict[int, tuple[EpubBook, str, str]] = {}

        self._build_ui()
        self._scan()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.info_label = QLabel(
            f"Scanning Title and Series for {len(self.books)} book(s): a period, comma, or "
            "similar punctuation directly followed by a letter, with no space -- usually "
            "from bad text extraction or scraped metadata."
        )
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Book", "Field", "Current", "Suggested", "Apply"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(CURRENT_COL, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(SUGGESTED_COL, QHeaderView.ResizeMode.Stretch)
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
        self._ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)

    def _scan(self) -> None:
        self._checkboxes = {}
        self._rows = {}
        found_rows = []

        for book in self.books:
            for field_key, _label in SCANNED_FIELDS:
                current = getattr(book.metadata, field_key, "") or ""
                if find_missing_spaces(current):
                    suggested = suggest_fix(current)
                    found_rows.append((book, field_key, current, suggested))

        self.table.setRowCount(len(found_rows))
        for row, (book, field_key, current, suggested) in enumerate(found_rows):
            field_label = dict(SCANNED_FIELDS)[field_key]
            self.table.setItem(row, BOOK_COL, self._readonly_item(os.path.basename(book.path)))
            self.table.setItem(row, FIELD_COL, self._readonly_item(field_label))
            self.table.setItem(row, CURRENT_COL, self._readonly_item(current))
            self.table.setItem(row, SUGGESTED_COL, self._readonly_item(suggested))
            cb = QCheckBox()
            cb.setChecked(True)
            self._checkboxes[row] = cb
            self._rows[row] = (book, field_key, suggested)
            self.table.setCellWidget(row, APPLY_COL, cb)
        self.table.resizeColumnsToContents()

        if not found_rows:
            self.status_label.setText("No missing spaces found in Title or Series.")
            self._ok_button.setEnabled(False)
        else:
            self.status_label.setText(
                f"Found {len(found_rows)} possible missing space(s). Untick any you don't want fixed."
            )
            self._ok_button.setEnabled(True)

    @staticmethod
    def _readonly_item(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    # ------------------------------------------------------------------
    # Result accessor, read by the caller after exec() returns Accepted

    def accepted_changes(self) -> list[tuple[EpubBook, str, str]]:
        """[(book, field_key, new_value), ...] for every row whose
        checkbox is checked."""
        return [
            self._rows[row] for row, cb in self._checkboxes.items() if cb.isChecked()
        ]
