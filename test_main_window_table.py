"""Tests for MainWindow's table population -- specifically that a
multiline field's embedded newlines (e.g. a Description imported
verbatim from an EPUB's dc:description containing raw, newline-
separated HTML like "<div>\\n<p>...</p>\\n<p></p>...") never blow up a
row's height, even in a "fixed row height" text-overflow mode. Qt
renders a literal newline in cell text as a real line break regardless
of the table's word-wrap setting -- word wrap only controls whether
ONE long line breaks to fit the column width, it doesn't suppress
newlines already in the string. Real bug, reported after Truncate mode
still showed a multi-line-tall row for a book with an HTML-formatted
description."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from PyQt6.QtWidgets import QApplication  # noqa: E402

import gui.main_window as mw  # noqa: E402
from core.epub_metadata import EpubBook, EpubMetadata  # noqa: E402
from core.fields import FIELDS  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)

_DESC_COL = mw.FIRST_FIELD_COL + [key for key, _label, _m in FIELDS].index("description")


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
    book.metadata = EpubMetadata(**metadata_kwargs)
    return book


def test_field_display_text_collapses_whitespace_for_multiline_in_non_wrap_modes():
    window = MainWindow()
    window.set_text_overflow_mode("ellipsis")
    raw = "<div>\n<p>Line one</p>\n<p></p>\n<p>Line two</p>"
    assert window._field_display_text(raw, multiline=True) == \
        "<div> <p>Line one</p> <p></p> <p>Line two</p>"
    # A non-multiline field's value is passed through untouched, even
    # if it somehow contains embedded whitespace -- only Description
    # (the one field actually flagged multiline) gets collapsed.
    assert window._field_display_text("Weird\nTitle", multiline=False) == "Weird\nTitle"
    print("PASS: _field_display_text collapses whitespace only for multiline fields, "
          "outside Wrap Text mode")


def test_field_display_text_preserves_newlines_in_wrap_mode():
    window = MainWindow()
    window.set_text_overflow_mode("wrap")
    raw = "<div>\n<p>Line one</p>\n<p>Line two</p>"
    assert window._field_display_text(raw, multiline=True) == raw
    print("PASS: _field_display_text leaves a multiline field's real newlines alone in Wrap Text mode")


def test_field_display_text_handles_empty_string():
    window = MainWindow()
    window.set_text_overflow_mode("ellipsis")
    assert window._field_display_text("", multiline=True) == ""
    print("PASS: an empty value stays empty")


def test_html_description_does_not_grow_row_height_in_ellipsis_mode():
    window = MainWindow()
    window.set_text_overflow_mode("ellipsis")  # "Truncate with …" -- fixed row height

    plain = _fake_book("/x/plain.epub", title="Plain Book")
    html_desc = _fake_book(
        "/x/html.epub", title="HTML Desc Book",
        description="<div>\n<p>1942. The war began.</p>\n<p></p>\n<p>The invasion followed.</p>",
    )
    window.books = [plain, html_desc]
    window._rebuild_table()

    assert window.table.rowHeight(0) == window.table.rowHeight(1), (
        window.table.rowHeight(0), window.table.rowHeight(1),
    )
    print("PASS: a book with an HTML-formatted, newline-laden description gets the same "
          "fixed row height as a plain book in Truncate mode")


def test_underlying_description_metadata_is_never_mutated():
    window = MainWindow()
    window.set_text_overflow_mode("ellipsis")
    raw = "<div>\n<p>Some description</p>\n<p></p>\n<p>More text</p>"
    book = _fake_book("/x/html2.epub", title="Book", description=raw)
    window.books = [book]
    window._rebuild_table()

    displayed = window.table.item(0, _DESC_COL).text()
    assert displayed == "<div> <p>Some description</p> <p></p> <p>More text</p>", displayed
    assert book.metadata.description == raw, book.metadata.description
    print("PASS: the table's display normalization never touches the book's actual metadata")


def test_switching_modes_round_trips_the_description_cell():
    window = MainWindow()
    window.set_text_overflow_mode("wrap")
    raw = "<div>\n<p>Para one</p>\n<p>Para two</p>"
    book = _fake_book("/x/roundtrip.epub", title="Book", description=raw)
    window.books = [book]
    window._rebuild_table()
    assert window.table.item(0, _DESC_COL).text() == raw

    window.set_text_overflow_mode("clip")
    assert window.table.item(0, _DESC_COL).text() == "<div> <p>Para one</p> <p>Para two</p>"

    window.set_text_overflow_mode("wrap")
    assert window.table.item(0, _DESC_COL).text() == raw
    print("PASS: switching Wrap -> Clip -> Wrap round-trips the Description cell's text cleanly")


def test_switching_modes_never_mutates_metadata_or_pushes_undo():
    # The real bug caught above: _refresh_multiline_field_cells()'s own
    # item.setText() calls fire itemChanged, which -- unguarded -- write
    # straight back into book.metadata AND push an undo entry, treating
    # a display-only refresh as a genuine user edit. Assert both effects
    # are absent directly, not just that the cell shows the right text.
    window = MainWindow()
    window.set_text_overflow_mode("wrap")
    raw = "<div>\n<p>Para one</p>\n<p>Para two</p>"
    book = _fake_book("/x/nomutate.epub", title="Book", description=raw)
    window.books = [book]
    window._rebuild_table()
    assert not window.undo_manager.can_undo()

    window.set_text_overflow_mode("clip")
    assert book.metadata.description == raw, book.metadata.description
    assert not book.dirty
    assert not window.undo_manager.can_undo()

    window.set_text_overflow_mode("wrap")
    assert book.metadata.description == raw, book.metadata.description
    assert not book.dirty
    assert not window.undo_manager.can_undo()
    print("PASS: switching text-overflow modes never mutates book metadata, "
          "marks dirty, or pushes an undo entry")


def test_wrap_mode_still_shows_raw_multiline_text():
    # Wrap mode's whole point is to show everything, growing the row --
    # collapsing newlines there too isn't necessary and isn't done.
    window = MainWindow()
    window.set_text_overflow_mode("wrap")
    raw = "<div>\n<p>Line one</p>\n<p>Line two</p>"
    book = _fake_book("/x/wrap.epub", title="Book", description=raw)
    window.books = [book]
    window._rebuild_table()
    displayed = window.table.item(0, _DESC_COL).text()
    assert displayed == raw, displayed
    print("PASS: Wrap Text mode still shows the description's real newlines, unmodified")


def test_refresh_rows_full_is_efficient_for_a_large_batch():
    # Real bug, found profiling a reported "freezing while adding
    # languages" complaint: several batch-apply handlers refreshed each
    # affected book's row via a per-book loop of _refresh_row_full(),
    # which internally re-derives its row via _find_row_for_book()'s
    # O(row count) scan on EVERY call -- O(n^2) overall for a large
    # batch, the exact same shape of bug _on_cover_icon_ready() had
    # before it was fixed earlier. _refresh_rows_full() must build the
    # book->row map via _rows_by_book() exactly ONCE for the whole
    # batch, not call _find_row_for_book() at all.
    window = MainWindow()
    books = [_fake_book(f"/x/book{i}.epub", title=f"Book {i}") for i in range(200)]
    window.books = books
    window._rebuild_table()

    rows_by_book_calls = {"n": 0}
    find_row_calls = {"n": 0}
    orig_rows_by_book = window._rows_by_book
    orig_find_row = window._find_row_for_book

    def counting_rows_by_book():
        rows_by_book_calls["n"] += 1
        return orig_rows_by_book()

    def counting_find_row(book):
        find_row_calls["n"] += 1
        return orig_find_row(book)

    window._rows_by_book = counting_rows_by_book
    window._find_row_for_book = counting_find_row
    try:
        window._refresh_rows_full(books)
    finally:
        window._rows_by_book = orig_rows_by_book
        window._find_row_for_book = orig_find_row

    assert rows_by_book_calls["n"] == 1, rows_by_book_calls["n"]
    assert find_row_calls["n"] == 0, find_row_calls["n"]
    print("PASS: _refresh_rows_full() builds the row map exactly once for the whole "
          "batch, never calling the O(row count) per-book lookup")


if __name__ == "__main__":
    test_field_display_text_collapses_whitespace_for_multiline_in_non_wrap_modes()
    test_field_display_text_preserves_newlines_in_wrap_mode()
    test_field_display_text_handles_empty_string()
    test_html_description_does_not_grow_row_height_in_ellipsis_mode()
    test_underlying_description_metadata_is_never_mutated()
    test_switching_modes_round_trips_the_description_cell()
    test_switching_modes_never_mutates_metadata_or_pushes_undo()
    test_wrap_mode_still_shows_raw_multiline_text()
    test_refresh_rows_full_is_efficient_for_a_large_batch()
    print("\nALL MAIN WINDOW TABLE TESTS PASSED")
