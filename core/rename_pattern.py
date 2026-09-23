"""
core/rename_pattern.py

mp3tag-style "Tag -> Filename" engine: turn a book's metadata into a
filename using a pattern with %placeholder% tokens, e.g.

    %series% %series_index% - %title%
    %authors% - %title%

No GUI dependencies -- pure string logic, so it's fully unit-testable.

The engine itself (optional [..] groups, sanitizing, reserved names,
length cap, collision-free paths, single-file rename) is
redactor_common.core.rename_pattern, which was generalized from this
module; since 2026-09-23 this file only holds what's epub-specific --
the placeholder list, legacy aliases, suggested patterns, and how an
EpubMetadata becomes the plain values dict the shared engine renders.
"""

from __future__ import annotations

from core.epub_metadata import EpubBook, EpubMetadata
from redactor_common.core import rename_pattern as _shared
from redactor_common.core.rename_pattern import (  # noqa: F401 -- re-exported
    MAX_FILENAME_LENGTH,
    sanitize_filename,
    unique_path,
    validate_filename_stem,
)

PLACEHOLDERS = [
    ("title", "Title"),
    ("isbn", "ISBN"),
    ("authors", "Author(s)"),
    ("author_sort", "Author Sort"),
    ("series", "Series"),
    ("series_index", "Series #"),
    ("collection", "Collection"),
    ("genres", "Genre"),
    ("publisher", "Publisher"),
    ("year", "Year"),
    ("month", "Month"),
    ("day", "Day"),
    ("ddc", "DDC"),
    ("language", "Language"),
]

# "%tags%" was the original token for the Genre field, before the field
# itself was relabeled from "Tags/Genre" to just "Genre" and "%genres%"
# became the advertised placeholder to match. "%pub_year%"/"%pub_month%"/
# "%pub_day%" were the original tokens for Year/Month/Day, before
# "%year%"/"%month%"/"%day%" became the advertised ones to match how
# people actually expect to write these in scripting. All kept working
# silently (not listed in PLACEHOLDERS/the hint text) so any pattern
# saved before either rename still renders and parses correctly.
_LEGACY_ALIASES = {
    "tags": "genres",
    "pub_year": "year",
    "pub_month": "month",
    "pub_day": "day",
}

DEFAULT_PATTERN = "%series% %series_index% - %title%"

# Common real-world naming conventions, offered as ready-made starting
# points for Parse Filename -> Metadata (see gui/filename_parse_dialog.py)
# alongside the user's own pattern history -- checked against the actual
# loaded filenames the same way history is, so whichever one (history or
# built-in) genuinely fits best naturally rises to the top. Covers the
# "standard template" shape -- author, optional bracketed series/index,
# title, optional year -- without needing anyone to already have one
# well-tagged book on hand to reverse-engineer a pattern from.
SUGGESTED_PATTERNS = [
    "%authors% - [%series% %series_index%] - %title% (%year%)",
    "%authors% - [%series% %series_index%] - %title%",
    "%authors% - %title% (%year%)",
    "%authors% - %title%",
    "%series% %series_index% - %title%",
    "%author_sort% - %title%",
]

def zero_pad_series_value(value: str) -> str:
    """Zero-pad a series index to at least 2 digits, correctly handling
    decimal sub-indices like "5.5" -> "05.5" (only the integer part gets
    padded; the fractional part is left exactly as typed)."""
    return _shared.zero_pad_numeric_value(value, 2)


def placeholder_values(metadata: EpubMetadata, zero_pad_series: bool = False) -> dict:
    series_index = metadata.series_index
    if zero_pad_series:
        series_index = zero_pad_series_value(series_index)
    values = {
        "title": metadata.title,
        "isbn": metadata.isbn,
        # Filenames use " & " between multiple authors rather than the
        # "; " the Authors field itself is edited/displayed with (mp3tag
        # convention for multi-value fields) -- "; " reads as a stray
        # mid-filename separator, while "Author A & Author B" reads as
        # the two co-authors it is. Built straight from the authors list
        # rather than string-replacing authors_str, so a stray "; " or
        # "&" that happens to be part of one author's actual name is
        # never touched.
        "authors": " & ".join(a for a in metadata.authors if a),
        "author_sort": metadata.author_sort_str,
        "series": metadata.series,
        "series_index": series_index,
        "collection": metadata.collection,
        "genres": metadata.tags_str,
        "publisher": metadata.publisher,
        "year": metadata.pub_year,
        "month": metadata.pub_month,
        "day": metadata.pub_day,
        "ddc": metadata.ddc,
        "language": metadata.language,
    }
    for legacy_key, current_key in _LEGACY_ALIASES.items():
        values[legacy_key] = values[current_key]
    return values


def render_filename(
    metadata: EpubMetadata,
    pattern: str,
    zero_pad_series: bool = False,
    fallback: str = "untitled",
) -> str:
    """Render a metadata-based filename stem (no extension) from a
    pattern, via the shared engine. Falls back to `fallback` if the
    pattern produces nothing usable (e.g. every referenced field was
    empty)."""
    return _shared.render_filename(
        placeholder_values(metadata, zero_pad_series), pattern, fallback=fallback,
        aliases=_LEGACY_ALIASES,
    )


def rename_book_file(book: EpubBook, new_stem: str) -> None:
    """Renames `book`'s file on disk (same folder, same extension) to
    `new_stem`, updating book.path to match -- the shared
    rename_file_on_disk(): ValueError for an invalid name,
    FileExistsError rather than auto-numbering on a collision, and a
    no-op if the name is unchanged."""
    book.path = _shared.rename_file_on_disk(book.path, new_stem)
