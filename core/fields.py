"""Single source of truth for which metadata fields the app edits, their
display labels, and whether they're multi-line. Both the file table and
the bulk-edit tag panel are built from this list so they always agree
on order and naming.

Each tuple: (attribute_key, display_label, multiline)
`attribute_key` matches either an EpubMetadata attribute name directly
(title, series, series_index, publisher, language, description) or one
of the string-view properties (authors_str, tags_str) used for the
semicolon-separated multi-value fields.
"""

FIELDS: list[tuple[str, str, bool]] = [
    ("title", "Title", False),
    ("isbn", "ISBN", False),
    ("authors_str", "Author(s)", False),
    ("author_sort_str", "Author Sort", False),
    ("series", "Series", False),
    ("series_index", "Series #", False),
    ("collection", "Collection", False),
    ("tags_str", "Genre", False),
    ("publisher", "Publisher", False),
    ("pub_year", "Year", False),
    ("pub_month", "Month", False),
    ("pub_day", "Day", False),
    ("ddc", "DDC", False),
    ("language", "Language", False),
    ("description", "Description", True),
]

# Columns whose values should sort numerically (when parseable) rather
# than as plain text, e.g. "9" should come before "10".
NUMERIC_FIELD_KEYS = {"series_index", "pub_year", "pub_month", "pub_day"}
