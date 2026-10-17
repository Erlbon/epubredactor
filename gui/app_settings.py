"""
gui/app_settings.py

Thin wrapper around QSettings for the small set of things this app needs
to remember across runs: rename/export pattern history, the last folder
used in file/folder dialogs, custom genres/languages, and more. Stored
in a plain .ini file next to the executable (or, in dev mode, at the
project root) -- not the Windows registry (QSettings' default "native"
format there), since that turned out not to reliably persist across an
in-place version upgrade, and a plain file is easier to back up, copy
to a new machine, or inspect directly than registry keys are.

The storage itself is redactor_common's gui/qsettings_store (QSettingsStore
and its managed-list, pattern-history and column stores, shared with
cbzredactor): typed reads that never raise on a hand-edited value. This
file keeps only the app's keys, fallbacks and public load_x()/save_x()
names, so nobody's saved settings move and no caller changes.
"""

from __future__ import annotations

import os

from core.app_paths import base_dir
from core.languages import DEFAULT_LANGUAGES
from redactor_common.core import managed_list, pattern_history
from redactor_common.core import settings_coerce as sc
from redactor_common.gui.qsettings_store import (
    ColumnSettingsStore, ManagedListStore, PatternHistoryStore, QSettingsStore,
)

_SETTINGS_FILENAME = "epubredactor_settings.ini"
_HISTORY_KEY = "rename/pattern_history"
_MAX_HISTORY = 15
_LAST_SESSION_FILES_KEY = "files/last_session_files"
_CUSTOM_LANGUAGES_KEY = "languages/custom"
_HIDDEN_DEFAULT_LANGUAGES_KEY = "languages/hidden_defaults"
_CUSTOM_GENRES_KEY = "genres/custom"
_HIDDEN_DEFAULT_GENRES_KEY = "genres/hidden_defaults"
_CALIBRE_INSTALL_DIR_KEY = "calibre/install_dir"
_SIGIL_PATH_KEY = "sigil/exe_path"
_EREADER_SERVERS_KEY = "ereader/servers"
DEFAULT_EREADER_SERVERS = ["https://send.djazz.se", "https://bookdrop.cc"]
_COLUMN_WIDTHS_KEY = "table/column_widths"
_HIDDEN_COLUMNS_KEY = "table/hidden_columns"
_JUNK_COVER_HASHES_KEY = "covers/junk_hashes"
_TEXT_OVERFLOW_MODE_KEY = "table/text_overflow_mode"
_PERF_LOGGING_ENABLED_KEY = "debug/perf_logging_enabled"


def _dedupe_and_trim(history: list[str], new_pattern: str, max_history: int = _MAX_HISTORY) -> list[str]:
    """Move new_pattern to the front of history, deduped, trimmed --
    redactor_common.core.pattern_history's rule (promoted from here),
    shared by every Redactor app."""
    return pattern_history.dedupe_and_trim(history, new_pattern, max_history)


def _settings_ini_path() -> str:
    """Where the settings file lives -- see core.app_paths.base_dir()
    for the frozen-vs-dev-mode reasoning, shared with the crash logger."""
    return os.path.join(base_dir(), _SETTINGS_FILENAME)


def _settings():
    # Imported lazily so this module's pure logic (_dedupe_and_trim) can
    # be unit-tested in environments without a Qt platform backend.
    from PyQt6.QtCore import QSettings
    return QSettings(_settings_ini_path(), QSettings.Format.IniFormat)


class _Store(QSettingsStore):
    """The shared store, opening its QSettings through this module's
    _settings() (looked up on each call), so a test that points
    _settings or _settings_ini_path somewhere else moves every load/save."""

    def settings(self):
        return _settings()


_STORE = _Store(lambda: _settings_ini_path())
_PATTERNS = PatternHistoryStore(_STORE, _HISTORY_KEY, _MAX_HISTORY)


def _common_genres():
    from core.genres import COMMON_GENRES  # imported lazily, as before
    return COMMON_GENRES


_LANGUAGES = ManagedListStore(_STORE, _CUSTOM_LANGUAGES_KEY, _HIDDEN_DEFAULT_LANGUAGES_KEY, DEFAULT_LANGUAGES, pairs=True)
_GENRES = ManagedListStore(_STORE, _CUSTOM_GENRES_KEY, _HIDDEN_DEFAULT_GENRES_KEY, _common_genres)


