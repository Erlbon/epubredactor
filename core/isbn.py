"""
core/isbn.py

ISBN-10 / ISBN-13 validation, normalization, and conversion. Pure logic,
no GUI or network dependencies.
"""

from __future__ import annotations

import re

_STRIP_RE = re.compile(r"[^0-9Xx]")


def normalize_isbn(text: str) -> str:
    """Strip dashes/spaces/punctuation, uppercase any trailing X.
    Does NOT validate -- just cleans up formatting for comparison/storage."""
    if not text:
        return ""
    return _STRIP_RE.sub("", text).upper()


def is_valid_isbn10(text: str) -> bool:
    s = normalize_isbn(text)
    if len(s) != 10:
        return False
    total = 0
    for i, ch in enumerate(s):
        if ch == "X":
            if i != 9:  # 'X' is only valid as the final check character
                return False
            value = 10
        elif ch.isdigit():
            value = int(ch)
        else:
            return False
        total += (i + 1) * value
    return total % 11 == 0


def is_valid_isbn13(text: str) -> bool:
    s = normalize_isbn(text)
    if len(s) != 13 or not s.isdigit():
        return False
    total = 0
    for i, ch in enumerate(s):
        weight = 1 if i % 2 == 0 else 3
        total += weight * int(ch)
    return total % 10 == 0


def is_valid_isbn(text: str) -> bool:
    return is_valid_isbn10(text) or is_valid_isbn13(text)


def isbn10_to_isbn13(isbn10: str) -> str:
    """Convert a valid ISBN-10 to its ISBN-13 equivalent (978 prefix with
    a freshly computed check digit). Raises ValueError if input isn't a
    valid ISBN-10."""
    if not is_valid_isbn10(isbn10):
        raise ValueError(f"Not a valid ISBN-10: {isbn10!r}")
    core9 = normalize_isbn(isbn10)[:9]
    base = "978" + core9
    total = 0
    for i, ch in enumerate(base):
        weight = 1 if i % 2 == 0 else 3
        total += weight * int(ch)
    check = (10 - (total % 10)) % 10
    return base + str(check)


def best_isbn13(text: str) -> str:
    """Given any ISBN string (10 or 13 digit), return a normalized
    ISBN-13 if possible -- Kobo and most modern catalogs prefer 13-digit
    identifiers. Returns "" if the input isn't a recognizable ISBN."""
    s = normalize_isbn(text)
    if is_valid_isbn13(s):
        return s
    if is_valid_isbn10(s):
        return isbn10_to_isbn13(s)
    return ""
