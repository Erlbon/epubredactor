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


def _dedupe_and_trim(history: list[str], new_pattern: str, max_history: int = _MAX_HISTORY) -> list[str]:
    """Pure logic: move new_pattern to the front of history, deduped,
    trimmed to max_history. Split out from save_pattern_used() so it's
    testable without a live QSettings backend."""
    new_pattern = new_pattern.strip()
    if not new_pattern:
        return history
    result = [p for p in history if p != new_pattern]
    result.insert(0, new_pattern)
    return result[:max_history]


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
    raw = _settings().value(_HISTORY_KEY, "", type=str)
    if not raw:
        return []
    try:
        history = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return [p for p in history if isinstance(p, str) and p.strip()]


def save_pattern_used(pattern: str) -> None:
    """Record that `pattern` was actually used (e.g. the user clicked
    Apply in the rename dialog with it). Moves it to the front of the
    history if already present, dedupes, and trims to _MAX_HISTORY."""
    history = load_pattern_history()
    history = _dedupe_and_trim(history, pattern)
    _settings().setValue(_HISTORY_KEY, json.dumps(history))


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
# Languages: built-in defaults (which can now be individually hidden --
# not deleted, just excluded from the merged list, and restorable) plus
# any custom ones added via the Language field's "+" menu.
# ------------------------------------------------------------------

