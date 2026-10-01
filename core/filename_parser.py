"""
core/filename_parser.py

The reverse of core/rename_pattern.py: instead of turning metadata into a
filename, this turns a filename BACK into metadata field values, using
the same %placeholder% pattern syntax.

How it works: the pattern is compiled into a regex, where each %field%
token becomes a named capture group and everything else (dashes,
punctuation) is treated as literal text that must match exactly --
except whitespace, which is never required or exact: a space in the
pattern matches any amount of whitespace in the filename, including
none at all (see _flexible_literal_regex()). A (...)/[...]/{...} group
containing a %field% token is optional as a whole (see
build_parser_regex()), which is how "the standard template" tolerates a
missing series or year without needing two different patterns for
"with" and "without". A BARE field with no wrapper of its own stays
required, deliberately -- see _compile_tokens()'s docstring for why
that one's not just an oversight.

This works well for patterns with clear separators between fields
(which is the normal case -- e.g. "%series% %series_index% - %title%"),
but is inherently ambiguous for adjacent fields with no separator
between them, or when a field's own value happens to contain the
literal text used as a separator elsewhere in the pattern. There's no
way around that with a plain pattern-matching approach; it's a
limitation worth knowing about rather than something to silently paper
over.

The matching engine is redactor_common.core.filename_parser, generalized
from this module; since 2026-09-23 this file holds only what's
epub-specific -- which fields exist, each field's shape (series-index
ranges, month names, 2-or-4-digit years), the value clean-up, and the
sibling-folder corroboration helpers used by the Parse Filename dialog.
Whitespace is now tried strictly first and only loosened if nothing
matches, so a hyphenated author ("Jean-Paul Sartre - Nausea") is no
longer split on its own hyphen.
"""

from __future__ import annotations

import os

from core.epub_metadata import split_ampersand_names
from core.rename_pattern import PLACEHOLDERS
from redactor_common.core import filename_parser as _shared
from redactor_common.core.filename_parser import (  # noqa: F401 -- re-exported
    MONTH_NAMES,
    normalize_field_value,
)

# "tags" and "pub_year"/"pub_month"/"pub_day" are kept parseable for
# backward compatibility even though they're no longer advertised in
# PLACEHOLDERS -- see the notes in rename_pattern.py.
VALID_FIELD_KEYS = {key for key, _label in PLACEHOLDERS} | {"tags", "pub_year", "pub_month", "pub_day"}

# Each field's regex shape. A shape hint is what lets "%series%
# %series_index% - %title%" split a multi-word series from its index on
# a single space; a 1-3 digit index can never be confused with a 4-digit
# year by shape alone.
FIELD_PATTERNS = {
    "year": _shared.YEAR_FIELD_PATTERN,
    "pub_year": _shared.YEAR_FIELD_PATTERN,
    "month": _shared.MONTH_FIELD_PATTERN,
    "pub_month": _shared.MONTH_FIELD_PATTERN,
    "day": _shared.DAY_FIELD_PATTERN,
    "pub_day": _shared.DAY_FIELD_PATTERN,
    "series_index": _shared.SERIES_INDEX_FIELD_PATTERN,
    "ddc": _shared.NUMERIC_FIELD_PATTERN,
    "isbn": _shared.ISBN_FIELD_PATTERN,
}

# series_index: "007" -> "7", "03.5" -> "3.5", "01-06." -> "1-6" (filename
# padding and ordinal dots aren't part of the value); a month name
# becomes its unpadded digit ("Jan." -> "1").
STRIP_LEADING_ZEROS_FIELDS = {"series_index"}

def split_author_ampersands(value: str) -> str:
    """"Author A & Author B" -> "Author A; Author B": the read side of
    rename_pattern's %authors%, which joins multiple authors with " & "
    in a filename. See split_ampersand_names() for the rule."""
    from core.author_sort import space_initials

    return space_initials("; ".join(split_ampersand_names(value)))


NORMALIZERS = {
    "month": _shared.normalize_month,
    "pub_month": _shared.normalize_month,
    "authors": split_author_ampersands,
}

_PARSE_OPTIONS = {
    "strip_leading_zeros_fields": STRIP_LEADING_ZEROS_FIELDS,
    "field_patterns": FIELD_PATTERNS,
    "normalizers": NORMALIZERS,
}


def build_parser_regex(pattern: str):
    """Compile a %field% pattern into a regex (strict whitespace) with
    this app's field shapes -- see redactor_common's build_parser_regex()."""
    return _shared.build_parser_regex(pattern, VALID_FIELD_KEYS, field_patterns=FIELD_PATTERNS)


