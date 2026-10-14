"""History journal entries follow a renamed or moved book (core/history.on_files_moved, the on_move hook on every
RenameLog the app builds, and the command line's rename / move / redact): Tools > History must still find the file
where it is now. With History off nothing is written at all."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import gui.main_window as mw  # noqa: E402
from core import history  # noqa: E402
from core.epub_metadata import EpubBook  # noqa: E402
from gui import app_settings  # noqa: E402
from test_redact_steps import env, make_epub, only, run, trash  # noqa: E402,F401

_app = QApplication.instance() or QApplication(sys.argv)


def _saved_book(tmp_path, name="a.epub"):
    path = make_epub(str(tmp_path / name), title="Dune")
    book = EpubBook(path)
    book.apply_metadata({"title": "Arrakis"})
    book.save()
    return path, book


def _rename_in_window(monkeypatch, window, book, stem):
    import redactor_common.gui.rename_single_file as rsf

    monkeypatch.setattr(rsf.QInputDialog, "getText", staticmethod(lambda *a, **k: (stem, True)))
    window.rename_single_file(book)


def test_every_rename_log_the_app_builds_carries_the_history_hook():
    assert mw._rename_log().on_move is history.on_files_moved
    assert mw._make_rename_log("x.json").on_move is history.on_files_moved
    assert mw.MainWindow()._redact_env().rename_log.on_move is history.on_files_moved


def test_rename_file_and_undo_move_the_entries_along(tmp_path, monkeypatch):
    app_settings.save_history_enabled(True)
    path, book = _saved_book(tmp_path)
    window = mw.MainWindow()
    window.books = [book]
    window._rebuild_table()
    _rename_in_window(monkeypatch, window, book, "Renamed")
    new = str(tmp_path / "Renamed.epub")
    assert book.path == new and os.path.isfile(new)
    [entry] = history.get_journal().entries()
    assert entry.path == new and entry.original_path == path

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window.undo_last_rename()
    assert os.path.isfile(path) and book.path == path
    [entry] = history.get_journal().entries()
    assert entry.path == path and entry.original_path == path


def test_with_history_off_a_rename_writes_nothing(tmp_path, monkeypatch):
    path, book = _saved_book(tmp_path)
    window = mw.MainWindow()
    window.books = [book]
    window._rebuild_table()
    _rename_in_window(monkeypatch, window, book, "Renamed")
    assert os.path.isfile(tmp_path / "Renamed.epub")
    assert not os.path.exists(history.get_journal().path)
    history.on_files_moved([(path, str(tmp_path / "Renamed.epub"))])
    assert not os.path.exists(history.get_journal().path)


def test_redact_entry_is_written_where_saved_and_follows_rename_and_move(tmp_path, env):
    app_settings.save_history_enabled(True)
    root = tmp_path / "lib"
    root.mkdir()
    path = make_epub(str(tmp_path / "orig.epub"), authors=("Ann &amp; Bob",))
    env.rename_log = mw._rename_log()  # the GUI's log (conftest builds it with the app's factory)
    env.library_root = str(root)
    recipe = only("validate_fix", "rename", "move_into_folders", options={"rename": {"pattern": "%title%"}})
    run([EpubBook(path)], env, recipe)
    [entry] = history.get_journal().entries()
    assert entry.kind == "redact" and entry.original_path == path  # written at the path the save happened
    assert os.path.isfile(entry.path) and os.path.dirname(entry.path) != str(tmp_path)
    assert entry.path == env.moves[0][1]
    assert env.renames[0] == (path, str(tmp_path / "Test Book.epub"))


def _cli(capsys, *argv):
    from epubcli.main import main

    code = main([*argv, "--json"])
    return code, json.loads(capsys.readouterr().out)


def test_command_line_rename_and_move_move_the_entries_along(tmp_path, capsys):
    app_settings.save_history_enabled(True)
    path, _book = _saved_book(tmp_path)
    code, _doc = _cli(capsys, "rename", path, "-p", "%title% (renamed)")
    renamed = str(tmp_path / "Arrakis (renamed).epub")
    assert code == 0 and os.path.isfile(renamed)
    [entry] = history.get_journal().entries()
    assert entry.path == renamed and entry.original_path == path

    lib = tmp_path / "lib"
    lib.mkdir()
    code, doc = _cli(capsys, "move", renamed, "-p", "Shelf/%title%", "--root", str(lib))
    moved = doc["results"][0]["new_path"]
    assert code == 0 and os.path.isfile(moved)
    [entry] = history.get_journal().entries()
    assert entry.path == moved and entry.original_path == path

    code, doc = _cli(capsys, "move", moved, "-p", "Copies/%title%", "--root", str(lib), "--copy")
    assert code == 0 and doc["results"][0]["status"] == "copied"
    assert history.get_journal().entries()[0].path == moved  # a copy leaves the entry with the original


def test_command_line_redact_entry_follows_its_rename(tmp_path, capsys):
    app_settings.save_history_enabled(True)
    app_settings.save_pattern_used("%title% (redacted)")
    path = make_epub(str(tmp_path / "html.epub"), title="Marked", description="&lt;p&gt;Hi&lt;/p&gt;")
    steps = [r["step"] for r in _cli(capsys, "redact", "--list-steps")[1]["results"]]
    argv = [a for s in steps if s not in ("strip_description_html", "rename") for a in ("--disable", s)]
    code, _doc = _cli(
        capsys, "redact", path, *argv, "--enable", "strip_description_html", "--enable", "rename",
        "--trash-dir", str(tmp_path / "bin"),
    )
    renamed = str(tmp_path / "Marked (redacted).epub")
    assert code == 0 and os.path.isfile(renamed) and not os.path.exists(path)
    [entry] = history.get_journal().entries()
    assert entry.kind == "redact" and entry.original_path == path and entry.path == renamed


def test_command_line_rename_with_history_off_writes_nothing(tmp_path, capsys):
    path = make_epub(str(tmp_path / "a.epub"), title="Dune")
    assert _cli(capsys, "rename", path, "-p", "%title% (x)")[0] == 0
    assert not os.path.exists(history.get_journal().path)
