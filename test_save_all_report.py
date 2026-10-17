"""Save All reports its result after EVERY run (status line with counts or the reason nothing was saved, a box listing
each problem file, an unexpected error in the "Something went wrong" box), never stops at the first bad book, and
names a book left marked unsaved without an error. Real MainWindow offscreen."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402
from redactor_common.gui import crash_dialog  # noqa: E402

import gui.main_window as mw  # noqa: E402
from core import crash_log, history  # noqa: E402
from core.epub_metadata import EpubBook, EpubError  # noqa: E402
from test_epub_duplicates import make_epub  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(crash_log, "log_path", lambda: str(tmp_path / "logs" / "epubredactor_crash.log"))
    monkeypatch.setattr(crash_dialog, "_reporter", None)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))


@pytest.fixture
def reporter(tmp_path):
    rep = crash_dialog.install(tmp_path / "logs" / "epubredactor_crash.log")
    yield rep
    if rep.dialog is not None:
        rep.dialog.close()
    _app.processEvents()


@pytest.fixture
def boxes(monkeypatch):
    seen = {"warning": [], "information": []}
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda p, title, text, *a: seen["warning"].append((title, text))))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda p, title, text, *a: seen["information"].append((title, text))))
    return seen


@pytest.fixture
def window(tmp_path):
    win = mw.MainWindow()
    win.resize(1500, 600)
    win.show()
    win._load_paths([make_epub(tmp_path, n, title=f"Old {n}") for n in ("a.epub", "b.epub", "c.epub")])
    yield win
    for book in win.books:
        book.dirty = False
    win.close()


def _by_name(window, name):
    return next(b for b in window.books if os.path.basename(b.path) == name)


def _dirty(book, title):
    book.metadata.title = title
    book.dirty = True


def _title_on_disk(book):
    return EpubBook(book.path).metadata.title


def _status(window):
    return window.status.currentMessage()


def test_all_clean_says_why_nothing_was_saved(window, boxes):
    window.save_changed()
    assert _status(window) == "Nothing to save: no file has unsaved changes"
    assert boxes["information"][-1][1] == "Nothing to save: no file has unsaved changes"


def test_all_changed_books_with_load_errors_name_them(window, boxes):
    for name in ("a.epub", "b.epub"):
        book = _by_name(window, name)
        book.dirty = True
        book.load_error = "broken"
    window.save_changed()
    assert _status(window).startswith("Nothing to save: all 2 changed file(s) have load errors")
    assert "a.epub" in _status(window) and "b.epub" in _status(window)


def test_a_failing_book_is_listed_in_the_box_and_the_others_are_saved(window, boxes, monkeypatch):
    for book in window.books:
        _dirty(book, "New " + os.path.basename(book.path))
    real = EpubBook.save

    def flaky(self, *a, **k):
        if self.path.endswith("b.epub"):
            raise EpubError("disk says no")
        return real(self, *a, **k)

    monkeypatch.setattr(EpubBook, "save", flaky)
    window.save_changed()
    assert _status(window) == "Saved 2 file(s), 1 failed"
    assert any("b.epub" in text for _title, text in boxes["warning"])
    assert _title_on_disk(_by_name(window, "a.epub")) == "New a.epub"
    assert _title_on_disk(_by_name(window, "c.epub")) == "New c.epub"


def test_an_unexpected_exception_in_the_middle_shows_the_box_and_the_rest_is_saved(window, boxes, reporter, monkeypatch):
    for book in window.books:
        _dirty(book, "New " + os.path.basename(book.path))
    real = EpubBook.save

    def explode(self, *a, **k):
        if self.path.endswith("b.epub"):
            raise ValueError("kaboom")
        return real(self, *a, **k)

    monkeypatch.setattr(EpubBook, "save", explode)
    window.save_changed()
    _app.processEvents()
    assert reporter.dialog is not None and "kaboom" in reporter.dialog.details_text()
    assert _title_on_disk(_by_name(window, "a.epub")) == "New a.epub"
    assert _title_on_disk(_by_name(window, "c.epub")) == "New c.epub"  # the loop went on
    assert _status(window) == "Saved 2 file(s), 1 failed"


def test_an_exception_outside_the_per_book_loop_is_reported_and_shown_in_the_status_bar(window, reporter, monkeypatch):
    _dirty(window.books[0], "x")

    def boom(*a, **k):
        raise RuntimeError("no way")

    monkeypatch.setattr(window, "_save_changed_among", boom)
    window.save_changed()
    _app.processEvents()
    assert reporter.dialog is not None
    assert reporter.dialog.summary_label.text().startswith("Save All stopped because of an unexpected error")
    assert "no way" in _status(window)


def test_the_invariant_names_a_book_left_unsaved_without_an_error(window, boxes, monkeypatch):
    book = _by_name(window, "a.epub")
    _dirty(book, "x")
    monkeypatch.setattr(EpubBook, "save", lambda self, *a, **k: None)  # "saves" but leaves it dirty, no error
    monkeypatch.setattr(EpubBook, "revalidate", lambda self: None)
    window.save_changed()
    assert "still marked unsaved" in _status(window)
    assert any("1 file(s) are still marked unsaved after saving: a.epub" in text for _t, text in boxes["warning"])


def test_the_save_log_is_opt_in_and_has_no_file_names(window, boxes, tmp_path, monkeypatch):
    log = tmp_path / "logs" / "save_log.txt"
    _dirty(_by_name(window, "a.epub"), "x")
    window.save_changed()
    assert not log.exists()  # data logging is off by default
    monkeypatch.setattr(history, "history_enabled", lambda: True)
    _dirty(_by_name(window, "b.epub"), "y")
    window.save_changed()
    text = log.read_text(encoding="utf-8")
    assert text.count("\n") == 1 and "saved=1" in text and "b.epub" not in text
