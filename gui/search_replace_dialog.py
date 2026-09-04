"""
gui/search_replace_dialog.py

Search & Replace across any column -- every metadata field, plus
Filename itself. Metadata fields are simple in-memory edits like
everywhere else in the app (staged, nothing written until Save).
Filename is different: a match there means an actual on-disk rename,
so it's handled separately and is NOT covered by the app's Undo stack
(same reasoning as the Rename/Export dialog -- see core/undo.py).

Only books where the replace would actually change something are shown
in the preview, each with its own checkbox so you can exclude any you
don't want touched before applying.
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
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.epub_metadata import EpubBook
from core.fields import FIELDS
from core.search_replace import SearchReplaceError, apply_replace

FILENAME_FIELD_KEY = "__filename__"
BOOK_COL, OLD_COL, NEW_COL, APPLY_COL = range(4)


class SearchReplaceDialog(QDialog):
    def __init__(self, books: list[EpubBook], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Search & Replace")
        self.resize(800, 520)
        self.books = books
        self._checkboxes: dict[int, QCheckBox] = {}
        self._new_values: dict[int, str] = {}  # book index -> proposed new value

        self._build_ui()
        self._refresh_preview()

    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Applies to {len(self.books)} book(s)."))

        field_row = QHBoxLayout()
        field_row.addWidget(QLabel("Column:"))
        self.field_combo = QComboBox()
        self.field_combo.addItem("Filename", FILENAME_FIELD_KEY)
        for key, label, _multiline in FIELDS:
            self.field_combo.addItem(label, key)
        self.field_combo.currentIndexChanged.connect(self._refresh_preview)
        field_row.addWidget(self.field_combo, 1)
        layout.addLayout(field_row)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Find:"))
        self.search_edit = QLineEdit()
        self.search_edit.textChanged.connect(self._refresh_preview)
        search_row.addWidget(self.search_edit, 1)
        layout.addLayout(search_row)

        replace_row = QHBoxLayout()
        replace_row.addWidget(QLabel("Replace with:"))
        self.replace_edit = QLineEdit()
        self.replace_edit.textChanged.connect(self._refresh_preview)
        replace_row.addWidget(self.replace_edit, 1)
        layout.addLayout(replace_row)

        options_row = QHBoxLayout()
        self.case_sensitive_cb = QCheckBox("Case sensitive")
        self.case_sensitive_cb.stateChanged.connect(self._refresh_preview)
        options_row.addWidget(self.case_sensitive_cb)

        self.regex_cb = QCheckBox("Use regular expression")
        self.regex_cb.setToolTip(
            "Enables regex patterns and \\1, \\2... backreferences in Replace with"
        )
        self.regex_cb.stateChanged.connect(self._refresh_preview)
        options_row.addWidget(self.regex_cb)
        options_row.addStretch(1)
        layout.addLayout(options_row)

        self.preview_table = QTableWidget()
        self.preview_table.setColumnCount(4)
        self.preview_table.setHorizontalHeaderLabels(["Book", "Current value", "New value", "Apply"])
        self.preview_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.preview_table.horizontalHeader().setStretchLastSection(False)
        layout.addWidget(self.preview_table, 1)

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

    # ------------------------------------------------------------------

    def result_field_key(self) -> str:
        return self.field_combo.currentData()

    def _current_value(self, book: EpubBook, field_key: str) -> str:
        if field_key == FILENAME_FIELD_KEY:
            return os.path.basename(book.path)
        return getattr(book.metadata, field_key, "") or ""

    def _refresh_preview(self) -> None:
        field_key = self.result_field_key()
        search = self.search_edit.text()
        replace = self.replace_edit.text()
        case_sensitive = self.case_sensitive_cb.isChecked()
        use_regex = self.regex_cb.isChecked()

        self._new_values = {}
        self._checkboxes = {}
        rows_to_show: list[tuple[int, str, str]] = []  # (book_index, old, new)
        error_msg = ""

        if search:
            for i, book in enumerate(self.books):
                if book.load_error:
                    continue
                old_value = self._current_value(book, field_key)
                try:
                    new_value = apply_replace(old_value, search, replace, use_regex, case_sensitive)
                except SearchReplaceError as exc:
                    error_msg = str(exc)
                    break
                if new_value != old_value:
                    rows_to_show.append((i, old_value, new_value))

        self.preview_table.setRowCount(len(rows_to_show))
        for row, (book_index, old_value, new_value) in enumerate(rows_to_show):
            book = self.books[book_index]
            self.preview_table.setItem(row, BOOK_COL, self._readonly_item(os.path.basename(book.path)))
            self.preview_table.setItem(row, OLD_COL, self._readonly_item(old_value))
            self.preview_table.setItem(row, NEW_COL, self._readonly_item(new_value))

            cb = QCheckBox()
            cb.setChecked(True)
            self._checkboxes[book_index] = cb
            self.preview_table.setCellWidget(row, APPLY_COL, cb)
            self._new_values[book_index] = new_value

        self.preview_table.resizeColumnsToContents()

        if error_msg:
            self.status_label.setText(error_msg)
            self.status_label.setStyleSheet("color: #b91c1c; font-size: 11px;")
            self._ok_button.setEnabled(False)
        elif not search:
            self.status_label.setText("Enter text to find.")
            self.status_label.setStyleSheet("color: gray; font-size: 11px;")
            self._ok_button.setEnabled(False)
        elif not rows_to_show:
            self.status_label.setText("No books would be changed.")
            self.status_label.setStyleSheet("color: gray; font-size: 11px;")
            self._ok_button.setEnabled(False)
        else:
            self.status_label.setText(f"{len(rows_to_show)} book(s) would be changed.")
            self.status_label.setStyleSheet("color: gray; font-size: 11px;")
            self._ok_button.setEnabled(True)

    @staticmethod
    def _readonly_item(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    # ------------------------------------------------------------------
    # Result accessor, read by the caller after exec() returns Accepted

    def accepted_changes(self) -> dict[int, str]:
        """book index (into the list passed to the constructor) -> new value,
        for every row whose checkbox is still ticked."""
        return {
            book_index: self._new_values[book_index]
            for book_index, cb in self._checkboxes.items()
            if cb.isChecked()
        }