def load_pattern_history() -> list[str]:
    """Most-recently-used pattern first."""
    return _PATTERNS.load()


def save_pattern_used(pattern: str) -> None:
    """Record that `pattern` was actually used (e.g. the user clicked
    Apply in the rename dialog with it). Moves it to the front of the
    history if already present, dedupes, and trims to _MAX_HISTORY."""
    _PATTERNS.record(pattern)


def load_last_pattern(default: str) -> str:
    return _PATTERNS.last(default)


# ------------------------------------------------------------------
# Last-used directory (for Open Files / Open Folder dialogs)
# ------------------------------------------------------------------

def load_last_directory() -> str:
    """Returns "" if nothing's been remembered yet, or the remembered
    directory no longer exists (e.g. a removable drive that's unplugged)
    -- callers should treat "" as "let Qt use its own default"."""
    return _STORE.last_directory()


def load_include_subfolders() -> bool:
    """File > Include Subfolders: ON unless the user turned it off (how Open Folder always behaved)."""
    return _STORE.include_subfolders()


def save_include_subfolders(on: bool) -> None:
    _STORE.set_include_subfolders(on)


def save_last_directory(path: str) -> None:
    """Remember the directory containing `path` (a file or folder that
    was just added) as the starting point for the next file dialog."""
    _STORE.remember_directory(path)


# ------------------------------------------------------------------
# Open Folder's "Don't ask again for this folder" on the offer to convert
# other e-book formats (redactor_common's gui/convert_offer): the folders
# the user ticked it for.
# ------------------------------------------------------------------

_CONVERT_OFFER_DECLINED_KEY = "convert_offer/declined_folders"


def load_convert_offer_declined_folders() -> list[str]:
    return _STORE.str_list(_CONVERT_OFFER_DECLINED_KEY, drop_blank=True)


def save_convert_offer_declined_folders(folders: list[str]) -> None:
    _STORE.set_str_list(_CONVERT_OFFER_DECLINED_KEY, folders)


# ------------------------------------------------------------------
# Last working session -- the exact set of files loaded when the app
# was last closed, restored automatically on the next launch. Separate
# from the "last directory" above, which only affects where file
# dialogs open, not what's actually loaded.
# ------------------------------------------------------------------

def _parse_session_files(raw) -> list[str]:
    """The stored JSON as a list of paths, dropping anything malformed
    (non-strings, blanks) rather than failing outright."""
    return sc.parse_str_list(raw, drop_blank=True)


def load_last_session_files() -> list[str]:
    """The exact file paths loaded when the app last closed -- an empty
    list if nothing was loaded then, or nothing's ever been saved yet.
    Callers should still check each path actually exists before trying
    to load it (a file can easily have moved or been deleted between
    sessions)."""
    return _STORE.str_list(_LAST_SESSION_FILES_KEY, drop_blank=True)


def save_last_session_files(paths: list[str]) -> None:
    """Saves the exact current set of loaded file paths, including an
    empty list if nothing was loaded -- if the last session ended
    empty, the next one should start empty too, not silently resurrect
    an older, no-longer-current session."""
    _STORE.set_str_list(_LAST_SESSION_FILES_KEY, paths)


# ------------------------------------------------------------------
# Languages and genres: built-in defaults (individually hideable --
# excluded from the merged list, not deleted, and restorable) plus any
# custom entries added via the field's "+" picker or Settings ->
# Add/Remove Genres/Languages. The merge/hide/add/remove rules are
# redactor_common.core.managed_list, the storage its ManagedListStore;
# only the keys live in this file.
# ------------------------------------------------------------------

_merge_languages = managed_list.merge_pairs
_exclude_hidden_languages = managed_list.exclude_hidden_codes
_merge_genres = managed_list.merge_names
_exclude_hidden_genres = managed_list.exclude_hidden_names


def load_hidden_default_language_codes() -> list[str]:
    return _LANGUAGES.hidden()


def hide_default_language(code: str) -> None:
    _LANGUAGES.hide(code)


def restore_default_languages() -> None:
    _LANGUAGES.restore_defaults()


def load_visible_default_languages() -> list[tuple[str, str]]:
    return _LANGUAGES.visible_defaults()


