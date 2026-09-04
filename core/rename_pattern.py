"""
core/rename_pattern.py

mp3tag-style "Tag -> Filename" engine: turn a book's metadata into a
filename using a pattern with %placeholder% tokens, e.g.

    %series% %series_index% - %title%
    %authors% - %title%

No GUI dependencies -- pure string logic, so it's fully unit-testable.
"""

from __future__ import annotations

import os
import re

from core.epub_metadata import EpubBook, EpubMetadata

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

# Characters Windows forbids in filenames, plus control characters.
_ILLEGAL_CHARS_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_MULTI_SPACE_RE = re.compile(r"[ \t]+")
_REPEATED_SEPARATOR_RE = re.compile(r"(?:\s*-\s*){2,}")
_TRIM_SEPARATORS_RE = re.compile(r"^[\s\-–—]+|[\s\-–—]+$")

# Windows reserved device names -- a file literally named "CON.epub" fails.
_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

MAX_FILENAME_LENGTH = 150  # stem only, conservative vs. Windows' ~255 path limit


def zero_pad_series_value(value: str) -> str:
    """Zero-pad a series index to at least 2 digits, correctly handling
    decimal sub-indices like "5.5" -> "05.5" (only the integer part gets
    padded; the fractional part is left exactly as typed)."""
    value = (value or "").strip()
    if not value:
        return value
    if "." in value:
        int_part, sep, frac_part = value.partition(".")
        if int_part.isdigit():
            return f"{int_part.zfill(2)}{sep}{frac_part}"
        return value
    if value.isdigit():
        return value.zfill(2)
    return value


def placeholder_values(metadata: EpubMetadata, zero_pad_series: bool = False) -> dict:
    series_index = metadata.series_index
    if zero_pad_series:
        series_index = zero_pad_series_value(series_index)
    values = {
        "title": metadata.title,
        "isbn": metadata.isbn,
        "authors": metadata.authors_str,
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


def sanitize_filename(name: str) -> str:
    """Strip characters Windows forbids in filenames and tidy whitespace."""
    name = _ILLEGAL_CHARS_RE.sub("", name)
    name = _MULTI_SPACE_RE.sub(" ", name)
    # Empty %field% tokens commonly leave behind dangling " - " runs
    # (e.g. no series -> " - Title"); collapse those down.
    name = _REPEATED_SEPARATOR_RE.sub(" - ", name)
    name = _TRIM_SEPARATORS_RE.sub("", name)
    name = name.strip().strip(".")  # trailing dots/spaces are invalid on Windows
    return name


def render_filename(
    metadata: EpubMetadata,
    pattern: str,
    zero_pad_series: bool = False,
    fallback: str = "untitled",
) -> str:
    """Render a metadata-based filename stem (no extension) from a pattern.

    Falls back to `fallback` if the pattern produces nothing usable (e.g.
    every referenced field was empty).
    """
    values = placeholder_values(metadata, zero_pad_series)
    result = pattern
    for key, value in values.items():
        result = result.replace(f"%{key}%", value or "")

    result = sanitize_filename(result)

    if not result:
        result = fallback

    if result.upper() in _RESERVED_NAMES:
        result = f"_{result}"

    if len(result) > MAX_FILENAME_LENGTH:
        result = result[:MAX_FILENAME_LENGTH].rstrip()

    return result


def unique_path(directory: str, stem: str, ext: str, taken: set[str]) -> str:
    """Return a filesystem path for `stem+ext` inside `directory` that
    doesn't collide with anything already on disk or already claimed in
    this batch (`taken`, a set of absolute paths already assigned during
    the current rename/export run -- normalized case-insensitively since
    Windows filesystems are case-insensitive by default).
    """
    def norm(p: str) -> str:
        return os.path.normcase(os.path.abspath(p))

    candidate = os.path.join(directory, f"{stem}{ext}")
    if not os.path.exists(candidate) and norm(candidate) not in taken:
        return candidate

    n = 2
    while True:
        candidate = os.path.join(directory, f"{stem} ({n}){ext}")
        if not os.path.exists(candidate) and norm(candidate) not in taken:
            return candidate
        n += 1


def validate_filename_stem(name: str) -> str:
    """Checks whether `name` (without extension) is a valid Windows
    filename on its own merits -- returns "" if it's fine, or a clear,
    specific reason why not. Used when someone types a filename
    directly (see rename_book_file() below), as opposed to
    render_filename()'s own pattern output, which is sanitized
    automatically rather than rejected -- nobody's hand-typing pattern
    output character by character, but a single, deliberate rename
    deserves a clear "here's what's wrong" instead of silently changing
    what was actually typed."""
    if not name.strip():
        return "The filename can't be empty."
    illegal = sorted(set(_ILLEGAL_CHARS_RE.findall(name)))
    if illegal:
        return f"These characters aren't allowed in a filename: {' '.join(illegal)}"
    if name != name.rstrip():
        return "A filename can't end with a space."
    if name.rstrip(".") != name:
        return "A filename can't end with a dot."
    if name.upper() in _RESERVED_NAMES:
        return f'"{name}" is a reserved name on Windows and can\'t be used.'
    if len(name) > MAX_FILENAME_LENGTH:
        return f"That name is too long (max {MAX_FILENAME_LENGTH} characters)."
    return ""


def rename_book_file(book: EpubBook, new_stem: str) -> None:
    """Renames `book`'s file on disk (same folder, same extension) to
    `new_stem`, updating book.path to match. For fixing a typo or small
    mistake in one file's name directly, without going through the
    pattern-based Rename/Export tool.

    Raises ValueError if new_stem isn't a valid Windows filename (see
    validate_filename_stem()), or FileExistsError if a file with that
    name already exists in the same folder -- deliberately NOT
    auto-numbered here, unlike Rename/Export's batch mode: a single,
    deliberate rename should end up with exactly the name given, or
    fail clearly, not silently end up numbered to something else
    without the person necessarily noticing.

    A no-op (doesn't touch the filesystem at all) if new_stem is
    already the book's current filename."""
    error = validate_filename_stem(new_stem)
    if error:
        raise ValueError(error)

    directory = os.path.dirname(book.path)
    ext = os.path.splitext(book.path)[1]
    new_path = os.path.join(directory, new_stem + ext)

    if os.path.normcase(os.path.abspath(new_path)) == os.path.normcase(os.path.abspath(book.path)):
        return

    if os.path.exists(new_path):
        raise FileExistsError(
            f'A file named "{os.path.basename(new_path)}" already exists in this folder.'
        )

    os.rename(book.path, new_path)
    book.path = new_path
