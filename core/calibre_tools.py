"""
core/calibre_tools.py

Shared logic for locating the user's Calibre installation and deriving
paths to its bundled command-line tools. Both core/calibre_lookup.py
(fetch-ebook-metadata) and core/ebook_convert.py (ebook-convert) use
this, so the user only ever has to point this app at their Calibre
install folder once, not once per tool.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

WINDOWS_INSTALL_DIR_CANDIDATES = [
    r"C:\Program Files\Calibre2",
    r"C:\Program Files (x86)\Calibre2",
]

DOWNLOAD_URL = "https://calibre-ebook.com/download"

# key -> the executable's base name (Windows suffix added where relevant)
TOOL_BASE_NAMES = {
    "fetch-ebook-metadata": "fetch-ebook-metadata",
    "ebook-convert": "ebook-convert",
}


def no_console_window_kwargs() -> dict:
    """Extra subprocess.run() kwargs that suppress the console window
    Windows would otherwise pop up for any console-mode .exe (every one
    of Calibre's CLI tools is one) launched from this windowed GUI app.
    That popup can steal focus entirely from this app -- and if the
    tool errors with a lot of stderr output, the console window fills
    with raw text with no way to reach anything in this app's own
    dialog (including its own Apply button) until the console window is
    manually closed. Shared here since every Calibre subprocess call
    (fetch-ebook-metadata, ebook-convert, ebook-polish) needs it, not
    just one.

    Uses getattr rather than a direct subprocess.CREATE_NO_WINDOW
    reference: that constant is only ever defined on an actual Windows
    Python build, so a direct reference would itself raise
    AttributeError if this function is ever exercised on a non-Windows
    interpreter (e.g. under a sys.platform test mock) -- this way it's a
    harmless no-op there instead, same as it already is on any genuinely
    non-Windows platform."""
    if sys.platform == "win32":
        flag = getattr(subprocess, "CREATE_NO_WINDOW", None)
        if flag is not None:
            return {"creationflags": flag}
    return {}


def _exe_name(base_name: str) -> str:
    return base_name if base_name.lower().endswith(".exe") else f"{base_name}.exe"


def _candidate_install_dirs(extra_dirs: list[str] | None = None) -> list[str]:
    dirs = list(extra_dirs or [])
    dirs += list(WINDOWS_INSTALL_DIR_CANDIDATES)
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    if local_appdata:
        dirs.append(os.path.join(local_appdata, "Programs", "Calibre2"))
    return dirs


def find_tool(
    tool_key: str,
    configured_install_dir: str = "",
    which_fn=shutil.which,
    extra_install_dirs: list[str] | None = None,
) -> str | None:
    """Locate a specific Calibre CLI tool by key ("fetch-ebook-metadata"
    or "ebook-convert"). Tries, in order: the configured install
    directory, PATH, then common Windows install locations."""
    base_name = TOOL_BASE_NAMES.get(tool_key, tool_key)
    exe_name = _exe_name(base_name)

    if configured_install_dir:
        candidate = os.path.join(configured_install_dir, exe_name)
        if os.path.isfile(candidate):
            return candidate

    found = which_fn(base_name) or which_fn(exe_name)
    if found:
        return found

    for install_dir in _candidate_install_dirs(extra_install_dirs):
        candidate = os.path.join(install_dir, exe_name)
        if os.path.isfile(candidate):
            return candidate
    return None


def find_install_dir(
    configured_install_dir: str = "",
    which_fn=shutil.which,
    extra_install_dirs: list[str] | None = None,
) -> str | None:
    """Best-effort: locate Calibre's install directory itself, by finding
    any one of its known tools and taking its parent folder. Used by the
    "locate Calibre" GUI flow, which lets the user point at the install
    folder once rather than each tool individually."""
    for tool_key in TOOL_BASE_NAMES:
        found = find_tool(tool_key, configured_install_dir, which_fn, extra_install_dirs)
        if found:
            return os.path.dirname(found)
    return None
