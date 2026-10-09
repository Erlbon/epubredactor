"""
epubcli/main.py

The epubredactor command line, run through the app's own exe (main.py dispatches here when its first
argument is a command; the window never starts):

    epubredactor info     PATH...                      what the books are
    epubredactor set      PATH... -s Series=Dune       change metadata fields
    epubredactor rename   PATH... -p "%series% %series_index% - %title%"
    epubredactor move     PATH... -p "%authors%/%series%/..." --root LIBRARY
    epubredactor convert  PATH...                      MOBI/AZW3/DOCX/... -> EPUB (Calibre)
    epubredactor redact   PATH...                      run the saved Redact recipe
    epubredactor validate PATH... [--fix]              check (and repair) the EPUB structure

Every command takes --json (one JSON document), --quiet and --output FILE (the result goes to a file: the
reliable way to read it from a script, since a windowed exe cannot be waited for by an interactive shell),
and the ones that change files take --dry-run. Exit codes: 0 done, 1 some files failed or have problems,
2 bad arguments, 70 internal error, 130 interrupted. It reads the same settings file as the app.
"""

from __future__ import annotations

import argparse
from typing import Sequence

from core.version import APP_VERSION
from redactor_common.cli import make_output

from epubcli import COMMANDS, cmd_files, cmd_redact, cmd_tags, cmd_validate

PROG = "epubredactor"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG, description="The EPUB Redactor on the command line: inspect, edit, rename, convert, validate and redact EPUB books.",
    )
    parser.add_argument("--version", action="version", version=f"{PROG} {APP_VERSION}")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True
    cmd_tags.add_info_parser(sub)
    cmd_tags.add_set_parser(sub)
    cmd_files.add_rename_parser(sub)
    cmd_files.add_move_parser(sub)
    cmd_files.add_convert_parser(sub)
    cmd_redact.add_redact_parser(sub)
    cmd_validate.add_validate_parser(sub)
    assert tuple(sub.choices) == COMMANDS, "epubcli.COMMANDS must list the subcommands"
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out = make_output(args)
    try:
        return args.handler(args, out)
    finally:
        out.close()
