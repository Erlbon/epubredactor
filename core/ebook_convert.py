"""
core/ebook_convert.py

Converts other ebook formats (MOBI, AZW/AZW3, DOCX, RTF, TXT, FB2, and
others) into EPUB by shelling out to Calibre's bundled ebook-convert
command-line tool -- same rationale as core/calibre_lookup.py for not
reimplementing this ourselves: format conversion is a genuinely deep
problem, and Calibre is the right tool to lean on rather than something
worth rebuilding from scratch.

PDF is deliberately NOT in the default supported set. PDF has no real
text-flow structure to extract, so PDF -> EPUB conversion quality is
notoriously inconsistent -- offering it as a default, ordinary option
would set an expectation this integration can't reliably meet. The other
formats here are all native ebook/document formats that convert cleanly
in the common case.
"""

from __future__ import annotations

import os
import subprocess

from core.calibre_tools import no_console_window_kwargs

SUPPORTED_SOURCE_EXTENSIONS = {
    ".mobi", ".azw", ".azw3", ".azw4", ".kfx",
    ".docx", ".odt", ".rtf", ".txt",
    ".fb2", ".fbz", ".lit", ".lrf", ".pdb", ".pml",
    ".cbz", ".cbr", ".cbc", ".html", ".htmlz", ".chm", ".snb",
}

DEFAULT_TIMEOUT_SECONDS = 180  # conversion can be slow for larger books


class EbookConvertError(Exception):
    """Raised for any problem running Calibre's ebook-convert, or for an
    unsupported/missing source file."""


def is_supported_source(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in SUPPORTED_SOURCE_EXTENSIONS


def convert_to_epub(
    exe_path: str,
    source_path: str,
    output_path: str,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    run_fn=subprocess.run,
) -> None:
    """Convert `source_path` to an EPUB at `output_path`. Raises
    EbookConvertError on any failure. `run_fn` is injectable (defaults to
    subprocess.run) so this is testable without a real Calibre install --
    see test_ebook_convert.py."""
    if not source_path or not os.path.isfile(source_path):
        raise EbookConvertError(f"Source file not found: {source_path}")
    if not is_supported_source(source_path):
        ext = os.path.splitext(source_path)[1] or "(no extension)"
        raise EbookConvertError(f"Unsupported source format: {ext}")

    args = [exe_path, source_path, output_path]
    try:
        proc = run_fn(args, capture_output=True, timeout=timeout, **no_console_window_kwargs())
    except subprocess.TimeoutExpired as exc:
        raise EbookConvertError(f"Conversion timed out after {timeout}s.") from exc
    except OSError as exc:
        raise EbookConvertError(f"Could not run Calibre's ebook-convert: {exc}") from exc

    if proc.returncode != 0:
        stderr_text = _decode(proc.stderr).strip()
        raise EbookConvertError(stderr_text or "Conversion failed with no error message.")


def _decode(data) -> str:
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data or ""
