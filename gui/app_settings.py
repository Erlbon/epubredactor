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
"""

from __future__ import annotations

import json
import os

from core.app_paths import base_dir
from core.languages import DEFAULT_LANGUAGES
from redactor_common.core import managed_list, pattern_history

_SETTINGS_FILENAME = "epubredactor_settings.ini"
_HISTORY_KEY = "rename/pattern_history"
_MAX_HISTORY = 15
_LAST_DIR_KEY = "files/last_directory"
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


def load_pattern_history() -> list[str]:
    """Most-recently-used pattern first."""
    return pattern_history.decode_history(_settings().value(_HISTORY_KEY, "", type=str))


def save_pattern_used(pattern: str) -> None:
    """Record that `pattern` was actually used (e.g. the user clicked
    Apply in the rename dialog with it). Moves it to the front of the
    history if already present, dedupes, and trims to _MAX_HISTORY."""
    history = _dedupe_and_trim(load_pattern_history(), pattern)
    _settings().setValue(_HISTORY_KEY, pattern_history.encode_history(history))


def load_last_pattern(default: str) -> str:
    history = load_pattern_history()
    return history[0] if history else default


# ------------------------------------------------------------------
# Last-used directory (for Add Files / Add Folder dialogs)
# ------------------------------------------------------------------

def load_last_directory() -> str:
    """Returns "" if nothing's been remembered yet, or the remembered
    directory no longer exists (e.g. a removable drive that's unplugged)
    -- callers should treat "" as "let Qt use its own default"."""
    path = _settings().value(_LAST_DIR_KEY, "", type=str)
    return path if path and os.path.isdir(path) else ""


def save_last_directory(path: str) -> None:
    """Remember the directory containing `path` (a file or folder that
    was just added) as the starting point for the next file dialog."""
    directory = path if os.path.isdir(path) else os.path.dirname(path)
    if directory and os.path.isdir(directory):
        _settings().setValue(_LAST_DIR_KEY, directory)


# ------------------------------------------------------------------
# Last working session -- the exact set of files loaded when the app
# was last closed, restored automatically on the next launch. Separate
# from the "last directory" above, which only affects where file
# dialogs open, not what's actually loaded.
# ------------------------------------------------------------------

def _parse_session_files(raw: str) -> list[str]:
    """Pure logic: parse the stored JSON into a list of paths, dropping
    anything malformed rather than failing outright. Split out for
    testability."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [p for p in data if isinstance(p, str) and p.strip()]


def load_last_session_files() -> list[str]:
    """The exact file paths loaded when the app last closed -- an empty
    list if nothing was loaded then, or nothing's ever been saved yet.
    Callers should still check each path actually exists before trying
    to load it (a file can easily have moved or been deleted between
    sessions)."""
    raw = _settings().value(_LAST_SESSION_FILES_KEY, "", type=str)
    return _parse_session_files(raw)


def save_last_session_files(paths: list[str]) -> None:
    """Saves the exact current set of loaded file paths, including an
    empty list if nothing was loaded -- if the last session ended
    empty, the next one should start empty too, not silently resurrect
    an older, no-longer-current session."""
    _settings().setValue(_LAST_SESSION_FILES_KEY, json.dumps(list(paths)))


# ------------------------------------------------------------------
# Languages and genres: built-in defaults (individually hideable --
# excluded from the merged list, not deleted, and restorable) plus any
# custom entries added via the field's "+" picker or Settings ->
# Add/Remove Genres/Languages. The merge/hide/add/remove rules are
# redactor_common.core.managed_list (promoted from here, shared with cbz
# and mp3); only the storage keys live in this file.
# ------------------------------------------------------------------

_merge_languages = managed_list.merge_pairs
_exclude_hidden_languages = managed_list.exclude_hidden_codes
_merge_genres = managed_list.merge_names
_exclude_hidden_genres = managed_list.exclude_hidden_names


def _load_names(key: str) -> list[str]:
    return managed_list.decode_names(_settings().value(key, "", type=str))


def _save_names(key: str, names: list[str]) -> None:
    _settings().setValue(key, managed_list.encode_names(names))


def load_hidden_default_language_codes() -> list[str]:
    return _load_names(_HIDDEN_DEFAULT_LANGUAGES_KEY)


def hide_default_language(code: str) -> None:
    _save_names(_HIDDEN_DEFAULT_LANGUAGES_KEY, managed_list.add_code(load_hidden_default_language_codes(), code))


def restore_default_languages() -> None:
    _save_names(_HIDDEN_DEFAULT_LANGUAGES_KEY, [])


def load_visible_default_languages() -> list[tuple[str, str]]:
    return _exclude_hidden_languages(DEFAULT_LANGUAGES, load_hidden_default_language_codes())


def load_languages() -> list[tuple[str, str]]:
    """Visible (non-hidden) default languages plus any custom ones
    added previously -- what the Language "+" picker shows."""
    return _merge_languages(load_visible_default_languages(), load_custom_languages())


def add_custom_language(code: str, name: str) -> None:
    pairs = managed_list.add_pair(load_custom_languages(), code, name)
    _settings().setValue(_CUSTOM_LANGUAGES_KEY, managed_list.encode_pairs(pairs))


def load_custom_languages() -> list[tuple[str, str]]:
    return managed_list.decode_pairs(_settings().value(_CUSTOM_LANGUAGES_KEY, "", type=str))


def remove_custom_language(code: str) -> None:
    pairs = managed_list.remove_pair(load_custom_languages(), code)
    _settings().setValue(_CUSTOM_LANGUAGES_KEY, managed_list.encode_pairs(pairs))


def load_hidden_default_genres() -> list[str]:
    return _load_names(_HIDDEN_DEFAULT_GENRES_KEY)


def hide_default_genre(genre: str) -> None:
    _save_names(_HIDDEN_DEFAULT_GENRES_KEY, managed_list.add_name(load_hidden_default_genres(), genre))


def restore_default_genres() -> None:
    _save_names(_HIDDEN_DEFAULT_GENRES_KEY, [])


def load_visible_default_genres() -> list[str]:
    """Built-in defaults (COMMON_GENRES) minus any the user has hidden --
    used both by load_genres() and by the Add/Remove Genres dialog."""
    from core.genres import COMMON_GENRES
    return _exclude_hidden_genres(COMMON_GENRES, load_hidden_default_genres())


def load_genres() -> list[str]:
    """Visible (non-hidden) default genres plus any custom ones added
    previously."""
    return _merge_genres(load_visible_default_genres(), load_custom_genres())


def load_custom_genres() -> list[str]:
    return _load_names(_CUSTOM_GENRES_KEY)


def add_custom_genre(genre: str) -> None:
    _save_names(_CUSTOM_GENRES_KEY, managed_list.add_name(load_custom_genres(), genre))


def remove_custom_genre(genre: str) -> None:
    _save_names(_CUSTOM_GENRES_KEY, managed_list.remove_name(load_custom_genres(), genre))


# ------------------------------------------------------------------
# Calibre install folder (both fetch-ebook-metadata and ebook-convert
# are derived from this single location -- see core/calibre_tools.py)
# ------------------------------------------------------------------

def load_calibre_install_dir() -> str:
    """Returns "" if never configured, or if the remembered folder no
    longer exists (e.g. Calibre was moved/reinstalled elsewhere)."""
    path = _settings().value(_CALIBRE_INSTALL_DIR_KEY, "", type=str)
    return path if path and os.path.isdir(path) else ""


def save_calibre_install_dir(path: str) -> None:
    if path and os.path.isdir(path):
        _settings().setValue(_CALIBRE_INSTALL_DIR_KEY, path)


# ------------------------------------------------------------------
# Sigil executable path (see core/sigil_tools.py) -- a single exe path,
# not an install dir, since core.sigil_tools.find_sigil() takes and
# remembers the exe location directly.
# ------------------------------------------------------------------

def load_sigil_path() -> str:
    """Returns "" if never configured, or if the remembered path no
    longer exists (e.g. Sigil was moved/reinstalled elsewhere)."""
    path = _settings().value(_SIGIL_PATH_KEY, "", type=str)
    return path if path and os.path.isfile(path) else ""


def save_sigil_path(path: str) -> None:
    if path and os.path.isfile(path):
        _settings().setValue(_SIGIL_PATH_KEY, path)


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
    raw = _settings().value(_EREADER_SERVERS_KEY, "", type=str)
    if not raw:
        return list(DEFAULT_EREADER_SERVERS)
    try:
        servers = [s for s in json.loads(raw) if isinstance(s, str) and s.strip()]
    except (json.JSONDecodeError, TypeError, ValueError):
        servers = []
    return servers or list(DEFAULT_EREADER_SERVERS)


def add_ereader_server(url: str) -> None:
    servers = _add_server(load_ereader_servers(), url)
    _settings().setValue(_EREADER_SERVERS_KEY, json.dumps(servers))


def remove_ereader_server(url: str) -> None:
    servers = _remove_server(load_ereader_servers(), url)
    _settings().setValue(_EREADER_SERVERS_KEY, json.dumps(servers))


# ------------------------------------------------------------------
# Table column widths -- keyed by logical column index (Path=0,
# Filename=1, Status=2, then each core.fields.FIELDS entry in its fixed
# order), which stays stable across sessions regardless of how columns
# have been visually reordered or hidden.
# ------------------------------------------------------------------

def _parse_column_widths(raw: str) -> dict[int, int]:
    """Pure logic: parse+validate the stored JSON into {logical_index:
    width}, dropping anything malformed rather than failing outright.
    Split out for testability."""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    result = {}
    for key, value in data.items():
        try:
            col = int(key)
            width = int(value)
        except (TypeError, ValueError):
            continue
        if width > 0:
            result[col] = width
    return result


def load_column_widths() -> dict[int, int]:
    """Empty dict if never saved -- callers should fall back to their
    own sensible default (e.g. auto-fit-to-content) in that case."""
    raw = _settings().value(_COLUMN_WIDTHS_KEY, "", type=str)
    return _parse_column_widths(raw)


def save_column_widths(widths: dict[int, int]) -> None:
    _settings().setValue(_COLUMN_WIDTHS_KEY, json.dumps({str(k): v for k, v in widths.items()}))


# ------------------------------------------------------------------
# Table column visibility -- which columns are hidden (Settings ->
# Add/Remove Columns, or the column header's own "Hide" quick action),
# keyed by the same stable logical column index as column widths above.
# ------------------------------------------------------------------

def _parse_hidden_columns(raw: str) -> set[int]:
    """Pure logic: parse+validate the stored JSON into a set of hidden
    logical column indices, dropping anything malformed rather than
    failing outright. Split out for testability."""
    if not raw:
        return set()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return set()
    if not isinstance(data, list):
        return set()
    result = set()
    for value in data:
        try:
            col = int(value)
        except (TypeError, ValueError):
            continue
        if col >= 0:
            result.add(col)
    return result


def load_hidden_columns() -> set[int]:
    """Empty set if never saved (or nothing is hidden) -- every column
    shows by default in that case."""
    raw = _settings().value(_HIDDEN_COLUMNS_KEY, "", type=str)
    return _parse_hidden_columns(raw)


def save_hidden_columns(hidden: set[int]) -> None:
    _settings().setValue(_HIDDEN_COLUMNS_KEY, json.dumps(sorted(hidden)))


# ------------------------------------------------------------------
# Column widths/visibility by FIELD KEY (2026-09-23) -- the index-based
# values above break silently if a column is ever inserted in code (a
# saved "hide column 7" would then hide a different column). Same scheme
# as redactor_common.core.table_settings and the other apps. The first
# load after upgrading migrates the old index-based values once, through
# the caller's current column_keys list (valid: the layout hasn't changed
# since they were saved), and writes them back in the new form.
# ------------------------------------------------------------------

_HIDDEN_COLUMN_KEYS_KEY = "table/hidden_column_keys"
_COLUMN_WIDTHS_BY_KEY_KEY = "table/column_widths_by_key"


def load_hidden_column_keys(column_keys: list[str]) -> set[str]:
    settings = _settings()
    if settings.contains(_HIDDEN_COLUMN_KEYS_KEY):
        return set(managed_list.decode_names(settings.value(_HIDDEN_COLUMN_KEYS_KEY, "", type=str)))
    migrated = {column_keys[i] for i in load_hidden_columns() if 0 <= i < len(column_keys)}
    save_hidden_column_keys(migrated)
    return migrated


def save_hidden_column_keys(hidden: set[str]) -> None:
    _settings().setValue(_HIDDEN_COLUMN_KEYS_KEY, managed_list.encode_names(sorted(hidden)))


def _parse_column_widths_by_key(raw: str) -> dict[str, int]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    result = {}
    for key, value in data.items():
        try:
            width = int(value)
        except (TypeError, ValueError):
            continue
        if isinstance(key, str) and width > 0:
            result[key] = width
    return result


def load_column_widths_by_key(column_keys: list[str]) -> dict[str, int]:
    settings = _settings()
    if settings.contains(_COLUMN_WIDTHS_BY_KEY_KEY):
        return _parse_column_widths_by_key(settings.value(_COLUMN_WIDTHS_BY_KEY_KEY, "", type=str))
    migrated = {column_keys[i]: w for i, w in load_column_widths().items() if 0 <= i < len(column_keys)}
    if migrated:
        save_column_widths_by_key(migrated)
    return migrated


def save_column_widths_by_key(widths: dict[str, int]) -> None:
    _settings().setValue(_COLUMN_WIDTHS_BY_KEY_KEY, json.dumps(widths))


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

def _parse_junk_cover_hashes(raw: str) -> set[str]:
    """Pure logic: parse+validate the stored JSON into a set of cover
    hashes, dropping anything malformed rather than failing outright.
    Split out for testability, same pattern as _parse_hidden_columns."""
    if not raw:
        return set()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return set()
    if not isinstance(data, list):
        return set()
    return {h for h in data if isinstance(h, str) and h}


def load_junk_cover_hashes() -> set[str]:
    raw = _settings().value(_JUNK_COVER_HASHES_KEY, "", type=str)
    return _parse_junk_cover_hashes(raw)


def save_junk_cover_hashes(hashes: set[str]) -> None:
    _settings().setValue(_JUNK_COVER_HASHES_KEY, json.dumps(sorted(hashes)))


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
    mode = _settings().value(_TEXT_OVERFLOW_MODE_KEY, DEFAULT_TEXT_OVERFLOW_MODE, type=str)
    return mode if mode in TEXT_OVERFLOW_MODES else DEFAULT_TEXT_OVERFLOW_MODE


def save_text_overflow_mode(mode: str) -> None:
    if mode in TEXT_OVERFLOW_MODES:
        _settings().setValue(_TEXT_OVERFLOW_MODE_KEY, mode)


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
    return _settings().value(_BLANK_LANGUAGE_DEFAULT_ENABLED_KEY, True, type=bool)


def save_blank_language_default_enabled(enabled: bool) -> None:
    _settings().setValue(_BLANK_LANGUAGE_DEFAULT_ENABLED_KEY, bool(enabled))


def load_blank_language_default_code() -> str:
    code = _settings().value(_BLANK_LANGUAGE_DEFAULT_CODE_KEY, DEFAULT_BLANK_LANGUAGE_CODE, type=str)
    return code.strip() or DEFAULT_BLANK_LANGUAGE_CODE


def save_blank_language_default_code(code: str) -> None:
    code = code.strip()
    if code:
        _settings().setValue(_BLANK_LANGUAGE_DEFAULT_CODE_KEY, code)


# ------------------------------------------------------------------
# Performance logging (Settings -> Enable Performance Logging, see
# core/perf_log.py) -- off by default, persisted across launches so
# turning it on once catches every rebuild in a session, not just the
# next one, and so it stays on across restarts while diagnosing
# something that only shows up on a real, very large library.
# ------------------------------------------------------------------

def load_perf_logging_enabled() -> bool:
    return _settings().value(_PERF_LOGGING_ENABLED_KEY, False, type=bool)


def save_perf_logging_enabled(enabled: bool) -> None:
    _settings().setValue(_PERF_LOGGING_ENABLED_KEY, bool(enabled))
