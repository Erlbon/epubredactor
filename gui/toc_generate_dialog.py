"""
gui/toc_generate_dialog.py

Generate Table of Contents: a standalone, explicitly-triggered action
(Repair menu) for books with no TOC at all (validation issue NO_TOC --
typical of badly converted scanned-PDF EPUBs). Same review-before-touch
shape as Rebuild Manifest / Repair Navigation: lists the affected books
with how many entries would be generated, previews the first few for
the selected book, and only books left ticked are touched. The entries
come from core/toc_generate.py's heading heuristic, a best guess -- hence
the preview.
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
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.epub_metadata import EpubBook
from core.toc_generate import TocEntry, generate_toc_entries, needs_toc
from redactor_common.gui.progress import run_with_progress

BOOK_COL, ENTRIES_COL, APPLY_COL = range(3)
PREVIEW_ENTRIES = 10


class TocGenerateDialog(QDialog):
    def __init__(self, books: list[EpubBook], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Generate Table of Contents")
        self.resize(680, 520)
        self.books = [b for b in books if not b.load_error]
        self._entries: dict[int, list[TocEntry]] = {}  # book index -> proposed entries
        self._row_books: list[int] = []  # table row -> book index
        self._checkboxes: dict[int, QCheckBox] = {}
        self._unbuildable = 0  # books with no TOC but nothing to build one from

        self._build_ui()
        self._scan()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.info_label = QLabel("")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Book", "Entries", "Generate"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.itemSelectionChanged.connect(self._update_preview)
        layout.addWidget(self.table, 1)

        self.preview_label = QLabel("Preview (first entries of the selected book):")
        layout.addWidget(self.preview_label)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMaximumHeight(170)
        layout.addWidget(self.preview)

        note = QLabel(
            "The table of contents is built from each book's h1-h3 headings (or page titles) "
            "in reading order, and written as an NCX (plus an EPUB3 nav document for EPUB3 "
            "books). Chapter files are not modified. Headings repeated across many files "
            "(running page headers) are ignored. Nothing is written until you save."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #b45309; font-size: 11px;")
        layout.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Generate")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)

    def _scan(self) -> None:
        self._entries = {}
        rows: list[int] = []
        candidates = [i for i, b in enumerate(self.books) if needs_toc(b)]

        def _step(book_index: int, _i: int) -> None:
            entries = generate_toc_entries(self.books[book_index])
            if entries:
                self._entries[book_index] = entries
                rows.append(book_index)
            else:
                self._unbuildable += 1

        run_with_progress(
            self, candidates, _step, "Reading book headings…", cancellable=False, update_every=5,
        )

        self._row_books = rows
        self.table.setRowCount(len(rows))
        for row, book_index in enumerate(rows):
            book = self.books[book_index]
            self.table.setItem(row, BOOK_COL, self._readonly_item(os.path.basename(book.path)))
            self.table.setItem(row, ENTRIES_COL, self._readonly_item(str(len(self._entries[book_index]))))
            cb = QCheckBox()
            cb.setChecked(True)
            self._checkboxes[book_index] = cb
            self.table.setCellWidget(row, APPLY_COL, cb)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(BOOK_COL, QHeaderView.ResizeMode.Stretch)

        if not rows:
            text = "No books without a table of contents were found in the selection."
            if self._unbuildable:
                text = (
                    f"{self._unbuildable} book(s) have no table of contents, but no readable "
                    "content documents to build one from."
                )
            self.info_label.setText(text)
            self._ok_button.setEnabled(False)
        else:
            text = (
                f"{len(rows)} book(s) have no table of contents. Untick any you don't want "
                f"generated; select a book to preview its entries."
            )
            if self._unbuildable:
                text += f" ({self._unbuildable} more had nothing to build one from.)"
            self.info_label.setText(text)
            self._ok_button.setEnabled(True)
            self.table.selectRow(0)
        self._update_preview()

    def _update_preview(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._row_books):
            self.preview.setPlainText("")
            return
        entries = self._entries[self._row_books[row]]
        lines = ["    " * (e.level - 1) + e.title for e in entries[:PREVIEW_ENTRIES]]
        if len(entries) > PREVIEW_ENTRIES:
            lines.append(f"... and {len(entries) - PREVIEW_ENTRIES} more")
        self.preview.setPlainText("\n".join(lines))

    @staticmethod
    def _readonly_item(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    # ------------------------------------------------------------------
    # Result accessors, read by the caller after exec() returns Accepted

    def accepted_book_indices(self) -> list[int]:
        """Indices (into `books`, as filtered to exclude load errors) of
        books whose checkbox is checked and for which entries were found."""
        return [i for i in self._entries if self._checkboxes[i].isChecked()]

    def entries_for(self, book_index: int) -> list[TocEntry]:
        return self._entries[book_index]
