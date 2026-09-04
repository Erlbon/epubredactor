"""
core/missing_space.py

Detects a common metadata-quality problem: a missing space right after
punctuation, e.g. "Hello.World" or "Foo,Bar" -- usually from bad text
extraction or metadata scraping where words got concatenated.

Deliberately does NOT also flag a lowercase letter directly followed by
an uppercase one (e.g. "TheGreatGatsby"). That pattern does catch real
concatenation bugs, but it false-positives constantly on legitimate
names with an internal capital -- McDonald, DiCaprio, MacArthur, LeBron
-- so it's left out rather than shipped as a noisy, unreliable check.
Starting with just the punctuation rule, which essentially never
misfires on ordinary text: a period/comma/etc. directly followed by a
letter (no space) basically never happens in normal prose, since
abbreviations and decimals are followed by a space or a digit, not
directly by a letter.
"""

from __future__ import annotations

import re

# A period, comma, semicolon, colon, or closing ! / ? immediately
# followed by a letter, with no space between.
_MISSING_SPACE_RE = re.compile(r"[.,;:!?][A-Za-z]")


def find_missing_spaces(text: str) -> list[tuple[int, str]]:
    """Returns (position, matched_snippet) for every spot in `text`
    where punctuation is immediately followed by a letter with no space.
    `position` is the index of the punctuation character itself."""
    if not text:
        return []
    return [(m.start(), m.group(0)) for m in _MISSING_SPACE_RE.finditer(text)]


def suggest_fix(text: str) -> str:
    """Inserts a single space after every detected missing-space spot.
    Doesn't otherwise alter the text."""
    if not text:
        return text
    return _MISSING_SPACE_RE.sub(lambda m: m.group(0)[0] + " " + m.group(0)[1], text)
