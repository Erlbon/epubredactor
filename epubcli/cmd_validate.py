"""
epubcli/cmd_validate.py

  validate PATH...   check each EPUB's structure (the Validate / Fix dialog's checks) and list the issues;
                     --fix repairs the ones that can be repaired automatically and saves the book.

Exit code 1 when a book still has errors or warnings (or could not be read) after the command; a DRM-locked
book is reported but is not a failure.
"""

from __future__ import annotations

import argparse

from core.epub_metadata import EpubBook, EpubError
from core.validation_issue import STATUS_DRM, STATUS_OK
from redactor_common.cli import EXIT_OK, EXIT_PARTIAL, Output, add_common_options

from epubcli.files import add_path_arguments, collect, load_books


def add_validate_parser(sub) -> None:
    parser = sub.add_parser(
        "validate", help="check the EPUB structure, optionally fix it",
        description="List the structural issues of each EPUB. With --fix, the issues that can be repaired "
                    "automatically are fixed and the book is saved in place.",
    )
    add_path_arguments(parser)
    parser.add_argument("--fix", action="store_true", help="repair the fixable issues and save the book")
    parser.add_argument("-n", "--dry-run", action="store_true", help="with --fix: show what would be fixed, change nothing")
    add_common_options(parser)
    parser.set_defaults(handler=run_validate)


def _issues(book: EpubBook) -> list[dict]:
    return [
        {"code": i.code, "severity": i.severity, "message": i.message, "fixable": i.fixable}
        for i in book.validation_issues
    ]


def run_validate(args: argparse.Namespace, out: Output) -> int:
    files = collect(args.paths, out, recurse=not args.no_recurse)
    problems = 0
    for index, book in enumerate(load_books(files), start=1):
        out.progress(index, len(files), book.path)
        row = {
            "path": book.path, "status": book.load_error or book.validation_status, "problem": False,
            "issues": _issues(book), "fixed": [], "message": "",
        }
        if book.load_error:
            row["problem"], row["message"] = True, book.load_error
        elif args.fix and book.validation_issues:
            fixable = [i for i in book.validation_issues if i.fixable]
            if args.dry_run:
                row["fixed"] = [f"would fix {i.code}: {i.message}" for i in fixable]
            elif fixable:
                book.save_error = ""
                try:
                    row["fixed"] = book.apply_fixes()
                    book.save()
                except (EpubError, OSError) as exc:
                    row["message"] = str(book.save_error or exc)
                    row["problem"] = True
                else:
                    after = EpubBook(book.path)  # what is on disk now
                    row["status"], row["issues_after"] = after.validation_status, _issues(after)
        status = row["status"]
        if not row["problem"] and status not in (STATUS_OK, STATUS_DRM):
            row["problem"] = True
        problems += row["problem"]
        out.record(row)
        out.line(f"{'PROBLEM' if row['problem'] else status.lower():8} {book.path}  [{status}]")
        if row["message"]:
            out.line(f"         {row['message']}")
        for issue in row["issues"]:
            out.line(f"         {issue['severity']}: {issue['code']} - {issue['message']}" + ("  (fixable)" if issue["fixable"] else ""))
        for text in row["fixed"]:
            out.line(f"         fixed: {text}")
    out.finish({"files": len(files), "problems": problems, "fix": args.fix, "dry_run": args.dry_run})
    return EXIT_PARTIAL if problems else EXIT_OK
