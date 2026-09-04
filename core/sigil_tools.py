"""
core/sigil_tools.py

Locates the user's Sigil (https://sigil-ebook.com) installation and
launches it to open a specific EPUB file. Sigil is a free, open-source
(GPLv3) standalone EPUB editor -- unlike Calibre's own CLI tools, it's
not something this app shells out to and parses output from; it's an
interactive GUI app this app hands a file to and steps out of the way
of. Since it's GPLv3 too, launching it as a separate process (never
linking or embedding it) is the same safe boundary already used for
Calibre -- see core/calibre_lookup.py's module docstring for the fuller
licensing/security/maintenance reasoning, which applies equally here.
"""

from __future__ import annotations

import os
import shutil
import subprocess

DOWNLOAD_URL = "https://sigil-ebook.com/sigil/download/"

WINDOWS_INSTALL_DIR_CANDIDATES = [
    r"C:\Program Files\Sigil",
    r"C:\Program Files (x86)\Sigil",
]

_EXE_NAME = "sigil.exe"


class SigilLaunchError(Exception):
    """Raised if Sigil can't be located or launched."""


def find_sigil(configured_path: str = "", which_fn=shutil.which) -> str | None:
    """Locate the Sigil executable. Tries, in order: a previously
    configured/remembered path, PATH, then common Windows install
    locations. Mirrors core/calibre_tools.find_tool()'s approach, kept
    as a separate small function here rather than folded into that
    module -- Sigil isn't part of a Calibre install, it has its own
    entirely separate install location and versioning."""
    if configured_path and os.path.isfile(configured_path):
        return configured_path

    found = which_fn("sigil") or which_fn(_EXE_NAME)
    if found:
        return found

    for install_dir in WINDOWS_INSTALL_DIR_CANDIDATES:
        candidate = os.path.join(install_dir, _EXE_NAME)
        if os.path.isfile(candidate):
            return candidate
    return None


def open_in_sigil(sigil_path: str, epub_path: str, popen_fn=subprocess.Popen) -> None:
    """Launches Sigil pointed at epub_path. Fire-and-forget -- Sigil is
    an interactive GUI app, so there's no output to capture and nothing
    further for this app to do once it's launched. Raises
    SigilLaunchError if either path doesn't exist, or the launch itself
    fails."""
    if not sigil_path or not os.path.isfile(sigil_path):
        raise SigilLaunchError(f"Sigil executable not found: {sigil_path}")
    if not epub_path or not os.path.isfile(epub_path):
        raise SigilLaunchError(f"Book file not found: {epub_path}")
    try:
        popen_fn([sigil_path, epub_path])
    except OSError as exc:
        raise SigilLaunchError(f"Could not launch Sigil: {exc}") from exc
