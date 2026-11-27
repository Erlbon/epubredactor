"""
core/reader_html.py

Pure text helpers for the read-only reader (gui/read_book_dialog.py): no
Qt, so they are testable without a display. QTextBrowser cannot show SVG
and ignores <svg><image> cover wrappers, so those are rewritten here.
"""

from __future__ import annotations

import re
from bisect import bisect_left
from html import escape

# The tags are found by hand, not with one regex over the page: a pattern
# such as "<img\b[^>]*?...>" rescans to the end of the page for every
# unclosed "<img " (or "<svg" without "</svg>"), so a damaged page cost time
# in the square of its size and froze the reader (20,000 of them: 14 s).
# Here each opener looks up its closer in a sorted list of closer positions,
# and the regexes below only ever run on the text of one tag.
_SVG_OPEN = re.compile(r"<svg\b", re.I)
_SVG_CLOSE = re.compile(r"</svg\s*>", re.I)
_IMAGE_OPEN = re.compile(r"<image\b", re.I)
_IMG_OPEN = re.compile(r"<img\b", re.I)
_SVG_INNER_IMAGE = re.compile(r"<image\b[^>]*?(?:xlink:)?href\s*=\s*([\"'])(.*?)\1", re.I | re.S)
_IMG_SVG = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*([\"'])([^\"']*?\.svg(?:[?#][^\"']*)?)\1[^>]*>", re.I | re.S)
# A tag longer than this is not a real <img>/<image> tag; it is left as it is.
_MAX_TAG = 8192


def _bare(name: str) -> str:
    return name.split("?")[0].split("#")[0]


def _tags(text: str, opener: re.Pattern):
    """(start, end) of each `opener` tag up to its first ">", in order; none
    after the last ">" of the text."""
    closes = [m.start() for m in re.finditer(">", text)]
    for m in opener.finditer(text):
        i = bisect_left(closes, m.end())
        if i == len(closes):
            return
        end = closes[i] + 1
        if end - m.start() <= _MAX_TAG:
            yield m.start(), end


def _svg_blocks(text: str):
    """(start, end) of each <svg ...>...</svg> block, as the lazy regex
    "<svg\\b.*?</svg\\s*>" would find them (left to right, no overlap)."""
    closes = [(m.start(), m.end()) for m in _SVG_CLOSE.finditer(text)]
    starts = [s for s, _e in closes]
    pos = 0
    for m in _SVG_OPEN.finditer(text):
        if m.start() < pos:
            continue
        i = bisect_left(starts, m.end())
        if i == len(closes):
            return
        pos = closes[i][1]
        yield m.start(), pos


def _first_inner_image(block: str) -> re.Match | None:
    for start, end in _tags(block, _IMAGE_OPEN):
        match = _SVG_INNER_IMAGE.match(block[start:end])
        if match:
            return match
    return None


def prepare_reader_html(html: str) -> str:
    """An <svg> wrapper around one raster <image> (the usual cover page)
    becomes a plain <img>; an <svg> with no raster image and an <img>
    pointing at an .svg file become a bracketed placeholder."""

    def svg_block(block: str) -> str:
        inner = _first_inner_image(block)
        if inner and not _bare(inner.group(2)).lower().endswith(".svg"):
            return f'<img src="{inner.group(2)}">'
        return "<p>[SVG graphic not shown]</p>"

    def img_svg(match: re.Match) -> str:
        name = _bare(match.group(2)).rsplit("/", 1)[-1]
        return f"[SVG image not shown: {escape(name)}]"

    parts, last = [], 0
    for start, end in _svg_blocks(html):
        parts += [html[last:start], svg_block(html[start:end])]
        last = end
    html = "".join(parts) + html[last:]

    parts, last = [], 0
    for start, end in _tags(html, _IMG_OPEN):
        match = _IMG_SVG.match(html[start:end])
        if match and match.end() == end - start:
            parts += [html[last:start], img_svg(match)]
            last = end
    return "".join(parts) + html[last:]


DEFAULT_STYLESHEET = """
body { font-family: 'Georgia', 'Times New Roman', serif; line-height: 140%; }
p { margin-top: 0px; margin-bottom: 8px; }
h1, h2, h3 { text-align: center; margin-top: 18px; margin-bottom: 12px; }
blockquote { margin-left: 30px; margin-right: 30px; }
"""
