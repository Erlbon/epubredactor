"""
core/series_numbering.py

Generates a sequence of Series # values for numbering several books in
one go -- the thing a plain bulk-edit can't do, since applying the same
value to every selected book is the opposite of what you want when
numbering an entire series at once. Modeled on mp3tag's "auto-number
tracks" feature.

Uses decimal.Decimal throughout rather than float, specifically to
avoid float step-accumulation error (0.1 + 0.1 + 0.1 != 0.3 in binary
floating point) -- this matters here since a fractional step (e.g. 0.5,
for a novella slotted between two main-series entries) is a real,
common use case, not an edge case to shrug off.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

DEFAULT_START = "1"
DEFAULT_STEP = "1"


def parse_decimal(text: str, default: str) -> Decimal:
    """Parses text as a Decimal, falling back to `default` (itself
    parsed as a Decimal) for blank or unparseable input -- never raises,
    since this is always driven by a live text field the user may be
    mid-edit on."""
    text = (text or "").strip()
    if not text:
        text = default
    try:
        return Decimal(text)
    except InvalidOperation:
        return Decimal(default)


def format_series_number(value: Decimal) -> str:
    """Plain, minimal string form: whole numbers have no trailing
    ".0" or decimal point, fractional ones keep only as many decimal
    places as they actually need. Deliberately avoids Decimal.normalize()
    for whole numbers, since normalize() can produce scientific notation
    for round values (e.g. Decimal("100").normalize() -> Decimal('1E+2'))."""
    if value == value.to_integral_value():
        return str(value.to_integral_value())
    text = format(value, "f")
    return text.rstrip("0").rstrip(".")


def generate_series_numbers(count: int, start: str = DEFAULT_START, step: str = DEFAULT_STEP) -> list[str]:
    """Returns `count` sequential Series # values as strings, starting
    at `start` and increasing by `step` each time (both parsed leniently
    via parse_decimal -- blank or invalid input just falls back to the
    default rather than raising, since the caller is a live preview that
    updates on every keystroke)."""
    if count <= 0:
        return []
    start_val = parse_decimal(start, DEFAULT_START)
    step_val = parse_decimal(step, DEFAULT_STEP)

    result = []
    current = start_val
    for _ in range(count):
        result.append(format_series_number(current))
        current += step_val
    return result
