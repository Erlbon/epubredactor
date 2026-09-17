"""
gui/nav_repair_dialog.py

Repair Navigation: a standalone, explicitly-triggered action (Repair
menu) for two specific, safely-verifiable problems -- EPUB2-style
<guide> references pointing at files that no longer exist, and archive
files present on disk but referenced by no manifest item at all
("orphaned" files). Same review-before-touch shape as Rebuild Manifest,
and deliberately as narrow in scope: this does NOT rewrite NCX/NAV
document content (duplicate TOC entries, duplicate element ids, or the
cross-document fragment links that point at them) -- only what's
readable straight from the OPF + archive file listing.
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

BOOK_COL, ISSUES_COL, APPLY_COL = range(3)


class NavRepairDialog(QDialog):
    def __init__(self, books: list[EpubBook], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Repair Navigation")
        self.resize(680, 480)
        self.books = [b for b in books if not b.load_error]
        # book index -> (broken guide hrefs, orphaned file paths)
        self._issues: dict[int, tuple[list[str], list[str]]] = {}
        self._checkboxes: dict[int, QCheckBox] = {}

        self._build_ui()
        self._scan()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.info_label = QLabel("")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Book", "Issues found", "Repair"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(ISSUES_COL, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

        warning = QLabel(
            "Removes broken <guide> references (the files they pointed to are already "
            "gone from the archive either way) and any file present in the archive but "
            "not referenced by any manifest item. Doesn't touch reading-order content or "
            "any file an item still points to. Review carefully before continuing."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color: #b45309; font-size: 11px;")
        layout.addWidget(warning)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Repair")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)

    def _scan(self) -> None:
        self._issues = {}
        rows = []
        for i, book in enumerate(self.books):
            broken_guide = [href for _type, _title, href in book.find_broken_guide_references()]
            orphans = book.find_orphaned_files()
            if broken_guide or orphans:
                self._issues[i] = (broken_guide, orphans)
                rows.append(i)

        self.table.setRowCount(len(rows))
        for row, book_index in enumerate(rows):
            book = self.books[book_index]
            broken_guide, orphans = self._issues[book_index]
            parts = []
            if broken_guide:
                parts.append(f"{len(broken_guide)} broken guide reference(s): {', '.join(broken_guide)}")
            if orphans:
                parts.append(f"{len(orphans)} orphaned file(s): {', '.join(orphans)}")
            self.table.setItem(row, BOOK_COL, self._readonly_item(os.path.basename(book.path)))
            self.table.setItem(row, ISSUES_COL, self._readonly_item("; ".join(parts)))
            cb = QCheckBox()
            cb.setChecked(True)
            self._checkboxes[book_index] = cb
            self.table.setCellWidget(row, APPLY_COL, cb)
        self.table.resizeColumnsToContents()

        if not self._issues:
            self.info_label.setText("No broken guide references or orphaned files found.")
            self._ok_button.setEnabled(False)
        else:
            total_books = len(self._issues)
            self.info_label.setText(
                f"Found issues in {total_books} book(s). Untick any you don't want repaired."
            )
            self._ok_button.setEnabled(True)

    @staticmethod
    def _readonly_item(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    # ------------------------------------------------------------------
    # Result accessor, read by the caller after exec() returns Accepted

    def accepted_book_indices(self) -> list[int]:
        """Indices (into the `books` list passed to the constructor, as
        filtered to exclude load errors) of books whose checkbox is
        checked and which had at least one issue found."""
        return [i for i in self._issues if self._checkboxes[i].isChecked()]
