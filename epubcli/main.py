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
    epubredactor headers  PATH... [--fix]              find (and remove) running headers and page numbers left by a scan

Every command takes --json (one JSON document), --quiet and --output FILE (the result goes to a file: the
reliable way to read it from a script, since a windowed exe cannot be waited for by an interactive shell),
and the ones that change files take --dry-run. Exit codes: 0 done, 1 some files failed or have problems,
2 bad arguments, 70 internal error, 130 interrupted. It reads the same settings file as the app.
"""

from __future__ import annotations

from core.version import APP_VERSION
from redactor_common.cli.main_factory import make_main

from epubcli import COMMANDS, cmd_files, cmd_headers, cmd_redact, cmd_tags, cmd_validate

PROG = "epubredactor"

# redactor_common's make_main: the parser (--version, one subcommand per adder, checked against COMMANDS)
# and main(argv), which runs the chosen handler with an Output and always closes it.
build_parser, main = make_main(
    PROG, APP_VERSION,
    "The EPUB Redactor on the command line: inspect, edit, rename, convert, validate and redact EPUB books.",
    [
        cmd_tags.add_info_parser, cmd_tags.add_set_parser, cmd_files.add_rename_parser,
        cmd_files.add_move_parser, cmd_files.add_convert_parser, cmd_redact.add_redact_parser,
        cmd_validate.add_validate_parser, cmd_headers.add_headers_parser,
    ],
    commands=COMMANDS,
)
