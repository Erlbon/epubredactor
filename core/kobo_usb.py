"""
core/kobo_usb.py

Detects a Kobo eReader connected via USB and copies files directly onto
it -- the same mechanism Calibre itself uses for "Send to Device": Kobo
mounts as an ordinary USB drive with a ".kobo" folder at its root, and
placing an EPUB anywhere on that drive is enough for the device to pick
it up on its next library scan. No network, no third-party server, no
API to reverse-engineer -- just a filesystem copy.

Windows enumerates drive letters; Linux and macOS look at the usual
removable-media mount points (see _mount_points()).
"""

from __future__ import annotations

import os
import shutil
import string
import sys

from core.rename_pattern import unique_path

KOBO_MARKER_FOLDER = ".kobo"


class KoboSendError(Exception):
    """Raised for any problem copying a file onto a connected Kobo."""


def _mount_points(listdir_fn=os.listdir, isdir_fn=os.path.isdir) -> list[str]:
    """Candidate mount roots on non-Windows systems: every entry under
    /media/$USER, /run/media/$USER (Linux desktops' automounters) and
    /Volumes (macOS)."""
    if sys.platform == "darwin":
        parents = ["/Volumes"]
    else:
        user = os.environ.get("USER") or os.environ.get("LOGNAME") or ""
        parents = [f"/media/{user}", f"/run/media/{user}"] if user else []
    roots = []
    for parent in parents:
        if not isdir_fn(parent):
            continue
        try:
            names = sorted(listdir_fn(parent))
        except OSError:
            continue
        roots.extend(os.path.join(parent, name) for name in names)
    return roots


def find_connected_kobos(drive_letters=None, isdir_fn=os.path.isdir, mount_points=None) -> list[str]:
    """Returns the root path of every connected Kobo found (usually 0 or
    1, but more than one reader at once is possible). Checks each drive
    letter for the .kobo marker folder every Kobo firmware creates at
    the root of its storage. `drive_letters` and `isdir_fn` are
    injectable so this is testable without a real Windows machine or a
    real Kobo -- see test_kobo_usb.py.

    On Windows (or when `drive_letters` is given) drive letters are
    checked; elsewhere the mount points from _mount_points() (or the
    injected `mount_points`) are."""
    if drive_letters is None and sys.platform != "win32":
        roots = mount_points if mount_points is not None else _mount_points()
        return [root for root in roots if isdir_fn(os.path.join(root, KOBO_MARKER_FOLDER))]
    letters = drive_letters if drive_letters is not None else string.ascii_uppercase
    found = []
    for letter in letters:
        root = f"{letter}:\\"
        # Plain concatenation, not os.path.join -- this is a Windows-style
        # path being deliberately constructed regardless of which OS the
        # code happens to run on, and os.path.join's behavior differs
        # between ntpath and posixpath (posixpath would insert an extra
        # "/" after the trailing backslash rather than treating it as
        # already-separated), which made this untestable outside Windows
        # for no real benefit.
        marker = root + KOBO_MARKER_FOLDER
        if isdir_fn(marker):
            found.append(root)
    return found


def send_to_kobo(kobo_root: str, source_path: str, copy_fn=shutil.copy2) -> str:
    """Copies source_path onto the Kobo at kobo_root. Kobo scans its
    entire filesystem for supported formats, so there's no required
    destination folder -- files go straight in the root, auto-numbered
    on a filename collision (same collision-safe logic as Rename/Export
    and Import to EPUB). Returns the path actually written to. Raises
    KoboSendError if the source file doesn't exist or the copy fails."""
    if not source_path or not os.path.isfile(source_path):
        raise KoboSendError(f"Source file not found: {source_path}")

    stem = os.path.splitext(os.path.basename(source_path))[0]
    ext = os.path.splitext(source_path)[1]
    dest_path = unique_path(kobo_root, stem, ext, set())
    try:
        copy_fn(source_path, dest_path)
    except OSError as exc:
        raise KoboSendError(f"Could not copy to Kobo: {exc}") from exc
    return dest_path
