"""
The Google Books / Open Library / Calibre lookup dialogs on
redactor_common's LookupDialogBase (2026-09-23). Network and Calibre
calls are stubbed at each dialog module's own imports.
"""

import os
import sys
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import gui.calibre_lookup_dialog as cal  # noqa: E402
import gui.google_books_dialog as gb  # noqa: E402
import gui.open_library_dialog as ol  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)


def _book(path, title="Mort", authors="Terry Pratchett", isbn="", cover=None):
    return SimpleNamespace(
        path=path, cover_bytes=cover,
        metadata=SimpleNamespace(title=title, authors_str=authors, isbn=isbn),
    )


def _candidate(**fields):
    return SimpleNamespace(as_dict=lambda: dict(fields), cover_url="https://c", cover_id=7)


def test_google_books_applies_fields_and_cover(monkeypatch):
    seen = []
    monkeypatch.setattr(gb, "search_google_books",
                        lambda title, authors: seen.append((title, authors)) or [_candidate(title="Mort", publisher="Gollancz")])
    monkeypatch.setattr(gb, "download_cover_image", lambda c: b"jpegbytes")
    dialog = gb.GoogleBooksDialog([_book("a.epub"), _book("b.epub", title="")])
    assert seen == [("Mort", "Terry Pratchett")]  # the untitled book isn't searched
    assert dialog.accepted_metadata() == {0: {"title": "Mort", "publisher": "Gollancz"}}
    assert dialog.accepted_covers() == {0: (b"jpegbytes", "image/jpeg")}
    assert "no title set" in dialog.status_label.text()


def test_open_library_unticked_row_is_not_applied(monkeypatch):
    monkeypatch.setattr(ol, "search_open_library", lambda title, authors: [_candidate(title="X")])
    monkeypatch.setattr(ol, "download_cover_image", lambda c: b"img")
    dialog = ol.OpenLibraryDialog([_book("a.epub"), _book("b.epub")])
    dialog._checkboxes[1].setChecked(False)
    assert set(dialog.accepted_metadata()) == {0}
    assert set(dialog.accepted_covers()) == {0}


def test_search_this_item_uses_the_corrected_query(monkeypatch):
    seen = []

    def search(title, authors):
        seen.append(title)
        return [_candidate(title=title)] if title == "Guards! Guards!" else []

    monkeypatch.setattr(gb, "search_google_books", search)
    dialog = gb.GoogleBooksDialog([_book("a.epub", title="Gaurds Gaurds")])
    assert dialog.accepted_metadata() == {}
    dialog.table.selectRow(0)
    dialog._query_edits["title"].setText("Guards! Guards!")
    dialog._search_current_row()
    assert seen == ["Gaurds Gaurds", "Guards! Guards!"]
    assert dialog.accepted_metadata() == {0: {"title": "Guards! Guards!"}}


def test_calibre_missing_tool_prompts_instead_of_searching(monkeypatch):
    monkeypatch.setattr(cal, "find_tool", lambda *a, **k: None)
    monkeypatch.setattr(cal, "fetch_metadata", lambda *a, **k: (_ for _ in ()).throw(AssertionError("searched")))
    dialog = cal.CalibreLookupDialog([_book("a.epub")])
    assert "Couldn't find Calibre" in dialog.status_label.text()
    assert not dialog.download_btn.isHidden()
    assert dialog.table.rowCount() == 0


def test_calibre_found_searches_with_isbn_and_returns_changes(monkeypatch):
    calls = []
    monkeypatch.setattr(cal, "find_tool", lambda *a, **k: "C:/Calibre2/fetch-ebook-metadata.exe")

    def fetch(tool, title, authors, isbn):
        calls.append((tool, title, isbn))
        return SimpleNamespace(as_dict=lambda: {"series": "Discworld"})

    monkeypatch.setattr(cal, "fetch_metadata", fetch)
    dialog = cal.CalibreLookupDialog([_book("a.epub", isbn="9780552131063")])
    assert calls == [("C:/Calibre2/fetch-ebook-metadata.exe", "Mort", "9780552131063")]
    assert dialog.accepted_changes() == {0: {"series": "Discworld"}}


def test_calibre_large_batch_can_be_declined(monkeypatch):
    monkeypatch.setattr(cal, "find_tool", lambda *a, **k: "tool")
    monkeypatch.setattr(cal, "fetch_metadata", lambda *a, **k: (_ for _ in ()).throw(AssertionError("searched")))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    books = [_book(f"{i}.epub") for i in range(cal.WARN_BATCH_SIZE + 1)]
    dialog = cal.CalibreLookupDialog(books)
    assert dialog.accepted_changes() == {}