def parse_filename(filename_stem: str, pattern: str) -> dict[str, str] | None:
    """Extract field values from a filename (without extension) using
    `pattern`. Returns None if the filename doesn't match the pattern's
    shape at all; returns {} if the pattern has no recognized fields."""
    return _shared.parse_filename(filename_stem, pattern, VALID_FIELD_KEYS, **_PARSE_OPTIONS)


# rename_pattern's placeholder keys (%authors%, %genres%, %author_sort%,
# %year%/%month%/%day%) are short forms for readability in the pattern
# editor, but EpubBook.apply_metadata expects the actual EpubMetadata
# attribute/property names -- for these, that's the "_str" property (not
# the plain list-typed dataclass field, which also happens to exist
# under the short name, so passing it through unmapped would silently
# overwrite a list field with a raw string instead of raising) or the
# "pub_"-prefixed attribute name for the date fields. "tags"/"pub_year"/
# "pub_month"/"pub_day" are kept as legacy aliases (see rename_pattern.py).
_PLACEHOLDER_TO_METADATA_KEY = {
    "authors": "authors_str",
    "genres": "tags_str",
    "tags": "tags_str",
    "author_sort": "author_sort_str",
    "year": "pub_year",
    "month": "pub_month",
    "day": "pub_day",
}


def parsed_to_metadata_kwargs(parsed: dict[str, str]) -> dict[str, str]:
    """Translate parse_filename()'s output into keys safe to pass to
    EpubBook.apply_metadata()."""
    return {_PLACEHOLDER_TO_METADATA_KEY.get(k, k): v for k, v in parsed.items()}


def count_matching_filenames(filenames: list[str], pattern: str) -> int:
    """How many of these filename stems does `pattern` parse, extracting
    at least one field?"""
    return _shared.count_matching_filenames(filenames, pattern, VALID_FIELD_KEYS, **_PARSE_OPTIONS)


def best_matching_pattern(filenames: list[str], patterns: list[str]) -> tuple[str, int] | None:
    """The (pattern, match_count) matching the most stems; ties go to
    the earlier pattern (newest-first history wins)."""
    return _shared.best_matching_pattern(filenames, patterns, VALID_FIELD_KEYS, **_PARSE_OPTIONS)


def field_value_counts(filenames: list[str], pattern: str, field: str) -> dict[str, int]:
    """normalized value -> how many of these stems produced it for
    `field` -- see redactor_common's field_value_counts()."""
    return _shared.field_value_counts(filenames, pattern, field, VALID_FIELD_KEYS, **_PARSE_OPTIONS)


def sibling_epub_stems(book_path: str) -> list[str]:
    """Filename stems (no extension) of every .epub file sharing
    `book_path`'s own folder, excluding book_path itself. A cheap
    directory listing -- doesn't open or parse any file -- used as a
    fallback source of "other books" for field_value_counts() when the
    CURRENTLY LOADED/selected batch is too small to show any real
    repetition on its own (e.g. importing metadata for just one or two
    books at a time from a folder that has many more)."""
    directory = os.path.dirname(book_path)
    try:
        entries = os.listdir(directory)
    except OSError:
        return []
    this_name = os.path.basename(book_path)
    stems = []
    for name in entries:
        if name.lower().endswith(".epub") and name != this_name:
            stems.append(os.path.splitext(name)[0])
    return stems


# A real cost, unlike sibling_epub_stems()'s plain directory listing --
# folder_metadata_field_counts() below actually opens each candidate
# file to read its saved metadata, so it's capped rather than
# exhaustive for a folder with many thousands of files (a genre-wide
# folder, say, not just one author's). The book actually being fixed
# almost never has good metadata to check against on its own (if it
# did, it wouldn't need fixing) -- but plenty of OTHER, already-tagged
# files commonly sit in the very same folder, e.g. a handful of newly
# added, badly-named books dropped into a genre folder that's mostly
# already curated.
MAX_SIBLINGS_OPENED_FOR_METADATA_CHECK = 200


