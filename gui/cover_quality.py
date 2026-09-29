"""
gui/cover_quality.py

The Cover column: each book's cover size in pixels, so low-resolution
and missing covers stand out (the idea of cbzredactor's Size column,
applied to ebook covers) -- and Operations > Find Better Covers...
(gui/better_cover_dialog.py) to replace them.

Only the image HEADER is read (QImageReader.size()), never the whole
picture decoded, and the answer is remembered per cover (by the bytes
object's identity, the way EpubBook.cover_hash() caches), so a table
rebuild over a large library costs next to nothing.

Bands, by height (covers are portrait; a 600x900 cover looks soft on a
current e-reader's ~1400-1700px-tall screen):
- no cover                  -> red "none"
- under LOW_RES_HEIGHT       -> yellow, "low-res"
- otherwise                 -> plain "W x H"
"""

from __future__ import annotations

import weakref
from typing import Optional

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
from PyQt6.QtGui import QColor, QImageReader

LOW_RES_HEIGHT = 1000
LOW_RES_COLOR = QColor("#fff3cd")  # the shared soft amber
MISSING_COLOR = QColor("#f8d7da")  # the shared soft red

_sizes: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def image_size(data: Optional[bytes]) -> Optional[tuple[int, int]]:
    """(width, height) from the image header, or None if unreadable."""
    if not data:
        return None
    buffer = QBuffer()
    buffer.setData(QByteArray(data))
    buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    size = QImageReader(buffer).size()
    return (size.width(), size.height()) if size.isValid() and size.width() > 0 else None


def cover_size(book) -> Optional[tuple[int, int]]:
    """The book's cover size, remembered until its cover changes."""
    data = book.cover_bytes
    if not data:
        return None
    cached = _sizes.get(book)
    if cached is not None and cached[0] is data:
        return cached[1]
    size = image_size(data)
    _sizes[book] = (data, size)
    return size


def describe(book) -> tuple[str, Optional[QColor], str, float]:
    """(cell text, background or None, tooltip, sort value) for the Cover
    column. Sorts missing first, then smallest."""
    if not book.cover_bytes:
        return "none", MISSING_COLOR, "No cover image. Operations > Find Better Covers… can look one up by ISBN.", -1.0
    size = cover_size(book)
    if size is None:
        return "?", MISSING_COLOR, "The cover image can't be read.", 0.0
    width, height = size
    text = f"{width}×{height}"
    if height < LOW_RES_HEIGHT:
        return (text, LOW_RES_COLOR,
                f"Low-resolution cover (under {LOW_RES_HEIGHT}px tall): it will look soft on a current "
                "e-reader. Operations > Find Better Covers… can look for a larger one by ISBN.",
                float(height))
    return text, None, "", float(height)
