"""Redact in the main window: menu/toolbar entries, target choice (selection
or all after asking), the run through redactor_common's run_redact, reload
of what was written, the cleared Undo stack, and Edit Redact Recipe."""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(__file__))

from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox, QToolBar  # noqa: E402

import gui.main_window as mw  # noqa: E402
from core.epub_metadata import EpubBook  # noqa: E402
from core.redact_steps import RedactEnv, build_catalogue  # noqa: E402
from gui import app_settings  # noqa: E402
from redactor_common.core.pipeline import FileStatus, Recipe  # noqa: E402
from redactor_common.gui.background_call import call_in_background  # noqa: E402
from test_redact_steps import GEN_COVER, Trash, make_epub, quiet_lookups  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)
YES = QMessageBox.StandardButton.Yes


def _window(tmp_path, monkeypatch, *paths):
    window = mw.MainWindow()
    window.books = [EpubBook(p) for p in paths]
    window._rebuild_table()
    trash = Trash(str(tmp_path) + "-bin")
    env = RedactEnv(trash=trash, lookups=quiet_lookups(), make_cover=lambda *a: GEN_COVER)
    monkeypatch.setattr(window, "_redact_env", lambda: env)
    shown = []
    monkeypatch.setattr(mw.RedactResultsDialog, "exec", lambda self: shown.append(self) or 0)
    return window, env, trash, shown


def test_redact_is_in_the_edit_menu_and_the_toolbar():
    window = mw.MainWindow()
    assert window.redact_act.shortcut().toString() == "Ctrl+Shift+E"
    toolbar_actions = [a for bar in window.findChildren(QToolBar) for a in bar.actions()]
    assert window.redact_act in toolbar_actions
    edit = next(a.menu() for a in window.menuBar().actions() if a.text() == "&Edit")
    texts = [a.text() for a in edit.actions()]
    assert "Redac&t" in texts and "&Edit Redact Recipe…" in texts


def test_nothing_selected_asks_then_redacts_all_and_reloads(tmp_path, monkeypatch):
    a = make_epub(str(tmp_path / "a.epub"), dup_ids=True)
    b = make_epub(str(tmp_path / "b.epub"), dup_ids=True)
    window, env, trash, shown = _window(tmp_path, monkeypatch, a, b)
    asked = []
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda parent, title, text, *rest: asked.append(text) or YES))
    window._push_undo("edit", window.books)  # an Undo entry that must not survive the run
    old_books = list(window.books)

    window.redact_books()

    assert "Redact all 2 loaded book(s)?" in asked[0]
    assert len(trash.trashed) == 2
    assert all(not EpubBook(p).find_duplicate_manifest_ids() for p in (a, b))
    assert len(window.books) == 2 and all(n is not o for n, o in zip(window.books, old_books))  # re-read
    assert all(not bk.find_duplicate_manifest_ids() for bk in window.books)
    assert not window.undo_act.isEnabled() and not window.redo_act.isEnabled()
    assert not window.undo_manager.can_undo()
    dialog = shown[0]
    assert dialog.report.count(FileStatus.CHANGED) == 2
    assert "Recycle Bin" in dialog.header_label.text()
    assert window.table.rowCount() == 2


def test_only_the_selection_is_redacted_and_unsaved_books_are_skipped(tmp_path, monkeypatch):
    a = make_epub(str(tmp_path / "a.epub"), dup_ids=True)
    b = make_epub(str(tmp_path / "b.epub"), dup_ids=True)
    c = make_epub(str(tmp_path / "c.epub"), dup_ids=True)
    window, env, trash, shown = _window(tmp_path, monkeypatch, a, b, c)
    asked = []
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda parent, title, text, *rest: asked.append(title) or YES))
    window.books[1].apply_metadata({"title": "Edited"})  # unsaved in the list
    window._select_books([window.books[0], window.books[1]])

    window.redact_books()

    assert asked == ["Unsaved changes"]  # no "redact all?" question: there was a selection
    report = shown[0].report
    assert {e.file: e.status for e in report.entries} == {"a.epub": FileStatus.CHANGED, "b.epub": FileStatus.SKIPPED}
    assert len(trash.trashed) == 1
    assert EpubBook(c).find_duplicate_manifest_ids()  # not selected: untouched
    assert EpubBook(b).find_duplicate_manifest_ids()  # skipped: untouched
    assert window.books[1].dirty and window.books[1].metadata.title == "Edited"  # in-memory edit kept
    assert len(window._selected_rows()) == 2  # the selection survives the reload


def test_declining_the_question_does_nothing(tmp_path, monkeypatch):
    a = make_epub(str(tmp_path / "a.epub"), dup_ids=True)
    window, env, trash, shown = _window(tmp_path, monkeypatch, a)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *args, **kw: QMessageBox.StandardButton.Cancel))
    window.redact_books()
    assert trash.trashed == [] and shown == []


def test_a_renaming_run_updates_the_row_paths(tmp_path, monkeypatch):
    a = make_epub(str(tmp_path / "orig.epub"))
    window, env, trash, shown = _window(tmp_path, monkeypatch, a)
    app_settings.save_pattern_used("%title%")  # a saved pattern turns the Rename step on
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *args, **kw: YES))
    window.redact_books()
    assert [os.path.basename(b.path) for b in window.books] == ["Test Book.epub"]
    assert os.path.exists(tmp_path / "Test Book.epub") and not os.path.exists(a)
    assert window.table.item(0, mw.FILENAME_COL).text() == "Test Book.epub"


def test_the_real_env_carries_the_app_settings(tmp_path, monkeypatch):
    window = mw.MainWindow()
    app_settings.save_library_root(str(tmp_path))
    app_settings.save_ascii_filenames(True)
    app_settings.save_rename_zero_pad(True, 3)
    env = window._redact_env()
    assert env.library_root == str(tmp_path) and env.ascii_only is True and env.zero_pad == (True, 3)
    assert env.net is call_in_background and env.make_cover is mw.generate_cover_image
    assert env.junk_hashes is window._junk_cover_hashes


def test_edit_redact_recipe_stores_the_result(monkeypatch):
    window = mw.MainWindow()
    edited = Recipe.default_for(build_catalogue())
    edited.enabled["cover"] = False
    edited.confidence_threshold = 0.8
    monkeypatch.setattr(mw.RecipeEditorDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(mw.RecipeEditorDialog, "recipe", lambda self: edited)
    window.edit_redact_recipe()
    saved = window._redact_recipe()
    assert saved.enabled["cover"] is False and saved.confidence_threshold == 0.8
    # cancelled edits are not stored
    monkeypatch.setattr(mw.RecipeEditorDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    monkeypatch.setattr(mw.RecipeEditorDialog, "recipe", lambda self: Recipe())
    window.edit_redact_recipe()
    assert window._redact_recipe().confidence_threshold == 0.8
