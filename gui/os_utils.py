"""
gui/os_utils.py

Small shared OS-integration helpers, used from more than one dialog/menu
(the eReader send dialog, and the table's right-click context menu) so
there's exactly one implementation to keep correct across platforms.
"""

from __future__ import annotations

import os
import subprocess
import sys


def reveal_in_file_manager(path: str) -> None:
    """Opens the system file manager showing (ideally selecting) path.
    Best-effort -- silently does nothing if the platform call fails,
    since this is always a convenience, never a core function in
    whatever's calling it."""
    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path)])
    except OSError:
        pass
