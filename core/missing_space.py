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

Two kinds of dot are left alone, since they are written without a space
on purpose: a dot between single letters (initials and acronyms such as
"R.U.R.", "P.S.", "e.g.", "U.S.A.") and the dot before a web address
ending ("example.com", "www.site.org").
"""

from __future__ import annotations

import re

# A period, comma, semicolon, colon, or closing ! / ? immediately
# followed by a letter, with no space between.
_MISSING_SPACE_RE = re.compile(r"[.,;:!?][A-Za-z]")

# Common web address endings, lower case as written in addresses.
_DOMAIN_ENDINGS = frozenset({
    "com", "org", "net", "edu", "gov", "mil", "int", "info", "biz", "io", "co", "us", "uk", "de", "no",
    "se", "dk", "fi", "fr", "nl", "be", "es", "it", "pt", "ch", "at", "pl", "ru", "jp", "cn", "au",
    "ca", "nz", "ie", "eu", "tv", "me", "app", "dev",
})


def _is_initials_dot(text: str, pos: int) -> bool:
    """The dot at `pos` sits between two single letters, the second one
    followed by another dot: "R.U.R.", "P.S.", "e.g."."""
    before_ok = pos >= 1 and text[pos - 1].isalpha() and (pos == 1 or not text[pos - 2].isalpha())
    after_ok = pos + 2 < len(text) and text[pos + 1].isalpha() and text[pos + 2] == "."
    return before_ok and after_ok


def _is_domain_dot(text: str, pos: int) -> bool:
    """The dot at `pos` starts a known web address ending ("example.com"),
    or follows "www"."""
    if text[max(0, pos - 3):pos].lower() == "www" and (pos == 3 or not text[pos - 4].isalnum()):
        return True
    m = re.match(r"[a-z]+", text[pos + 1:])
    if not m or m.group(0) not in _DOMAIN_ENDINGS:
        return False
    end = pos + 1 + m.end()
    return end == len(text) or not text[end].isalpha()


def _skipped(text: str, pos: int) -> bool:
    return text[pos] == "." and (_is_initials_dot(text, pos) or _is_domain_dot(text, pos))


def find_missing_spaces(text: str) -> list[tuple[int, str]]:
    """Returns (position, matched_snippet) for every spot in `text`
    where punctuation is immediately followed by a letter with no space.
    `position` is the index of the punctuation character itself."""
    if not text:
        return []
    return [(m.start(), m.group(0)) for m in _MISSING_SPACE_RE.finditer(text) if not _skipped(text, m.start())]


def suggest_fix(text: str) -> str:
    """Inserts a single space after every detected missing-space spot.
    Doesn't otherwise alter the text."""
    if not text:
        return text
    return _MISSING_SPACE_RE.sub(
        lambda m: m.group(0) if _skipped(text, m.start()) else m.group(0)[0] + " " + m.group(0)[1], text,
    )
