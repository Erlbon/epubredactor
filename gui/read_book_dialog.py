"""
gui/read_book_dialog.py

File > Read Book... : a read-only reader for previewing and checking a
book in place. A chapter list (the cover, then the book's text documents
in reading order) beside a text view. Only the chapter you pick is read
from the EPUB (see EpubBook.read_text_page, capped at 2 MB); images are
read on demand from the zip, one at a time, capped in size and cached.
The book's own CSS is stripped (QTextBrowser handles it badly) and a
plain reading stylesheet is applied instead. Nothing here writes to the
book. Keys: Ctrl++ / Ctrl+- / Ctrl+0 zoom, Ctrl+F find, F3 / Shift+F3 find
next / previous, Alt+Left / Alt+Right previous / next chapter, PageUp /
PageDown / Space scroll. (Never Ctrl+Alt: that is AltGr on Norwegian
keyboards.)
"""

from __future__ import annotations

import posixpath

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, Qt, QUrl
from PyQt6.QtGui import QImage, QImageReader, QKeySequence, QShortcut, QTextDocument, QTextCursor
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton, QSplitter,
    QTextBrowser, QVBoxLayout, QWidget,
)

from core.epub_metadata import EpubBook, resolve_resource_path
from core.reader_html import DEFAULT_STYLESHEET, prepare_reader_html

MAX_IMAGE_BYTES = 20 * 1024 * 1024      # skip image files bigger than this
MAX_IMAGE_PIXELS = 40_000_000           # ...or that decode to more pixels
COVER_URL = "epub-cover:"
MIN_POINT_SIZE, MAX_POINT_SIZE, DEFAULT_POINT_SIZE = 8, 40, 13


def decode_image_capped(data: bytes, max_width: int = 0, max_pixels: int = MAX_IMAGE_PIXELS) -> QImage | None:
    """Decode image bytes, or None when they are not an image or declare
    more than max_pixels (checked from the header, before decoding).
    Wider than max_width (when > 0) is scaled down, keeping the ratio."""
    ba = QByteArray(data)
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.ReadOnly)
    reader = QImageReader(buf)
    size = reader.size()
    if size.isValid() and size.width() * size.height() > max_pixels:
        return None
    image = reader.read()
    if image.isNull() or image.width() * image.height() > max_pixels:
        return None
    if max_width > 0 and image.width() > max_width:
        image = image.scaledToWidth(max_width, Qt.TransformationMode.SmoothTransformation)
    return image


class ReaderBrowser(QTextBrowser):
    """QTextBrowser that resolves <img src> against the current chapter's
    path inside the EPUB and reads the image on demand."""

    def __init__(self, book: EpubBook, parent=None) -> None:
        super().__init__(parent)
        self._book = book
        self.base_path = ""
        self._image_cache: dict[tuple[str, int], QImage | None] = {}
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)

    def loadResource(self, rtype: int, name: QUrl):  # noqa: N802 (Qt override)
        if rtype != QTextDocument.ResourceType.ImageResource.value:
            return None
        width = max(self.viewport().width() - 30, 100)
        raw = name.toString()
        if raw == COVER_URL:
            path = "\0cover"
        else:
            path = resolve_resource_path(self.base_path, raw)
            if path is None:
                return None
        key = (path, width)
        if key not in self._image_cache:
            data = self._book.cover_bytes if raw == COVER_URL else self._book.read_resource(path, MAX_IMAGE_BYTES)
            image = decode_image_capped(data, width) if data and len(data) <= MAX_IMAGE_BYTES else None
            self._image_cache[key] = image
        return self._image_cache[key]


