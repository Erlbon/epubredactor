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
import time

from redactor_common.core.subprocess_utils import no_window_kwargs
from redactor_common.core.tool_locator import find_tool as _shared_find_tool
from redactor_common.core.tool_locator import windows_program_dirs

# Well-known install folders, checked after PATH (Calibre's installer
# doesn't always put itself on PATH). Resolved from %ProgramFiles% etc.
# by redactor_common's windows_program_dirs(); empty off Windows.
def _default_install_dirs() -> list[str]:
    """Tests patch this to isolate from a real Calibre install."""
    return [str(d) for d in windows_program_dirs("Calibre2")]


DOWNLOAD_URL = "https://calibre-ebook.com/download"

# key -> the executable's base name (Windows suffix added where relevant)
TOOL_BASE_NAMES = {
    "fetch-ebook-metadata": "fetch-ebook-metadata",
    "ebook-convert": "ebook-convert",
}


def no_console_window_kwargs() -> dict:
    """Extra subprocess.run() kwargs that stop a Calibre console tool
    popping up (and stealing focus with) its own console window from
    this windowed app -- redactor_common's no_window_kwargs(), shared
    with mp3 and video since 2026-09-23."""
    return no_window_kwargs()


class ToolCancelled(OSError):
    """The user cancelled a running Calibre tool; its process was killed.
    An OSError so the converters' existing error handling (clean up the
    half-written output, report per file) applies unchanged."""


def cancellable_run(cancel_event, poll_seconds: float = 0.2):
    """A drop-in for subprocess.run(args, capture_output=True, timeout=...,
    **kwargs) that kills the process as soon as `cancel_event` (a
    threading.Event) is set, raising ToolCancelled. Lets a progress
    dialog's Cancel stop a long ebook-convert / ebook-polish run instead
    of waiting for it to finish."""

    def run(args, capture_output=True, timeout=None, **kwargs):
        if cancel_event.is_set():
            raise ToolCancelled("Cancelled.")
        if capture_output:
            kwargs.setdefault("stdout", subprocess.PIPE)
            kwargs.setdefault("stderr", subprocess.PIPE)
        kwargs.setdefault("stdin", subprocess.DEVNULL)
        deadline = None if timeout is None else time.monotonic() + timeout
        proc = subprocess.Popen(args, **kwargs)
        try:
            while True:
                try:
                    stdout, stderr = proc.communicate(timeout=poll_seconds)
                    return subprocess.CompletedProcess(args, proc.returncode, stdout, stderr)
                except subprocess.TimeoutExpired:
                    if cancel_event.is_set():
                        raise ToolCancelled("Cancelled.") from None
                    if deadline is not None and time.monotonic() > deadline:
                        raise subprocess.TimeoutExpired(args, timeout) from None
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.communicate()

    return run


def _exe_name(base_name: str) -> str:
    return base_name if base_name.lower().endswith(".exe") else f"{base_name}.exe"


def _candidate_install_dirs(extra_dirs: list[str] | None = None) -> list[str]:
    return list(extra_dirs or []) + _default_install_dirs()


def find_tool(
    tool_key: str,
    configured_install_dir: str = "",
    which_fn=shutil.which,
    extra_install_dirs: list[str] | None = None,
) -> str | None:
    """Locate a specific Calibre CLI tool by key ("fetch-ebook-metadata"
    or "ebook-convert"). Tries, in order: the configured install
    directory, PATH, then common install locations -- redactor_common's
    tool_locator.find_tool() tiers 2-4 (the configured folder plays the
    bundled-tools-folder role)."""
    base_name = TOOL_BASE_NAMES.get(tool_key, tool_key)
    found = _shared_find_tool(
        base_name,
        tools_dir=configured_install_dir or None,
        install_dirs=_candidate_install_dirs(extra_install_dirs),
        which=lambda name: which_fn(name) or which_fn(_exe_name(name)),
    )
    return str(found) if found else None


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
