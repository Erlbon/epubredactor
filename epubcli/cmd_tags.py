"""
epubcli/cmd_tags.py

  info PATH...   what each EPUB is: its metadata, cover and validation status
  set  PATH...   change metadata fields (-s Series=Dune -s series_index=2, --clear Description), saved in place
"""

from __future__ import annotations

import argparse

from core.epub_metadata import EpubBook, EpubError
from redactor_common.cli import EXIT_OK, EXIT_PARTIAL, CliError, Output, add_common_options

from epubcli.fields import CLI_FIELDS, DEFAULT_INFO_FIELDS, FIELD_NAMES, attr_for, parse_assignment, resolve_field
from epubcli.files import add_path_arguments, collect, load_books, skip_reason

LABELS = {attr: name for name, attr in CLI_FIELDS.items()}


# --- info ---------------------------------------------------------------------------


def add_info_parser(sub) -> None:
    parser = sub.add_parser("info", help="show what the EPUB files are", description="Show each book's metadata, cover and validation status.")
    add_path_arguments(parser)
    parser.add_argument("--fields", metavar="LIST", help="comma-separated fields to show (default: title, authors, series, series_index, year)")
    parser.add_argument("--all", action="store_true", help="show every field that has a value")
    add_common_options(parser)
    parser.set_defaults(handler=run_info)


def run_info(args: argparse.Namespace, out: Output) -> int:
    files = collect(args.paths, out, recurse=not args.no_recurse)
    wanted = FIELD_NAMES if args.all else (
        [resolve_field(name) for name in args.fields.split(",") if name.strip()] if args.fields else DEFAULT_INFO_FIELDS
    )
    failed = 0
    for index, book in enumerate(load_books(files), start=1):
        out.progress(index, len(files), book.path)
        fields = {n: getattr(book.metadata, CLI_FIELDS[n], "") for n in wanted}
        fields = {n: v for n, v in fields.items() if (v or "").strip()}
        status = book.load_error or book.validation_status
        failed += bool(book.load_error)
        out.record({
            "path": book.path, "status": status, "has_cover": book.cover_bytes is not None,
            "issues": len(book.validation_issues), "fields": fields,
        })
        out.line(f"{book.path}  [{status}{', cover' if book.cover_bytes is not None else ', no cover'}]")
        for name, value in fields.items():
            out.line(f"  {name}: {value}")
    out.finish({"files": len(files), "failed": failed})
    return EXIT_PARTIAL if failed else EXIT_OK


# --- set ----------------------------------------------------------------------------


def add_set_parser(sub) -> None:
    parser = sub.add_parser(
        "set", help="change metadata fields",
        description="Set or empty metadata fields and save each EPUB in place. Several authors or genres are "
                    "separated by \";\".",
    )
    add_path_arguments(parser)
    parser.add_argument("-s", "--set", dest="assignments", action="append", default=[], metavar="FIELD=VALUE",
                        help="set a field (repeat for several), e.g. -s Series=Dune -s series_index=2")
    parser.add_argument("--clear", action="append", default=[], metavar="FIELD", help="empty a field (repeatable)")
    parser.add_argument("-n", "--dry-run", action="store_true", help="show the changes, write nothing")
    add_common_options(parser)
    parser.set_defaults(handler=run_set)


def run_set(args: argparse.Namespace, out: Output) -> int:
    changes: dict[str, str] = {}
    for text in args.assignments:
        attr, value = parse_assignment(text)
        changes[attr] = value
    for name in args.clear:
        changes[attr_for(name)] = ""
    if not changes:
        raise CliError("nothing to change: give at least one -s FIELD=VALUE or --clear FIELD")

    files = collect(args.paths, out, recurse=not args.no_recurse)
    failed = 0
    for index, book in enumerate(load_books(files), start=1):
        out.progress(index, len(files), book.path)
        row = {"path": book.path, "status": "", "changes": {}, "message": ""}
        reason = skip_reason(book)
        if reason:
            row["status"], row["message"] = "failed", reason
            failed += 1
        else:
            for attr, new in changes.items():
                old = getattr(book.metadata, attr, "") or ""
                if old != new:
                    row["changes"][LABELS[attr]] = {"old": old, "new": new}
            if not row["changes"]:
                row["status"] = "unchanged"
            elif args.dry_run:
                row["status"] = "planned"
            else:
                row["status"] = _save(book, changes, row)
                failed += row["status"] == "failed"
        out.record(row)
        out.line(f"{row['status']:9} {book.path}" + (f"  ({row['message']})" if row["message"] else ""))
        for name, change in row["changes"].items():
            out.line(f"          {name}: {change['old']!r} -> {change['new']!r}")
    out.finish({"files": len(files), "failed": failed, "dry_run": args.dry_run})
    return EXIT_PARTIAL if failed else EXIT_OK


def _save(book: EpubBook, changes: dict[str, str], row: dict) -> str:
    book.apply_metadata(changes)
    try:
        book.save()
    except (EpubError, OSError) as exc:
        row["message"] = str(book.save_error or exc)
        return "failed"
    return "changed"
