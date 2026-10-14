"""
core/history.py

The operations journal for this app (redactor_common.core.journal): every tag change written into an EPUB
(plain Save, Save All, a Save As Copy that overwrites a file, the command line, Redact, a metadata change made
by Calibre Polish, and Restore itself) is recorded with the old and new text of each changed field, so an
unwanted change can be undone from Tools > History after the app was closed.

Only the text fields are kept (core/fields.py, under their display labels). Covers and other binary data are
not: a changed cover is noted as such. A very long description is cut by the journal and marked as not
restorable. Replaced or converted files are covered by the Recycle Bin, not by this.

OPT-IN (owner decision 2026-10-14): nothing is recorded, and no journal file is created, unless the user turned
it on (Tools > Preferences > History, or Yes on Tools > History's question). The setting is the ini key
history/enabled in the app's settings file; it is read here without Qt, so the command line obeys it too.
A missing or garbled value counts as off.

Qt-free. apply_restore() runs on a worker thread (the History dialog's progress dialog), so it touches no
widgets, and it does not write a journal entry itself: the dialog records the restore.
"""

from __future__ import annotations

import os
import sys
import threading
from typing import Callable, Mapping

from redactor_common.core.journal import (
    KIND_REDACT,
    KIND_RESTORE,
    KIND_SAVE,
    Journal,
    default_journal_path,
    diff_fields,
)

from core.app_paths import APP_SLUG, base_dir
from core.fields import FIELDS

__all__ = [
    "KIND_REDACT", "KIND_RESTORE", "KIND_SAVE", "apply_restore", "begin", "delete_journal", "fields_text",
    "finish", "get_journal", "history_enabled", "journal_exists", "journal_path", "set_journal", "take_notice",
]

SETTINGS_FILENAME = "epubredactor_settings.ini"  # the same file gui/app_settings.py writes through QSettings
ENABLED_SECTION, ENABLED_OPTION = "history", "enabled"
ENABLED_KEY = f"{ENABLED_SECTION}/{ENABLED_OPTION}"
_TRUE = {"1", "true", "yes", "on"}

# (path, mtime_ns, size) -> enabled: a Save All of thousands of books re-reads the ini only when it changed.
_enabled_cache: tuple[tuple[str, int, int], bool] | None = None


def _settings_ini_path() -> str:
    return os.path.join(base_dir(), SETTINGS_FILENAME)


def history_enabled() -> bool:
    """Whether the user turned the history on (off by default; missing, unreadable or garbled = off)."""
    global _enabled_cache
    path = _settings_ini_path()
    try:
        st = os.stat(path)
    except OSError:
        return False
    stamp = (path, st.st_mtime_ns, st.st_size)
    cached = _enabled_cache
    if cached is not None and cached[0] == stamp:
        return cached[1]
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            enabled = _read_enabled(f)
    except OSError:
        enabled = False
    _enabled_cache = (stamp, enabled)
    return enabled


def _read_enabled(lines) -> bool:
    """[history] enabled=true in a QSettings ini, read line by line: any other odd line in the file (QSettings
    writes @Variant(...) values, escaped keys) is simply skipped, never a reason to read the whole file as off."""
    section = ""
    value = ""
    for raw in lines:
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            continue
        if section != ENABLED_SECTION or "=" not in line:
            continue
        key, _sep, text = line.partition("=")
        if key.strip().lower() == ENABLED_OPTION:
            value = text  # the last one wins, as in QSettings
    return value.strip().strip('"').strip().lower() in _TRUE


def journal_exists() -> bool:
    return os.path.isfile(get_journal().path)


def delete_journal(trash: Callable[[str], object] | None = None) -> str:
    """Removes the journal file (to the Recycle Bin by default, the family's standing rule). Returns "" or a
    plain-language problem. Nothing to delete is not a problem."""
    path = get_journal().path
    if not os.path.isfile(path):
        return ""
    if trash is None:
        from redactor_common.core.trash import move_to_trash as trash
    with _lock:
        try:
            trash(path)
        except Exception as exc:  # noqa: BLE001 - shown to the user
            return f"the history file could not be deleted ({exc})"
    return ""

# display label -> EpubMetadata attribute (or its "; "-joined string view)
LABEL_TO_KEY: dict[str, str] = {label: key for key, label, _multiline in FIELDS}

_lock = threading.Lock()
_journal: Journal | None = None
_warned = False
_notice = ""


def journal_path() -> str:
    """Next to the settings ini, crash log and perf log (core/app_paths.base_dir)."""
    return default_journal_path(APP_SLUG, base_dir())


