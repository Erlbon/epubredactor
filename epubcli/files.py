"""
epubcli/files.py

Finding and loading the EPUB files a command works on, and the app's own log, read without any window.
"""

from __future__ import annotations

from collections.abc import Iterator

from core.epub_metadata import EpubBook
from redactor_common.cli import CliError, Output, expand_paths
from redactor_common.core.temp_names import is_app_temp_name

EXTENSIONS = (".epub",)


def add_path_arguments(parser) -> None:
    parser.add_argument("paths", nargs="+", metavar="PATH", help="EPUB files, folders or wildcards")
    parser.add_argument(
        "-R", "--no-recurse", action="store_true", help="for a folder, look only at the files directly in it"
    )


def collect(paths: list[str], out: Output, recurse: bool = True, extensions=EXTENSIONS, noun: str = "EPUB") -> list[str]:
    """The files the arguments name. An argument that matches nothing is a usage error (exit 2), raised after
    every argument was looked at and before any file is touched, so a typo never leaves a half-done run that
    exits 0. The app's own temp/backup leftovers (e.g. "x.redact-orig.epub") found in a folder or by a wildcard
    are skipped; a file named explicitly is still processed."""
    files, missing = expand_paths(paths, extensions, recursive=recurse, skip=is_app_temp_name)
    for argument in missing:
        out.error(f"nothing found for {argument}")
    if not files:
        raise CliError(f"no {noun} files found")
    if missing:
        raise CliError(f"nothing found for {', '.join(missing)}; no file was changed")
    return files


def iter_books(files: list[str]) -> Iterator[EpubBook]:
    """Each file loaded in turn: the caller works on one book and drops it before the next is read, so a big
    library neither waits for every file nor holds them all in memory. A book that cannot be read comes with
    its load_error set (EpubBook never raises on load)."""
    for path in files:
        yield EpubBook(path)


def load_books(files: list[str], out: Output | None = None) -> list[EpubBook]:
    """Loads every file into a list (rename, move and redact work on the whole batch); `out` shows
    "reading N/M" on stderr while a big batch is read."""
    books = []
    for index, path in enumerate(files, start=1):
        if out is not None:
            out.progress(index, len(files), f"reading {path}")
        books.append(EpubBook(path))
    return books


def skip_reason(book: EpubBook) -> str:
    return f"it could not be loaded ({book.load_error})" if book.load_error else ""
