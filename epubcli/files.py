"""
epubcli/files.py

Finding and loading the EPUB files a command works on, and the app's own log, read without any window.
"""

from __future__ import annotations

import os

from core.app_paths import base_dir
from core.epub_metadata import EpubBook
from redactor_common.cli import CliError, Output, expand_paths
from redactor_common.core.rename_log import RenameLog

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


def load_books(files: list[str]) -> list[EpubBook]:
    return [EpubBook(path) for path in files]


def rename_log() -> RenameLog:
    """The same log File > Undo Last Rename reads, so a rename done here can be undone from the app."""
    return RenameLog(os.path.join(str(base_dir()), "epubredactor_rename_log.json"))


def skip_reason(book: EpubBook) -> str:
    return f"it could not be loaded ({book.load_error})" if book.load_error else ""
