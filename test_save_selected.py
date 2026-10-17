"""Right-click > Save Selected (N): saves only the selected books that have unsaved changes, through the same flow
as File > Save All (confirmation, progress, failure box); greyed when none of the selection is changed; a failing
book does not block the others."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PyQt6.QtCore import QPoint  # noqa: E402
from PyQt6.QtWidgets import QApplication, QMenu, QMessageBox  # noqa: E402

from core.epub_metadata import EpubBook, EpubError  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402
from test_epub_duplicates import make_epub  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def window(tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok))
    win = MainWindow()
    win.resize(1500, 600)
    win.show()
    win._load_paths([make_epub(tmp_path, n, title=f"Old {n}") for n in ("a.epub", "b.epub", "c.epub")])
    yield win
    for book in win.books:
        book.dirty = False
    win.close()


def _by_name(window, name):
    return next(b for b in window.books if os.path.basename(b.path) == name)


def _row_of(window, book):
    return next(r for r in range(window.table.rowCount()) if window._book_for_row(r) is book)


def _dirty(book, title):
    book.metadata.title = title
    book.dirty = True


def _title_on_disk(book):
    return EpubBook(book.path).metadata.title


def _select(window, books):
    window.table.clearSelection()
    sm = window.table.selectionModel()
    for book in books:
        sm.select(window.table.model().index(_row_of(window, book), 0), sm.SelectionFlag.Select | sm.SelectionFlag.Rows)
    _app.processEvents()


def _open_menu(window, books):
    _select(window, books)
    row = _row_of(window, books[0])
    shown = []
    original = QMenu.exec
    QMenu.exec = lambda self, *a: shown.extend(self.actions())
    try:
        window._show_table_context_menu(QPoint(5, window.table.rowViewportPosition(row) + 5))
    finally:
        QMenu.exec = original
    return shown


def _save_action(actions):
    return next(a for a in actions if a.text().startswith("Save Selected"))


def test_count_counts_only_changed_selected_books(window):
    a, b, c = (_by_name(window, n) for n in ("a.epub", "b.epub", "c.epub"))
    _dirty(a, "New A")
    _dirty(c, "New C")
    action = _save_action(_open_menu(window, [a, b]))
    assert action.text() == "Save Selected (1)" and action.isEnabled()


def test_menu_item_saves_only_the_selected_changed_books(window):
    a, b, c = (_by_name(window, n) for n in ("a.epub", "b.epub", "c.epub"))
    for book, title in ((a, "New A"), (b, "New B"), (c, "New C")):
        _dirty(book, title)
    _save_action(_open_menu(window, [a, b])).trigger()
    assert _title_on_disk(a) == "New A" and _title_on_disk(b) == "New B"
    assert _title_on_disk(c) == "Old c.epub"  # not selected: untouched on disk
    assert not a.dirty and not b.dirty
    assert c.dirty  # and still changed in the list


def test_greyed_when_nothing_selected_is_changed(window):
    a, b, c = (_by_name(window, n) for n in ("a.epub", "b.epub", "c.epub"))
    _dirty(c, "New C")
    action = _save_action(_open_menu(window, [a, b]))
    assert action.text() == "Save Selected (0)" and not action.isEnabled()
    assert action.toolTip() == "The selected files have no unsaved changes"


def test_a_failing_book_does_not_block_the_others_and_shows_the_failure_box(window, monkeypatch):
    a, b, c = (_by_name(window, n) for n in ("a.epub", "b.epub", "c.epub"))
    for book in (a, b, c):
        _dirty(book, "New " + os.path.basename(book.path))
    real_save = EpubBook.save

    def flaky(self, *args, **kwargs):
        if self.path.endswith("b.epub"):
            raise EpubError("disk says no")
        return real_save(self, *args, **kwargs)

    monkeypatch.setattr(EpubBook, "save", flaky)
    boxes = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda parent, title, text, *x: boxes.append((title, text))))
    window.save_selected_books([a, b, c])
    assert _title_on_disk(a) == "New a.epub" and _title_on_disk(c) == "New c.epub"
    assert _title_on_disk(b) == "Old b.epub"
    assert b.dirty and b.save_error
    assert len(boxes) == 1 and boxes[0][0] == "Some files failed to save"
    assert "b.epub" in boxes[0][1] and "1 of 3" not in boxes[0][1] and "2 of 3 saved" in boxes[0][1]
