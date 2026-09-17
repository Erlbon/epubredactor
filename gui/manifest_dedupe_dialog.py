"""
gui/manifest_dedupe_dialog.py

Deduplicate Manifest IDs: a standalone, explicitly-triggered action
(Repair menu) for badly-converted EPUB2->EPUB3 files whose manifest has
two <item> entries sharing the same id (most often id="ncx") -- causes
this app's own validation to report DUPLICATE_MANIFEST_ID, and generally
means a reader can't reliably resolve <spine toc="ncx">, an itemref
idref, or a meta refines pointing at that id. Kept separate from
Rebuild Manifest (which only removes entries for files that no longer
exist) since this is a different kind of manifest defect with a
different fix -- same one-dialog-per-repair convention as the rest of
the Repair menu.
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
from redactor_common.gui.progress import run_with_progress

BOOK_COL, DUPLICATE_COL, APPLY_COL = range(3)


class ManifestDedupeDialog(QDialog):
    def __init__(self, books: list[EpubBook], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Deduplicate Manifest IDs")
        self.resize(640, 480)
        self.books = [b for b in books if not b.load_error]
        self._duplicates: dict[int, dict[str, list[str]]] = {}  # book index -> {id: [href, ...]}
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
        self.table.setHorizontalHeaderLabels(["Book", "Duplicate id(s)", "Fix"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(DUPLICATE_COL, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

        info = QLabel(
            "Renames every duplicate manifest item id to a fresh, unused one (e.g. \"ncx\" -> "
            "\"ncx-2\") so every item in the manifest has a unique id, the way the EPUB spec "
            "requires. Whichever item actually matches what the id conventionally means (e.g. "
            "the real toc.ncx for id=\"ncx\") keeps the original id, so existing references to "
            "it (<spine toc=\"...\">, etc.) keep working unchanged -- only the stray duplicate's "
            "id changes."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #b45309; font-size: 11px;")
        layout.addWidget(info)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Fix Duplicates")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)

    def _scan(self) -> None:
        self._duplicates = {}
        rows = []

        def _step(book: EpubBook, i: int) -> None:
            dups = book.find_duplicate_manifest_ids()
            if dups:
                self._duplicates[i] = dups
                rows.append(i)

        run_with_progress(
            self, self.books, _step, "Checking manifests…", cancellable=False, update_every=25,
        )

        self.table.setRowCount(len(rows))
        for row, book_index in enumerate(rows):
            book = self.books[book_index]
            dups = self._duplicates[book_index]
            preview = ", ".join(f"{item_id} ({len(hrefs)}x)" for item_id, hrefs in sorted(dups.items()))
            self.table.setItem(row, BOOK_COL, self._readonly_item(os.path.basename(book.path)))
            self.table.setItem(row, DUPLICATE_COL, self._readonly_item(preview))
            cb = QCheckBox()
            cb.setChecked(True)
            self._checkboxes[book_index] = cb
            self.table.setCellWidget(row, APPLY_COL, cb)
        self.table.resizeColumnsToContents()

        if not self._duplicates:
            self.info_label.setText("No duplicate manifest ids found in the selected book(s).")
            self._ok_button.setEnabled(False)
        else:
            total = sum(len(v) for v in self._duplicates.values())
            self.info_label.setText(
                f"Found {total} duplicate manifest id(s) across {len(self._duplicates)} "
                f"book(s). Untick any you don't want fixed."
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
        checked and which had duplicate manifest ids."""
        return [i for i in self._duplicates if self._checkboxes[i].isChecked()]