def _merge_languages(defaults: list[tuple[str, str]], custom: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Pure logic: append custom languages after the defaults, skipping
    any whose code already appears (defaults win on conflict). Split out
    for testability."""
    seen_codes = {code for code, _name in defaults}
    result = list(defaults)
    for code, name in custom:
        code = code.strip()
        name = name.strip()
        if not code or not name or code in seen_codes:
            continue
        seen_codes.add(code)
        result.append((code, name))
    return result


def _exclude_hidden_languages(
    defaults: list[tuple[str, str]], hidden_codes: list[str]
) -> list[tuple[str, str]]:
    """Pure logic: drop any default language whose code is in
    hidden_codes. Split out for testability, same pattern as the merge
    functions elsewhere in this module."""
    hidden = set(hidden_codes)
    return [(code, name) for code, name in defaults if code not in hidden]


def load_hidden_default_language_codes() -> list[str]:
    raw = _settings().value(_HIDDEN_DEFAULT_LANGUAGES_KEY, "", type=str)
    if not raw:
        return []
    try:
        return [c for c in json.loads(raw) if isinstance(c, str)]
    except (json.JSONDecodeError, TypeError, ValueError):
        return []


def hide_default_language(code: str) -> None:
    """Removes a built-in default language from the active list (not a
    deletion of the constant itself -- restore_default_languages() undoes
    this for all hidden defaults at once)."""
    hidden = load_hidden_default_language_codes()
    if code not in hidden:
        hidden.append(code)
    _settings().setValue(_HIDDEN_DEFAULT_LANGUAGES_KEY, json.dumps(hidden))


def restore_default_languages() -> None:
    """Un-hides every previously-hidden default language."""
    _settings().setValue(_HIDDEN_DEFAULT_LANGUAGES_KEY, json.dumps([]))


def load_visible_default_languages() -> list[tuple[str, str]]:
    """Built-in defaults minus any the user has hidden -- used both by
    load_languages() and by the Add/Remove Languages management dialog."""
    return _exclude_hidden_languages(DEFAULT_LANGUAGES, load_hidden_default_language_codes())


def load_languages() -> list[tuple[str, str]]:
    """Visible (non-hidden) default languages plus any custom ones added
    previously."""
    raw = _settings().value(_CUSTOM_LANGUAGES_KEY, "", type=str)
    custom: list[tuple[str, str]] = []
    if raw:
        try:
            custom = [(c, n) for c, n in json.loads(raw)]
        except (json.JSONDecodeError, TypeError, ValueError):
            custom = []
    return _merge_languages(load_visible_default_languages(), custom)


def add_custom_language(code: str, name: str) -> None:
    code = code.strip()
    name = name.strip()
    if not code or not name:
        return
    raw = _settings().value(_CUSTOM_LANGUAGES_KEY, "", type=str)
    try:
        custom = json.loads(raw) if raw else []
    except (json.JSONDecodeError, TypeError):
        custom = []
    custom = [pair for pair in custom if isinstance(pair, list) and pair and pair[0] != code]
    custom.append([code, name])
    _settings().setValue(_CUSTOM_LANGUAGES_KEY, json.dumps(custom))


def load_custom_languages() -> list[tuple[str, str]]:
    """Just the user-added languages (not the built-in defaults) -- used
    by the Add/Remove Languages management dialog, since only these can
    be removed."""
    raw = _settings().value(_CUSTOM_LANGUAGES_KEY, "", type=str)
    if not raw:
        return []
    try:
        return [(c, n) for c, n in json.loads(raw)]
    except (json.JSONDecodeError, TypeError, ValueError):
        return []


def remove_custom_language(code: str) -> None:
    raw = _settings().value(_CUSTOM_LANGUAGES_KEY, "", type=str)
    try:
        custom = json.loads(raw) if raw else []
    except (json.JSONDecodeError, TypeError):
        custom = []
    custom = [pair for pair in custom if isinstance(pair, list) and pair and pair[0] != code]
    _settings().setValue(_CUSTOM_LANGUAGES_KEY, json.dumps(custom))


# ------------------------------------------------------------------
# Genres: built-in defaults (individually hideable/restorable, same as
# languages above) plus any custom genres added via the Genre field's
# "+" menu, or Settings -> Add/Remove Genres.
# ------------------------------------------------------------------

def _merge_genres(defaults: list[str], custom: list[str]) -> list[str]:
    """Pure logic: append custom genres after the defaults, skipping any
    that duplicate a default (case-insensitively). Split out for
    testability, same pattern as _merge_languages above."""
    seen = {g.lower() for g in defaults}
    result = list(defaults)
    for genre in custom:
        genre = genre.strip()
        if not genre or genre.lower() in seen:
            continue
        seen.add(genre.lower())
        result.append(genre)
    return result


def _exclude_hidden_genres(defaults: list[str], hidden: list[str]) -> list[str]:
    """Pure logic: drop any default genre (case-insensitively) that's in
    hidden. Split out for testability."""
    hidden_lower = {g.lower() for g in hidden}
    return [g for g in defaults if g.lower() not in hidden_lower]


def load_hidden_default_genres() -> list[str]:
    raw = _settings().value(_HIDDEN_DEFAULT_GENRES_KEY, "", type=str)
    if not raw:
        return []
    try:
        return [g for g in json.loads(raw) if isinstance(g, str)]
    except (json.JSONDecodeError, TypeError, ValueError):
        return []


def hide_default_genre(genre: str) -> None:
    """Removes a built-in default genre from the active list (not a
    deletion of the constant itself -- restore_default_genres() undoes
    this for all hidden defaults at once)."""
    hidden = load_hidden_default_genres()
    if not any(g.lower() == genre.lower() for g in hidden):
        hidden.append(genre)
    _settings().setValue(_HIDDEN_DEFAULT_GENRES_KEY, json.dumps(hidden))


def restore_default_genres() -> None:
    """Un-hides every previously-hidden default genre."""
    _settings().setValue(_HIDDEN_DEFAULT_GENRES_KEY, json.dumps([]))


def load_visible_default_genres() -> list[str]:
    """Built-in defaults (COMMON_GENRES) minus any the user has hidden --
    used both by load_genres() and by the Add/Remove Genres management
    dialog."""
    from core.genres import COMMON_GENRES
    return _exclude_hidden_genres(COMMON_GENRES, load_hidden_default_genres())


def load_genres() -> list[str]:
    """Visible (non-hidden) default genres plus any custom ones added
    previously."""
    raw = _settings().value(_CUSTOM_GENRES_KEY, "", type=str)
    custom: list[str] = []
    if raw:
        try:
            custom = [g for g in json.loads(raw) if isinstance(g, str)]
        except (json.JSONDecodeError, TypeError, ValueError):
            custom = []
    return _merge_genres(load_visible_default_genres(), custom)


def load_custom_genres() -> list[str]:
    """Just the user-added genres (not the built-in defaults) -- used by
    the Add/Remove Genres management dialog, since only these can be
    removed."""
    raw = _settings().value(_CUSTOM_GENRES_KEY, "", type=str)
    if not raw:
        return []
    try:
        return [g for g in json.loads(raw) if isinstance(g, str)]
    except (json.JSONDecodeError, TypeError, ValueError):
        return []


def add_custom_genre(genre: str) -> None:
    genre = genre.strip()
    if not genre:
        return
    custom = load_custom_genres()
    custom = [g for g in custom if g.lower() != genre.lower()]
    custom.append(genre)
    _settings().setValue(_CUSTOM_GENRES_KEY, json.dumps(custom))


def remove_custom_genre(genre: str) -> None:
    custom = load_custom_genres()
    custom = [g for g in custom if g.lower() != genre.lower()]
    _settings().setValue(_CUSTOM_GENRES_KEY, json.dumps(custom))


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
