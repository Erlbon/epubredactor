"""
core/conversion_safety.py

The shared conversion policy (redactor_common.core.conversion_policy) for this app, and what happens to the ORIGINAL
e-book after Calibre has converted it to EPUB.

Before the policy existed the app never touched an original: the EPUB was written beside the source under a unique
name and the source stayed where it was. So the never-saved policy (legacy_policy) is: on_open ASK, originals KEEP,
no dry run. Nothing changes until the owner saves Preferences > Conversion.

  KEEP        the original stays (the result has a different extension, so this is always possible).
  QUARANTINE  the original is moved to "converted originals <date>" (inside the set quarantine folder, else beside the
              file) and a TSV undo log gets one line per change, written right after the change succeeded:
                  new_path<TAB>old_path     a move
                  path<TAB>CREATED          a new file
  RECYCLE     the original goes to the Recycle Bin (redactor_common.core.trash.move_to_trash).

Only a VERIFIED result (a non-empty, valid EPUB zip) ever touches an original, and a file modified in the last
`recent_minutes` is left alone. Media is never deleted outright. Qt-free.
"""

from __future__ import annotations

import os
import shutil
import time
import zipfile
from dataclasses import dataclass
from datetime import date
from typing import Callable

from redactor_common.core import conversion_policy as policy_mod
from redactor_common.core.trash import move_to_trash

KIND_CONVERTED = "converted originals"
UNDO_CREATED = "CREATED"

Get = Callable[[str, str, str], str]
Put = Callable[[str, str, str], None]


def legacy_policy() -> policy_mod.ConversionPolicy:
    """What the policy is for a user who never saved the page: what the app always did."""
    return policy_mod.ConversionPolicy(
        on_open=policy_mod.ON_OPEN_ASK, originals=policy_mod.ORIGINALS_KEEP, quarantine_folder="", undo_log_folder="",
        recent_minutes=policy_mod.DEFAULT_RECENT_MINUTES, dry_run_first=False,
    )


def _ini_get(section: str, key: str, default: str) -> str:
    from gui import app_settings
    value = app_settings.raw_setting(f"{section}/{key}")
    return default if value is None else str(value)


def _ini_put(section: str, key: str, value: str) -> None:
    from gui import app_settings
    app_settings.write_settings({f"{section}/{key}": value})


def get_policy(get: Get | None = None) -> policy_mod.ConversionPolicy:
    return policy_mod.load_policy(get or _ini_get, legacy_policy())


def save_policy(policy: policy_mod.ConversionPolicy, put: Put | None = None) -> None:
    policy_mod.save_policy(policy, put or _ini_put)


# --- verifying and settling ---------------------------------------------------------------------------------------


def verify_epub(path: str) -> str:
    """"" when `path` is a non-empty, readable EPUB zip, else the reason it is not."""
    try:
        if os.path.getsize(path) <= 0:
            return "the converted file is empty"
        with zipfile.ZipFile(path) as zf:
            if zf.testzip() is not None:
                return "the converted file is a damaged zip"
            names = set(zf.namelist())
        if "META-INF/container.xml" not in names:
            return "the converted file is not an EPUB (no META-INF/container.xml)"
    except (OSError, zipfile.BadZipFile) as exc:
        return f"the converted file cannot be opened: {exc}"
    return ""


@dataclass
class Outcome:
    source: str
    result: str
    action: str  # "kept" | "quarantined" | "recycled" | "failed"
    destination: str = ""  # the quarantined path
    note: str = ""

    def line(self) -> str:
        name = os.path.basename(self.source)
        if self.action == "quarantined":
            return f"{name}: converted; original moved to {self.destination}"
        if self.action == "recycled":
            return f"{name}: converted; original sent to the Recycle Bin"
        if self.action == "failed":
            return f"{name}: converted; original NOT touched ({self.note})"
        return f"{name}: converted; original kept" + (f" ({self.note})" if self.note else "")


def quarantine_dir(source: str, policy: policy_mod.ConversionPolicy, today: date | None = None) -> str:
    base = policy.quarantine_folder or os.path.dirname(os.path.abspath(source))
    return os.path.join(base, f"{KIND_CONVERTED} {(today or date.today()).isoformat()}")


def undo_log_path(source: str, policy: policy_mod.ConversionPolicy, today: date | None = None) -> str:
    folder = quarantine_dir(source, policy, today)
    parent = policy.undo_log_folder or os.path.dirname(folder)
    return os.path.join(parent, os.path.basename(folder) + " undo log.tsv")


def _unique(path: str) -> str:
    stem, ext = os.path.splitext(path)
    candidate, n = path, 2
    while os.path.exists(candidate):
        candidate = f"{stem} ({n}){ext}"
        n += 1
    return candidate


def _log(path: str, new: str, old: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="") as f:
        f.write(f"{new}\t{old}\n")


def _too_recent(source: str, minutes: int) -> bool:
    try:
        return minutes > 0 and time.time() - os.path.getmtime(source) < minutes * 60
    except OSError:
        return False


def settle_original(
    source: str, result: str, policy: policy_mod.ConversionPolicy, dry_run: bool = False,
    trash: Callable[[str], None] = move_to_trash, today: date | None = None,
) -> Outcome:
    """Applies policy.originals to `source` after `result` was written. With `dry_run` nothing is touched; the Outcome
    says what WOULD happen (in a dry run `result` need not exist). A result that fails verification leaves the
    original alone."""
    mode = policy.originals
    if mode == policy_mod.ORIGINALS_KEEP:
        return Outcome(source, result, "kept")
    if not dry_run:
        problem = verify_epub(result)
        if problem:
            return Outcome(source, result, "failed", note=problem)
    if _too_recent(source, policy.recent_minutes):
        return Outcome(source, result, "kept", note=f"modified in the last {policy.recent_minutes} minutes")
    if mode == policy_mod.ORIGINALS_RECYCLE:
        if not dry_run:
            try:
                trash(source)
            except Exception as exc:  # noqa: BLE001 - whatever the Recycle Bin says, the original is still there
                return Outcome(source, result, "failed", note=f"Recycle Bin: {exc}")
        return Outcome(source, result, "recycled")
    folder = quarantine_dir(source, policy, today)
    destination = _unique(os.path.join(folder, os.path.basename(source)))
    if not dry_run:
        log = undo_log_path(source, policy, today)
        try:
            os.makedirs(folder, exist_ok=True)
            shutil.move(source, destination)
            _log(log, destination, source)
            _log(log, result, UNDO_CREATED)
        except OSError as exc:
            return Outcome(source, result, "failed", destination=destination, note=str(exc))
    return Outcome(source, result, "quarantined", destination=destination)
