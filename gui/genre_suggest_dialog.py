"""
gui/genre_suggest_dialog.py

Suggests genres for each selected book from its folder path, its
description, its first few pages and its DDC number (see
core/genre_detect.py), and lets you tick which ones to add. Same
"find candidates, human decides" pattern as Import Metadata from File
Content -- nothing is applied without review.

Add-only by design: a book's existing genre tags are shown for
reference, never replaced or removed, and the caller merges the ticked
genres into whatever the Genre field holds at apply time
(core.genres.add_genres). Suggestions for a book that already has
genre tags start unticked, so nothing is added to a book someone
already tagged without a deliberate tick.
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
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.epub_metadata import EpubBook
from core.genre_detect import GenreSuggestion, scan_book_genres
from redactor_common.gui.progress import run_with_progress

BOOK_COL, CURRENT_COL, GENRE_COL, SOURCE_COL, ADD_COL = range(5)


class GenreSuggestDialog(QDialog):
    def __init__(self, books: list[EpubBook], vocabulary: list[str] | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Suggest Genres")
        self.resize(980, 520)
        self.books = books
        self.vocabulary = vocabulary
        # table row -> (book index, genre); only rows with a suggestion
        self._row_targets: dict[int, tuple[int, str]] = {}
        self._checkboxes: dict[int, QCheckBox] = {}

        self._build_ui()
        self._run_scan()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        info = QLabel(
            f"Genres suggested for {len(self.books)} book(s) from the folder path, the "
            "description, the first few pages (catalog/subject lines) and the DDC number.\n"
            "Ticked genres are ADDED to the Genre field; existing genres are never replaced "
            "or removed. Suggestions for books that already have genres start unticked."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Book", "Current Genre", "Suggested", "Found In", "Add"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(SOURCE_COL, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

        tick_row = QHBoxLayout()
        tick_all = QPushButton("Tick All")
        tick_all.clicked.connect(lambda: self._set_all(True))
        untick_all = QPushButton("Untick All")
        untick_all.clicked.connect(lambda: self._set_all(False))
        tick_row.addWidget(tick_all)
        tick_row.addWidget(untick_all)
        tick_row.addStretch(1)
        layout.addLayout(tick_row)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self.status_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Add Ticked Genres")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _run_scan(self) -> None:
        results: list[tuple[int, list[GenreSuggestion]]] = []

        def _step(book: EpubBook, index: int) -> None:
            try:
                suggestions = scan_book_genres(book, self.vocabulary) if not book.load_error else []
            except Exception:  # noqa: BLE001 - one unreadable book shouldn't crash the dialog
                suggestions = []
            results.append((index, suggestions))

        run_with_progress(
            self, self.books, _step, "Suggesting genres…", threshold=1, cancellable=False,
            label_for=lambda book: f"Scanning: {os.path.basename(book.path)}",
        )
        self._fill_table(results)

    def _fill_table(self, results: list[tuple[int, list[GenreSuggestion]]]) -> None:
        rows = sum(max(1, len(suggestions)) for _index, suggestions in results)
        self.table.setRowCount(rows)
        row = 0
        books_with_suggestions = 0
        for index, suggestions in results:
            book = self.books[index]
            current = book.metadata.tags_str
            if suggestions:
                books_with_suggestions += 1
            for n, suggestion in enumerate(suggestions or [None]):
                first = n == 0
                self.table.setItem(row, BOOK_COL, self._readonly_item(os.path.basename(book.path) if first else ""))
                self.table.setItem(row, CURRENT_COL, self._readonly_item(current if first else ""))
                cb = QCheckBox()
                if suggestion is None:
                    self.table.setItem(row, GENRE_COL, self._readonly_item("(nothing found)"))
                    self.table.setItem(row, SOURCE_COL, self._readonly_item(""))
                    cb.setEnabled(False)
                else:
                    self.table.setItem(row, GENRE_COL, self._readonly_item(suggestion.genre))
                    source_item = self._readonly_item(", ".join(suggestion.source_kinds))
                    source_item.setToolTip(
                        "\n".join(f"{source}: {snippet}" for source, snippet in suggestion.sources)
                    )
                    self.table.setItem(row, SOURCE_COL, source_item)
                    cb.setChecked(not current.strip())
                    self._row_targets[row] = (index, suggestion.genre)
                self._checkboxes[row] = cb
                self.table.setCellWidget(row, ADD_COL, cb)
                row += 1
        self.table.resizeColumnsToContents()
        self.status_label.setText(
            f"Found genre suggestions for {books_with_suggestions} of {len(self.books)} book(s). "
            "Hover over 'Found In' to see the matched text."
        )

    def _set_all(self, checked: bool) -> None:
        for row, cb in self._checkboxes.items():
            if row in self._row_targets:
                cb.setChecked(checked)

    @staticmethod
    def _readonly_item(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    # ------------------------------------------------------------------
    # Result accessor, read by the caller after exec() returns Accepted

    def accepted_additions(self) -> dict[int, list[str]]:
        """book index -> genres to ADD (in table order), for every ticked
        suggestion. The caller merges these into the book's current
        genres; nothing here is a replacement value."""
        additions: dict[int, list[str]] = {}
        for row, (index, genre) in sorted(self._row_targets.items()):
            if self._checkboxes[row].isChecked():
                additions.setdefault(index, []).append(genre)
        return additions
