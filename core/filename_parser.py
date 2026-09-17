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
_NUMERIC_FIELDS = {"ddc"}
_ISBN_FIELD_PATTERN = r"[\dXx\-]+"

# A series index is almost always a small number, 0-999 -- 1-3 digits,
# optionally with a decimal sub-index ("5.5" for a novella between two
# main entries). Bounded to 3 digits specifically so it can never be
# confused with a 4-digit year -- a bare number in a filename can be
# told apart by shape alone: 4 digits is a year, 1-3 is a series index.
_SERIES_INDEX_FIELD_PATTERN = r"\d{1,3}(?:\.\d+)?"

# A publication year is almost always 4 digits, occasionally 2 -- never
# a decimal, never 1 or 3 digits. Tried longest-first (the regex engine
# already prefers the first alternative that matches), so "2020" is
# read as one 4-digit year rather than accidentally matching just "20".
_YEAR_FIELD_PATTERN = r"\d{4}|\d{2}"
_DAY_FIELD_PATTERN = r"\d{1,2}"

# A month is either 1-2 digits or an English name/abbreviation -- e.g.
# "Jan", "January", "jan.". Matched case-insensitively; parse_filename()
# below normalizes whichever form matched to the same plain digit string
# (no zero-padding -- "7", not "07", matching how pub_month is stored
# elsewhere in this app; see MONTH_NAMES).
MONTH_NAMES = {
    "jan": "1", "january": "1",
    "feb": "2", "february": "2",
    "mar": "3", "march": "3",
    "apr": "4", "april": "4",
    "may": "5",
    "jun": "6", "june": "6",
    "jul": "7", "july": "7",
    "aug": "8", "august": "8",
    "sep": "9", "sept": "9", "september": "9",
    "oct": "10", "october": "10",
    "nov": "11", "november": "11",
    "dec": "12", "december": "12",
}
_MONTH_NAME_ALTERNATION = "|".join(sorted(MONTH_NAMES, key=len, reverse=True))
_MONTH_FIELD_PATTERN = rf"(?i:(?:\d{{1,2}}|{_MONTH_NAME_ALTERNATION})\.?)"

_TOKEN_RE = re.compile(r"%(\w+)%")
# A (...)/[...]/{...} segment (no nesting) containing at least one
# %field% token is an OPTIONAL group when parsing too -- mirrors
# render_filename()'s own _resolve_optional_brackets() in
# core/rename_pattern.py, so a filename with no series section still
# matches the standard "%authors% - [%series% %series_index%] -
# %title% (%year%)" template. All three wrapper styles are recognized
# so "(%year%)" is just as optional as "[%series%]" without needing to
# rewrite anyone's existing pattern. A wrapper segment with no field
# token inside is left as literal, required text.
_OPTIONAL_GROUP_RE = re.compile(r"\[([^\[\]]*)\]|\(([^()]*)\)|\{([^{}]*)\}")

def _field_regex(field: str) -> str:
    if field in ("year", "pub_year"):
        return _YEAR_FIELD_PATTERN
    if field in ("month", "pub_month"):
        return _MONTH_FIELD_PATTERN
    if field in ("day", "pub_day"):
        return _DAY_FIELD_PATTERN
    if field == "series_index":
        return _SERIES_INDEX_FIELD_PATTERN
    if field in _NUMERIC_FIELDS:
        return _NUMERIC_FIELD_PATTERN
    if field == "isbn":
        return _ISBN_FIELD_PATTERN
    return ".+?"


def _flexible_literal_regex(literal: str) -> str:
    """Converts a literal (non-placeholder) pattern-text segment into a
    regex fragment where any run of whitespace matches any run of
    whitespace in the filename -- OR NONE AT ALL. Spaces don't count as
    meaningful characters of their own: one space in the pattern
    matches one space in the filename, but also two, three, a stray
    tab, or nothing there at all. Real filenames often pick up an extra
    or missing space somewhere (a double space from a rename tool,
    inconsistent spacing around a dash, no space at all around a
    slash), and that shouldn't break matching altogether when the
    surrounding text is otherwise a clean match. Non-whitespace
    characters are still escaped and matched exactly -- this doesn't
    loosen anything about the literal punctuation/text itself, only
    whitespace around it."""
    pieces = []
    for chunk in re.split(r"(\s+)", literal):
        if not chunk:
            continue
        pieces.append(r"\s*" if chunk.isspace() else re.escape(chunk))
    return "".join(pieces)


# A run of punctuation/whitespace immediately after a wrapper group's
# closing char -- stops at the first letter/digit/underscore or the
# start of the next %field%/wrapper -- folded INTO the same optional
# group as the wrapper itself (see build_parser_regex()'s docstring for
# why).
_TRAILING_SEPARATOR_RE = re.compile(r"[^%\[({\w]*")


