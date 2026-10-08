"""Scratch folders for the tests that build real files on disk.

The tests used fixed paths such as "/tmp/epub_test_core", which on Windows is
C:\\tmp and was never cleaned up. scratch_dir() hands out a named folder under
ONE per-run temp directory (created with tempfile.mkdtemp) that is removed when
the test process exits, so nothing is left behind and nothing is written to a
fixed location. Used instead of pytest's tmp_path because many tests build
their folders at import time and the test files also run as plain scripts.

Not named test_*.py or test_*() on purpose: pytest must not collect it.
"""
import atexit
import os
import shutil
import tempfile

_base = None


def _cleanup():
    if _base:
        shutil.rmtree(_base, ignore_errors=True)


def scratch_dir(name):
    """Return a fresh-per-process folder `name` inside the run's temp directory, created."""
    global _base
    if _base is None:
        _base = tempfile.mkdtemp(prefix="epubredactor-tests-")
        atexit.register(_cleanup)
    path = os.path.join(_base, name)
    os.makedirs(path, exist_ok=True)
    return path