def folder_metadata_field_counts(
    directory: str, field: str, exclude_path: str | None = None,
    limit: int = MAX_SIBLINGS_OPENED_FOR_METADATA_CHECK,
) -> dict[str, int]:
    """normalized value -> how many .epub files in `directory` already
    have that (real, previously-saved) value for `field` -- "authors" or
    "series" -- in their OWN metadata, not derived from their filename
    at all. Opens up to `limit` files (see MAX_SIBLINGS_OPENED_FOR_
    METADATA_CHECK) and stops there even if the folder has more.
    A load failure on any one file is skipped, not fatal to the rest."""
    from collections import Counter

    from core.epub_metadata import EpubBook

    try:
        entries = os.listdir(directory)
    except OSError:
        return {}
    exclude_name = os.path.basename(exclude_path) if exclude_path else None

    counts: Counter[str] = Counter()
    opened = 0
    for name in entries:
        if opened >= limit:
            break
        if not name.lower().endswith(".epub") or name == exclude_name:
            continue
        try:
            book = EpubBook(os.path.join(directory, name))
        except Exception:
            continue
        opened += 1
        if book.load_error:
            continue
        if field == "authors":
            values = [a for a in book.metadata.authors if a]
            if len(values) > 1:
                # A parsed "A & B" arrives as "A; B" -- let the whole
                # co-author list confirm it too, not just each name.
                values.append("; ".join(values))
        elif field == "series":
            values = [book.metadata.series] if book.metadata.series else []
        else:
            values = []
        for value in values:
            counts[normalize_field_value(value)] += 1
    return dict(counts)


# ---------------------------------------------------------------------------
# Folder-path parsing (a pattern containing "/" or "\"), on redactor_common's
# core/path_parser.py. Shared by the Parse Filename dialog and the Redact
# "path_tags" step.
# ---------------------------------------------------------------------------


def folder_authors_to_display(value: str) -> str:
    """An author FOLDER is usually in author-sort form ("Tolkien, J.R.R.")
    while the Author(s) field holds display names ("J.R.R. Tolkien"):
    "A & B" is split first (as for filenames), then each "Last, First"
    entry is flipped with core.author_sort. A name with no comma is left
    as it is, so "Terry Pratchett" folders work unchanged."""
    from core.author_sort import author_sort_to_authors

    return author_sort_to_authors(split_author_ampersands(value))


# Same clean-up as a filename parse, except %authors% also accepts
# author-sort form.
PATH_NORMALIZERS = {**NORMALIZERS, "authors": folder_authors_to_display}


def parse_book_path(path: str, pattern: str, root: str = "", corroborate=None):
    """redactor_common's parse_path_detailed() with this app's field
    shapes: a PathParseResult (values, confidence, matched/missing
    segments, notes). `root` is the library root ("" = use the last
    folders of the path)."""
    from redactor_common.core.path_parser import parse_path_detailed

    return parse_path_detailed(
        path, pattern, root, VALID_FIELD_KEYS,
        strip_leading_zeros_fields=STRIP_LEADING_ZEROS_FIELDS,
        field_patterns=FIELD_PATTERNS, normalizers=PATH_NORMALIZERS, corroborate=corroborate,
    )


def _saved_keys(metadata, field: str) -> set[str]:
    """The comparison keys folder_metadata_field_counts() counts for one book."""
    if field == "authors":
        names = [a for a in metadata.authors if a]
        keys = [normalize_field_value(a) for a in names]
        if len(names) > 1:
            keys.append(normalize_field_value("; ".join(names)))
        return set(keys)
    return {normalize_field_value(metadata.series)} if field == "series" and metadata.series else set()


def path_corroborator(book_path: str, batch_counts: dict | None = None, metadata_counts=None, own_metadata=None):
    """A `corroborate(field, value)` callback for parse_book_path(): how
    many books in all share this folder value, this one included (the
    parser lifts a folder from 2). `batch_counts` is redactor_common's
    folder_value_counts() over the batch; `metadata_counts(directory,
    field)` returns folder_metadata_field_counts() for the book's own
    folder, i.e. the saved author/series of the files there (this book's
    own saved value, `own_metadata`, is taken out of that). Only authors
    and series are checked; a folder author is converted to display form
    first, so it compares with the saved metadata."""
    directory = os.path.dirname(book_path)

    def corroborate(field: str, value: str) -> int:
        if field not in ("authors", "series"):
            return 0
        if field == "authors":
            value = folder_authors_to_display(value)
        key = normalize_field_value(value)
        count = max((batch_counts or {}).get((field, key), 0), 1)
        if metadata_counts is not None:
            saved = metadata_counts(directory, field).get(key, 0)
            if saved and own_metadata is not None and key in _saved_keys(own_metadata, field):
                saved -= 1
            count += saved
        return count

    return corroborate
