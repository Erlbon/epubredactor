"""Typed-but-unapplied edits in the bulk-edit panel are never lost when the table selection changes: they are applied
to the PREVIOUS selection through the normal Apply path (one undo entry, a status-bar message), then the new
selection is loaded. Real MainWindow, offscreen."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from gui.main_window import MainWindow  # noqa: E402
from test_epub_duplicates import make_epub  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))


def _window(tmp_path, names=("a.epub", "b.epub", "c.epub")):
    win = MainWindow()
    win.resize(1500, 900)
    win.show()
    win._load_paths([make_epub(tmp_path, n, title=f"Old {n}") for n in names])
    _app.processEvents()
    return win


def _book(window, name):
    return next(b for b in window.books if os.path.basename(b.path) == name)


def _select(window, *names):
    window._select_books([_book(window, n) for n in names])
    _app.processEvents()


def _type_publisher(window, text):
    editor = window.tag_panel._editors["publisher"]
    editor.setText(text)
    editor.textEdited.emit(text)
    assert window.tag_panel._checkboxes["publisher"].isChecked()


def test_selection_change_applies_pending_edit_to_the_previous_selection_with_one_undo(tmp_path):
    window = _window(tmp_path)
    _select(window, "a.epub", "b.epub")
    _type_publisher(window, "Pending House")
    assert not window.undo_manager.can_undo()

    _select(window, "c.epub")

    a, b, c = (_book(window, n) for n in ("a.epub", "b.epub", "c.epub"))
    assert a.metadata.publisher == "Pending House" and b.metadata.publisher == "Pending House"
    assert c.metadata.publisher != "Pending House"
    assert a.dirty and b.dirty and not c.dirty
    # the panel now shows C, with nothing ticked
    assert window.tag_panel._current_books == [c]
    assert not window.tag_panel._checkboxes["publisher"].isChecked()

    window.on_undo()  # ONE undo restores both books
    assert a.metadata.publisher != "Pending House" and b.metadata.publisher != "Pending House"
    assert not window.undo_manager.can_undo()
    window.close()


def test_status_bar_says_how_many_books_got_the_pending_edits(tmp_path):
    window = _window(tmp_path)
    _select(window, "a.epub", "b.epub")
    _type_publisher(window, "Pending House")
    _select(window, "c.epub")
    assert window.status.currentMessage() == "Applied pending edits to 2 books"
    window.close()


def test_no_auto_apply_when_the_previous_selection_was_empty(tmp_path):
    window = _window(tmp_path)
    window.table.clearSelection()
    _app.processEvents()
    _type_publisher(window, "Nobody Gets This")
    window.status.clearMessage()
    _select(window, "c.epub")
    assert all(b.metadata.publisher != "Nobody Gets This" for b in window.books)
    assert not any(b.dirty for b in window.books)
    assert not window.undo_manager.can_undo()
    assert window.status.currentMessage() == ""
    window.close()


def test_nothing_ticked_or_unchanged_values_make_no_undo_entry_and_no_message(tmp_path):
    window = _window(tmp_path)
    _select(window, "a.epub")
    window.status.clearMessage()
    _select(window, "b.epub")  # nothing ticked
    assert not window.undo_manager.can_undo()
    title_editor = window.tag_panel._editors["title"]
    title_editor.setText("Old b.epub")  # what is already there
    title_editor.textEdited.emit("Old b.epub")
    assert window.tag_panel._checkboxes["title"].isChecked()
    _select(window, "c.epub")
    assert not window.undo_manager.can_undo()
    assert not any(b.dirty for b in window.books)
    assert window.status.currentMessage() == ""
    window.close()


def test_a_refresh_of_the_same_selection_keeps_the_pending_edit_pending(tmp_path):
    """Undo, a rebuild, or any operation that re-reads the selection into the panel keeps what was typed (still
    ticked, not applied), so nothing is lost and nothing is applied on top of the operation behind your back."""
    window = _window(tmp_path)
    _select(window, "a.epub", "b.epub")
    _type_publisher(window, "Still Pending")
    window._rebuild_table()
    window._on_selection_changed()
    _app.processEvents()
    panel = window.tag_panel
    assert panel._checkboxes["publisher"].isChecked()
    assert panel._editors["publisher"].text() == "Still Pending"
    assert not window.undo_manager.can_undo()
    _select(window, "c.epub")
    assert _book(window, "a.epub").metadata.publisher == "Still Pending"
    window.close()


def _record_questions(monkeypatch, answer):
    asked = []

    def question(*args, **kwargs):
        asked.append(args[2] if len(args) > 2 else "")
        return answer
    monkeypatch.setattr(QMessageBox, "question", staticmethod(question))
    return asked


@pytest.mark.parametrize("command", ["refresh_list", "clear_list"])
def test_list_commands_ask_about_pending_edits_and_keep_them_when_cancelled(tmp_path, monkeypatch, command):
    """Refresh List / Clear List with only a typed, not Applied edit: it is applied first (undoable), so it counts
    as an unsaved change in the "discard?" question; answering No loses nothing."""
    window = _window(tmp_path)
    _select(window, "a.epub", "b.epub")
    _type_publisher(window, "Asked About")
    asked = _record_questions(monkeypatch, QMessageBox.StandardButton.No)
    getattr(window, command)()
    assert len(asked) == 1 and "unsaved changes" in asked[0]
    assert len(window.books) == 3
    a, b = _book(window, "a.epub"), _book(window, "b.epub")
    assert a.metadata.publisher == "Asked About" and b.metadata.publisher == "Asked About"
    assert a.dirty and b.dirty
    window.on_undo()
    assert a.metadata.publisher != "Asked About"
    window.close()


@pytest.mark.parametrize("command", ["refresh_list", "clear_list"])
def test_list_commands_without_pending_edits_ask_nothing(tmp_path, monkeypatch, command):
    window = _window(tmp_path)
    _select(window, "a.epub", "b.epub")
    asked = _record_questions(monkeypatch, QMessageBox.StandardButton.No)
    getattr(window, command)()
    assert asked == []
    assert not window.undo_manager.can_undo()
    window.close()


def test_quitting_asks_about_pending_edits(tmp_path, monkeypatch):
    window = _window(tmp_path)
    _select(window, "a.epub")
    _type_publisher(window, "Do Not Lose Me")
    asked = _record_questions(monkeypatch, QMessageBox.StandardButton.No)
    window.close()
    assert len(asked) == 1 and window.isVisible()
    assert _book(window, "a.epub").metadata.publisher == "Do Not Lose Me"
    for book in window.books:
        book.dirty = False
    window.close()


def test_remove_from_list_drops_pending_edits_for_the_removed_books_without_an_undo_entry(tmp_path):
    window = _window(tmp_path)
    _select(window, "a.epub", "b.epub")
    _type_publisher(window, "Gone Too")
    window.remove_selected()
    _app.processEvents()
    assert [os.path.basename(b.path) for b in window.books] == ["c.epub"]
    assert _book(window, "c.epub").metadata.publisher != "Gone Too"
    assert not window.undo_manager.can_undo()
    window.close()