def load_languages() -> list[tuple[str, str]]:
    """Visible (non-hidden) default languages plus any custom ones
    added previously -- what the Language "+" picker shows."""
    return _LANGUAGES.merged()


def add_custom_language(code: str, name: str) -> None:
    _LANGUAGES.add_custom(code, name)


def load_custom_languages() -> list[tuple[str, str]]:
    return _LANGUAGES.custom()


def remove_custom_language(code: str) -> None:
    _LANGUAGES.remove_custom(code)


def load_hidden_default_genres() -> list[str]:
    return _GENRES.hidden()


def hide_default_genre(genre: str) -> None:
    _GENRES.hide(genre)


def restore_default_genres() -> None:
    _GENRES.restore_defaults()


def load_visible_default_genres() -> list[str]:
    """Built-in defaults (COMMON_GENRES) minus any the user has hidden --
    used both by load_genres() and by the Add/Remove Genres dialog."""
    return _GENRES.visible_defaults()


def load_genres() -> list[str]:
    """Visible (non-hidden) default genres plus any custom ones added
    previously."""
    return _GENRES.merged()


def load_custom_genres() -> list[str]:
    return _GENRES.custom()


def add_custom_genre(genre: str) -> None:
    _GENRES.add_custom(genre)


def remove_custom_genre(genre: str) -> None:
    _GENRES.remove_custom(genre)


# ------------------------------------------------------------------
# Calibre install folder (both fetch-ebook-metadata and ebook-convert
# are derived from this single location -- see core/calibre_tools.py)
# ------------------------------------------------------------------

def load_calibre_install_dir() -> str:
    """Returns "" if never configured, or if the remembered folder no
    longer exists (e.g. Calibre was moved/reinstalled elsewhere)."""
    return _STORE.existing_path(_CALIBRE_INSTALL_DIR_KEY, "dir")


def save_calibre_install_dir(path: str) -> None:
    _STORE.set_existing_path(_CALIBRE_INSTALL_DIR_KEY, path, "dir")


# ------------------------------------------------------------------
# Sigil executable path (see core/sigil_tools.py) -- a single exe path,
# not an install dir, since core.sigil_tools.find_sigil() takes and
# remembers the exe location directly.
# ------------------------------------------------------------------

def load_sigil_path() -> str:
    """Returns "" if never configured, or if the remembered path no
    longer exists (e.g. Sigil was moved/reinstalled elsewhere)."""
    return _STORE.existing_path(_SIGIL_PATH_KEY, "file")


def save_sigil_path(path: str) -> None:
    _STORE.set_existing_path(_SIGIL_PATH_KEY, path, "file")


# ------------------------------------------------------------------
# "Send to eReader" server list (send2ereader-style services -- see
# core/ereader_servers.py and gui/send_to_ereader_dialog.py). A user can
# self-host send2ereader (https://github.com/daniel-j/send2ereader) or
# use a public instance; send.djazz.se ships as a starting suggestion,
# but isn't hardcoded anywhere except as this one default.
# ------------------------------------------------------------------

def _normalize_server_url(url: str) -> str:
    return url.strip().rstrip("/")


def _add_server(servers: list[str], url: str) -> list[str]:
    """Pure logic: add url to servers, replacing any existing entry that
    matches case-insensitively (so re-adding the same server moves it to
    the end rather than duplicating it) and dropping blank input.
    Split out for testability."""
    url = _normalize_server_url(url)
    if not url:
        return list(servers)
    result = [s for s in servers if s.lower() != url.lower()]
    result.append(url)
    return result


def _remove_server(servers: list[str], url: str) -> list[str]:
    """Pure logic: remove url (case-insensitive), never leaving the list
    empty -- falls back to the starting suggestions. Split out for
    testability."""
    result = [s for s in servers if s.lower() != url.strip().lower()]
    return result or list(DEFAULT_EREADER_SERVERS)


def load_ereader_servers() -> list[str]:
    """Configured server URLs, defaulting to the starting suggestions
    (send.djazz.se, bookdrop.cc) if the user hasn't added/removed
    anything yet."""
    return _STORE.str_list(_EREADER_SERVERS_KEY, drop_blank=True) or list(DEFAULT_EREADER_SERVERS)