class ReadBookDialog(QDialog):
    def __init__(self, book: EpubBook, parent=None) -> None:
        super().__init__(parent)
        self._book = book
        self._paths = book.list_text_pages()
        # Entries: (label, archive path or None for the cover).
        self._entries: list[tuple[str, str | None]] = []
        if book.cover_bytes:
            self._entries.append(("Cover", None))
        self._first_chapter_row = len(self._entries)
        for index, path in enumerate(self._paths, start=1):
            self._entries.append((f"{index}. {posixpath.basename(path)}", path))
        title = (book.metadata.title or "").strip() or posixpath.basename(book.path)
        self._title = title
        self.setWindowTitle(f"Read Book - {title}")
        self.resize(950, 700)
        self._point_size = DEFAULT_POINT_SIZE

        self.header_label = QLabel()
        self.header_label.setStyleSheet("font-weight: bold;")
        self.position_label = QLabel()

        self.chapter_list = QListWidget()
        for label, _path in self._entries:
            self.chapter_list.addItem(label)
        self.chapter_list.currentRowChanged.connect(self._show_row)

        self.text_view = ReaderBrowser(book)
        self.text_view.document().setDefaultStyleSheet(DEFAULT_STYLESHEET)
        self._apply_zoom()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.chapter_list)
        splitter.addWidget(self.text_view)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([220, 730])

        # Find bar (hidden until Ctrl+F)
        self.find_bar = QWidget()
        find_row = QHBoxLayout(self.find_bar)
        find_row.setContentsMargins(0, 0, 0, 0)
        self.find_edit = QLineEdit()
        self.find_edit.setPlaceholderText("Find in this chapter")
        self.find_edit.returnPressed.connect(lambda: self._find(True))
        self.find_edit.textChanged.connect(lambda _t: self._find(True, from_start=True))
        find_next = QPushButton("Find Next")
        find_prev = QPushButton("Find Previous")
        find_close = QPushButton("Close Find")
        find_next.clicked.connect(lambda: self._find(True))
        find_prev.clicked.connect(lambda: self._find(False))
        find_close.clicked.connect(self._hide_find)
        self.find_status = QLabel()
        for widget in (self.find_edit, find_next, find_prev, find_close, self.find_status):
            find_row.addWidget(widget)
        find_row.setStretch(0, 1)
        self.find_bar.hide()

        self.prev_btn = QPushButton("< Previous")
        self.next_btn = QPushButton("Next >")
        self.smaller_btn = QPushButton("A-")
        self.larger_btn = QPushButton("A+")
        self.smaller_btn.setToolTip("Smaller text (Ctrl+-)")
        self.larger_btn.setToolTip("Larger text (Ctrl++)")
        close_btn = QPushButton("Close")
        self.prev_btn.clicked.connect(lambda: self._step(-1))
        self.next_btn.clicked.connect(lambda: self._step(1))
        self.smaller_btn.clicked.connect(lambda: self.zoom(-1))
        self.larger_btn.clicked.connect(lambda: self.zoom(1))
        close_btn.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addWidget(self.prev_btn)
        buttons.addWidget(self.next_btn)
        buttons.addWidget(self.position_label)
        buttons.addStretch(1)
        buttons.addWidget(self.smaller_btn)
        buttons.addWidget(self.larger_btn)
        buttons.addWidget(close_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self.header_label)
        layout.addWidget(splitter, 1)
        layout.addWidget(self.find_bar)
        layout.addLayout(buttons)

        self._shortcut(QKeySequence.StandardKey.ZoomIn, lambda: self.zoom(1))
        self._shortcut("Ctrl++", lambda: self.zoom(1))
        self._shortcut("Ctrl+=", lambda: self.zoom(1))
        self._shortcut(QKeySequence.StandardKey.ZoomOut, lambda: self.zoom(-1))
        self._shortcut("Ctrl+-", lambda: self.zoom(-1))
        self._shortcut("Ctrl+0", self.zoom_reset)
        self._shortcut("Ctrl+F", self._show_find)
        self._shortcut("F3", lambda: self._find(True))
        self._shortcut("Shift+F3", lambda: self._find(False))
        self._shortcut("Alt+Right", lambda: self._step(1))
        self._shortcut("Alt+Left", lambda: self._step(-1))
        self._shortcut("PgDown", lambda: self._scroll_page(1))
        self._shortcut("Space", lambda: self._scroll_page(1))
        self._shortcut("PgUp", lambda: self._scroll_page(-1))
        self._shortcut("Shift+Space", lambda: self._scroll_page(-1))

        if self._entries:
            self.chapter_list.setCurrentRow(self._first_chapter_row if self._paths else 0)
            self.text_view.setFocus()
        else:
            self.text_view.setPlainText("This book has no readable text documents.")
            self.prev_btn.setEnabled(False)
            self.next_btn.setEnabled(False)
            self.header_label.setText(title)

    def _shortcut(self, key, slot) -> None:
        shortcut = QShortcut(QKeySequence(key), self)
        shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        shortcut.activated.connect(slot)

    # --- zoom ----------------------------------------------------------

    def _apply_zoom(self) -> None:
        font = self.text_view.document().defaultFont()
        font.setPointSize(self._point_size)
        self.text_view.document().setDefaultFont(font)
        self.text_view.setFont(font)

    def zoom(self, delta: int) -> None:
        self._point_size = max(MIN_POINT_SIZE, min(MAX_POINT_SIZE, self._point_size + delta))
        self._apply_zoom()
        self.smaller_btn.setEnabled(self._point_size > MIN_POINT_SIZE)
        self.larger_btn.setEnabled(self._point_size < MAX_POINT_SIZE)

    def zoom_reset(self) -> None:
        self._point_size = DEFAULT_POINT_SIZE
        self.zoom(0)

    # --- find ----------------------------------------------------------

    def _show_find(self) -> None:
        self.find_bar.show()
        self.find_edit.setFocus()
        self.find_edit.selectAll()

    def _hide_find(self) -> None:
        self.find_bar.hide()
        self.find_status.clear()
        self.text_view.setFocus()

    def _find(self, forward: bool, from_start: bool = False) -> None:
        text = self.find_edit.text()
        if not text:
            self.find_status.clear()
            return
        view = self.text_view
        if from_start:
            cursor = view.textCursor()
            cursor.setPosition(min(cursor.selectionStart(), cursor.position()))
            view.setTextCursor(cursor)
        flags = QTextDocument.FindFlag(0) if forward else QTextDocument.FindFlag.FindBackward
        found = view.find(text, flags)
        if not found:  # wrap around
            cursor = view.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start if forward else QTextCursor.MoveOperation.End)
            view.setTextCursor(cursor)
            found = view.find(text, flags)
        self.find_status.setText("" if found else "Not found")

    # --- navigation ----------------------------------------------------

    def _scroll_page(self, direction: int) -> None:
        bar = self.text_view.verticalScrollBar()
        bar.setValue(bar.value() + direction * max(bar.pageStep() - 20, 20))

    def _step(self, delta: int) -> None:
        row = self.chapter_list.currentRow() + delta
        if 0 <= row < len(self._entries):
            self.chapter_list.setCurrentRow(row)

    def _show_row(self, row: int) -> None:
        if not 0 <= row < len(self._entries):
            return
        label, path = self._entries[row]
        view = self.text_view
        if path is None:
            view.base_path = ""
            view.setHtml(f'<p align="center"><img src="{COVER_URL}"></p>')
            self.position_label.setText("Cover")
        else:
            view.base_path = path
            html = self._book.read_text_page(path)
            if html is None:
                view.setPlainText(f"Could not read {path}")
            else:
                view.setHtml(prepare_reader_html(html))
                if not view.toPlainText().strip() and "<img" not in html.lower():
                    view.setPlainText("(no text in this document)")
            number = row - self._first_chapter_row + 1
            self.position_label.setText(f"Chapter {number} / {len(self._paths)}")
        self.header_label.setText(f"{self._title}  -  {label}")
        view.verticalScrollBar().setValue(0)
        self.prev_btn.setEnabled(row > 0)
        self.next_btn.setEnabled(row < len(self._entries) - 1)
