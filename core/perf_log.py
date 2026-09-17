"""
core/perf_log.py

Optional performance-timing log for diagnosing a "this is slow" report
that can't be reproduced with synthetic test data -- e.g. a real,
very large library with real cover images and descriptions, where a
guessed-at synthetic benchmark (random bytes standing in for a real
JPEG, say) can quietly measure the wrong thing entirely (an instant
decode failure instead of a real decode).

Off by default -- even cheap timing calls add real, measurable
overhead across tens of thousands of rows, so this should never be
running for someone who isn't actively diagnosing a slowdown. Enabled
via Settings -> Enable Performance Logging (gui/main_window.py), which
just flips the module-level flag this checks -- no restart needed, so
turning it on right before reproducing a slow operation captures that
exact run.

Writes to the same location as the crash log (see
core.app_paths.base_dir()) -- one block of "<section>: <seconds>s,
<count> calls, <ms>/call avg" lines per Accumulator.dump() call, sorted
by total time descending, so the actual dominant cost is right at the
top rather than something to go hunting for.
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager

from core.app_paths import base_dir

LOG_FILENAME = "epubredactor_perf.log"

# Same reasoning and same cap as crash_log.py: appended to, not
# overwritten, so a pattern across multiple runs stays visible, but
# trimmed from the front once it gets large so it doesn't grow
# unboundedly on a machine that's left this on for a while.
MAX_LOG_BYTES = 2_000_000

_enabled = False


def is_enabled() -> bool:
    return _enabled


def set_enabled(enabled: bool) -> None:
    global _enabled
    _enabled = enabled


def log_path() -> str:
    return os.path.join(base_dir(), LOG_FILENAME)


def _trim_if_oversized(path: str) -> None:
    try:
        if os.path.getsize(path) <= MAX_LOG_BYTES:
            return
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        trimmed = content[-MAX_LOG_BYTES:]
        marker = "=" * 70
        idx = trimmed.find(marker)
        if idx > 0:
            trimmed = trimmed[idx:]
        with open(path, "w", encoding="utf-8") as f:
            f.write(trimmed)
    except OSError:
        pass


def log_block(text: str) -> None:
    """Appends one timestamped block to the perf log, if enabled. Never
    raises -- a failure here (e.g. a read-only install location) must
    never be the reason a real operation fails."""
    if not _enabled:
        return
    try:
        import datetime

        path = log_path()
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"\n{'=' * 70}\n{timestamp}\n{text.rstrip(chr(10))}\n")
        _trim_if_oversized(path)
    except OSError:
        pass


@contextmanager
def timed(label: str):
    """Times the wrapped block on its own, logging "<label>: <seconds>s"
    immediately when performance logging is enabled. A complete no-op
    (not even the time.perf_counter() calls) when disabled. For timing
    something called once (e.g. the whole of _rebuild_table()) -- for
    something called many times in a loop, use Accumulator instead so
    the many individual timings collapse into one summary rather than
    flooding the log with one line per call."""
    if not _enabled:
        yield
        return
    start = time.perf_counter()
    yield
    elapsed = time.perf_counter() - start
    log_block(f"{label}: {elapsed:.3f}s")


class Accumulator:
    """Collects per-section timings across many calls (e.g. once per
    row in a table rebuild) and reports one summary per section instead
    of one log line per call. `section()` is a complete no-op (not even
    the time.perf_counter() calls) when performance logging is
    disabled, so leaving Accumulator.section() calls in permanently
    (rather than needing to add/remove instrumentation to diagnose the
    next slowdown) costs nothing in the common case."""

    def __init__(self):
        self._totals: dict[str, float] = {}
        self._counts: dict[str, int] = {}

    @contextmanager
    def section(self, label: str):
        if not _enabled:
            yield
            return
        start = time.perf_counter()
        yield
        elapsed = time.perf_counter() - start
        self._totals[label] = self._totals.get(label, 0.0) + elapsed
        self._counts[label] = self._counts.get(label, 0) + 1

    def dump(self, title: str) -> None:
        if not _enabled or not self._totals:
            return
        lines = [title]
        for label, total in sorted(self._totals.items(), key=lambda kv: -kv[1]):
            count = self._counts[label]
            per_call = (total / count * 1000) if count else 0.0
            lines.append(f"  {label}: {total:.3f}s total, {count} call(s), {per_call:.4f} ms/call avg")
        log_block("\n".join(lines))
