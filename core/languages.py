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

DEFAULT_LANGUAGES: list[tuple[str, str]] = [
    ("en", "English"),
    ("de", "German"),
    ("fr", "French"),
    ("es", "Spanish"),
    ("nl", "Dutch"),
    ("no", "Norwegian"),
    ("it", "Italian"),
    ("sv", "Swedish"),
    ("da", "Danish"),
]
