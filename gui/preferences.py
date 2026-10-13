"""
gui/preferences.py

Tools > Preferences (Ctrl+,): the shared Preferences dialog from
redactor_common with this app's pages.

  Filenames   shared: ASCII-safe filenames, zero-pad numbers + width
              (this app has no Auto-Numbering, so no padding setting for it)
  Language    shared: the blank-language default (with its on/off switch)
  Tools and Paths   Calibre folder, Sigil program, Open Library database and dumps,
                    ISFDB database and backup

Text wrapping and performance logging are NOT here: they live in the menus
(View > Text Wrapping, Tools > Enable Performance Logging), where the
family's menu skeleton puts them. A second copy here was a duplicate.

The dialog only maps its setting names onto the EXISTING ini keys (INI_KEYS
below), so every loader in app_settings and File > Export / Import Settings
keep reading and writing the very same entries.
"""

from __future__ import annotations

from redactor_common.core.preferences import (
    KEY_ASCII_FILENAMES,
    KEY_BLANK_LANGUAGE_ENABLED,
    KEY_DEFAULT_LANGUAGE,
    KEY_ZERO_PAD_NUMBERS,
    KEY_ZERO_PAD_WIDTH,
    CallbackBackend,
    PrefSection,
    PrefSpec,
    filenames_section,
    language_section,
)
from redactor_common.gui.preferences_dialog import PreferencesDialog

from gui import app_settings

# App-specific setting names.
KEY_CALIBRE_DIR = "calibre_install_dir"
KEY_SIGIL_PATH = "sigil_exe_path"
KEY_OPENLIBRARY_DB = "openlibrary_database"
KEY_OPENLIBRARY_EDITIONS = "openlibrary_editions_dump"
KEY_OPENLIBRARY_AUTHORS = "openlibrary_authors_dump"
KEY_OPENLIBRARY_WORKS = "openlibrary_works_dump"
KEY_ISFDB_DB = "isfdb_database"
KEY_ISFDB_BACKUP = "isfdb_backup"

# setting name -> the ini key it has always been stored under.
INI_KEYS = {
    KEY_ASCII_FILENAMES: "rename/ascii_only",
    KEY_ZERO_PAD_NUMBERS: "rename/zero_pad_enabled",
    KEY_ZERO_PAD_WIDTH: "rename/zero_pad_width",
    KEY_BLANK_LANGUAGE_ENABLED: "language/blank_default_enabled",
    KEY_DEFAULT_LANGUAGE: "language/blank_default_code",  # stored as an ISO 639-1 (alpha2) code
    KEY_CALIBRE_DIR: "calibre/install_dir",
    KEY_SIGIL_PATH: "sigil/exe_path",
    KEY_OPENLIBRARY_DB: "openlibrary/database",
    KEY_OPENLIBRARY_EDITIONS: "openlibrary/editions_dump",
    KEY_OPENLIBRARY_AUTHORS: "openlibrary/authors_dump",
    KEY_OPENLIBRARY_WORKS: "openlibrary/works_dump",
    KEY_ISFDB_DB: "isfdb/database",
    KEY_ISFDB_BACKUP: "isfdb/backup",
}


def build_sections() -> list[PrefSection]:
    """The dialog's pages, in order. The language list is the app's own
    (defaults minus hidden ones, plus custom languages)."""
    languages = tuple(app_settings.load_languages())
    tools = PrefSection(
        "tools", "Tools and Paths",
        (
            PrefSpec(
                KEY_CALIBRE_DIR, "Calibre folder", "path", "", path_mode="folder",
                help="The folder that holds Calibre's ebook-convert and ebook-polish. Leave empty to "
                     "look for it automatically.",
            ),
            PrefSpec(
                KEY_SIGIL_PATH, "Sigil program", "path", "", path_mode="file",
                help="The Sigil program file, used by Open in Sigil. Leave empty to look for it "
                     "automatically.",
            ),
            PrefSpec(
                KEY_OPENLIBRARY_DB, "Open Library database", "path", "", path_mode="file",
                help="The offline Open Library lookup database. Build it with Tools > Open Library "
                     "Database.",
            ),
            PrefSpec(
                KEY_OPENLIBRARY_EDITIONS, "Open Library editions dump", "path", "", path_mode="file",
                help="The dump the database is built from (kept for the next rebuild).",
            ),
            PrefSpec(
                KEY_OPENLIBRARY_AUTHORS, "Open Library authors dump", "path", "", path_mode="file",
                help="The authors dump used when building the database.",
            ),
            PrefSpec(
                KEY_OPENLIBRARY_WORKS, "Open Library works dump (optional)", "path", "", path_mode="file",
                help="Optional: adds authors to editions that list none themselves. Leave empty to skip.",
            ),
            PrefSpec(
                KEY_ISFDB_DB, "ISFDB database", "path", "", path_mode="file",
                help="The offline ISFDB lookup database (series and series numbers). Build it with "
                     "Tools > ISFDB Database.",
            ),
            PrefSpec(
                KEY_ISFDB_BACKUP, "ISFDB backup", "path", "", path_mode="file",
                help="The ISFDB MySQL backup the database is built from (kept for the next rebuild).",
            ),
        ),
        "Where the optional outside tools and databases live.",
    )
    return [
        filenames_section(auto_number=False),
        language_section(
            style="alpha2", include_enabled=True, default_code=app_settings.DEFAULT_BLANK_LANGUAGE_CODE,
            overrides={KEY_DEFAULT_LANGUAGE: {"choices": languages}},
        ),
        tools,
    ]


def make_backend() -> CallbackBackend:
    def _get(key: str):
        return app_settings.raw_setting(INI_KEYS[key])

    def _set(values: dict) -> None:
        app_settings.write_settings({INI_KEYS[key]: value for key, value in values.items()})

    return CallbackBackend(_get, _set)


def make_dialog(parent=None) -> PreferencesDialog:
    return PreferencesDialog(build_sections(), make_backend(), parent)
