"""
epubcli/cmd_redact.py

  redact PATH...   run the Redact recipe on the EPUB files: the same steps as Operations > Redact in the app
                   (repair, clean up, tags from the path and filename, lookups on Open Library / ISFDB /
                   Google Books, cover, rename, move), saved in place with each original in the Recycle Bin
                   (or moved to --trash-dir).

The recipe is the one saved in the app (Operations > Edit Redact Recipe) unless --recipe FILE names a JSON
recipe; --enable / --disable / --threshold adjust it for this run only. The offline Open Library and ISFDB
databases and the library root come from the app's settings. A cover that needs drawing (the "regenerate a
junk cover" part of the cover step) needs the window's renderer and is skipped from the command line. Running
the recipe and the report are the shared ones in redactor_common.cli.commands.
"""

from __future__ import annotations

import argparse
import os

from core.redact_steps import (
    EpubCtx, RedactEnv, build_catalogue, recipe_for_run, recipe_from_setting, run_catalogue, save_finalize,
)
from gui import app_settings
from redactor_common.cli import CliError, Output, add_common_options
from redactor_common.cli.commands import (
    add_redact_options, build_recipe, list_steps, read_recipe_file, redact_items, trash_to,
)
from redactor_common.core.path_parser import split_pattern_history

from epubcli.files import collect, load_books, rename_log


def add_redact_parser(sub) -> None:
    parser = sub.add_parser(
        "redact", help="run the Redact recipe",
        description="Run the Redact recipe on the EPUB files. Each changed book is saved in place and its original goes "
                    "to the Recycle Bin (or --trash-dir). Guesses below the confidence threshold are listed, not applied.",
    )
    parser.add_argument("paths", nargs="*", metavar="PATH", help="EPUB files, folders or wildcards")
    parser.add_argument("-R", "--no-recurse", action="store_true", help="for a folder, look only at the files directly in it")
    add_redact_options(parser)
    add_common_options(parser)
    parser.set_defaults(handler=run_redact)


def _patterns() -> tuple[str, str]:
    """The most recent saved filename pattern and folder pattern: the Rename and path steps' defaults."""
    names, paths = split_pattern_history(app_settings.load_pattern_history())
    return (names[0] if names else ""), (paths[0] if paths else "")


def build_env(args: argparse.Namespace) -> RedactEnv:
    """What the steps share, read from the app's settings like the window does -- minus anything visual."""
    return RedactEnv(
        trash=trash_to(args.trash_dir) if args.trash_dir else None,
        rename_log=rename_log(),
        library_root=app_settings.load_library_root(),
        ascii_only=app_settings.load_ascii_filenames(),
        zero_pad=app_settings.load_rename_zero_pad(),
        junk_hashes=app_settings.load_junk_cover_hashes(),
        openlibrary_local=app_settings.load_open_library_database(),
        isfdb_local=app_settings.load_isfdb_database(),
    )


def run_redact(args: argparse.Namespace, out: Output) -> int:
    rename_pattern, path_pattern = _patterns()
    catalogue = build_catalogue(rename_pattern, path_pattern)
    text = read_recipe_file(args.recipe) if args.recipe else app_settings.load_redact_recipe()
    recipe = build_recipe(args, recipe_from_setting(text, catalogue), catalogue)
    if args.list_steps:
        return list_steps(recipe, catalogue, out)
    if not args.paths:
        raise CliError("give the EPUB files to redact (or --list-steps)")

    books = load_books(collect(args.paths, out, recurse=not args.no_recurse))
    env = build_env(args)
    env.begin()

    def after_run() -> list[str]:
        env.flush_log()
        return env.notes_text().splitlines()

    return redact_items(
        books, recipe_for_run(recipe), run_catalogue(rename_pattern, path_pattern),
        make_context=lambda book: EpubCtx(book, env), describe=lambda book: os.path.basename(book.path),
        finalize=save_finalize, finalize_label="Save", path_of=lambda book: book.path, out=out, after_run=after_run,
    )
