"""
gui/cover_generator_dialog.py

Generate Cover from Metadata: creates a new placeholder cover (title,
author, and series if present, on a deterministically-colored plain
background -- see core/cover_generator.py) for each selected book, to
replace a missing or wrong cover. Preview before applying, same pattern
as everywhere else in this app that touches a book's cover image.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon, QPixmap
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
from gui.cover_render import generate_cover_image

BOOK_COL, PREVIEW_COL, APPLY_COL = range(3)
THUMB_SIZE = QSize(70, 105)


class CoverGeneratorDialog(QDialog):
    def __init__(self, books: list[EpubBook], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Generate Cover from Metadata")
        self.resize(520, 560)
        self.books = [b for b in books if not b.load_error]
        self._checkboxes: dict[int, QCheckBox] = {}
        self._generated: dict[int, bytes] = {}

        self._build_ui()
        self._generate_previews()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        info = QLabel(
            f"Generates a new placeholder cover (title, author, and series if present, "
            f"on a plain background) for {len(self.books)} selected book(s), replacing "
            "any existing cover. Untick any you don't want changed."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Book", "Preview", "Apply"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(BOOK_COL, QHeaderView.ResizeMode.Stretch)
        self.table.setIconSize(THUMB_SIZE)
        layout.addWidget(self.table, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Apply")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _generate_previews(self) -> None:
        self.table.setRowCount(len(self.books))
        for row, book in enumerate(self.books):
            m = book.metadata
            image_bytes = generate_cover_image(m.title, m.authors_str, m.series, m.series_index)
            self._generated[row] = image_bytes

            self.table.setItem(row, BOOK_COL, self._readonly_item(os.path.basename(book.path)))

            preview_item = self._readonly_item("")
            pixmap = QPixmap()
            pixmap.loadFromData(image_bytes)
            scaled = pixmap.scaled(
                THUMB_SIZE, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            preview_item.setIcon(QIcon(scaled))
            self.table.setItem(row, PREVIEW_COL, preview_item)
            self.table.setRowHeight(row, THUMB_SIZE.height() + 10)

            cb = QCheckBox()
            cb.setChecked(True)
            self._checkboxes[row] = cb
            self.table.setCellWidget(row, APPLY_COL, cb)

        self.table.resizeColumnsToContents()

    @staticmethod
    def _readonly_item(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    # ------------------------------------------------------------------
    # Result accessor, read by the caller after exec() returns Accepted

    def accepted_covers(self) -> dict[int, tuple[bytes, str]]:
        """book index (into the `books` list passed to the constructor,
        as filtered to exclude load errors) -> (image_bytes, mime), for
        every checked row."""
        return {
            row: (self._generated[row], "image/png")
            for row, cb in self._checkboxes.items()
            if cb.isChecked()
        }