def add_ereader_server(url: str) -> None:
    _STORE.set_str_list(_EREADER_SERVERS_KEY, _add_server(load_ereader_servers(), url))


def remove_ereader_server(url: str) -> None:
    _STORE.set_str_list(_EREADER_SERVERS_KEY, _remove_server(load_ereader_servers(), url))


# ------------------------------------------------------------------
# Table column widths and hidden columns. The old form is keyed by
# logical column index (Path=0, Filename=1, Status=2, then each
# core.fields.FIELDS entry in its fixed order); since 2026-09-23 they are
# kept by FIELD KEY, because the index-based values break silently if a
# column is ever inserted in code (a saved "hide column 7" would then
# hide a different column). The first load after upgrading migrates the
# old index-based values once, through the caller's current column_keys
# list, and writes them back in the new form (redactor_common's
# ColumnSettingsStore does exactly this for its legacy keys).
# ------------------------------------------------------------------

_HIDDEN_COLUMN_KEYS_KEY = "table/hidden_column_keys"
_COLUMN_WIDTHS_BY_KEY_KEY = "table/column_widths_by_key"

_COLUMN_ORDER_KEY = "table/column_order_by_key"

_COLUMNS = ColumnSettingsStore(
    _STORE, _COLUMN_WIDTHS_BY_KEY_KEY, _HIDDEN_COLUMN_KEYS_KEY, _COLUMN_ORDER_KEY,
    legacy_widths_key=_COLUMN_WIDTHS_KEY, legacy_hidden_key=_HIDDEN_COLUMNS_KEY,
)


def _parse_column_widths(raw) -> dict[int, int]:
    """The old index-keyed widths: {logical_index: width}, malformed
    entries and non-positive widths dropped."""
    return sc.parse_width_map(raw, int_keys=True)


def load_column_widths() -> dict[int, int]:
    """Empty dict if never saved -- callers should fall back to their
    own sensible default (e.g. auto-fit-to-content) in that case."""
    return _STORE.width_map(_COLUMN_WIDTHS_KEY, int_keys=True)


def save_column_widths(widths: dict[int, int]) -> None:
    _STORE.set_width_map(_COLUMN_WIDTHS_KEY, widths)


def _parse_hidden_columns(raw) -> set[int]:
    """The old index-based hidden columns: a set of logical indices,
    malformed and negative entries dropped."""
    return sc.parse_int_set(raw)


def load_hidden_columns() -> set[int]:
    """Empty set if never saved (or nothing is hidden) -- every column
    shows by default in that case."""
    return _STORE.int_set(_HIDDEN_COLUMNS_KEY)


def save_hidden_columns(hidden: set[int]) -> None:
    _STORE.set_int_set(_HIDDEN_COLUMNS_KEY, hidden)


_PATH_COLUMN_SEEDED_KEY = "table/path_column_seeded"


def path_column_seeded() -> bool:
    """True once the one-time un-hiding of the shared Path column has run (redactor_common.core.path_column)."""
    return _STORE.bool_value(_PATH_COLUMN_SEEDED_KEY, False)


def set_path_column_seeded() -> None:
    _STORE.set_bool(_PATH_COLUMN_SEEDED_KEY, True)


def _legacy_index_order(column_keys: list[str]) -> list[str]:
    """The one-time migration of the OLD index-based values maps an index through this list. Those indices were
    written when Path was column 0 and Filename column 1; the table now has them the other way round (2026-10-17,
    the shared Path column goes after Filename), so the first two are swapped back for that mapping only."""
    keys = list(column_keys)
    if keys[:2] == ["filename", "path"]:
        keys[0], keys[1] = keys[1], keys[0]
    return keys


def load_hidden_column_keys(column_keys: list[str]) -> set[str]:
    return _COLUMNS.hidden(_legacy_index_order(column_keys))


def save_hidden_column_keys(hidden: set[str]) -> None:
    _COLUMNS.save_hidden(hidden)


def load_column_order() -> list[str]:
    """The user's left-to-right column order by field key ([] = never moved: the default order)."""
    return _COLUMNS.order()


def save_column_order(order: list[str]) -> None:
    _COLUMNS.save_order(order)


def _parse_column_widths_by_key(raw) -> dict[str, int]:
    return sc.parse_width_map(raw)


