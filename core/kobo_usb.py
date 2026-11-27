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
import secrets
import shutil
import string
import sys

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


COPY_CHUNK = 1024 * 1024


class KoboSendCancelled(KoboSendError):
    """The user cancelled while the book was being copied; the partial copy was removed."""


def copy_with_cancel(source_path: str, dest_path: str, cancel=None) -> None:
    """Copies in chunks, checking `cancel` (a threading.Event, or None) between them, then flushes the data to the
    device (fsync) and copies the timestamps. Raises KoboSendCancelled when cancelled."""
    with open(source_path, "rb") as src, open(dest_path, "wb") as dst:
        while True:
            if cancel is not None and cancel.is_set():
                raise KoboSendCancelled("Cancelled.")
            chunk = src.read(COPY_CHUNK)
            if not chunk:
                break
            dst.write(chunk)
        dst.flush()
        os.fsync(dst.fileno())
    try:
        shutil.copystat(source_path, dest_path)
    except OSError:
        pass  # FAT/exFAT may refuse some of it; the book itself is complete


def part_path(dest_path: str) -> str:
    """The name a book is copied under before it gets its real one: `.<8 hex>.part` beside it -- a family temp
    name (redactor_common core/temp_names), and not an e-book extension, so the Kobo never imports a half-copied
    book."""
    folder = os.path.dirname(dest_path)
    while True:
        candidate = os.path.join(folder, f".{secrets.token_hex(4)}.part")
        if not os.path.lexists(candidate):
            return candidate


def send_to_kobo(kobo_root: str, source_path: str, copy_fn=None, replace_existing: bool = True,
                 cancel=None) -> str:
    """Copies source_path onto the Kobo at kobo_root. Kobo scans its
    entire filesystem for supported formats, so there's no required
    destination folder -- files go straight in the root.

    The copy goes to a `.part` name first and is renamed to the book's
    name only when complete, so an unplugged cable or a full device never
    leaves a half-written book for the Kobo to import; the partial file is
    removed on any error or Cancel (`cancel`, a threading.Event).

    A book of the same file name already on the Kobo is replaced when
    `replace_existing` (a re-send of an edited book), else left alone and
    "" is returned (nothing sent). Never "Name (2).epub" duplicates.
    Returns the path written. Raises KoboSendError if the source file
    doesn't exist or the copy fails (KoboSendCancelled on Cancel).
    `copy_fn(src, dst)` replaces the chunked copy (tests)."""
    if not source_path or not os.path.isfile(source_path):
        raise KoboSendError(f"Source file not found: {source_path}")

    dest_path = os.path.join(kobo_root, os.path.basename(source_path))
    if os.path.lexists(dest_path) and not replace_existing:
        return ""
    temp = part_path(dest_path)
    try:
        if copy_fn is None:
            copy_with_cancel(source_path, temp, cancel)
        else:
            copy_fn(source_path, temp)
        if cancel is not None and cancel.is_set():
            raise KoboSendCancelled("Cancelled.")
        os.replace(temp, dest_path)
    except KoboSendError:
        _remove_quietly(temp)
        raise
    except OSError as exc:
        _remove_quietly(temp)
        raise KoboSendError(f"Could not copy to Kobo: {exc}") from exc
    return dest_path


def _remove_quietly(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
