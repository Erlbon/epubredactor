"""
gui/validation_dialog.py

Shows validation status/issues for a set of books (computed at load time
-- see EpubBook._validate in core/epub_metadata.py) and lets you apply
whichever fixes are safely automatable. Fixes can be applied repeatedly
while the dialog is open; the table refreshes in place after each Apply
so you can see what's left.

Deliberately NOT covered by the app's Undo stack -- see the docstring on
EpubBook.apply_fixes for why.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
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

STATUS_COLORS = {
    "OK": None,
    "ISSUES": "#fff3cd",
    "DRM": "#dce6fb",
    "INVALID": "#f8d7da",
}
BOOK_COL, STATUS_COL, ISSUES_COL, FIX_COL = range(4)


class ValidationDialog(QDialog):
    def __init__(self, books: list[EpubBook], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Validate / Fix Issues")
        self.resize(820, 480)
        self.books = books
        self._checkboxes: dict[int, QCheckBox] = {}

        self._build_ui()
        self._refresh_table()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            f"Showing {len(self.books)} book(s). Tick 'Fix' for any book with automatically "
            "fixable issues, then Apply. Issues without a fix listed need manual attention."
        ))

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Book", "Status", "Issues", "Fix"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(ISSUES_COL, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self.status_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.accept)
        buttons.accepted.connect(self.accept)
        apply_btn = buttons.addButton("Apply Fixes to Checked", QDialogButtonBox.ButtonRole.ActionRole)
        apply_btn.clicked.connect(self._apply_fixes)
        layout.addWidget(buttons)

    def _refresh_table(self) -> None:
        self.table.setRowCount(len(self.books))
        self._checkboxes = {}
        for row, book in enumerate(self.books):
            self.table.setItem(row, BOOK_COL, self._readonly_item(os.path.basename(book.path)))

            status_item = self._readonly_item(book.validation_status)
            color = STATUS_COLORS.get(book.validation_status)
            if color:
                status_item.setBackground(QColor(color))
                status_item.setForeground(QColor("#000000"))
            self.table.setItem(row, STATUS_COL, status_item)

            issue_text = "; ".join(i.message for i in book.validation_issues) or "(none)"
            self.table.setItem(row, ISSUES_COL, self._readonly_item(issue_text))

            fixable_count = sum(1 for i in book.validation_issues if i.fixable)
            cb = QCheckBox()
            cb.setEnabled(fixable_count > 0)
            cb.setChecked(fixable_count > 0)
            cb.setToolTip(f"{fixable_count} fixable issue(s)" if fixable_count else "Nothing auto-fixable")
            self._checkboxes[row] = cb
            self.table.setCellWidget(row, FIX_COL, cb)

        self.table.resizeColumnsToContents()
        total_fixable = sum(1 for b in self.books if any(i.fixable for i in b.validation_issues))
        self.status_label.setText(f"{total_fixable} of {len(self.books)} book(s) have at least one fixable issue.")

    @staticmethod
    def _readonly_item(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    def _apply_fixes(self) -> None:
        fixed_count = 0
        for row, book in enumerate(self.books):
            cb = self._checkboxes.get(row)
            if cb is not None and cb.isChecked() and cb.isEnabled():
                fixed = book.apply_fixes()
                if fixed:
                    fixed_count += 1
        self._refresh_table()
        if fixed_count:
            self.status_label.setText(f"Applied fixes to {fixed_count} book(s). Remember to Save.")
