"""
core/ebook_polish.py

"Polishes" an EPUB/AZW3/KEPUB via Calibre's bundled ebook-polish tool:
lightweight, targeted cleanups (smarten punctuation, subset/embed fonts,
compress images, remove unused CSS, add/remove soft hyphens,
insert/remove a book-jacket metadata page, upgrade EPUB2 -> EPUB3) that
don't rewrite the book's structure the way a full conversion would.

Same rationale as core/ebook_convert.py and core/calibre_lookup.py for
shelling out rather than reimplementing: these are genuinely non-trivial
operations (font subsetting, CSS analysis) Calibre already does well,
with no reason to duplicate that work ourselves.

Deliberately NOT exposed here: --cover and --opf (ebook-polish can also
update the cover/metadata from files you point it at) -- this app's own
metadata engine already handles both with more precision and control
than routing through an external tool would give us, so there's no
reason to offer a second, less-controllable path to the same result.

ebook-polish's own CLI accepts an optional output_file and, per its
documentation, its behavior when that's omitted isn't unambiguous enough
to rely on -- so polish_book() always requires and passes an explicit
output path. What the caller does with that output (overwrite the
original, keep it as a separate copy) is entirely up to the caller.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

from core.calibre_tools import no_console_window_kwargs

DEFAULT_TIMEOUT_SECONDS = 120

SUPPORTED_POLISH_EXTENSIONS = {".epub", ".azw3", ".kepub"}


class EbookPolishError(Exception):
    """Raised for any problem running Calibre's ebook-polish, for an
    unsupported/missing source file, or for contradictory options."""


@dataclass
class PolishOptions:
    smarten_punctuation: bool = False
    subset_fonts: bool = False
    embed_fonts: bool = False
    compress_images: bool = False
    remove_unused_css: bool = False
    add_soft_hyphens: bool = False
    remove_soft_hyphens: bool = False
    insert_jacket: bool = False
    remove_jacket: bool = False
    upgrade_book: bool = False

    def any_selected(self) -> bool:
        return any([
            self.smarten_punctuation, self.subset_fonts, self.embed_fonts,
            self.compress_images, self.remove_unused_css,
            self.add_soft_hyphens, self.remove_soft_hyphens,
            self.insert_jacket, self.remove_jacket, self.upgrade_book,
        ])

    def validate(self) -> None:
        if self.add_soft_hyphens and self.remove_soft_hyphens:
            raise EbookPolishError("Can't both add and remove soft hyphens in the same run.")
        if self.insert_jacket and self.remove_jacket:
            raise EbookPolishError("Can't both insert and remove the book jacket in the same run.")

    def to_args(self) -> list[str]:
        """Pure logic: translate selected options into ebook-polish CLI
        flags. Split out from polish_book() for direct testability."""
        args = []
        if self.smarten_punctuation:
            args.append("--smarten-punctuation")
        if self.subset_fonts:
            args.append("--subset-fonts")
        if self.embed_fonts:
            args.append("--embed-fonts")
        if self.compress_images:
            args.append("--compress-images")
        if self.remove_unused_css:
            args.append("--remove-unused-css")
        if self.add_soft_hyphens:
            args.append("--add-soft-hyphens")
        if self.remove_soft_hyphens:
            args.append("--remove-soft-hyphens")
        if self.insert_jacket:
            args.append("--jacket")
        if self.remove_jacket:
            args.append("--remove-jacket")
        if self.upgrade_book:
            args.append("--upgrade-book")
        return args


def is_supported_polish_target(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in SUPPORTED_POLISH_EXTENSIONS


def polish_book(
    exe_path: str,
    source_path: str,
    output_path: str,
    options: PolishOptions,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    run_fn=subprocess.run,
) -> None:
    """Polish `source_path`, writing the result to `output_path` (always
    an explicit path, never omitted -- see the module docstring for why).
    Raises EbookPolishError on any failure. `run_fn` is injectable
    (defaults to subprocess.run) so this is testable without a real
    Calibre install -- see test_ebook_polish.py."""
    options.validate()
    if not options.any_selected():
        raise EbookPolishError("No polish actions selected.")
    if not source_path or not os.path.isfile(source_path):
        raise EbookPolishError(f"Source file not found: {source_path}")
    if not is_supported_polish_target(source_path):
        ext = os.path.splitext(source_path)[1] or "(no extension)"
        raise EbookPolishError(f"Unsupported format for polishing: {ext}")

    args = [exe_path, *options.to_args(), source_path, output_path]
    try:
        proc = run_fn(args, capture_output=True, timeout=timeout, **no_console_window_kwargs())
    except subprocess.TimeoutExpired as exc:
        raise EbookPolishError(f"Polishing timed out after {timeout}s.") from exc
    except OSError as exc:
        raise EbookPolishError(f"Could not run Calibre's ebook-polish: {exc}") from exc

    if proc.returncode != 0:
        stderr_text = _decode(proc.stderr).strip()
        raise EbookPolishError(stderr_text or "Polishing failed with no error message.")


def _decode(data) -> str:
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data or ""
