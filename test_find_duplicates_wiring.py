"""Repair > Find Duplicates in the main window: the menu entry, that it
reviews ALL loaded books, the dialog hooks (select in list, removal after a
trash) and the guard that never trashes a book with unsaved edits."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from PyQt6.QtWidgets import QApplication  # noqa: E402

import gui.main_window as mw  # noqa: E402
from core.epub_duplicates import COLUMNS, find_duplicate_groups  # noqa: E402
from core.epub_metadata import EpubBook  # noqa: E402
from redactor_common.core import labels  # noqa: E402
from redactor_common.core.trash import TrashError  # noqa: E402
from redactor_common.gui.standard_menus import get_action_registry  # noqa: E402
from test_epub_duplicates import make_epub  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def captured(monkeypatch, tmp_path):
    """Replaces the review flow with a recorder of how the window calls it."""
    calls = []
    trashed_paths = []
    monkeypatch.setattr(mw, "run_find_duplicates", lambda *args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.setattr(mw, "move_to_trash", lambda path: trashed_paths.append(path))
    monkeypatch.setattr(mw, "_duplicates_dismissed_path", lambda: str(tmp_path / "dismissed.json"))
    return calls, trashed_paths


def _window(tmp_path, count=3):
    window = mw.MainWindow()
    paths = [make_epub(tmp_path, f"{i}.epub", title="Same", authors=("A A",), body=f"b{i}") for i in range(count)]
    window.books = [EpubBook(p) for p in paths]
    window._rebuild_table()
    return window


def test_menu_entry_is_in_repair_with_the_reserved_mnemonic():
    window = mw.MainWindow()
    action = get_action_registry(window)["find_duplicates"]
    assert action.text() == labels.FIND_DUPLICATES_ALT == "Find D&uplicates…"
    assert "Repair" in get_action_registry(window).path_of("find_duplicates")


def test_acts_on_all_loaded_books_not_just_the_selection(tmp_path, captured):
    calls, _ = captured
    window = _window(tmp_path)
    window.table.selectRow(0)
    window.find_duplicates()
    (args, kwargs), = calls
    assert args[1] == window.books                  # everything, not the one selected row
    assert args[2] is find_duplicate_groups and args[3] == COLUMNS
    assert kwargs["dismiss_store"].path.endswith("dismissed.json")


def test_needs_two_books(tmp_path, captured):
    calls, _ = captured
    window = mw.MainWindow()
    window.find_duplicates()
    assert calls == []


def test_dialog_hooks_select_in_list_and_remove_trashed(tmp_path, captured):
    calls, trashed_paths = captured
    window = _window(tmp_path)
    window.find_duplicates()
    kwargs = calls[0][1]

    kwargs["on_select_in_list"]([window.books[1], window.books[2]])
    selected = {id(b) for b in window._books_for_rows(window._selected_rows())}
    assert selected == {id(window.books[1]), id(window.books[2])}

    gone = window.books[0]
    kwargs["trash"](gone.path)
    assert trashed_paths == [gone.path]
    kwargs["on_trashed"]([gone])
    assert gone not in window.books and len(window.books) == 2
    assert window.table.rowCount() == 2


def test_a_book_with_unsaved_edits_is_never_trashed(tmp_path, captured):
    calls, trashed_paths = captured
    window = _window(tmp_path)
    window.books[0].dirty = True
    window.find_duplicates()
    kwargs = calls[0][1]
    assert "unsaved" in kwargs["intro_text"]
    with pytest.raises(TrashError, match="unsaved"):
        kwargs["trash"](window.books[0].path)
    assert trashed_paths == []
    kwargs["trash"](window.books[1].path)           # a clean one still goes
    assert trashed_paths == [window.books[1].path]


def test_dismissal_file_is_next_to_the_settings_and_not_a_setting(monkeypatch, tmp_path):
    monkeypatch.setattr(mw, "base_dir", lambda: str(tmp_path))
    assert mw._duplicates_dismissed_path() == str(tmp_path / "epubredactor_duplicates_dismissed.json")


def test_shared_dialog_shows_the_groups_with_nothing_selected(tmp_path):
    from redactor_common.gui.duplicates_dialog import DuplicatesDialog

    window = _window(tmp_path)
    groups = find_duplicate_groups(window.books)
    dialog = DuplicatesDialog(groups, COLUMNS, window)
    assert dialog.tree.topLevelItemCount() == 1
    assert dialog.selected_members() == []
