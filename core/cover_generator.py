"""
core/cover_generator.py

Decides WHAT a generated placeholder cover should say and what color
its background should be, given a book's metadata -- pure logic, no
actual image drawing. Drawing needs Qt's QPainter/QImage, which
requires a running Qt platform plugin, so that lives in
gui/cover_render.py instead, alongside the rest of this app's
Qt-specific rendering code, and can't be unit-tested headlessly the
way this module's decisions can.
"""

from __future__ import annotations

import hashlib

# A curated set of muted, book-cover-appropriate background colors
# (deliberately nothing neon/harsh) -- picked deterministically per
# book below, not randomly, so regenerating the same book's cover later
# reproduces the same color rather than a new random one each time.
COVER_PALETTE: list[tuple[int, int, int]] = [
    (44, 62, 80),      # dark slate blue
    (39, 55, 70),      # deep navy
    (91, 60, 17),      # warm brown
    (68, 90, 62),      # forest green
    (100, 40, 40),     # muted brick red
    (58, 45, 82),      # muted purple
    (30, 70, 70),      # deep teal
    (90, 70, 40),      # olive gold
    (50, 50, 50),      # charcoal
    (75, 35, 55),      # muted maroon
    (35, 65, 90),      # steel blue
    (70, 55, 35),      # tobacco
]

TEXT_COLOR: tuple[int, int, int] = (245, 245, 240)  # warm off-white, readable on every palette color


def color_for_title(title: str) -> tuple[int, int, int]:
    """Deterministically picks a background color from COVER_PALETTE
    based on the title -- the same title always gets the same color
    again later, but different titles are very likely to land on
    different ones, so a batch of generated covers looks visually
    distinct rather than all-identical. Case/whitespace-insensitive, so
    trivial differences in how a title happens to be typed don't change
    the color."""
    key = (title or "").strip().lower()
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    index = digest[0] % len(COVER_PALETTE)
    return COVER_PALETTE[index]


def cover_text_lines(
    title: str, authors_str: str = "", series: str = "", series_index: str = ""
) -> dict[str, str]:
    """Decides what text goes on the generated cover, given a book's
    metadata -- pure text logic only, no font/layout/wrapping decisions
    (those need real font metrics, which is Qt's job in
    gui/cover_render.py). Returns {"title", "author_line",
    "series_line"} -- author_line/series_line are "" when there's
    nothing to show for that part."""
    title = (title or "").strip() or "(Untitled)"
    authors_str = (authors_str or "").strip()
    author_line = f"by {authors_str}" if authors_str else ""

    series = (series or "").strip()
    series_index = (series_index or "").strip()
    if series and series_index:
        series_line = f"{series} #{series_index}"
    else:
        series_line = series  # "" if there's no series at all

    return {"title": title, "author_line": author_line, "series_line": series_line}
