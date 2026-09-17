"""Tests for lazy/viewport-based cover icon loading (see
MainWindow._request_icons_for_visible_rows / _apply_cached_cover_icon_only
/ _apply_cover_icon in gui/main_window.py).

Real bug found profiling a reported "Updating list takes several
minutes" complaint on a 15,462-book real library: decoding EVERY
book's cover icon during table population, even off the main thread,
still costs real wall-clock time overall (confirmed separately:
PyQt6's QImage decode doesn't release the GIL, so QThreadPool worker
threads don't add real throughput for this work) -- a user can only
ever look at a couple dozen rows at once regardless of library size,
so eagerly decoding all of them was almost entirely wasted work.
Measured fix: ~126s -> ~2.6s for _rebuild_table() on 15,462 books with
real JPEG covers."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from PyQt6.QtGui import QColor, QImage  # noqa: E402
from PyQt6.QtCore import QBuffer, QIODevice  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

import gui.main_window as mw  # noqa: E402
from core.epub_metadata import EpubBook, EpubMetadata  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)


def _real_jpeg_bytes() -> bytes:
    """A small but genuinely decodable JPEG -- unlike random bytes
    (which fail to decode instantly and would silently make this test
    measure nothing close to a real cover's actual cost)."""
    img = QImage(120, 160, QImage.Format.Format_RGB32)
    for y in range(0, 160, 4):
        for x in range(0, 120, 4):
            img.setPixelColor(x, y, QColor((x * 3) % 256, (y * 2) % 256, (x + y) % 256))
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "JPG", 85)
    buf.close()
    return bytes(buf.data())


_JPEG_BYTES = _real_jpeg_bytes()


def _fake_book(i: int) -> EpubBook:
    b = EpubBook.__new__(EpubBook)
    b.path = f"/x/book_{i:05d}.epub"
    b.load_error = None
    b.save_error = ""
    b.dirty = False
    b.cover_bytes = bytes(_JPEG_BYTES)  # distinct object identity per book, like real covers
    b.cover_mime = "image/jpeg"
    b.cover_changed = False
    b.cover_removed = False
    b._cover_hash_cache = None
    b._orphan_files_to_remove = set()
    b._image_replacements = {}
    b.validation_issues = []
    b.validation_status = "OK"
    b.metadata = EpubMetadata(title=f"Book {i}")
    return b


def _pump(seconds: float = 0.5) -> None:
    """Processes queued Qt events (including cross-thread signal
    delivery from completed background decodes) for up to `seconds`."""
    deadline = time.perf_counter() + seconds
    while time.perf_counter() < deadline:
        _app.processEvents()
        time.sleep(0.005)


def _icon_count(window: MainWindow) -> int:
    return sum(
        1 for row in range(window.table.rowCount())
        if not window.table.item(row, mw.FILENAME_COL).icon().isNull()
    )


def test_populating_a_large_table_does_not_decode_every_icon():
    window = MainWindow()
    window.resize(1280, 760)
    window._columns_sized = True
    books = [_fake_book(i) for i in range(500)]
    window.books = books
    window._rebuild_table()
    _pump()

    loaded = _icon_count(window)
    assert 0 < loaded < len(books), loaded
    print(f"PASS: populating 500 rows only decoded {loaded} icons (the visible ones), not all 500")


def test_scrolling_loads_icons_for_newly_visible_rows():
    window = MainWindow()
    window.resize(1280, 760)
    window._columns_sized = True
    books = [_fake_book(i) for i in range(500)]
    window.books = books
    window._rebuild_table()
    _pump()
    before = _icon_count(window)

    window.table.scrollToBottom()
    _pump()

    after = _icon_count(window)
    assert after > before, (before, after)
    last_item = window.table.item(window.table.rowCount() - 1, mw.FILENAME_COL)
    assert not last_item.icon().isNull()
    print(f"PASS: scrolling to the bottom loaded more icons ({before} -> {after}), "
          "including the very last row")


def test_a_book_edited_via_refresh_rows_full_still_gets_its_icon_regardless_of_visibility():
    # _refresh_row_full()/_refresh_rows_full() (used by Undo, bulk
    # edits, lookups, etc.) must keep using the REAL _apply_cover_icon
    # (which queues a decode), not the population-time cache-only
    # version -- an edited book's cover should always be shown
    # correctly, not left blank just because lazy-loading hasn't
    # scrolled to it yet.
    window = MainWindow()
    window.resize(1280, 760)
    window._columns_sized = True
    books = [_fake_book(i) for i in range(2000)]
    window.books = books
    window._rebuild_table()
    _pump()

    far_book = books[1500]  # well outside the initially-visible/loaded range
    item_before = window.table.item(1500, mw.FILENAME_COL)
    assert item_before.icon().isNull()  # confirm it wasn't eagerly loaded

    window._refresh_rows_full([far_book])
    _pump()

    item_after = window.table.item(1500, mw.FILENAME_COL)
    assert not item_after.icon().isNull()
    print("PASS: _refresh_rows_full() still loads a real icon for an off-screen book")


def test_request_icons_for_visible_rows_is_safe_with_zero_rows():
    window = MainWindow()
    window._request_icons_for_visible_rows()  # must not raise on an empty table
    print("PASS: _request_icons_for_visible_rows() is a safe no-op on an empty table")


if __name__ == "__main__":
    test_populating_a_large_table_does_not_decode_every_icon()
    test_scrolling_loads_icons_for_newly_visible_rows()
    test_a_book_edited_via_refresh_rows_full_still_gets_its_icon_regardless_of_visibility()
    test_request_icons_for_visible_rows_is_safe_with_zero_rows()
    print("\nALL LAZY ICON LOADING TESTS PASSED")