def _compile_tokens(segment: str, seen_fields: set[str]) -> str:
    """Compiles a pattern segment's plain %field% tokens and literal text
    into a regex fragment -- shared by build_parser_regex() for the
    top-level pattern and for the inside of an optional wrapper group,
    so a field inside one is compiled exactly the same way as one
    outside. `seen_fields` is shared across the whole pattern (mutated
    in place), so a field used a second time anywhere is still
    correctly treated as literal text to match rather than a second
    capture group, same as always.

    A bare (unwrapped) field is always REQUIRED, even one like
    %series_index% or %year% whose own shape is distinctive -- wrapping
    such a field in its own optional group individually (tried during
    development) turns out to be actively harmful next to a greedy
    ".+?" neighbor: with nothing forcing that neighbor to stop early,
    the regex engine happily skips the now-optional numeric field
    entirely and lets the neighbor swallow everything, silently
    misparsing files that DO have that field. Wrap a field in (), [] or
    {} (see build_parser_regex()) to make it genuinely optional --
    that's unambiguous, since the wrapper's own required-or-absent
    punctuation gives the regex engine something concrete to anchor on
    either way, instead of only a vague shape hint."""
    parts: list[str] = []
    last_end = 0
    for m in _TOKEN_RE.finditer(segment):
        literal = segment[last_end:m.start()]
        if literal:
            parts.append(_flexible_literal_regex(literal))

        field = m.group(1)
        if field in VALID_FIELD_KEYS and field not in seen_fields:
            parts.append(f"(?P<{field}>{_field_regex(field)})")
            seen_fields.add(field)
        else:
            parts.append(re.escape(m.group(0)))

        last_end = m.end()

    trailing = segment[last_end:]
    if trailing:
        parts.append(_flexible_literal_regex(trailing))
    return "".join(parts)


def build_parser_regex(pattern: str) -> re.Pattern:
    """Compile a %field% pattern into a regex with one named group per
    (first occurrence of a) valid field token. A field used a second time
    in the same pattern, or an unrecognized %something%, is treated as
    literal text to match rather than causing a crash.

    A (...)/[...]/{...} segment containing at least one %field% token
    compiles to an OPTIONAL group (mirrors render_filename()'s own
    wrapper handling in core/rename_pattern.py) -- a filename with no
    series section still matches "%authors% - [%series% %series_index%]
    - %title%". A wrapper segment with no field token inside compiles as
    ordinary, required literal text instead. A BARE field (no wrapper of
    its own) is always required -- see _compile_tokens()'s docstring for
    why that's deliberate, not an oversight.

    The separator text immediately following a wrapper group's closing
    character (e.g. the " - " between "]" and %title%) is folded into
    the SAME optional group as the wrapper, rather than staying
    separately required -- render_filename() collapses "Author -  -
    Title" (an empty bracket leaves two adjacent separators) down to a
    single "Author - Title", so the leading separator before the
    wrapper reads as the one connecting %authors% directly to %title%
    when there's no series, and the trailing one only appears alongside
    the wrapper. Matching has to accept both actual shapes, not just
    the one with a series."""
    parts: list[str] = []
    seen_fields: set[str] = set()
    last_end = 0

    for m in _OPTIONAL_GROUP_RE.finditer(pattern):
        literal_before = pattern[last_end:m.start()]
        if literal_before:
            parts.append(_compile_tokens(literal_before, seen_fields))

        open_ch, close_ch = m.group(0)[0], m.group(0)[-1]
        inner = next(g for g in m.groups() if g is not None)
        if _TOKEN_RE.search(inner):
            after_start = m.end()
            sep_match = _TRAILING_SEPARATOR_RE.match(pattern, after_start)
            after_end = sep_match.end() if sep_match else after_start
            trailing_literal = pattern[after_start:after_end]
            group = re.escape(open_ch) + _compile_tokens(inner, seen_fields) + re.escape(close_ch)
            if trailing_literal:
                group += _compile_tokens(trailing_literal, seen_fields)
            parts.append(f"(?:{group})?")
            last_end = after_end
        else:
            parts.append(re.escape(m.group(0)))  # plain literal wrapper, required as typed
            last_end = m.end()

    trailing = pattern[last_end:]
    if trailing:
        parts.append(_compile_tokens(trailing, seen_fields))

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


def _normalize_month(value: str) -> str:
    """A month captured as a name ("Jan", "January") becomes its plain
    digit string ("1"), unpadded, matching how pub_month is stored
    everywhere else in this app. A digit month is returned unchanged --
    a trailing "." (e.g. from "Jan." consuming the period as part of the
    match) is stripped first either way, since it's not meaningful on a
    digit value and would otherwise block the name lookup."""
    v = value.strip().rstrip(".")
    if not v:
        return v
    return MONTH_NAMES.get(v.lower(), v)


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
    for key in ("month", "pub_month"):
        if key in result:
            result[key] = _normalize_month(result[key])
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