def load_column_widths_by_key(column_keys: list[str]) -> dict[str, int]:
    return _COLUMNS.widths(_legacy_index_order(column_keys))


def save_column_widths_by_key(widths: dict[str, int]) -> None:
    _COLUMNS.save_widths(widths)


# ------------------------------------------------------------------
# Junk Cover hashes -- SHA-256 hashes (EpubBook.cover_hash) of cover
# images the user has flagged as junk (Table right-click > Flag Cover
# as Junk). The flag lives on the HASH, not any one book, so it's a
# workspace-wide "this exact cover image is junk" fact rather than a
# per-book setting -- every loaded book sharing that exact cover image
# is flagged too, automatically, on both sides of a load. Not tracked
# by Undo (see MainWindow.flag_selected_covers_as_junk): this isn't an
# edit to a book's own content, just a standing note about a cover
# image, same category of thing as a column width or a custom genre.
# ------------------------------------------------------------------

def _parse_junk_cover_hashes(raw) -> set[str]:
    """The stored JSON as a set of cover hashes, dropping anything
    malformed (non-strings, blanks) rather than failing outright."""
    return {h for h in sc.parse_str_list(raw) if h}


def load_junk_cover_hashes() -> set[str]:
    return _STORE.string_set(_JUNK_COVER_HASHES_KEY)


def save_junk_cover_hashes(hashes: set[str]) -> None:
    _STORE.set_string_set(_JUNK_COVER_HASHES_KEY, hashes)


# ------------------------------------------------------------------
# Table text overflow mode -- how an over-long cell value is displayed
# when its column is too narrow to show it in full (Settings -> Text
# Wrapping). Three modes:
#   "wrap"     -- wrap onto multiple lines, growing the row's height to
#                 fit (the table's row heights are reflowed to match
#                 whenever a column is resized -- see
#                 MainWindow._reflow_table_rows()).
#   "ellipsis" -- single-line rows always; text too long for the column
#                 is truncated with a trailing "…".
#   "clip"     -- single-line rows always; text too long for the column
#                 is hard-clipped at the column edge, no "…" shown.
# "wrap" is the default (matches the app's pre-existing behavior), but
# on its own that behavior is exactly what produced the "wonky line
# height" bug: word-wrap was always on, yet nothing ever re-ran
# resizeRowsToContents() after a column resize, so a row's height could
# be left over/under the text it now had to show. The two single-line
# modes exist for anyone who'd rather never see a row change height at
# all, at the cost of not seeing a wrapped value in full.
# ------------------------------------------------------------------

TEXT_OVERFLOW_MODES = ("wrap", "ellipsis", "clip")
DEFAULT_TEXT_OVERFLOW_MODE = "wrap"


def load_text_overflow_mode() -> str:
    return _STORE.choice(_TEXT_OVERFLOW_MODE_KEY, TEXT_OVERFLOW_MODES, DEFAULT_TEXT_OVERFLOW_MODE)


def save_text_overflow_mode(mode: str) -> None:
    _STORE.set_choice(_TEXT_OVERFLOW_MODE_KEY, mode, TEXT_OVERFLOW_MODES)


# ------------------------------------------------------------------
# Blank/Unknown Language default (Repair -> Set Blank/Unknown Language
# to Default) -- a deliberate exception to this app's usual
# "preview + per-book checkbox before Apply" pattern (see
# core.languages.is_blank_or_unknown_language and MainWindow.
# set_blank_languages_to_default): applies immediately across the
# working set with no review step, so an explicit enable/disable is
# offered here for anyone who doesn't want that risk at all -- e.g. a
# library where a blank language is a deliberate "not yet determined"
# marker, not just an oversight.
# ------------------------------------------------------------------

_BLANK_LANGUAGE_DEFAULT_ENABLED_KEY = "language/blank_default_enabled"
_BLANK_LANGUAGE_DEFAULT_CODE_KEY = "language/blank_default_code"
DEFAULT_BLANK_LANGUAGE_CODE = "en"


def load_blank_language_default_enabled() -> bool:
    return _STORE.bool_value(_BLANK_LANGUAGE_DEFAULT_ENABLED_KEY, True)


def save_blank_language_default_enabled(enabled: bool) -> None:
    _STORE.set_bool(_BLANK_LANGUAGE_DEFAULT_ENABLED_KEY, enabled)


