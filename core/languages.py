"""
core/languages.py

Default languages for the quick-pick "+" menu next to the Language field,
as (ISO 639-1 code, display name). EPUB's dc:language is meant to hold a
valid language code (readers use it for hyphenation, text-to-speech,
etc.), so picking from this menu sets the code -- the display name is
just what's shown in the menu itself. The field stays free text, so any
other code can still be typed directly, and more languages can be added
via the picker's "Add custom language..." option (persisted for future
sessions).
"""

from redactor_common.core.languages import language_pairs

# (ISO 639-1 code, English name) from redactor_common's shared ISO 639
# table (2026-09-23), the same one cbz (2-letter) and mp3 (3-letter) use.
DEFAULT_LANGUAGES: list[tuple[str, str]] = language_pairs(
    ["en", "de", "fr", "es", "nl", "no", "it", "sv", "da"], "alpha2",
)

# Values that mean "no real language was ever set" -- not just an empty
# string, but the handful of placeholder values conversion tools and
# earlier hand-edits commonly leave behind instead of leaving the field
# genuinely blank. "und" is ISO 639-2's own actual code for "undetermined",
# so it counts too. Deliberately NOT a general BCP-47 validator -- this
# only recognizes known placeholders, it doesn't judge whether some other
# value is a *valid* language code.
_BLANK_OR_UNKNOWN_LANGUAGE_VALUES = {
    "", "unknown", "und", "unk", "n/a", "na", "none", "not set", "unspecified",
}


def is_blank_or_unknown_language(value: str) -> bool:
    return (value or "").strip().lower() in _BLANK_OR_UNKNOWN_LANGUAGE_VALUES
