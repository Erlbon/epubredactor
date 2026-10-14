"""
core/reader_html.py

Pure text helpers for the read-only reader (gui/read_book_dialog.py): no
Qt, so they are testable without a display. QTextBrowser cannot show SVG
and ignores <svg><image> cover wrappers, so those are rewritten here.
"""

from __future__ import annotations

import re
from html import escape

_SVG_BLOCK = re.compile(r"<svg\b.*?</svg\s*>", re.I | re.S)
_SVG_INNER_IMAGE = re.compile(r"<image\b[^>]*?(?:xlink:)?href\s*=\s*([\"'])(.*?)\1", re.I | re.S)
_IMG_SVG = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*([\"'])([^\"']*?\.svg(?:[?#][^\"']*)?)\1[^>]*>", re.I | re.S)


def _bare(name: str) -> str:
    return name.split("?")[0].split("#")[0]


def prepare_reader_html(html: str) -> str:
    """An <svg> wrapper around one raster <image> (the usual cover page)
    becomes a plain <img>; an <svg> with no raster image and an <img>
    pointing at an .svg file become a bracketed placeholder."""

    def svg_block(match: re.Match) -> str:
        inner = _SVG_INNER_IMAGE.search(match.group(0))
        if inner and not _bare(inner.group(2)).lower().endswith(".svg"):
            return f'<img src="{inner.group(2)}">'
        return "<p>[SVG graphic not shown]</p>"

    def img_svg(match: re.Match) -> str:
        name = _bare(match.group(2)).rsplit("/", 1)[-1]
        return f"[SVG image not shown: {escape(name)}]"

    html = _SVG_BLOCK.sub(svg_block, html)
    return _IMG_SVG.sub(img_svg, html)


DEFAULT_STYLESHEET = """
body { font-family: 'Georgia', 'Times New Roman', serif; line-height: 140%; }
p { margin-top: 0px; margin-bottom: 8px; }
h1, h2, h3 { text-align: center; margin-top: 18px; margin-bottom: 12px; }
blockquote { margin-left: 30px; margin-right: 30px; }
"""
