"""
epubcli/files.py

Finding and loading the EPUB files a command works on, and the app's own log, read without any window.
"""

from __future__ import annotations


from core.epub_metadata import EpubBook
from redactor_common.cli import CliError, Output, expand_paths

EXTENSIONS = (".epub",)


def add_path_arguments(parser) -> None:
    parser.add_argument("paths", nargs="+", metavar="PATH", help="EPUB files, folders or wildcards")
    parser.add_argument(
        "-R", "--no-recurse", action="store_true", help="for a folder, look only at the files directly in it"
    )


def collect(paths: list[str], out: Output, recurse: bool = True, extensions=EXTENSIONS, noun: str = "EPUB") -> list[str]:
    """The files the arguments name. An argument that matches nothing is an error; if that leaves no files at
    all the command ends with a usage error."""
    files, missing = expand_paths(paths, extensions, recursive=recurse)
    for argument in missing:
        out.error(f"nothing found for {argument}")
    if not files:
        raise CliError(f"no {noun} files found")
    return files


def load_books(files: list[str], out: Output | None = None) -> list[EpubBook]:
    """Loads each file; `out` shows "reading N/M" on stderr while a big batch is read."""
    books = []
    for index, path in enumerate(files, start=1):
        if out is not None:
            out.progress(index, len(files), f"reading {path}")
        books.append(EpubBook(path))
    return books


def skip_reason(book: EpubBook) -> str:
    return f"it could not be loaded ({book.load_error})" if book.load_error else ""
