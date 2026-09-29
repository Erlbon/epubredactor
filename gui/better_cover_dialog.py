"""
gui/better_cover_dialog.py

Operations > Find Better Covers...: the review step. For each book where
Open Library has a LARGER cover for its ISBN (core/better_cover.py) --
or the book has none -- the current and the found cover side by side
with their sizes, ticked by default. The main window applies the ticked
ones as ordinary edits (one Undo step, written on Save).
"""

from __future__ import annotations

import os

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from gui.cover_quality import image_size

THUMB = QSize(90, 135)


def _thumbnail_item(data, caption: str) -> QTableWidgetItem:
    item = QTableWidgetItem(caption)
    if data:
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            item.setData(Qt.ItemDataRole.DecorationRole, pixmap.scaled(
                THUMB, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
    return item


def _size_text(data) -> str:
    size = image_size(data)
    return f"{size[0]}×{size[1]}" if size else ("none" if not data else "?")


class BetterCoverDialog(QDialog):
    def __init__(self, found: list, note: str = "", parent=None):
        """`found`: (book, new_cover_bytes) pairs, each an improvement."""
        super().__init__(parent)
        self.setWindowTitle("Find Better Covers")
        self.resize(760, 560)
        self._found = found

        layout = QVBoxLayout(self)
        intro = QLabel(
            f"Open Library has a larger cover for {len(found)} book(s), looked up by ISBN. Untick "
            "any that aren't the same edition, then Apply: the covers are replaced as ordinary edits "
            "-- one Undo step, written on Save. (Open Library's covers are often modest in size, so "
            "this helps most with missing and very small covers.)" + (f"<br><br>{note}" if note else "")
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.table = QTableWidget(len(found), 3)
        self.table.setHorizontalHeaderLabels(["Book", "Current", "Found"])
        self.table.setIconSize(THUMB)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(THUMB.height() + 10)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(1, 200)
        self.table.setColumnWidth(2, 200)
        for row, (book, data) in enumerate(found):
            title = getattr(book.metadata, "title", "") or os.path.basename(book.path)
            name = QTableWidgetItem(title)
            name.setToolTip(book.path)
            name.setFlags(name.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            name.setCheckState(Qt.CheckState.Checked)
            self.table.setItem(row, 0, name)
            self.table.setItem(row, 1, _thumbnail_item(book.cover_bytes, _size_text(book.cover_bytes)))
            self.table.setItem(row, 2, _thumbnail_item(data, _size_text(data)))
        layout.addWidget(self.table)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.apply_button = buttons.addButton("Apply", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.table.itemChanged.connect(self._update_button)
        layout.addWidget(buttons)
        self._update_button()

    def _update_button(self, *_args) -> None:
        count = len(self.ticked())
        self.apply_button.setText(f"Replace {count} Cover(s)")
        self.apply_button.setEnabled(count > 0)

    def ticked(self) -> list:
        return [
            self._found[row] for row in range(self.table.rowCount())
            if self.table.item(row, 0).checkState() == Qt.CheckState.Checked
        ]
