"""The Delete key asks Remove from List / Delete Files (Recycle Bin) / Cancel (Erlend, 2026-11-26: Delete only
took the book off the list, which is not what most people expect). Offscreen, tmp_path only."""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(__file__))

import pytest  # noqa: E402
from PyQt6.QtGui import QKeySequence  # noqa: E402
from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from redactor_common.gui.remove_or_delete import DELETE, REMOVE  # noqa: E402
from redactor_common.gui.standard_menus import get_action_registry  # noqa: E402

import gui.main_window as mw  # noqa: E402

_app = QApplication.instance() or QApplication([])


@pytest.fixture
def window(tmp_path):
    from core.epub_metadata import EpubBook
    from test_review_fixes import build

    w = mw.MainWindow()
    w.books = [EpubBook(build(tmp_path / f"{n}.epub")) for n in "ab"]
    w._rebuild_table()
    return w


def test_delete_key_is_the_question_and_remove_from_list_has_no_shortcut(window):
    reg = get_action_registry(window)
    assert reg["remove_or_delete"].shortcut() == QKeySequence("Delete")
    assert reg["remove_from_list"].shortcut().isEmpty()
    assert reg["delete_files"].shortcut() == QKeySequence("Shift+Delete")


def _select_all(window):
    window.table.selectAll()


def test_answer_remove_takes_the_books_off_the_list_and_keeps_the_files(window, monkeypatch):
    _select_all(window)
    paths = [b.path for b in window.books]
    monkeypatch.setattr(mw, "ask_remove_or_delete", lambda *a, **k: REMOVE)
    window.on_delete_key()
    assert window.books == [] and all(os.path.exists(p) for p in paths)


def test_answer_delete_trashes_without_a_second_question(window, monkeypatch):
    _select_all(window)
    paths = [b.path for b in window.books]
    trashed = []
    monkeypatch.setattr(mw, "ask_remove_or_delete", lambda *a, **k: DELETE)
    monkeypatch.setattr(mw, "move_to_trash", lambda p: (trashed.append(p), os.remove(p)))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: pytest.fail("asked twice"))
    window.on_delete_key()
    assert sorted(trashed) == sorted(paths) and window.books == []


def test_cancel_changes_nothing(window, monkeypatch):
    _select_all(window)
    before = list(window.books)
    monkeypatch.setattr(mw, "ask_remove_or_delete", lambda *a, **k: None)
    monkeypatch.setattr(mw, "move_to_trash", lambda p: pytest.fail("trashed on Cancel"))
    window.on_delete_key()
    assert window.books == before


def test_nothing_selected_asks_nothing(window, monkeypatch):
    window.table.clearSelection()
    monkeypatch.setattr(mw, "ask_remove_or_delete", lambda *a, **k: pytest.fail("asked with nothing selected"))
    window.on_delete_key()
    assert "select the books" in window.status.currentMessage()


def test_the_menu_item_still_confirms_on_its_own(window, monkeypatch):
    _select_all(window)
    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: (asked.append(a[1]), QMessageBox.StandardButton.No)[1])
    window.delete_files()
    assert asked == ["Delete Files (Recycle Bin)?"] and len(window.books) == 2
