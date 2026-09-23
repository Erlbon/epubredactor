"""
core/crash_log.py

Global crash logging via redactor_common.core.crash_log (promoted from
this file, 2026-09-23): an excepthook appending a full timestamped
traceback to epubredactor_crash.log next to the settings file (see
core.app_paths.base_dir()), plus faulthandler for native crashes inside
Qt's own C++ code, which sys.excepthook never sees.

Kept as a thin wrapper with this module's original names; MAX_LOG_BYTES
and write_crash_entry are read at call time so they stay patchable.
"""

from __future__ import annotations

import os

from redactor_common.core import crash_log as _shared

from core.app_paths import base_dir

LOG_FILENAME = "epubredactor_crash.log"
MAX_LOG_BYTES = _shared.MAX_LOG_BYTES
format_crash_entry = _shared.format_crash_entry


def log_path() -> str:
    return os.path.join(base_dir(), LOG_FILENAME)


def _trim_if_oversized(path: str) -> None:
    _shared.trim_if_oversized(path, MAX_LOG_BYTES)


def write_crash_entry(exc_type, exc_value, exc_tb, path: str | None = None) -> None:
    """Appends one crash entry; never raises. `path` defaults to
    log_path() but is injectable for testing."""
    _shared.write_crash_entry(exc_type, exc_value, exc_tb, path or log_path(), MAX_LOG_BYTES)


def install(also_call=None, faulthandler_path: str | None = None) -> None:
    """Installs the global hook (see redactor_common.core.crash_log).
    `faulthandler_path` is injectable for testing so the real log isn't
    touched."""
    _shared.install(
        faulthandler_path or log_path(),
        also_call=also_call,
        write_entry=lambda *exc: write_crash_entry(*exc),
    )
