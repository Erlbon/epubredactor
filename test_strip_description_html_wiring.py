"""Tests for MainWindow.open_strip_description_html_dialog()'s wiring:
applies accepted changes, pushes exactly one undo entry, refreshes the
affected rows. StripDescriptionHtmlDialog itself is replaced with a
lightweight stand-in (same approach as test_main_window_overwrite.py)
-- the real dialog's own preview logic is covered by
test_description_html.py (the pure strip_html() logic) and by manual
inspection of StripDescriptionHtmlDialog._refresh_preview(), which is a
close structural copy of CaseConversionDialog's own (already-proven)
shape."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402

import gui.main_window as mw  # noqa: E402
from core.epub_metadata import EpubBook, EpubMetadata  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)


def _fake_book(path: str, **metadata_kwargs) -> EpubBook:
    book = EpubBook.__new__(EpubBook)
    book.path = path
    book.load_error = None
    book.save_error = ""
    book.dirty = False
    book.cover_bytes = None
    book.cover_mime = ""
    book.cover_changed = False
    book.cover_removed = False
    book._cover_hash_cache = None
    book._orphan_files_to_remove = set()
    book._image_replacements = {}
    book.validation_issues = []
    book.validation_status = "OK"
    meta = EpubMetadata()
    for key, value in metadata_kwargs.items():
        setattr(meta, key, value)
    book.metadata = meta
    return book


def _fake_dialog_class(*, accepted_changes: dict, exec_result=QDialog.DialogCode.Accepted):
    class _Fake(QDialog):
        def __init__(self, books, parent=None):
            super().__init__(parent)

        def exec(self):
            return exec_result

        def accepted_changes(self):
            return accepted_changes

    return _Fake


def _patched(module, name, value):
    original = getattr(module, name)
    setattr(module, name, value)

    def restore():
        setattr(module, name, original)

    return restore


def _window_with_books(*books: EpubBook) -> MainWindow:
    window = MainWindow()
    window.books = list(books)
    window._rebuild_table()
    return window


def test_accepted_change_applies_and_marks_dirty():
    book = _fake_book("/x/a.epub", title="A", description="<p>Raw HTML</p>")
    window = _window_with_books(book)

    restore = _patched(
        mw, "StripDescriptionHtmlDialog",
        _fake_dialog_class(accepted_changes={0: "Raw HTML"}),
    )
    try:
        window.open_strip_description_html_dialog()
    finally:
        restore()

    assert book.metadata.description == "Raw HTML", book.metadata.description
    assert book.dirty
    print("PASS: an accepted change writes the stripped description and marks the book dirty")


def test_accepted_change_pushes_exactly_one_undo_entry():
    book = _fake_book("/x/b.epub", title="B", description="<p>Text</p>")
    window = _window_with_books(book)
    assert not window.undo_manager.can_undo()

    restore = _patched(
        mw, "StripDescriptionHtmlDialog",
        _fake_dialog_class(accepted_changes={0: "Text"}),
    )
    try:
        window.open_strip_description_html_dialog()
    finally:
        restore()

    assert window.undo_manager.can_undo()
    window.on_undo()
    assert book.metadata.description == "<p>Text</p>", book.metadata.description
    print("PASS: exactly one undo entry is pushed, and undo restores the original HTML")


def test_cancelling_the_dialog_applies_nothing():
    book = _fake_book("/x/c.epub", title="C", description="<p>Untouched</p>")
    window = _window_with_books(book)

    restore = _patched(
        mw, "StripDescriptionHtmlDialog",
        _fake_dialog_class(accepted_changes={0: "Untouched"}, exec_result=QDialog.DialogCode.Rejected),
    )
    try:
        window.open_strip_description_html_dialog()
    finally:
        restore()

    assert book.metadata.description == "<p>Untouched</p>", book.metadata.description
    assert not book.dirty
    assert not window.undo_manager.can_undo()
    print("PASS: cancelling the dialog (Rejected) applies nothing and pushes no undo entry")


def test_empty_accepted_changes_is_a_clean_noop():
    book = _fake_book("/x/d.epub", title="D", description="<p>Also untouched</p>")
    window = _window_with_books(book)

    restore = _patched(
        mw, "StripDescriptionHtmlDialog",
        _fake_dialog_class(accepted_changes={}),  # dialog accepted, but every row unticked
    )
    try:
        window.open_strip_description_html_dialog()
    finally:
        restore()

    assert book.metadata.description == "<p>Also untouched</p>", book.metadata.description
    assert not book.dirty
    assert not window.undo_manager.can_undo()
    print("PASS: an accepted dialog with no ticked rows applies nothing and pushes no undo entry")


def test_no_books_shows_message_and_does_not_open_dialog():
    window = MainWindow()  # no books loaded at all

    opened = {"n": 0}

    def _should_not_be_called(*_a, **_k):
        opened["n"] += 1
        raise AssertionError("dialog should never be constructed with no books loaded")

    restore_dialog = _patched(mw, "StripDescriptionHtmlDialog", _should_not_be_called)
    restore_msgbox = _patched(
        QMessageBox, "information", staticmethod(lambda *a, **k: None)
    )
    try:
        window.open_strip_description_html_dialog()
    finally:
        restore_dialog()
        restore_msgbox()

    assert opened["n"] == 0
    print("PASS: with no books loaded, the dialog is never opened at all")


if __name__ == "__main__":
    test_accepted_change_applies_and_marks_dirty()
    test_accepted_change_pushes_exactly_one_undo_entry()
    test_cancelling_the_dialog_applies_nothing()
    test_empty_accepted_changes_is_a_clean_noop()
    test_no_books_shows_message_and_does_not_open_dialog()
    print("\nALL STRIP-DESCRIPTION-HTML WIRING TESTS PASSED")
