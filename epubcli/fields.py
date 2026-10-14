"""
epubcli/fields.py

Metadata field names for the command line. Any spelling the user is likely to type finds the field
("author", "Author(s)", "authors", "series_index", "Series #", "year", "pub_year"), and a value is checked
before anything is written. Multi-value fields (authors, genres) take names separated by ";".
"""

from __future__ import annotations

import re

from core.fields import FIELDS
from core.isbn import is_valid_isbn, normalize_isbn
from redactor_common.cli import CliError
from redactor_common.cli.fields import FieldResolver, spelling_variants
from redactor_common.cli.values import check_text, is_ascii_number

# Field names as the CLI presents them, mapped to the EpubMetadata attribute the app edits.
CLI_FIELDS = {
    "title": "title", "isbn": "isbn", "authors": "authors_str", "author_sort": "author_sort_str",
    "series": "series", "series_index": "series_index", "collection": "collection", "genres": "tags_str",
    "publisher": "publisher", "year": "pub_year", "month": "pub_month", "day": "pub_day", "ddc": "ddc",
    "language": "language", "description": "description",
}
ATTR_TO_CLI = {attr: name for name, attr in CLI_FIELDS.items()}
FIELD_NAMES = list(CLI_FIELDS)

_ALIASES = {
    "author": "authors", "authors_str": "authors", "author(s)": "authors", "author_sort_str": "author_sort",
    "authorsort": "author_sort", "series_number": "series_index", "series_no": "series_index", "series #": "series_index",
    "series#": "series_index", "genre": "genres", "tags": "genres", "tag": "genres", "tags_str": "genres",
    "pub_year": "year", "pub_month": "month", "pub_day": "day", "lang": "language",
}
_NUMBER = re.compile(r"^[0-9]+(\.[0-9]+)?$")
_LANGUAGE = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})?$")

DEFAULT_INFO_FIELDS = ["title", "authors", "series", "series_index", "year"]


def _spellings() -> dict[str, str]:
    """Every spelling -> CLI field name: each name, alias and the app's column label, in each of the usual
    spellings (series_index, series-index, "series index", seriesindex)."""
    table: dict[str, str] = {}
    for name in CLI_FIELDS:
        table.update(dict.fromkeys(spelling_variants(name), name))
    for alias, name in _ALIASES.items():
        table.update(dict.fromkeys(spelling_variants(alias), name))
    for key, label, _multiline in FIELDS:
        name = ATTR_TO_CLI.get(key)
        if name:
            table.update(dict.fromkeys(spelling_variants(label), name))
    return table


def resolve_field(name: str) -> str:
    """The CLI field name for what the user typed. Raises CliError listing the valid names."""
    return RESOLVER.resolve(name)


def attr_for(name: str) -> str:
    return CLI_FIELDS[resolve_field(name)]


MULTI_VALUE_ATTRS = ("authors_str", "author_sort_str", "tags_str")


def normalize(attr: str, value: str) -> str:
    """A value the way the book stores and reads it back, so a change is only a change when it differs
    ("A;B" and "A; B" are the same authors)."""
    value = (value or "").strip()
    if attr in MULTI_VALUE_ATTRS:
        return "; ".join(part.strip() for part in value.split(";") if part.strip())
    return value


def check_value(name: str, value: str) -> str:
    """The value to store (stripped), or a CliError when the field would not take it. "" clears the field."""
    value = check_text(name, value, multiline=name == "description")
    if not value:
        return ""
    if name == "isbn":
        if not is_valid_isbn(value):
            raise CliError(f"isbn must be a valid ISBN-10 or ISBN-13, not {value!r}")
        return normalize_isbn(value)
    if name == "series_index" and not _NUMBER.match(value):
        raise CliError(f"series_index must be a number (2 or 2.5), not {value!r}")
    if name in ("year", "month", "day"):
        if not is_ascii_number(value):
            raise CliError(f"{name} must be a whole number written with the digits 0-9, not {value!r}")
        number = int(value)
        if name == "year" and not (len(value) == 4 and number >= 1):
            raise CliError("year must be a four-digit year")
        if name == "month" and not 1 <= number <= 12:
            raise CliError("month must be 1 to 12")
        if name == "day" and not 1 <= number <= 31:
            raise CliError("day must be 1 to 31")
    if name == "series_index" and float(value) > 99999:
        raise CliError(f"series_index is too large: {value}")
    if name == "language" and not _LANGUAGE.match(value):
        raise CliError(f"language must be a language code (en, eng, nb, en-GB), not {value!r}")
    return value


# redactor_common's resolver over this app's table: case-insensitive, and "series index", "series-index",
# "series_index" and "seriesindex" all find the field.
RESOLVER = FieldResolver(_spellings(), FIELD_NAMES, check=check_value)


def parse_assignment(text: str) -> tuple[str, str]:
    """"series=Dune" -> (field attribute, checked value). Splits on the first "="."""
    field, value = RESOLVER.parse_assignment(text)
    return CLI_FIELDS[field], value
