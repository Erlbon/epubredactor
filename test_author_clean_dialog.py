"""Clean Up Authors dialog (rows, ticking, exclusivity) and its MainWindow wiring."""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(__file__))

from PyQt6.QtWidgets import QApplication, QDialog  # noqa: E402

import gui.main_window as mw  # noqa: E402
from gui.author_clean_dialog import KIND_FLAG, KIND_REVIEW, KIND_SAFE, AuthorCleanDialog, build_rows  # noqa: E402
from test_strip_description_html_wiring import _fake_book, _patched, _window_with_books  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)


def _book(path, authors, sort=()):
    return _fake_book(path, title="T", authors=list(authors), author_sort=list(sort))


def test_rows_split_safe_review_and_flag():
    safe_only = build_rows(0, _book("/x/a.epub", ["J.R.R.Tolkien"]))
    assert [r.kind for r in safe_only] == [KIND_SAFE]
    assert safe_only[0].new_authors == "J. R. R. Tolkien" and safe_only[0].new_sort == "Tolkien, J. R. R."

    both = build_rows(1, _book("/x/b.epub", ["Jane  Doe", "Simon & Schuster"], []))
    assert [r.kind for r in both] == [KIND_SAFE, KIND_REVIEW]
    assert both[0].new_authors == "Jane Doe; Simon & Schuster"      # guess not in the safe row
    assert both[1].new_authors == "Jane Doe; Simon; Schuster"       # included in the review row

    moved = build_rows(4, _book("/x/e.epub", ["van Gogh, Vincent"]))
    assert [r.kind for r in moved] == [KIND_SAFE]
    assert moved[0].new_authors == "Vincent van Gogh" and moved[0].new_sort == "van Gogh, Vincent"
    conflict = build_rows(5, _book("/x/f.epub", ["Tolkien, J. R. R."], ["Foo, Bar"]))
    assert KIND_REVIEW in [r.kind for r in conflict]

    flag = build_rows(2, _book("/x/c.epub", ["J. K. Rowling (Robert Galbraith)"]))
    assert [r.kind for r in flag] == [KIND_FLAG]

    assert build_rows(3, _book("/x/d.epub", ["Jane Doe"], ["Doe, Jane"])) == []


def test_dialog_ticks_safe_rows_only_and_keeps_one_row_per_book():
    books = [_book("/x/a.epub", ["J.R.R.Tolkien"]), _book("/x/b.epub", ["Jane Doe", "Simon & Schuster"]),
             _book("/x/c.epub", ["J. K. Rowling (Robert Galbraith)"]), _book("/x/d.epub", ["Jane Doe"], ["Doe, Jane"])]
    dialog = AuthorCleanDialog(books)
    assert [r.kind for r in dialog.rows] == [KIND_SAFE, KIND_SAFE, KIND_REVIEW, KIND_FLAG]
    assert set(dialog.accepted_changes()) == {0, 1}
    assert dialog.accepted_changes()[1]["authors_str"] == "Jane Doe; Simon & Schuster"

    review_row = 2
    dialog._checkboxes[review_row].setChecked(True)
    assert not dialog._checkboxes[1].isChecked()  # the review row replaces the book's safe row
    changes = dialog.accepted_changes()
    assert changes[1]["authors_str"] == "Jane Doe; Simon; Schuster"
    assert set(changes) == {0, 1}

    dialog._checkboxes[1].setChecked(True)
    assert not dialog._checkboxes[review_row].isChecked()


def test_nothing_to_do_disables_apply():
    dialog = AuthorCleanDialog([_book("/x/d.epub", ["Jane Doe"], ["Doe, Jane"])])
    assert dialog.rows == [] and not dialog._ok_button.isEnabled()


def _fake_dialog(changes, result=QDialog.DialogCode.Accepted):
    class _Fake(QDialog):
        def __init__(self, books, parent=None):
            super().__init__(parent)

        def exec(self):
            return result

        def accepted_changes(self):
            return changes

    return _Fake


def test_accepting_applies_through_the_edit_path_with_one_undo_entry():
    book = _book("/x/a.epub", ["J.R.R.Tolkien"])
    window = _window_with_books(book)
    restore = _patched(mw, "AuthorCleanDialog", _fake_dialog(
        {0: {"authors_str": "J. R. R. Tolkien", "author_sort_str": "Tolkien, J. R. R."}}))
    try:
        window.open_author_clean_dialog()
    finally:
        restore()
    assert book.metadata.authors == ["J. R. R. Tolkien"] and book.metadata.author_sort == ["Tolkien, J. R. R."]
    assert book.dirty
    assert window.undo_manager.can_undo()
    window.on_undo()
    assert book.metadata.authors == ["J.R.R.Tolkien"] and book.metadata.author_sort == []


def test_cancelling_applies_nothing():
    book = _book("/x/a.epub", ["J.R.R.Tolkien"])
    window = _window_with_books(book)
    restore = _patched(mw, "AuthorCleanDialog", _fake_dialog(
        {0: {"authors_str": "X", "author_sort_str": "X"}}, QDialog.DialogCode.Rejected))
    try:
        window.open_author_clean_dialog()
    finally:
        restore()
    assert book.metadata.authors == ["J.R.R.Tolkien"] and not book.dirty and not window.undo_manager.can_undo()
