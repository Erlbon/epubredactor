"""
core/app_paths.py

Where this app's persistent, non-bundled files live -- the settings
ini, the crash log and the perf log -- via redactor_common.core.
app_paths (2026-09-23): next to the real executable when frozen, the
project root when running from source. Deliberately not sys._MEIPASS
(a one-file build's temp extraction folder, recreated every launch).
This project's own root is passed in, since the shared package lives
in site-packages.

Pure logic, no Qt dependency -- importable before QApplication exists.
"""

from __future__ import annotations

import os

from redactor_common.core import app_paths as _shared

APP_SLUG = "epubredactor"
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def base_dir() -> str:
    return str(_shared.base_dir(PROJECT_ROOT))


def asset_path(*parts: str) -> str:
    """A bundled read-only asset (icon, README) -- sys._MEIPASS when frozen."""
    return str(_shared.asset_path(os.path.join(*parts), PROJECT_ROOT))
