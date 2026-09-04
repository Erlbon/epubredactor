"""
gui/cover_render.py

Draws a placeholder cover image (background color + title/author/series
text) using Qt's own QPainter/QImage -- deliberately not a new image
library dependency (Pillow etc.): PyQt6 is already this app's only
dependency, and QPainter's text layout/word-wrap/font handling is more
than capable for this. What color and text to show is decided by
core/cover_generator.py (pure, testable, no Qt involved); this module
only handles the actual drawing, which needs a running Qt platform
plugin and so can't be unit-tested headlessly the way that decision
logic can -- syntax-checked and code-reviewed only, same as every other
Qt-rendering module in this app.
"""

from __future__ import annotations

from PyQt6.QtCore import QBuffer, QIODevice, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter

from core.cover_generator import TEXT_COLOR, color_for_title, cover_text_lines

# A fairly standard EPUB cover aspect ratio (2:3, portrait) -- large
# enough to look reasonable on any e-reader's library grid without
# producing an unnecessarily large file for what's just a placeholder.
COVER_WIDTH = 1200
COVER_HEIGHT = 1800
MARGIN = 100
FONT_FAMILY = "Georgia"  # a serif face reads more like a book cover than a UI sans-serif


def generate_cover_image(
    title: str, authors_str: str = "", series: str = "", series_index: str = ""
) -> bytes:
    """Renders a placeholder cover as PNG bytes, ready to pass straight
    to EpubBook.set_cover(bytes, "image/png"). PNG rather than JPEG
    deliberately -- this is mostly sharp text on a flat background,
    exactly the case JPEG's lossy compression handles worst (visible
    artifacting around letter edges)."""
    bg_color = color_for_title(title)
    text = cover_text_lines(title, authors_str, series, series_index)

    image = QImage(COVER_WIDTH, COVER_HEIGHT, QImage.Format.Format_RGB32)
    image.fill(QColor(*bg_color))

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    painter.setPen(QColor(*TEXT_COLOR))

    content_x = MARGIN
    content_width = COVER_WIDTH - 2 * MARGIN

    y = float(MARGIN)

    if text["series_line"]:
        series_font = QFont(FONT_FAMILY, 40)
        series_font.setItalic(True)
        painter.setFont(series_font)
        series_rect = QRectF(content_x, y, content_width, 140)
        painter.drawText(
            series_rect,
            int(Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap),
            text["series_line"],
        )
        y += 160

    # Title takes up the main middle portion of the cover, vertically
    # centered within its own allotted band so it looks balanced
    # whether it's one short word or several wrapped lines.
    title_font = QFont(FONT_FAMILY, 84)
    title_font.setBold(True)
    painter.setFont(title_font)
    title_bottom = COVER_HEIGHT - MARGIN - (220 if text["author_line"] else 0)
    title_rect = QRectF(content_x, y, content_width, title_bottom - y)
    painter.drawText(
        title_rect,
        int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap),
        text["title"],
    )

    if text["author_line"]:
        author_font = QFont(FONT_FAMILY, 46)
        painter.setFont(author_font)
        author_rect = QRectF(content_x, COVER_HEIGHT - MARGIN - 200, content_width, 200)
        painter.drawText(
            author_rect,
            int(Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap),
            text["author_line"],
        )

    painter.end()

    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    data = bytes(buffer.data())
    buffer.close()
    return data
