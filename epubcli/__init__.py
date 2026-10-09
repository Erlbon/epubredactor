"""
epubcli -- epubredactor's command line. It is not a second program: main.py hands over to epubcli.main when
its first argument is one of COMMANDS (see cli_requested), otherwise the window starts. Kept light on
purpose: this package is imported on every start, the commands themselves only when one is asked for.
"""

from redactor_common.cli import is_cli_invocation

COMMANDS = ("info", "set", "rename", "move", "convert", "redact", "validate")


def cli_requested(argv) -> bool:
    return is_cli_invocation(argv, COMMANDS)