def get_journal() -> Journal:
    """The process-wide journal, created on first use."""
    global _journal
    with _lock:
        if _journal is None:
            _journal = Journal(journal_path())
        return _journal


def set_journal(journal: Journal | None) -> None:
    """Points the app at another journal (tests: one under tmp_path); None goes back to the default."""
    global _journal, _warned, _notice
    with _lock:
        _journal = journal
        _warned = False
        _notice = ""


def fields_text(book_or_metadata) -> dict[str, str]:
    """{display label: plain text} for every editable metadata field. No covers, no technical fields."""
    metadata = getattr(book_or_metadata, "metadata", book_or_metadata)
    values = metadata.as_dict()
    return {label: str(values.get(key) or "").strip() for key, label, _multiline in FIELDS}


def _problem(action: str, exc: BaseException) -> None:
    """A journal failure never blocks or fails a save: said once on stderr, and once to the GUI
    (take_notice) for its status bar."""
    global _warned, _notice
    with _lock:
        if _warned:
            return
        _warned = True
        _notice = f"The History journal could not be written ({exc}); saving goes on without it."
    try:
        print(f"epubredactor: history journal {action} failed: {exc}", file=sys.stderr)
    except Exception:  # noqa: BLE001 - no console (windowed exe)
        pass


def take_notice() -> str:
    """The pending journal problem message (once), or ""."""
    global _notice
    with _lock:
        notice, _notice = _notice, ""
    return notice


def begin(
    path: str, kind: str, old: Mapping[str, str] | None, new: Mapping[str, str], *,
    cover_changed: bool = False, note: str = "",
) -> str | None:
    """Announces a write of `path` with the fields that differ between `old` and `new`. None when nothing
    changed, the old values are unknown, or the journal could not be written."""
    if old is None or not history_enabled():
        return None  # history off (the default): nothing is written and no journal file is created
    changes = diff_fields(old, new)
    if not changes and not cover_changed:
        return None
    try:
        return get_journal().begin(path, kind, changes, cover_changed=cover_changed, note=note)
    except Exception as exc:  # noqa: BLE001 - see _problem
        _problem("write", exc)
        return None


def finish(entry_id: str | None, ok: bool = True, error: str = "") -> None:
    if entry_id is None:
        return
    try:
        get_journal().finish(entry_id, ok, error)
    except Exception as exc:  # noqa: BLE001 - see _problem
        _problem("write", exc)


def record(path: str, kind: str, old: Mapping[str, str] | None, new: Mapping[str, str], **kwargs) -> str | None:
    """begin() + finish() for a change something else already made (Calibre Polish)."""
    entry_id = begin(path, kind, old, new, **kwargs)
    finish(entry_id)
    return entry_id


def apply_restore(path: str, values: Mapping[str, str]) -> str:
    """Writes {field label: text} into the EPUB at `path`: loads its CURRENT metadata, sets the given fields,
    saves through EpubBook.save (temp file + atomic replace) without journaling, then reads the file back and
    checks the fields. Returns "" or a plain-language problem. Runs on a worker thread: no widgets."""
    from core.epub_metadata import EpubBook, EpubError  # here: epub_metadata imports this module

    unknown = [label for label in values if label not in LABEL_TO_KEY]
    if unknown:
        return f"this program does not know the field(s) {', '.join(unknown)}"
    try:
        book = EpubBook(path)
    except Exception as exc:  # noqa: BLE001
        return f"the file could not be read ({exc})"
    if book.load_error:
        return f"the file could not be read ({book.load_error})"
    if any(i.code == "DRM_DETECTED" for i in book.validation_issues):
        return "the file is DRM-protected and is left untouched"
    book.apply_metadata({LABEL_TO_KEY[label]: text for label, text in values.items()})
    try:
        book.save(journal_kind=None)
    except (EpubError, OSError) as exc:
        return f"the file could not be written ({exc})"
    except Exception as exc:  # noqa: BLE001
        return f"the file could not be written ({exc})"
    try:
        check = EpubBook(path)
    except Exception as exc:  # noqa: BLE001
        return f"the file was written but does not open again ({exc})"
    if check.load_error:
        return f"the file was written but does not open again ({check.load_error})"
    now = fields_text(check)
    wrong = [label for label, text in values.items() if now.get(label, "") != str(text or "").strip()]
    if wrong:
        return f"the file was written, but {', '.join(wrong)} did not read back as restored"
    return ""
