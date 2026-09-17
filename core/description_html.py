"""
core/description_html.py

Converts HTML markup that ended up verbatim in a book's Description
field (common: some EPUBs' dc:description is literally a publisher's
marketing HTML, tags and all, e.g. "<div>\\n<p>1942...</p>\\n<p></p>...")
into clean plain text. Used by Repair -> Strip HTML from Description
-- an explicit, reviewed batch action, never applied automatically on
load (see gui/strip_description_html_dialog.py).

No GUI dependencies -- pure string logic (aside from lxml.html, already
a project dependency via lxml, used the same way core/content_scan.py
already parses book content documents), so it's fully unit-testable.
"""

from __future__ import annotations

import lxml.etree
import lxml.html

# Elements that represent a real paragraph/line boundary -- text
# extraction inserts a blank line after each of these closes, so
# "<p>A</p><p>B</p>" (real-world descriptions are often written with
# zero whitespace between tags) still comes out as two paragraphs, not
# "AB" mashed together the way a naive .text_content() would produce.
_BLOCK_TAGS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"}


def _extract_paragraphs(text: str) -> list[str]:
    """Walks the parsed HTML tree in document order, collecting text
    and inserting a paragraph break after each block-level element,
    then collapses each paragraph's own internal whitespace (including
    any newlines that were already in the source) down to single
    spaces. Returns [] if nothing parseable was found."""
    try:
        doc = lxml.html.fromstring(f"<div>{text}</div>")
    except (lxml.etree.ParserError, ValueError):
        return []

    pieces: list[str] = []

    def walk(el) -> None:
        if el.text:
            pieces.append(el.text)
        for child in el:
            walk(child)
            if child.tag in _BLOCK_TAGS:
                pieces.append("\n\n")
            if child.tail:
                pieces.append(child.tail)

    walk(doc)
    plain = "".join(pieces)
    return [p for p in (" ".join(chunk.split()) for chunk in plain.split("\n\n")) if p]


def strip_html(text: str) -> str:
    """Converts HTML markup in `text` to clean plain text: tags
    removed, entities decoded (&amp; -> &), paragraph structure
    (<p>/<div>/<br>/... boundaries) preserved as blank-line-separated
    paragraphs. Returns `text` completely unchanged if it contains no
    "<" at all (the overwhelmingly common case -- a genuinely plain
    description is never touched, not even whitespace-normalized) or
    if nothing recognizable as a tag was actually found in it (e.g.
    stray "<"/">" used mathematically, not as markup)."""
    if not text or "<" not in text:
        return text
    paragraphs = _extract_paragraphs(text)
    if not paragraphs:
        return text
    result = "\n\n".join(paragraphs)
    return result if result != text else text


def has_html_markup(text: str) -> bool:
    """Whether stripping `text` would actually change it -- used to
    decide which books' descriptions are worth listing in the Strip
    HTML from Description batch dialog."""
    return bool(text) and strip_html(text) != text
