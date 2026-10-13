"""Three slow spots on a huge library: undo snapshots, the right-click menu's cover fingerprinting, and the row-height refit.
Each shows a progress dialog (or stays off the slow path) instead of freezing the window."""

import os
import sys
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

import gui.main_window as mw

_app = QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def window():
    win = mw.MainWindow()
    yield win
    win.close()


class RecordingReporter:
    """Stands in for ProgressReporter: records that a dialog was asked for and what it was told."""

    created: list = []

    def __init__(self, parent, total, label, threshold=3, cancellable=True, title=None):
        self.total, self.label, self.values, self.closed = total, label, [], False
        self.dialog = SimpleNamespace(setRange=lambda a, b: None)
        RecordingReporter.created.append(self)

    def set_value(self, done, pump=True):
        self.values.append(done)

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


@pytest.fixture
def reporter(monkeypatch):
    RecordingReporter.created = []
    monkeypatch.setattr(mw, "ProgressReporter", RecordingReporter)
    return RecordingReporter


def test_a_big_undo_snapshot_shows_a_progress_dialog_and_a_small_one_does_not(window, reporter, monkeypatch):
    monkeypatch.setattr(mw.MainWindow, "_snapshot_book", staticmethod(lambda book: book))
    window._push_undo("Bulk Edit", [object() for _ in range(10)])
    assert reporter.created == []  # a small undo never flashes a dialog
    window._push_undo("Bulk Edit", [object() for _ in range(mw.UNDO_PROGRESS_AFTER + 50)])
    assert len(reporter.created) == 1 and reporter.created[0].closed and reporter.created[0].total == 0


def test_a_big_undo_and_redo_also_show_the_dialog(window, reporter, monkeypatch):
    restored = []
    monkeypatch.setattr(mw.MainWindow, "_snapshot_book", staticmethod(lambda book: "snap"))
    monkeypatch.setattr(mw.MainWindow, "_restore_book", staticmethod(lambda book, snap: restored.append(book)))
    monkeypatch.setattr(window, "_refresh_rows_full", lambda affected: None)
    monkeypatch.setattr(window, "_refresh_status", lambda: None)
    monkeypatch.setattr(window, "_on_selection_changed", lambda: None)
    books = [object() for _ in range(mw.UNDO_PROGRESS_AFTER * 2)]
    window._push_undo("Bulk Edit", books)
    reporter.created.clear()
    window.on_undo()
    assert len(restored) == len(books) and len(reporter.created) == 1
    reporter.created.clear()
    window.on_redo()
    assert len(reporter.created) == 1


class _NoCoverTouch(SimpleNamespace):
    @property
    def cover_hash(self):
        raise AssertionError("the right-click menu must not fingerprint covers for a huge selection")


def test_the_right_click_menu_does_not_fingerprint_covers_for_a_huge_selection(window):
    books = [_NoCoverTouch(load_error="") for _ in range(mw.CONTEXT_COVER_CHECK_MAX + 1)]
    items = window._context_menu_items(books)
    cover = next(i for i in items if isinstance(i, mw.Submenu) and i.text == "Cover")
    keys = [getattr(entry, "key", None) for entry in cover.items]
    assert "flag_junk_cover" in keys and "unflag_junk_cover" in keys  # both offered; each action skips what does not apply


def test_flag_and_unflag_read_a_big_selection_of_covers_under_a_progress_dialog(window, monkeypatch):
    seen = []
    monkeypatch.setattr(mw, "run_with_progress", lambda parent, items, step, label, **k: (seen.append((label, k)), [step(i, n) for n, i in enumerate(items)]))
    books = [SimpleNamespace(cover_hash=f"h{n % 3}") for n in range(40)] + [SimpleNamespace(cover_hash=None)]
    assert window._selected_cover_hashes(books, "Reading covers...") == {"h0", "h1", "h2"}
    assert seen and seen[0][0] == "Reading covers..." and seen[0][1]["cancellable"] is False


def test_row_heights_are_refit_row_by_row_under_a_dialog_for_a_huge_table(window, reporter, monkeypatch):
    calls = {"all": 0, "rows": 0}
    monkeypatch.setattr(window.table, "resizeRowsToContents", lambda: calls.__setitem__("all", calls["all"] + 1))
    monkeypatch.setattr(window.table, "resizeRowToContents", lambda row: calls.__setitem__("rows", calls["rows"] + 1))
    window.table.setRowCount(10)
    window._reflow_table_rows()
    assert calls == {"all": 1, "rows": 0} and reporter.created == []  # small: the one Qt call, no dialog
    window.table.setRowCount(mw.ROW_REFLOW_PROGRESS_THRESHOLD + 100)
    window._reflow_table_rows()
    assert calls["all"] == 1 and calls["rows"] == mw.ROW_REFLOW_PROGRESS_THRESHOLD + 100
    assert len(reporter.created) == 1 and reporter.created[0].closed and reporter.created[0].values
