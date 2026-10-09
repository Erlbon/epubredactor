"""
epubcli/cmd_files.py

  rename  PATH...   rename by a metadata pattern ("%series% %series_index% - %title%")
  move    PATH...   move (or copy) into folders under a library root by a pattern ("%authors%/%series%/...")
  convert PATH...   MOBI/AZW3/DOCX/FB2/... to EPUB with Calibre's ebook-convert, beside the original

Rename and move are the shared implementations in redactor_common.cli.commands; this file only says how a
book's fields and path are read. There is no undo for the command line (it is not recorded in the app's rename log).
"""

from __future__ import annotations

import argparse
import os

from core.calibre_tools import find_tool
from core.ebook_convert import SUPPORTED_SOURCE_EXTENSIONS, EbookConvertError, convert_to_epub
from core.epub_metadata import EpubBook
from core.rename_pattern import DEFAULT_PATTERN, placeholder_values
from gui import app_settings
from redactor_common.cli import EXIT_PARTIAL, CliError, Output, add_common_options, commands
from redactor_common.cli.commands import add_pattern_options, new_row, say
from redactor_common.core.rename_pattern import zero_pad_numeric_value
from redactor_common.core.trash import TrashError, move_to_trash

from epubcli.files import add_path_arguments, collect, load_books, skip_reason


def _values_for(book: EpubBook, zero_pad: int) -> dict[str, str]:
    values = dict(placeholder_values(book.metadata))
    if zero_pad > 0 and values.get("series_index"):
        values["series_index"] = zero_pad_numeric_value(values["series_index"], zero_pad)
    return values


# --- rename -------------------------------------------------------------------------


def add_rename_parser(sub) -> None:
    parser = sub.add_parser(
        "rename", help="rename files by a metadata pattern",
        description="Rename each EPUB from its metadata. Never overwrites: a name that is taken gets (2), (3)...",
    )
    add_path_arguments(parser)
    add_pattern_options(parser, pattern_required=False)
    add_common_options(parser)
    parser.set_defaults(handler=run_rename)


def run_rename(args: argparse.Namespace, out: Output) -> int:
    pattern = args.pattern or DEFAULT_PATTERN
    books = load_books(collect(args.paths, out, recurse=not args.no_recurse))
    failed = commands.rename_items(
        books, pattern=pattern, values_for=lambda b: _values_for(b, args.zero_pad), path_of=lambda b: b.path,
        skip_reason=skip_reason, out=out, dry_run=args.dry_run, ascii_only=args.ascii,
    )
    return commands.finish_run(out, failed, files=len(books), dry_run=args.dry_run, pattern=pattern)


# --- move ---------------------------------------------------------------------------


def add_move_parser(sub) -> None:
    parser = sub.add_parser(
        "move", help="move files into folders under a library root",
        description="Move (or copy) each EPUB to <root>/<pattern>, the pattern may contain / to make sub-folders, "
                    "e.g. \"%authors%/%series%/%title%\". Never overwrites.",
    )
    add_path_arguments(parser)
    add_pattern_options(parser, pattern_required=True)
    parser.add_argument("--root", metavar="FOLDER", help="the library folder (default: the one saved in the app)")
    parser.add_argument("--copy", action="store_true", help="copy instead of move, leaving the originals")
    add_common_options(parser)
    parser.set_defaults(handler=run_move)


def run_move(args: argparse.Namespace, out: Output) -> int:
    root = args.root or app_settings.load_library_root()
    books = load_books(collect(args.paths, out, recurse=not args.no_recurse))
    failed = commands.move_items(
        books, root=root, pattern=args.pattern, values_for=lambda b: _values_for(b, args.zero_pad),
        path_of=lambda b: b.path, skip_reason=skip_reason, out=out, dry_run=args.dry_run, copy=args.copy,
        ascii_only=args.ascii,
    )
    return commands.finish_run(out, failed, files=len(books), dry_run=args.dry_run, root=root)


# --- convert ------------------------------------------------------------------------


def add_convert_parser(sub) -> None:
    parser = sub.add_parser(
        "convert", help="convert MOBI/AZW3/DOCX/FB2/... to EPUB",
        description="Convert other e-book formats to EPUB with Calibre's ebook-convert (Calibre must be installed), "
                    "beside the original (same name, .epub). Never overwrites: if the .epub exists the file is skipped.",
    )
    add_path_arguments(parser)
    parser.add_argument("--trash-original", action="store_true",
                        help="send the original to the Recycle Bin after the .epub is made (never deleted for good)")
    parser.add_argument("-n", "--dry-run", action="store_true", help="show what would be converted, change nothing")
    add_common_options(parser)
    parser.set_defaults(handler=run_convert)


def run_convert(args: argparse.Namespace, out: Output) -> int:
    files = collect(
        args.paths, out, recurse=not args.no_recurse, extensions=sorted(SUPPORTED_SOURCE_EXTENSIONS), noun="e-book"
    )
    tool = None
    failed = 0
    for index, path in enumerate(files, start=1):
        out.progress(index, len(files), path)
        row = new_row(path)
        target = os.path.splitext(path)[0] + ".epub"
        if path.lower().endswith(".epub"):
            row["status"], row["message"] = "skipped", "already an EPUB"
        elif os.path.lexists(target):
            row["status"], row["message"], row["new_path"] = "skipped", "an .epub of that name already exists; left alone", target
        elif args.dry_run:
            row["status"], row["new_path"] = "planned", target
        else:
            if tool is None:
                tool = find_tool("ebook-convert", app_settings.load_calibre_install_dir())
                if tool is None:
                    raise CliError(
                        "Calibre's ebook-convert was not found. Install Calibre (calibre-ebook.com) or set its folder "
                        "in the app (Tools > Calibre).", EXIT_PARTIAL,
                    )
            try:
                convert_to_epub(tool, path, target)
            except EbookConvertError as exc:
                row["status"], row["message"] = "failed", str(exc)
                failed += 1
            else:
                row["status"], row["new_path"] = "converted", target
                if args.trash_original:
                    try:
                        move_to_trash(path)
                    except TrashError as exc:
                        row["message"] = f"converted, but the original was kept: {exc}"
                        out.warn(f"{os.path.basename(path)}: the original was kept ({exc})")
        out.record(row)
        say(out, row)
    return commands.finish_run(out, failed, files=len(files), dry_run=args.dry_run)
