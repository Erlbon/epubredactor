"""
gui/read_book_dialog.py

File > Read Book... : the whole book as text, so the title page, copyright
page and other front matter are easy to check without leaving the app.
A chapter list (the book's text documents in reading order) beside a text
view. Only the chapter you pick is read from the EPUB (see
EpubBook.read_text_page); book styling is stripped and images are not
shown, same as the cover preview's page browser.
"""

from __future__ import annotations

import posixpath

from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QListWidget, QPushButton, QSplitter, QTextBrowser, QVBoxLayout,
)
from PyQt6.QtCore import Qt

from core.epub_metadata import EpubBook


class ReadBookDialog(QDialog):
    def __init__(self, book: EpubBook, parent=None) -> None:
        super().__init__(parent)
        self._book = book
        self._paths = book.list_text_pages()
        title = (book.metadata.title or "").strip() or posixpath.basename(book.path)
        self.setWindowTitle(f"Read Book - {title}")
        self.resize(900, 650)

        self.chapter_list = QListWidget()
        for index, path in enumerate(self._paths, start=1):
            self.chapter_list.addItem(f"{index}. {posixpath.basename(path)}")
        self.chapter_list.currentRowChanged.connect(self._show_row)

        self.text_view = QTextBrowser()
        self.text_view.setOpenLinks(False)
        self.text_view.setOpenExternalLinks(False)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.chapter_list)
        splitter.addWidget(self.text_view)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([220, 680])

        self.prev_btn = QPushButton("< Previous")
        self.next_btn = QPushButton("Next >")
        close_btn = QPushButton("Close")
        self.prev_btn.clicked.connect(lambda: self._step(-1))
        self.next_btn.clicked.connect(lambda: self._step(1))
        close_btn.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addWidget(self.prev_btn)
        buttons.addWidget(self.next_btn)
        buttons.addStretch(1)
        buttons.addWidget(close_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter, 1)
        layout.addLayout(buttons)

        if self._paths:
            self.chapter_list.setCurrentRow(0)
        else:
            self.text_view.setPlainText("This book has no readable text documents.")
            self.prev_btn.setEnabled(False)
            self.next_btn.setEnabled(False)

    def _step(self, delta: int) -> None:
        row = self.chapter_list.currentRow() + delta
        if 0 <= row < len(self._paths):
            self.chapter_list.setCurrentRow(row)

    def _show_row(self, row: int) -> None:
        if not 0 <= row < len(self._paths):
            return
        html = self._book.read_text_page(self._paths[row])
        if html is None:
            self.text_view.setPlainText(f"Could not read {self._paths[row]}")
        else:
            self.text_view.setHtml(html)
            if not self.text_view.toPlainText().strip():
                self.text_view.setPlainText("(no text in this document)")
        self.prev_btn.setEnabled(row > 0)
        self.next_btn.setEnabled(row < len(self._paths) - 1)
