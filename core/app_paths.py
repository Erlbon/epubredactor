"""
core/app_paths.py

Where this app's persistent, non-bundled files live -- the settings
ini and the crash log both need the same answer: next to the real
executable when frozen (an installed .exe), or the project root when
running from source. Deliberately not sys._MEIPASS for a frozen
one-file PyInstaller build: that's a temporary extraction directory
recreated fresh on every single launch, not a stable place to keep
anything meant to persist between runs.

Pure logic, no Qt dependency -- so it can be imported as early as
possible (before QApplication even exists) by the crash logger, and
reused by gui/app_settings.py for the same answer rather than each
computing it separately.
"""

from __future__ import annotations

import os
import sys


def base_dir() -> str:
    """This file lives one level inside the project root (in core/),
    same as gui/app_settings.py lives one level inside it (in gui/) --
    so the same two-dirname walk up from THIS file's own location
    lands on the project root correctly in dev mode either way."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
