"""
core/filename_parser.py

The reverse of core/rename_pattern.py: instead of turning metadata into a
filename, this turns a filename BACK into metadata field values, using
the same %placeholder% pattern syntax.

How it works: the pattern is compiled into a regex, where each %field%
token becomes a named capture group and everything else (spaces, dashes,
punctuation) is treated as literal text that must match exactly. This
works well for patterns with clear separators between fields (which is
the normal case -- e.g. "%series% %series_index% - %title%"), but is
inherently ambiguous for adjacent fields with no separator between them,
or when a field's own value happens to contain the literal text used as
a separator elsewhere in the pattern. There's no way around that with a
plain pattern-matching approach; it's a limitation worth knowing about
rather than something to silently paper over.
"""

from __future__ import annotations

import re

from core.rename_pattern import PLACEHOLDERS

# "tags" and "pub_year"/"pub_month"/"pub_day" are kept parseable for
# backward compatibility even though they're no longer advertised in
# PLACEHOLDERS -- see the notes in rename_pattern.py.
VALID_FIELD_KEYS = {key for key, _label in PLACEHOLDERS} | {"tags", "pub_year", "pub_month", "pub_day"}

# Fields whose values are reliably digit-shaped get a stricter regex
# fragment instead of generic ".+?" -- this matters in practice: a
# pattern like "%series% %series_index% - %title%" only has a single
# space separating a (possibly multi-word) series name from the index,
# which is ambiguous with a plain ".+?" match. Requiring the index to
# actually look like a number resolves that ambiguity in the common case.
_NUMERIC_FIELD_PATTERN = r"\d+(?:\.\d+)?"
_NUMERIC_FIELDS = {"series_index", "year", "month", "day", "pub_year", "pub_month", "pub_day", "ddc"}
_ISBN_FIELD_PATTERN = r"[\dXx\-]+"

_TOKEN_RE = re.compile(r"%(\w+)%")


def _flexible_literal_regex(literal: str) -> str:
    """Converts a literal (non-placeholder) pattern-text segment into a
    regex fragment where any run of whitespace matches any run of
    whitespace in the filename -- one space in the pattern still
    matches one space, but also two, three, or a stray tab, rather than
    requiring the exact same character-for-character spacing. Real
    filenames often pick up an extra or missing space somewhere (a
    double space from a rename tool, inconsistent spacing around a
    dash), and that shouldn't break matching altogether when the
    surrounding text is otherwise a clean match. Non-whitespace
    characters are still escaped and matched exactly -- this doesn't
    loosen anything about the literal punctuation/text itself, only
    how much whitespace is required where the pattern already has some."""
    pieces = []
    for chunk in re.split(r"(\s+)", literal):
        if not chunk:
            continue
        pieces.append(r"\s+" if chunk.isspace() else re.escape(chunk))
    return "".join(pieces)


def build_parser_regex(pattern: str) -> re.Pattern:
    """Compile a %field% pattern into a regex with one named group per
    (first occurrence of a) valid field token. A field used a second time
    in the same pattern, or an unrecognized %something%, is treated as
    literal text to match rather than causing a crash."""
    parts: list[str] = []
    seen_fields: set[str] = set()
    last_end = 0

    for m in _TOKEN_RE.finditer(pattern):
        literal = pattern[last_end:m.start()]
        if literal:
            parts.append(_flexible_literal_regex(literal))

        field = m.group(1)
        if field in VALID_FIELD_KEYS and field not in seen_fields:
            if field in _NUMERIC_FIELDS:
                parts.append(f"(?P<{field}>{_NUMERIC_FIELD_PATTERN})")
            elif field == "isbn":
                parts.append(f"(?P<{field}>{_ISBN_FIELD_PATTERN})")
            else:
                parts.append(f"(?P<{field}>.+?)")
            seen_fields.add(field)
        else:
            parts.append(re.escape(m.group(0)))

        last_end = m.end()

    trailing = pattern[last_end:]
    if trailing:
        parts.append(_flexible_literal_regex(trailing))

    return re.compile("^" + "".join(parts) + "$")


def _strip_series_index_leading_zeros(value: str) -> str:
    """Strips leading zeros from the integer part of a series index,
    preserving any decimal part exactly ("03.5" -> "3.5", "007" -> "7",
    "0" -> "0"). Filenames often zero-pad a series index purely for
    correct sort order ("Book 03"), but that padding isn't meaningful
    metadata -- it's a filename-ordering artifact, not part of the
    actual series number, so it shouldn't carry over into the field
    value itself."""
    if not value:
        return value
    if "." in value:
        int_part, sep, frac_part = value.partition(".")
        stripped = int_part.lstrip("0") or "0"
        return f"{stripped}{sep}{frac_part}"
    return value.lstrip("0") or "0"


def parse_filename(filename_stem: str, pattern: str) -> dict[str, str] | None:
    """Extract field values from a filename (without extension) using
    `pattern`. Returns None if the filename doesn't match the pattern's
    shape at all; returns {} if the pattern has no recognized fields."""
    regex = build_parser_regex(pattern)
    match = regex.match((filename_stem or "").strip())
    if match is None:
        return None
    result = {key: (value or "").strip() for key, value in match.groupdict().items()}
    if "series_index" in result:
        result["series_index"] = _strip_series_index_leading_zeros(result["series_index"])
    return result


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
    """How many of these filename stems does `pattern` successfully
    parse, extracting at least one field? Used to detect which of a set
    of candidate patterns (e.g. previously-used ones from history)
    actually fits a given batch of loaded files, rather than making the
    person try each one by hand to find out."""
    count = 0
    for stem in filenames:
        if parse_filename(stem, pattern):  # None or {} both count as no match
            count += 1
    return count


def best_matching_pattern(filenames: list[str], patterns: list[str]) -> tuple[str, int] | None:
    """Given a list of candidate patterns (e.g. pattern history, newest
    first), returns the (pattern, match_count) pair that matches the
    most of these filename stems -- or None if none of them match
    anything at all. A tie is broken toward whichever pattern comes
    first in `patterns`, so passing history in its natural newest-first
    order naturally prefers the more recently-used pattern when two tie
    on match count."""
    best: str | None = None
    best_count = 0
    for pattern in patterns:
        count = count_matching_filenames(filenames, pattern)
        if count > best_count:
            best = pattern
            best_count = count
    return (best, best_count) if best is not None else None
