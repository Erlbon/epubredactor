"""
core/crash_log.py

Installs a global exception hook that catches any otherwise-unhandled
exception and appends a full timestamped traceback to a log file next
to the settings file (same location -- see core.app_paths.base_dir()),
rather than letting it vanish or bring the whole app down with nothing
to go on afterward.

This matters more for a PyQt app than a plain script: an exception
raised inside a signal/slot doesn't propagate back through Qt's C++
event loop the normal way. Depending on PyQt version and platform, an
uncaught one there can print a traceback and carry on, or silently
disappear, or bring the whole process down -- sys.excepthook is the
one place guaranteed to see it regardless of which of those happens
before the process actually exits.
"""

from __future__ import annotations

import datetime
import faulthandler
import os
import sys
import traceback

from core.app_paths import base_dir

LOG_FILENAME = "epubredactor_crash.log"

# A single log file, not one per run -- appended to, not overwritten,
# so a pattern across multiple crashes (e.g. "always around file N")
# is still visible afterward rather than only ever showing the latest.
# Capped so a machine that crashes repeatedly doesn't grow this
# unboundedly -- old entries are trimmed from the front once exceeded.
MAX_LOG_BYTES = 2_000_000


def log_path() -> str:
    return os.path.join(base_dir(), LOG_FILENAME)


def format_crash_entry(exc_type, exc_value, exc_tb) -> str:
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    return f"\n{'=' * 70}\n{timestamp}\n{tb_text}"


def _trim_if_oversized(path: str) -> None:
    """Keeps the log from growing without bound on a machine that
    crashes repeatedly -- drops entries from the front (oldest first)
    once the file exceeds MAX_LOG_BYTES, keeping the most recent
    activity, which is what's actually useful when diagnosing a fresh
    crash."""
    try:
        if os.path.getsize(path) <= MAX_LOG_BYTES:
            return
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        trimmed = content[-MAX_LOG_BYTES:]
        # Don't start mid-entry -- cut at the first entry separator so
        # what's left still begins cleanly.
        marker = "=" * 70
        idx = trimmed.find(marker)
        if idx > 0:
            trimmed = trimmed[idx:]
        with open(path, "w", encoding="utf-8") as f:
            f.write(trimmed)
    except OSError:
        pass  # trimming is a nice-to-have; never let it block logging itself


def write_crash_entry(exc_type, exc_value, exc_tb, path: str | None = None) -> None:
    """Appends one crash entry to the log file. Never raises -- a
    failure here (e.g. a read-only install location) must not prevent
    whatever else the caller does with the exception (like still
    showing it, or letting the previous exception hook run). `path`
    defaults to log_path() but is injectable for testing."""
    if path is None:
        path = log_path()
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(format_crash_entry(exc_type, exc_value, exc_tb))
        _trim_if_oversized(path)
    except OSError:
        pass


def install(also_call=None, faulthandler_path: str | None = None) -> None:
    """Installs the global hook. `also_call(exc_type, exc_value, exc_tb)`,
    if given, runs after logging (e.g. to show a dialog) -- also never
    allowed to prevent the previous hook (e.g. printing to stderr in a
    console run) from still running afterward.

    Also enables Python's own faulthandler for the same log file (or
    `faulthandler_path`, injectable for testing so this doesn't write to
    the real app's log location every time a test calls install()): a
    Python exception caught via sys.excepthook is only ever half the
    picture -- a genuine native-level crash (a segfault inside Qt's own
    C++ code, for instance) isn't a Python exception at all and
    sys.excepthook never sees it. faulthandler's signal handlers can
    still dump a minimal traceback of what was executing at the moment
    of a crash like that, which is the difference between having no clue
    where a "huge batch of files" crash came from and having a real lead
    on it. Deliberately kept as a best-effort addition, not a
    requirement -- if the log location isn't writable for some reason,
    the app should still launch normally rather than fail over this."""
    try:
        faulthandler.enable(file=open(faulthandler_path or log_path(), "a", encoding="utf-8"))
    except OSError:
        pass

    previous_hook = sys.excepthook

    def _hook(exc_type, exc_value, exc_tb):
        write_crash_entry(exc_type, exc_value, exc_tb)
        if also_call is not None:
            try:
                also_call(exc_type, exc_value, exc_tb)
            except Exception:  # noqa: BLE001 - the crash handler itself must never crash
                pass
        previous_hook(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook
