"""
gui/page_headers_dialog.py

Remove Running Headers and Page Numbers (Repair menu): for a scanned book whose text still carries the printed page
furniture ("30 BOOK TITLE", "CHAPTER TITLE 33", bare page numbers) and sentences a page break cut in two, lists
what core/page_headers.py found, book by book, with the evidence, and removes it for the books left ticked. Only
books where the headers prove themselves are listed (see that module). Same "preview, then Apply" shape as Strip
HTML from Description.

Nothing is written until the books are saved; Save then rewrites each book in place (a temp file beside it, swapped
in; the previous content is NOT kept, there is no Recycle Bin copy). Like the other structural repairs this is not
on the Undo stack; closing the book without saving drops the change.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.epub_metadata import EpubBook
from core.page_headers import PageFurniturePlan, find_page_furniture
from redactor_common.gui.progress import run_with_progress
from redactor_common.gui.table_columns import make_columns_resizable
from redactor_common.gui.owned_dialog import OwnedDialog

BOOK_COL, HEADERS_COL, REMOVED_COL, JOINED_COL, APPLY_COL = range(5)


class PageHeadersDialog(OwnedDialog):
    def __init__(self, books: list[EpubBook], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Remove Running Headers and Page Numbers")
        self.resize(900, 560)
        self.books = books
        self._plans: dict[int, PageFurniturePlan] = {}
        self._checkboxes: dict[int, QCheckBox] = {}
        self._rows: list[int] = []

        self._build_ui()
        self._refresh_preview()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        intro = QLabel(
            f"Looks at {len(self.books)} book(s) for the page furniture a scan-and-OCR conversion leaves in the text: "
            "running headers (\"30 BOOK TITLE\", \"CHAPTER TITLE 33\"), page numbers and the empty paragraphs around "
            "them. Only a book where the headers prove themselves (a repeating heading and page numbers that rise "
            "through the whole book) is listed. Nothing is written until you save; Save then rewrites the book in "
            "place (the previous content is not kept, so check the preview: this cannot be undone after saving)."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.join_check = QCheckBox("Also rejoin sentences a page break cut in two (and words hyphenated at the page end)")
        self.join_check.setChecked(True)
        self.join_check.toggled.connect(lambda _checked: self._refresh_preview())
        layout.addWidget(self.join_check)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Book", "Headers found", "Lines removed", "Sentences rejoined", "Apply"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.itemSelectionChanged.connect(self._show_examples)
        layout.addWidget(self.table, 1)

        self.examples = QPlainTextEdit()
        self.examples.setReadOnly(True)
        self.examples.setMaximumHeight(150)
        self.examples.setPlaceholderText("Select a book to see examples of what would be removed.")
        layout.addWidget(self.examples)

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
        self._plans, self._checkboxes, self._rows = {}, {}, []
        join = self.join_check.isChecked()

        def _step(book: EpubBook, i: int) -> None:
            if book.load_error:
                return
            plan = find_page_furniture(book, join_sentences=join)
            if plan.changed:
                self._plans[i] = plan

        run_with_progress(self, self.books, _step, "Looking for page headers…", cancellable=True, update_every=1)

        self._rows = sorted(self._plans)
        self.table.setRowCount(len(self._rows))
        for row, i in enumerate(self._rows):
            plan = self._plans[i]
            self.table.setItem(row, BOOK_COL, self._readonly_item(os.path.basename(self.books[i].path)))
            self.table.setItem(row, HEADERS_COL, self._readonly_item(str(plan.headers)))
            self.table.setItem(row, REMOVED_COL, self._readonly_item(str(plan.removed)))
            self.table.setItem(row, JOINED_COL, self._readonly_item(str(plan.joins)))
            cb = QCheckBox()
            cb.setChecked(True)
            self._checkboxes[i] = cb
            self.table.setCellWidget(row, APPLY_COL, cb)
        make_columns_resizable(self.table, wide_column=BOOK_COL)
        self.examples.clear()
        if self._rows:
            self.table.selectRow(0)
            self.status_label.setText(f"{len(self._rows)} book(s) would be cleaned.")
        else:
            self.status_label.setText("No book has running headers or page numbers that could be proved.")
        self._ok_button.setEnabled(bool(self._rows))

    def _show_examples(self) -> None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows or rows[0].row() >= len(self._rows):
            return
        plan = self._plans[self._rows[rows[0].row()]]
        lines = [plan.summary(), "", "Repeating headings: " + ", ".join(plan.headings[:8]) + (" …" if len(plan.headings) > 8 else ""), ""]
        lines += plan.examples
        self.examples.setPlainText("\n".join(lines))

    @staticmethod
    def _readonly_item(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    # ------------------------------------------------------------------
    # Result accessor, read by the caller after exec() returns Accepted

    def accepted_plans(self) -> dict[int, PageFurniturePlan]:
        """book index -> its plan, for every row whose checkbox is checked."""
        return {i: self._plans[i] for i, cb in self._checkboxes.items() if cb.isChecked()}
