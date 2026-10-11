"""
epubcli/cmd_headers.py

  headers PATH...   find the running headers and page numbers a scan-and-OCR conversion left in the text of each
                    EPUB (and the sentences a page break cut in two); --fix removes them and rejoins the sentences.

The detection is core/page_headers.py's, the same as Repair > Remove Running Headers and Page Numbers and the Redact
step: a book is only touched when its headers prove themselves (a repeating heading, page numbers that rise through
the whole book). Without --fix nothing is written. With --fix each changed book is saved in place by the Redact engine
(verified, the original going to the Recycle Bin or --trash-dir). Exit code 1 when a book still has page furniture
after the command (found but not fixed), or could not be read.
"""

from __future__ import annotations

import argparse
import os

from core.page_headers import find_page_furniture
from core.redact_steps import EpubCtx, RedactEnv, build_catalogue, recipe_for_run, run_catalogue, save_finalize
from redactor_common.cli import EXIT_OK, EXIT_PARTIAL, Output, add_common_options
from redactor_common.cli.commands import redact_items, trash_to, trash_with_retries
from redactor_common.core.pipeline import Recipe

from epubcli.files import add_path_arguments, collect, load_books

STEP = "remove_page_headers"


def add_headers_parser(sub) -> None:
    parser = sub.add_parser(
        "headers", help="find and remove running headers and page numbers left by a scan",
        description="List the books whose text still carries printed page headers and page numbers (a scan-and-OCR "
                    "leftover), and with --fix remove them and rejoin the sentences a page break cut in two. Only a "
                    "book whose headers prove themselves is touched.",
    )
    add_path_arguments(parser)
    parser.add_argument("--fix", action="store_true", help="remove the page furniture and save the book in place (the original goes to the Recycle Bin or --trash-dir)")
    parser.add_argument("--no-join", action="store_true", help="only remove the headers; leave the sentences a page break cut in two as they are")
    parser.add_argument("--trash-dir", metavar="FOLDER", help="with --fix: move originals here instead of the Recycle Bin")
    parser.add_argument("-n", "--dry-run", action="store_true", help="with --fix: only report what would be removed, change nothing")
    add_common_options(parser)
    parser.set_defaults(handler=run_headers)


def _row(book, plan) -> dict:
    return {
        "path": book.path, "status": "", "headers": plan.headers, "removed": plan.removed, "joined": plan.joins,
        "hyphenated": plan.hyphen_joins, "confidence": plan.confidence if plan.changed else None,
        "headings": plan.headings, "examples": plan.examples, "message": "",
    }


def run_headers(args: argparse.Namespace, out: Output) -> int:
    files = collect(args.paths, out, recurse=not args.no_recurse)
    books = load_books(files, out)
    if args.fix and not args.dry_run:
        return _fix(books, args, out)
    found = failed = 0
    for index, book in enumerate(books, start=1):
        out.progress(index, len(books), book.path)
        if book.load_error:
            row = {"path": book.path, "status": "failed", "headers": 0, "removed": 0, "joined": 0, "hyphenated": 0,
                   "confidence": None, "headings": [], "examples": [], "message": book.load_error}
            failed += 1
        else:
            plan = find_page_furniture(book, join_sentences=not args.no_join)
            row = _row(book, plan)
            row["status"] = "found" if plan.changed else "clean"
            row["message"] = plan.summary()
            found += plan.changed
        out.record(row)
        out.line(f"{row['status']:7} {book.path}" + (f"  ({row['message']})" if row["status"] != "clean" else ""))
        for example in row["examples"][:3]:
            out.line(f"        {example}")
    out.finish({"files": len(books), "found": found, "failed": failed, "fix": args.fix, "dry_run": args.dry_run})
    return EXIT_PARTIAL if (found or failed) else EXIT_OK


def _fix(books, args: argparse.Namespace, out: Output) -> int:
    """The Redact engine with this one step on, at confidence 0 (you asked for the fix): each changed book is saved
    in place, verified, and its original goes to the bin."""
    catalogue = build_catalogue("", "")
    recipe = Recipe(
        order=[s.key for s in catalogue], enabled={s.key: s.key == STEP for s in catalogue},
        options={STEP: {"join_sentences": not args.no_join}}, confidence_threshold=0.0,
    )
    env = RedactEnv(
        rename_log=None, trash=trash_to(args.trash_dir) if args.trash_dir else trash_with_retries(),
    )
    env.begin()
    return redact_items(
        books, recipe_for_run(recipe), run_catalogue("", ""), make_context=lambda book: EpubCtx(book, env),
        describe=lambda book: os.path.basename(book.path), finalize=save_finalize, finalize_label="Save",
        path_of=lambda book: book.path, out=out,
    )