def load_blank_language_default_code() -> str:
    code = _STORE.text(_BLANK_LANGUAGE_DEFAULT_CODE_KEY, DEFAULT_BLANK_LANGUAGE_CODE)
    return code.strip() or DEFAULT_BLANK_LANGUAGE_CODE


def save_blank_language_default_code(code: str) -> None:
    code = code.strip()
    if code:
        _STORE.set(_BLANK_LANGUAGE_DEFAULT_CODE_KEY, code)


# ------------------------------------------------------------------
# Performance logging (Settings -> Enable Performance Logging, see
# core/perf_log.py) -- off by default, persisted across launches so
# turning it on once catches every rebuild in a session, not just the
# next one, and so it stays on across restarts while diagnosing
# something that only shows up on a real, very large library.
# ------------------------------------------------------------------

def load_perf_logging_enabled() -> bool:
    return _STORE.bool_value(_PERF_LOGGING_ENABLED_KEY, False)


def save_perf_logging_enabled(enabled: bool) -> None:
    _STORE.set_bool(_PERF_LOGGING_ENABLED_KEY, enabled)


# ------------------------------------------------------------------
# History (Tools > History, core/history.py) -- OPT-IN, off by default.
# core/history.py reads the same key Qt-free (the command line obeys it).
# ------------------------------------------------------------------

HISTORY_ENABLED_KEY = "history/enabled"


def load_history_enabled() -> bool:
    from core.history import history_enabled
    return history_enabled()


def save_history_enabled(enabled: bool) -> None:
    write_settings({HISTORY_ENABLED_KEY: bool(enabled)})


def load_ascii_filenames() -> bool:
    """Rename/Export by Pattern's "ASCII-safe filenames" checkbox,
    remembered between runs (redactor_common's RenamePatternDialog)."""
    return _STORE.ascii_filenames()


def save_ascii_filenames(enabled: bool) -> None:
    _STORE.set_ascii_filenames(enabled)


def load_rename_zero_pad() -> tuple[bool, int]:
    """File > Rename / Export / Move's zero-pad checkbox and width, remembered
    between runs (redactor_common's RenamePatternDialog)."""
    return _STORE.rename_zero_pad()


def save_rename_zero_pad(enabled: bool, width: int) -> None:
    _STORE.set_rename_zero_pad(enabled, width)


# ------------------------------------------------------------------
# Redact recipe (Edit > Edit Redact Recipe...) -- one-line JSON from
# redactor_common's Recipe. QSettings writes the ini atomically.
# ------------------------------------------------------------------

_REDACT_RECIPE_KEY = "redact/recipe"


def load_redact_recipe() -> str:
    """The saved recipe JSON, or "" (= every step at its default)."""
    return _STORE.text(_REDACT_RECIPE_KEY)


def save_redact_recipe(text: str) -> None:
    _STORE.set(_REDACT_RECIPE_KEY, text)


# ------------------------------------------------------------------
# Library root for the Rename dialog's "Move into folders" mode -- also
# what the Redact recipe's Move into folders step moves under.
# ------------------------------------------------------------------

_LIBRARY_ROOT_KEY = "move/library_root"


def load_library_root() -> str:
    return _STORE.text(_LIBRARY_ROOT_KEY)


def save_library_root(path: str) -> None:
    _STORE.set(_LIBRARY_ROOT_KEY, path)


# ------------------------------------------------------------------
# Open Library local database (Tools > Open Library Database...): the
# built SQLite file (core/openlibrary_import.py), the two dump files it
# was/will be built from, and the build options. All of it is
# machine-specific (paths) except the language choice.
# ------------------------------------------------------------------

_OPEN_LIBRARY_DB_KEY = "openlibrary/database"
_OPEN_LIBRARY_EDITIONS_KEY = "openlibrary/editions_dump"
_OPEN_LIBRARY_AUTHORS_KEY = "openlibrary/authors_dump"
_OPEN_LIBRARY_WORKS_KEY = "openlibrary/works_dump"
_OPEN_LIBRARY_LANGUAGES_KEY = "openlibrary/languages"
_OPEN_LIBRARY_ALL_LANGUAGES_KEY = "openlibrary/all_languages"
_OPEN_LIBRARY_UNKNOWN_LANGUAGE_KEY = "openlibrary/include_unknown_language"


