"""Tests for the per-field overwrite-review wiring in MainWindow's
three metadata-lookup handlers (open_calibre_lookup_dialog,
open_google_books_dialog, open_open_library_dialog). Each now funnels
its found changes through redactor_common.gui.overwrite_review_dialog.
resolve_overwrite_conflicts() before applying anything, instead of
applying one whole book's worth of found fields on a single checkbox.

This is the actual fix for a real reported bug: Calibre's own
fetch-ebook-metadata frequently returns a placeholder
file-as="Unknown" for Author Sort alongside otherwise-good fields
(narrowly patched around the "Unknown" string itself first, see
core/calibre_lookup.py) -- with per-field review, ANY bad field found
by ANY lookup source can be rejected individually instead of forcing
an all-or-nothing choice on the whole book.

The real lookup dialogs (CalibreLookupDialog/GoogleBooksDialog/
OpenLibraryDialog) do real subprocess/network work in their own
constructors, so these tests replace the dialog CLASS itself (as
referenced in gui.main_window's own module namespace) with a
lightweight stand-in returning whatever a test configures -- never
constructing (or exec()ing) the real thing. OverwriteReviewDialog's
own exec() is faked via monkeypatching instead (never actually shown),
same reasoning -- but its accepted_changes() is exercised for REAL, so
the actual default-checked business logic (a safe fill starts ticked,
a real overwrite starts unticked) is what's under test, not a mocked
stand-in for it."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from PyQt6.QtWidgets import QApplication, QDialog  # noqa: E402

import gui.main_window as mw  # noqa: E402
from core.epub_metadata import EpubBook, EpubMetadata  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402
from redactor_common.gui.overwrite_review_dialog import OverwriteReviewDialog  # noqa: E402

# A QApplication is required to construct any QWidget (including
# MainWindow and the review dialog) -- created once per test session.
_app = QApplication.instance() or QApplication(sys.argv)


def _fake_book(path: str = "/x/fake.epub", **metadata_kwargs) -> EpubBook:
    """Bypasses EpubBook.__init__ (which loads a real zip file) --
    every attribute any code path under test actually reads is set
    directly instead, same bypass-__new__ approach cbzredactor's own
    equivalent test file uses for CbzBook."""
    book = EpubBook.__new__(EpubBook)
    book.path = path
    book.load_error = None
    book.save_error = ""
    book.dirty = False
    book.cover_bytes = None
    book.cover_mime = ""
    book.cover_changed = False
    book.cover_removed = False
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
    """A stand-in for CalibreLookupDialog's shape: one accepted_changes()
    accessor, one checkbox per book."""

    class _Fake(QDialog):
        def __init__(self, books, parent=None):
            super().__init__(parent)

        def exec(self):
            return exec_result

        def accepted_changes(self):
            return accepted_changes

    return _Fake


def _fake_metadata_cover_dialog_class(
    *, accepted_metadata: dict, accepted_covers: dict, exec_result=QDialog.DialogCode.Accepted
):
    """A stand-in for GoogleBooksDialog/OpenLibraryDialog's shape:
    separate accepted_metadata()/accepted_covers() accessors."""

    class _Fake(QDialog):
        def __init__(self, books, parent=None):
            super().__init__(parent)

        def exec(self):
            return exec_result

        def accepted_metadata(self):
            return accepted_metadata

        def accepted_covers(self):
            return accepted_covers

    return _Fake


def _window_with_books(*books: EpubBook) -> MainWindow:
    window = MainWindow()
    window.books = list(books)
    window._rebuild_table()
    return window


def _patched(module, name, value):
    """Returns (restore_fn,) after replacing module.name with value --
    plain save/restore, since this project's test suite is script-style
    (assert + print(PASS)), not pytest, so no monkeypatch fixture."""
    original = getattr(module, name)
    setattr(module, name, value)

    def restore():
        setattr(module, name, original)

    return restore


# ----------------------------------------------------------------------
# Look Up via Calibre
# ----------------------------------------------------------------------

def test_calibre_no_conflict_applies_without_prompting():
    """The real reported bug's SAFE case: a blank field getting filled
    in should never even show the review dialog."""
    book = _fake_book(title="", author_sort_str="")
    window = _window_with_books(book)

    restore_dialog = _patched(
        mw, "CalibreLookupDialog",
        _fake_dialog_class(accepted_changes={0: {"title": "The Hobbit", "author_sort_str": "Tolkien, J.R.R."}}),
    )
    restore_review_exec = _patched(
        OverwriteReviewDialog, "exec", lambda self: (_ for _ in ()).throw(AssertionError("should not prompt"))
    )
    try:
        window.open_calibre_lookup_dialog()
    finally:
        restore_dialog()
        restore_review_exec()

    assert book.metadata.title == "The Hobbit"
    assert book.metadata.author_sort_str == "Tolkien, J.R.R."
    print("PASS: filling in previously-blank fields never prompts the overwrite review")


def test_calibre_conflict_prompts_and_unticked_field_is_rejected():
    """The actual bug this whole mechanism fixes: Calibre found a good
    title AND a bad (placeholder) Author Sort for the same book. The
    good field (blank -> value) should apply; the bad one (real
    overwrite of a different existing value) should NOT, by default --
    exercised through the REAL OverwriteReviewDialog.accepted_changes()
    business logic, only its exec() popup is faked."""
    book = _fake_book(title="", author_sort_str="Doe, Jane")
    window = _window_with_books(book)

    restore_dialog = _patched(
        mw, "CalibreLookupDialog",
        _fake_dialog_class(accepted_changes={
            0: {"title": "New Title", "author_sort_str": "Unknown-ish"},
        }),
    )
    restore_review_exec = _patched(OverwriteReviewDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    try:
        window.open_calibre_lookup_dialog()
    finally:
        restore_dialog()
        restore_review_exec()

    assert book.metadata.title == "New Title", book.metadata.title
    assert book.metadata.author_sort_str == "Doe, Jane", book.metadata.author_sort_str
    print("PASS: a genuine overwrite is rejected by default even when the rest of the same book's changes apply")


def test_calibre_cancelling_review_applies_nothing():
    book = _fake_book(title="", author_sort_str="Doe, Jane")
    window = _window_with_books(book)

    restore_dialog = _patched(
        mw, "CalibreLookupDialog",
        _fake_dialog_class(accepted_changes={
            0: {"title": "New Title", "author_sort_str": "Unknown-ish"},
        }),
    )
    restore_review_exec = _patched(OverwriteReviewDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    try:
        window.open_calibre_lookup_dialog()
    finally:
        restore_dialog()
        restore_review_exec()

    assert book.metadata.title == "", book.metadata.title
    assert book.metadata.author_sort_str == "Doe, Jane", book.metadata.author_sort_str
    print("PASS: cancelling the overwrite review applies nothing at all, not even the non-conflicting fields")


# ----------------------------------------------------------------------
# Google Books / Open Library (metadata + separate cover changes)
# ----------------------------------------------------------------------

def test_google_books_metadata_conflict_does_not_block_cover_apply():
    """Covers are a separate, visual thing -- not reviewed field-by-field.
    A metadata conflict resolved via the review dialog should still let
    an independently-accepted cover change through."""
    book = _fake_book(title="Existing Title")
    window = _window_with_books(book)

    restore_dialog = _patched(
        mw, "GoogleBooksDialog",
        _fake_metadata_cover_dialog_class(
            accepted_metadata={0: {"title": "Different Title"}},
            accepted_covers={0: (b"fake-image-bytes", "image/png")},
        ),
    )
    restore_review_exec = _patched(OverwriteReviewDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    try:
        window.open_google_books_dialog()
    finally:
        restore_dialog()
        restore_review_exec()

    # The only field offered was a genuine overwrite -> unticked by
    # default -> title stays as it was...
    assert book.metadata.title == "Existing Title", book.metadata.title
    # ...but the cover, never part of the per-field review, still applies.
    assert book.cover_bytes == b"fake-image-bytes"
    print("PASS: a rejected metadata field doesn't block an independently-accepted cover change")


def test_open_library_cancelling_review_blocks_cover_too():
    """Cancelling the review dialog outright means the whole Apply is
    abandoned -- including the cover change, not just metadata."""
    book = _fake_book(title="Existing Title")
    window = _window_with_books(book)

    restore_dialog = _patched(
        mw, "OpenLibraryDialog",
        _fake_metadata_cover_dialog_class(
            accepted_metadata={0: {"title": "Different Title"}},
            accepted_covers={0: (b"fake-image-bytes", "image/png")},
        ),
    )
    restore_review_exec = _patched(OverwriteReviewDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    try:
        window.open_open_library_dialog()
    finally:
        restore_dialog()
        restore_review_exec()

    assert book.metadata.title == "Existing Title", book.metadata.title
    assert book.cover_bytes is None
    print("PASS: cancelling the overwrite review also blocks an independently-accepted cover change")


if __name__ == "__main__":
    test_calibre_no_conflict_applies_without_prompting()
    test_calibre_conflict_prompts_and_unticked_field_is_rejected()
    test_calibre_cancelling_review_applies_nothing()
    test_google_books_metadata_conflict_does_not_block_cover_apply()
    test_open_library_cancelling_review_blocks_cover_too()
    print("\nALL MAIN WINDOW OVERWRITE-REVIEW TESTS PASSED")
