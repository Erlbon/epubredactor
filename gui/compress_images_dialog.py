"""
gui/compress_images_dialog.py

Compress Images (Lossy): re-encodes every JPEG image in the working set
at a chosen quality, shrinking the archive at a real, permanent quality
cost. Deliberately separate from Polish Book's existing (lossless)
"Compress Images" checkbox -- that one never loses quality but saves
much less; this one trades quality for a bigger size win, so it's kept
as its own clearly-labeled action rather than folded into the same
checkbox.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.epub_metadata import EpubBook
from redactor_common.gui.progress import run_with_progress

BOOK_COL, IMAGES_COL, APPLY_COL = range(3)

DEFAULT_JPEG_QUALITY = 80


def format_size(num_bytes: int) -> str:
    if num_bytes >= 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.1f} MB"
    if num_bytes >= 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes} B"


class CompressImagesDialog(QDialog):
    def __init__(self, books: list[EpubBook], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Compress Images (Lossy)")
        self.resize(640, 480)
        self.books = [b for b in books if not b.load_error]
        # book index -> [(archive_path, current_size_bytes), ...]
        self._images: dict[int, list[tuple[str, int]]] = {}
        self._checkboxes: dict[int, QCheckBox] = {}

        self._build_ui()
        self._scan()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        warning = QLabel(
            "Re-encodes every JPEG image at the quality below, replacing the original "
            "bytes -- this permanently reduces image quality to shrink the archive. "
            "Separate from Polish Book's lossless image compression, which never loses "
            "quality but saves much less. Undo covers this in-session; the quality loss "
            "is real once saved. Review carefully before continuing."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color: #b45309; font-size: 11px;")
        layout.addWidget(warning)

        quality_row = QHBoxLayout()
        quality_row.addWidget(QLabel("JPEG quality:"))
        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(1, 100)
        self.quality_spin.setValue(DEFAULT_JPEG_QUALITY)
        self.quality_spin.setToolTip("Lower = smaller file, more visible quality loss.")
        quality_row.addWidget(self.quality_spin)
        quality_row.addStretch(1)
        layout.addLayout(quality_row)

        self.info_label = QLabel("")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Book", "JPEGs found", "Compress"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(IMAGES_COL, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Compress")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)

    def _scan(self) -> None:
        self._images = {}
        rows = []

        def _step(book: EpubBook, i: int) -> None:
            images = book.find_compressible_images()
            if images:
                self._images[i] = images
                rows.append(i)

        run_with_progress(
            self, self.books, _step, "Scanning for images…", cancellable=False, update_every=25,
        )

        self.table.setRowCount(len(rows))
        for row, book_index in enumerate(rows):
            book = self.books[book_index]
            images = self._images[book_index]
            total_size = sum(size for _path, size in images)
            summary = f"{len(images)} image(s), {format_size(total_size)} total"
            self.table.setItem(row, BOOK_COL, self._readonly_item(os.path.basename(book.path)))
            self.table.setItem(row, IMAGES_COL, self._readonly_item(summary))
            cb = QCheckBox()
            cb.setChecked(True)
            self._checkboxes[book_index] = cb
            self.table.setCellWidget(row, APPLY_COL, cb)
        self.table.resizeColumnsToContents()

        if not self._images:
            self.info_label.setText("No JPEG images found in the selected book(s).")
            self._ok_button.setEnabled(False)
        else:
            total_images = sum(len(v) for v in self._images.values())
            self.info_label.setText(
                f"Found {total_images} JPEG image(s) across {len(self._images)} book(s). "
                "Untick any you don't want compressed."
            )
            self._ok_button.setEnabled(True)

    @staticmethod
    def _readonly_item(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    # ------------------------------------------------------------------
    # Result accessors, read by the caller after exec() returns Accepted

    def quality(self) -> int:
        return self.quality_spin.value()

    def accepted_book_indices(self) -> list[int]:
        """Indices (into the `books` list passed to the constructor, as
        filtered to exclude load errors) of books whose checkbox is
        checked and which had at least one compressible image."""
        return [i for i in self._images if self._checkboxes[i].isChecked()]
