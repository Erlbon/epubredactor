"""
gui/author_clean_dialog.py

Clean Up Authors (Repair menu): reviews every loaded book's Author(s) and
Author Sort against core/author_clean.py. Per book, up to two rows:

  * "Safe" -- the deterministic fixes (spacing, junk, "Last, First" flip,
    duplicates, generated file-as ...). Ticked.
  * "Review" -- the same book with the guesses added too (splitting
    "Simon & Schuster", removing "Dr.", a file-as that disagrees with the
    author ...). NOT ticked; ticking it replaces the book's safe row.
  * "Flag" -- something worth a look that has no proposed change
    (unusual characters, an ambiguous comma list). No checkbox.

Nothing is written here: the caller applies accepted_changes() through the
normal edit path, so Save All writes it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

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

from core.author_clean import AuthorResult, clean_authors
from core.epub_metadata import EpubBook
from redactor_common.gui.progress import run_with_progress

(BOOK_COL, KIND_COL, OLD_AUTHORS_COL, NEW_AUTHORS_COL, OLD_SORT_COL, NEW_SORT_COL, WHY_COL,
 APPLY_COL) = range(8)

KIND_SAFE, KIND_REVIEW, KIND_FLAG = "Safe", "Review", "Flag"


@dataclass
class Row:
    book_index: int
    kind: str
    old_authors: str
    new_authors: str
    old_sort: str
    new_sort: str
    why: str


def _join(values: list[str]) -> str:
    return "; ".join(values)


def build_rows(book_index: int, book: EpubBook) -> list[Row]:
    """The rows for one book (empty when there is nothing to say)."""
    authors, sort = list(book.metadata.authors), list(book.metadata.author_sort)
    old_a = book.metadata.authors_str
    old_s = book.metadata.author_sort_str
    safe = clean_authors(authors, sort, allow_review=False)
    full = clean_authors(authors, sort, allow_review=True)
    rows: list[Row] = []

    def _why(result: AuthorResult, with_review: bool) -> str:
        parts = [str(c) for c in result.changes]
        if with_review:
            parts = [("REVIEW " if not c.safe else "") + str(c) for c in result.changes]
        else:
            parts += [f"held back for review - {c}" for c in result.review]
        parts += [f"flag - {f}" for f in result.flags]
        return "; ".join(parts)

    if safe.changed:
        rows.append(Row(book_index, KIND_SAFE, old_a, _join(safe.authors), old_s, _join(safe.author_sort),
                        _why(safe, False)))
    if full.changed and (full.authors, full.author_sort) != (safe.authors, safe.author_sort):
        rows.append(Row(book_index, KIND_REVIEW, old_a, _join(full.authors), old_s, _join(full.author_sort),
                        _why(full, True)))
    if not rows and safe.flags:
        rows.append(Row(book_index, KIND_FLAG, old_a, old_a, old_s, old_s, _why(safe, False)))
    return rows


class AuthorCleanDialog(QDialog):
    def __init__(self, books: list[EpubBook], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Clean Up Authors")
        self.resize(1180, 520)
        self.books = books
        self.rows: list[Row] = []
        self._checkboxes: dict[int, QCheckBox] = {}  # row number -> box

        self._build_ui()
        self._refresh_preview()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Looks at {len(self.books)} book(s)."))
        note = QLabel(
            "Safe rows are deterministic fixes and are ticked. Review rows include guesses (splitting "
            "\"Simon & Schuster\", removing \"Dr.\", an Author Sort that disagrees with the author) and are "
            "NOT ticked; ticking one replaces the book's Safe row. Flag rows only point something out. "
            "Corporate authors, \"Anonymous\" and non-Latin names are left alone. Nothing is saved until Save All."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(note)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Book", "Kind", "Authors now", "Authors new", "Sort now", "Sort new", "Why", "Apply",
        ])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(WHY_COL, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self.status_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Apply")
        self._ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _refresh_preview(self) -> None:
        rows: list[Row] = []

        def _step(book: EpubBook, i: int) -> None:
            if not book.load_error:
                rows.extend(build_rows(i, book))

        run_with_progress(self, self.books, _step, "Checking authors…", cancellable=False, update_every=25)
        self.rows = rows
        self._checkboxes = {}

        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            book = self.books[row.book_index]
            for col, text in ((BOOK_COL, os.path.basename(book.path)), (KIND_COL, row.kind),
                              (OLD_AUTHORS_COL, row.old_authors), (NEW_AUTHORS_COL, row.new_authors),
                              (OLD_SORT_COL, row.old_sort), (NEW_SORT_COL, row.new_sort), (WHY_COL, row.why)):
                self.table.setItem(r, col, self._readonly_item(text))
            if row.kind != KIND_FLAG:
                cb = QCheckBox()
                cb.setChecked(row.kind == KIND_SAFE)
                cb.toggled.connect(lambda checked, n=r: self._on_toggled(n, checked))
                self._checkboxes[r] = cb
                self.table.setCellWidget(r, APPLY_COL, cb)
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(WHY_COL, max(self.table.columnWidth(WHY_COL), 300))

        safe_n = sum(1 for r in rows if r.kind == KIND_SAFE)
        review_n = sum(1 for r in rows if r.kind == KIND_REVIEW)
        flag_n = sum(1 for r in rows if r.kind == KIND_FLAG)
        if not rows:
            self.status_label.setText("Nothing to clean up: every author and Author Sort looks consistent.")
        else:
            self.status_label.setText(
                f"{safe_n} book(s) with safe fixes, {review_n} with changes to review, {flag_n} flagged only."
            )
        self._ok_button.setEnabled(bool(self._checkboxes))

    def _on_toggled(self, row_number: int, checked: bool) -> None:
        """A book has at most one ticked row: its review row includes its safe row."""
        if not checked:
            return
        book_index = self.rows[row_number].book_index
        for other, cb in self._checkboxes.items():
            if other != row_number and self.rows[other].book_index == book_index and cb.isChecked():
                cb.blockSignals(True)
                cb.setChecked(False)
                cb.blockSignals(False)

    @staticmethod
    def _readonly_item(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    # ------------------------------------------------------------------
    # Result accessor, read by the caller after exec() returns Accepted

    def accepted_changes(self) -> dict[int, dict[str, str]]:
        """book index -> {"authors_str": ..., "author_sort_str": ...} for every
        ticked row (never both rows of one book)."""
        changes: dict[int, dict[str, str]] = {}
        for r, cb in self._checkboxes.items():
            if cb.isChecked():
                row = self.rows[r]
                changes[row.book_index] = {"authors_str": row.new_authors, "author_sort_str": row.new_sort}
        return changes
