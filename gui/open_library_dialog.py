"""
gui/open_library_dialog.py

Import Metadata from Open Library: for each selected book, searches
Open Library (openlibrary.org) using that book's own title/author and
shows the best match -- title, authors, publisher, year, ISBN, genre
tags (subjects), and a cover thumbnail, all from the same lookup.
Replaces the narrower "Import Cover from Open Library" dialog, which
only ever extracted the cover image even though the same response
already carries the rest.

One checkbox per book (not per field) -- ticking a row applies
everything found for that book, matching the same pattern already used
for Calibre Lookup and Google Books. Nothing is written until you click
Apply, and you can uncheck any row you don't trust before then.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QProgressDialog,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.epub_metadata import EpubBook
from core.error_summary import summarize_errors
from core.open_library_lookup import (
    OpenLibraryLookupError,
    download_cover_image,
    search_open_library,
)

BOOK_COL, COVER_COL, FOUND_COL, APPLY_COL = range(4)
THUMB_SIZE = QSize(50, 70)


class OpenLibraryDialog(QDialog):
    def __init__(self, books: list[EpubBook], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import Metadata from Open Library")
        self.resize(880, 520)
        self.books = books
        self._checkboxes: dict[int, QCheckBox] = {}
        self._results: dict[int, dict[str, str]] = {}
        self._cover_bytes: dict[int, bytes] = {}

        self._build_ui()
        self._run_search()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        info = QLabel(
            f"Searching Open Library for {len(self.books)} book(s) by title/author. Each "
            "match brings in title, authors, publisher, year, ISBN, genre, and cover "
            "together -- untick anything you don't trust, then Apply."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Book", "Cover", "Found", "Apply"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(FOUND_COL, QHeaderView.ResizeMode.Stretch)
        self.table.setIconSize(THUMB_SIZE)
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

    @staticmethod
    def _readonly_item(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    def _run_search(self) -> None:
        self.table.setRowCount(len(self.books))
        progress = QProgressDialog("Searching Open Library…", "Cancel", 0, len(self.books), self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)

        found_count = 0
        errors: list[str] = []

        for row, book in enumerate(self.books):
            if progress.wasCanceled():
                self.table.setRowCount(row)
                break
            progress.setValue(row)
            progress.setLabelText(f"Searching: {os.path.basename(book.path)}")
            QApplication.processEvents()

            self.table.setItem(row, BOOK_COL, self._readonly_item(os.path.basename(book.path)))
            cover_item = self._readonly_item("")
            self.table.setItem(row, COVER_COL, cover_item)
            self.table.setRowHeight(row, THUMB_SIZE.height() + 6)

            cb = QCheckBox()
            fields = {}
            if not book.metadata.title.strip():
                self.table.setItem(row, FOUND_COL, self._readonly_item("(no title set -- can't search)"))
                cb.setEnabled(False)
            else:
                try:
                    candidates = search_open_library(book.metadata.title, book.metadata.authors_str)
                except OpenLibraryLookupError as exc:
                    errors.append(f"{os.path.basename(book.path)}: {exc}")
                    candidates = []

                if candidates:
                    best = candidates[0]
                    fields = best.as_dict()
                    summary = "; ".join(f"{k}: {v}" for k, v in fields.items())
                    self.table.setItem(row, FOUND_COL, self._readonly_item(summary))

                    if best.cover_id:
                        try:
                            image_bytes = download_cover_image(best)
                            pixmap = QPixmap()
                            if pixmap.loadFromData(image_bytes):
                                scaled = pixmap.scaled(
                                    THUMB_SIZE,
                                    Qt.AspectRatioMode.KeepAspectRatio,
                                    Qt.TransformationMode.SmoothTransformation,
                                )
                                cover_item.setIcon(QIcon(scaled))
                                self._cover_bytes[row] = image_bytes
                        except OpenLibraryLookupError as exc:
                            errors.append(f"{os.path.basename(book.path)} (cover): {exc}")

                    cb.setChecked(True)
                    self._results[row] = fields
                    found_count += 1
                else:
                    self.table.setItem(row, FOUND_COL, self._readonly_item("(no match)"))
                    cb.setEnabled(False)

            self._checkboxes[row] = cb
            self.table.setCellWidget(row, APPLY_COL, cb)

        progress.setValue(len(self.books))
        self.table.resizeColumnsToContents()

        msg = f"Found something for {found_count} of {len(self.books)} book(s)."
        if errors:
            msg += f" {len(errors)} error(s): {summarize_errors(errors)}"
        self.status_label.setText(msg)

    # ------------------------------------------------------------------
    # Result accessors, read by the caller after exec() returns Accepted

    def accepted_metadata(self) -> dict[int, dict[str, str]]:
        """book index -> {field_key: value}, for every checked row that
        found something."""
        return {
            row: self._results[row]
            for row, cb in self._checkboxes.items()
            if cb.isChecked() and cb.isEnabled() and row in self._results
        }

    def accepted_covers(self) -> dict[int, tuple[bytes, str]]:
        """book index -> (image_bytes, mime), for every checked row that
        has a successfully downloaded cover. Open Library covers are
        JPEG."""
        return {
            row: (self._cover_bytes[row], "image/jpeg")
            for row, cb in self._checkboxes.items()
            if cb.isChecked() and cb.isEnabled() and row in self._cover_bytes
        }
