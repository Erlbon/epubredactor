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
_LOOKUP: dict[str, str] = {name: name for name in CLI_FIELDS}
_LOOKUP.update(_ALIASES)
for _key, _label, _multiline in FIELDS:
    _name = ATTR_TO_CLI.get(_key)
    if _name:
        _LOOKUP[_label.lower()] = _name

_NUMBER = re.compile(r"^\d+(\.\d+)?$")
_LANGUAGE = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})?$")

DEFAULT_INFO_FIELDS = ["title", "authors", "series", "series_index", "year"]


def resolve_field(name: str) -> str:
    """The CLI field name for what the user typed. Raises CliError listing the valid names."""
    key = _LOOKUP.get(name.strip().lower().replace("-", "_").replace(" ", "_")) or _LOOKUP.get(name.strip().lower())
    if key is None:
        raise CliError(f"unknown field {name!r}. Fields: {', '.join(FIELD_NAMES)}")
    return key


def attr_for(name: str) -> str:
    return CLI_FIELDS[resolve_field(name)]


def check_value(name: str, value: str) -> str:
    """The value to store (stripped), or a CliError when the field would not take it. "" clears the field."""
    value = value.strip()
    if not value:
        return ""
    if name == "isbn":
        if not is_valid_isbn(value):
            raise CliError(f"isbn must be a valid ISBN-10 or ISBN-13, not {value!r}")
        return normalize_isbn(value)
    if name == "series_index" and not _NUMBER.match(value):
        raise CliError(f"series_index must be a number (2 or 2.5), not {value!r}")
    if name in ("year", "month", "day"):
        if not value.isdigit():
            raise CliError(f"{name} must be a whole number, not {value!r}")
        number = int(value)
        if name == "year" and not 1 <= number <= 9999:
            raise CliError("year must be a four-digit year")
        if name == "month" and not 1 <= number <= 12:
            raise CliError("month must be 1 to 12")
        if name == "day" and not 1 <= number <= 31:
            raise CliError("day must be 1 to 31")
    if name == "language" and not _LANGUAGE.match(value):
        raise CliError(f"language must be a language code (en, eng, nb, en-GB), not {value!r}")
    return value


def parse_assignment(text: str) -> tuple[str, str]:
    """"series=Dune" -> (field attribute, checked value). Splits on the first "="."""
    if "=" not in text:
        raise CliError(f"expected FIELD=VALUE, got {text!r}")
    name, _, value = text.partition("=")
    field = resolve_field(name)
    return CLI_FIELDS[field], check_value(field, value)
