"""Rename/Export dialog's third mode, "Move into folders", wired into the
main window (2026-09-30): the library root is remembered in the settings,
the planned moves run through redactor_common's run_planned_moves, books
follow their files, and File > Undo Last Rename moves everything back.
Rename and Export are covered by test_rename_export_shared_dialog.py."""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(__file__))

from PyQt6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox  # noqa: E402

import gui.main_window as mw  # noqa: E402
from core.epub_metadata import EpubBook  # noqa: E402
from gui import app_settings  # noqa: E402
from test_redact_steps import make_epub  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)
YES = QMessageBox.StandardButton.Yes
NO = QMessageBox.StandardButton.No


def _window(tmp_path, *names, **epub_kwargs):
    window = mw.MainWindow()
    paths = [make_epub(str(tmp_path / n), **epub_kwargs) for n in names]
    window.books = [EpubBook(p) for p in paths]
    window._rebuild_table()
    return window, paths


def _accept_in_move_mode(monkeypatch, pattern, before=None):
    """Patch the dialog's exec(): optionally run `before(dialog)`, pick the
    Move radio, set the pattern and accept."""
    def fake_exec(dialog):
        if before:
            before(dialog)
        dialog.pattern_edit.setText(pattern)
        dialog.move_radio.setChecked(True)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(mw.RenamePatternDialog, "exec", fake_exec)


def test_move_mode_moves_the_files_repoints_the_books_and_logs_one_batch(tmp_path, monkeypatch):
    root = tmp_path / "library"
    root.mkdir()
    window, (a, b) = _window(tmp_path, "a.epub", "b.epub")
    window.books[1].apply_metadata({"title": "Other Book", "authors_str": "Zed"})
    app_settings.save_library_root(str(root))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *args, **kw: NO))  # keep source folders
    _accept_in_move_mode(monkeypatch, "%authors%/%title%")

    window.open_rename_dialog()

    new_a = root / "Jane Doe" / "Test Book.epub"
    new_b = root / "Zed" / "Other Book.epub"
    assert new_a.exists() and new_b.exists() and not os.path.exists(a) and not os.path.exists(b)
    assert [bk.path for bk in window.books] == [str(new_a), str(new_b)]
    assert window.books[1].dirty  # the unsaved edit is still pending; the move didn't save it
    assert EpubBook(str(new_b)).metadata.title == "Test Book"  # ...so the file itself is unchanged
    names = {window.table.item(r, mw.FILENAME_COL).text() for r in range(window.table.rowCount())}
    assert names == {"Test Book.epub", "Other Book.epub"}
    log = mw._rename_log()
    batch = log.last_batch()
    assert sorted(batch.renames) == sorted([(a, str(new_a)), (b, str(new_b))])
    assert len(batch.created_dirs) == 2 and batch.root
    assert len(log.batches()) == 1
    assert app_settings.load_pattern_history()[0] == "%authors%/%title%"


def test_the_chosen_library_root_is_remembered(tmp_path, monkeypatch):
    root = tmp_path / "chosen"
    root.mkdir()
    window, (a,) = _window(tmp_path, "a.epub")
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *args, **kw: str(root)))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *args, **kw: NO))
    assert app_settings.load_library_root() == ""

    def choose(dialog):
        assert dialog.library_root() == ""
        dialog.move_radio.setChecked(True)
        dialog._choose_root()

    _accept_in_move_mode(monkeypatch, "%title%", before=choose)
    window.open_rename_dialog()

    assert app_settings.load_library_root() == str(root)
    assert (root / "Test Book.epub").exists()
    # next time the dialog starts with it
    seen = []
    monkeypatch.setattr(mw.RenamePatternDialog, "exec", lambda dialog: seen.append(dialog.library_root()) or 0)
    window.open_rename_dialog()
    assert seen == [str(root)]


def test_without_a_library_root_apply_is_disabled_and_nothing_moves(tmp_path, monkeypatch):
    window, (a,) = _window(tmp_path, "a.epub")
    state = []

    def fake_exec(dialog):
        dialog.move_radio.setChecked(True)
        state.append((dialog._ok_button.isEnabled(), dialog.warning_label.text()))
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(mw.RenamePatternDialog, "exec", fake_exec)
    window.open_rename_dialog()
    assert state == [(False, "Choose a library root folder before applying.")]
    assert os.path.exists(a) and mw._rename_log().last_batch() is None


def test_colliding_destinations_are_numbered(tmp_path, monkeypatch):
    root = tmp_path / "library"
    root.mkdir()
    window, (a, b) = _window(tmp_path, "a.epub", "b.epub")
    app_settings.save_library_root(str(root))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *args, **kw: NO))
    _accept_in_move_mode(monkeypatch, "%authors%/%title%")
    window.open_rename_dialog()
    assert sorted(os.listdir(root / "Jane Doe")) == ["Test Book (2).epub", "Test Book.epub"]


def test_undo_last_rename_moves_everything_back(tmp_path, monkeypatch):
    root = tmp_path / "library"
    root.mkdir()
    window, (a, b) = _window(tmp_path, "a.epub", "b.epub")
    app_settings.save_library_root(str(root))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *args, **kw: YES))  # prune + undo + tidy
    _accept_in_move_mode(monkeypatch, "%authors%/%title%")
    window.open_rename_dialog()
    assert not os.path.exists(a) and not os.path.exists(b)

    window.undo_last_rename()

    assert os.path.exists(a) and os.path.exists(b)
    assert sorted(bk.path for bk in window.books) == sorted([a, b])
    assert not (root / "Jane Doe").exists()  # the folder the move created went with it
    assert mw._rename_log().last_batch() is None


def test_plain_rename_still_works_with_a_library_root_set(tmp_path, monkeypatch):
    window, (a,) = _window(tmp_path, "a.epub")
    app_settings.save_library_root(str(tmp_path / "library"))

    def fake_exec(dialog):
        dialog.pattern_edit.setText("%title%")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(mw.RenamePatternDialog, "exec", fake_exec)
    window.open_rename_dialog()
    assert os.path.exists(tmp_path / "Test Book.epub") and not os.path.exists(a)
    assert not (tmp_path / "library").exists()
