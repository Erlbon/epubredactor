"""
gui/manifest_rebuild_dialog.py

Rebuild Manifest: a standalone, explicitly-triggered action (Operations
menu) for cleaning up manifest entries that reference files no longer
present in the archive. Deliberately kept separate from Validate/Fix
Issues' one-click "Apply Fixes" flow -- removing a manifest entry can
affect actual reading-order content if the missing file was a spine
document, not just an orphaned image -- so this always lists exactly
which files are missing, for which books, and requires an explicit
confirmation before anything is touched.
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

BOOK_COL, MISSING_COL, APPLY_COL = range(3)


class ManifestRebuildDialog(QDialog):
    def __init__(self, books: list[EpubBook], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Rebuild Manifest")
        self.resize(640, 480)
        self.books = [b for b in books if not b.load_error]
        self._missing: dict[int, list[tuple[str, str]]] = {}  # book index -> [(item_id, href), ...]
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
        self.table.setHorizontalHeaderLabels(["Book", "Missing file(s)", "Remove && Rebuild"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(MISSING_COL, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

        warning = QLabel(
            "This permanently removes the listed manifest entries (and any reading-order "
            "reference to them) from each book. It cannot restore the missing files "
            "themselves -- only clean up the broken references to them, since the files are "
            "already gone from the archive either way. Review carefully before continuing."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color: #b45309; font-size: 11px;")
        layout.addWidget(warning)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Remove && Rebuild")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)

    def _scan(self) -> None:
        self._missing = {}
        rows = []
        for i, book in enumerate(self.books):
            missing = book.find_missing_manifest_files()
            if missing:
                self._missing[i] = missing
                rows.append(i)

        self.table.setRowCount(len(rows))
        for row, book_index in enumerate(rows):
            book = self.books[book_index]
            names_preview = ", ".join(href for _item_id, href in self._missing[book_index])
            self.table.setItem(row, BOOK_COL, self._readonly_item(os.path.basename(book.path)))
            self.table.setItem(row, MISSING_COL, self._readonly_item(names_preview))
            cb = QCheckBox()
            cb.setChecked(True)
            self._checkboxes[book_index] = cb
            self.table.setCellWidget(row, APPLY_COL, cb)
        self.table.resizeColumnsToContents()

        if not self._missing:
            self.info_label.setText("No missing manifest files found in the selected book(s).")
            self._ok_button.setEnabled(False)
        else:
            total_files = sum(len(v) for v in self._missing.values())
            self.info_label.setText(
                f"Found {total_files} missing file reference(s) across {len(self._missing)} "
                f"book(s). Untick any you don't want rebuilt."
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
        checked and which had missing files."""
        return [i for i in self._missing if self._checkboxes[i].isChecked()]