def load_open_library_database() -> str:
    """Path to the built Open Library lookup database, or ""."""
    return _STORE.text(_OPEN_LIBRARY_DB_KEY)


def save_open_library_database(path: str) -> None:
    _STORE.set(_OPEN_LIBRARY_DB_KEY, path or "")


def default_open_library_database_path() -> str:
    """Where a new build is suggested to go: next to the settings."""
    return os.path.join(base_dir(), "openlibrary.db")


def load_open_library_sources() -> tuple[str, str]:
    """(editions dump, authors dump) paths last used for a build, "" if none."""
    return _STORE.text(_OPEN_LIBRARY_EDITIONS_KEY), _STORE.text(_OPEN_LIBRARY_AUTHORS_KEY)


def save_open_library_sources(editions: str, authors: str) -> None:
    _STORE.write_many({_OPEN_LIBRARY_EDITIONS_KEY: editions or "", _OPEN_LIBRARY_AUTHORS_KEY: authors or ""})


def load_open_library_works_dump() -> str:
    """The optional works dump (authors for editions that have none), "" = not used."""
    return _STORE.text(_OPEN_LIBRARY_WORKS_KEY)


def save_open_library_works_dump(path: str) -> None:
    _STORE.set(_OPEN_LIBRARY_WORKS_KEY, path or "")


def load_open_library_build_options():
    """The saved BuildOptions (the user's library languages by default)."""
    from core.openlibrary_import import DEFAULT_LANGUAGE_IDS, LANGUAGE_CHOICES, BuildOptions

    known = {lang_id for lang_id, _label, _codes in LANGUAGE_CHOICES}
    raw = _STORE.raw(_OPEN_LIBRARY_LANGUAGES_KEY)
    if raw is None:
        chosen = DEFAULT_LANGUAGE_IDS
    else:
        chosen = tuple(p for p in str(raw).split(",") if p in known)
    return BuildOptions(
        languages=chosen,
        all_languages=_STORE.bool_value(_OPEN_LIBRARY_ALL_LANGUAGES_KEY, False),
        include_unknown_language=_STORE.bool_value(_OPEN_LIBRARY_UNKNOWN_LANGUAGE_KEY, True),
    )


def save_open_library_build_options(options) -> None:
    _STORE.write_many({
        _OPEN_LIBRARY_LANGUAGES_KEY: ",".join(options.languages),
        _OPEN_LIBRARY_ALL_LANGUAGES_KEY: bool(options.all_languages),
        _OPEN_LIBRARY_UNKNOWN_LANGUAGE_KEY: bool(options.include_unknown_language),
    })


# ------------------------------------------------------------------
# Offline ISFDB database (Tools > ISFDB Database): where the built
# lookup file is and the backup it was built from. Both are paths on
# this computer.
# ------------------------------------------------------------------

_ISFDB_DB_KEY = "isfdb/database"
_ISFDB_BACKUP_KEY = "isfdb/backup"


def load_isfdb_database() -> str:
    """Path to the built ISFDB lookup database, or ""."""
    return _STORE.text(_ISFDB_DB_KEY)


def save_isfdb_database(path: str) -> None:
    _STORE.set(_ISFDB_DB_KEY, path or "")


def default_isfdb_database_path() -> str:
    """Where a new build is suggested to go: next to the settings."""
    return os.path.join(base_dir(), "isfdb.db")


def load_isfdb_backup() -> str:
    """The ISFDB backup (.sql/.zip) last used for a build, "" if none."""
    return _STORE.text(_ISFDB_BACKUP_KEY)


def save_isfdb_backup(path: str) -> None:
    _STORE.set(_ISFDB_BACKUP_KEY, path or "")


# ------------------------------------------------------------------
# Raw access for the Preferences dialog (gui/preferences.py): it maps
# its setting names onto the ini keys above, so the loaders and
# Export/Import keep working on the very same entries.
# ------------------------------------------------------------------

def raw_setting(key: str):
    """The stored value for an ini key, as QSettings returns it (a string
    from an ini), or None when nothing is stored."""
    return _STORE.raw(key)


def write_settings(values: dict) -> None:
    """Stores several ini keys in one go (QSettings writes the file once)."""
    _STORE.write_many(values)
