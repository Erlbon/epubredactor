"""Tests for the Cover column (gui/cover_quality.py) and Operations >
Find Better Covers... (core/better_cover.py, gui/better_cover_dialog.py,
the window flow) -- Open Library faked, covers generated with Qt."""

import io
import sys
import urllib.error
import zipfile

import pytest
from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import QApplication

from core import better_cover
from gui import cover_quality

_app = QApplication.instance() or QApplication(sys.argv)


def _jpeg(width, height, color="#4466aa"):
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "JPG")
    return bytes(data)


def _epub(path, isbn="", cover=None, title="A Book"):
    identifier = f"urn:isbn:{isbn}" if isbn else "urn:uuid:abcd-1234"
    cover_item = '<item id="cover-img" href="cover.jpg" media-type="image/jpeg" properties="cover-image"/>' if cover else ""
    opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="BookId">{identifier}</dc:identifier>
    <dc:title>{title}</dc:title>
    <dc:creator>Some Author</dc:creator>
  </metadata>
  <manifest>
    <item id="chap1" href="chap1.xhtml" media-type="application/xhtml+xml"/>
    {cover_item}
  </manifest>
  <spine><itemref idref="chap1"/></spine>
</package>"""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>""")
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/chap1.xhtml", "<html><body><p>Hi</p></body></html>")
        if cover:
            zf.writestr("OEBPS/cover.jpg", cover)
    return str(path)


class _Book:
    def __init__(self, cover):
        self.cover_bytes = cover


def test_image_size_reads_only_what_it_needs():
    assert cover_quality.image_size(_jpeg(600, 900)) == (600, 900)
    assert cover_quality.image_size(b"not an image") is None and cover_quality.image_size(None) is None


def test_cover_column_bands_and_sorting():
    missing = cover_quality.describe(_Book(None))
    low = cover_quality.describe(_Book(_jpeg(600, 900)))
    good = cover_quality.describe(_Book(_jpeg(1200, 1800)))
    assert missing[0] == "none" and missing[1] == cover_quality.MISSING_COLOR
    assert low[0] == "600×900" and low[1] == cover_quality.LOW_RES_COLOR and "Find Better Covers" in low[2]
    assert good[0] == "1200×1800" and good[1] is None
    assert missing[3] < low[3] < good[3]  # sorts missing first, then smallest


def test_cover_size_is_remembered_until_the_cover_changes():
    book = _Book(_jpeg(600, 900))
    assert cover_quality.cover_size(book) == (600, 900)
    book.cover_bytes = _jpeg(1200, 1800)
    assert cover_quality.cover_size(book) == (1200, 1800)


def test_fetch_by_isbn(monkeypatch):
    asked = []

    def ok(url):
        asked.append(url)
        return b"jpeg bytes"

    assert better_cover.fetch_cover_by_isbn("978-0-14-103614-4", ok) == b"jpeg bytes"
    assert asked == ["https://covers.openlibrary.org/b/isbn/9780141036144-L.jpg?default=false"]
    assert better_cover.fetch_cover_by_isbn("", ok) is None

    def status(code):
        def get(url):
            raise urllib.error.HTTPError(url, code, "x", None, io.BytesIO())
        return get

    assert better_cover.fetch_cover_by_isbn("9780141036144", status(404)) is None  # no cover for it
    with pytest.raises(better_cover.IsbnCoverLimitError, match="try the rest again later"):
        better_cover.fetch_cover_by_isbn("9780141036144", status(429))
    with pytest.raises(better_cover.IsbnCoverError, match="500"):
        better_cover.fetch_cover_by_isbn("9780141036144", status(500))


# ---------------------------------------------------------------------------
# The window
# ---------------------------------------------------------------------------

def test_find_better_covers_offers_only_improvements_and_undoes(tmp_path, monkeypatch):
    from gui import better_cover_dialog
    from gui.main_window import COVER_SIZE_COL, MainWindow

    small, big = _jpeg(300, 450), _jpeg(1200, 1800)
    books = [
        _epub(tmp_path / "small.epub", "9780141036144", _jpeg(300, 450), "Small cover"),
        _epub(tmp_path / "none.epub", "9780000000002", None, "No cover"),
        _epub(tmp_path / "fine.epub", "9780000000019", _jpeg(1600, 2400), "Big cover already"),
        _epub(tmp_path / "noisbn.epub", "", small, "No ISBN"),
    ]
    by_isbn = {"9780141036144": big, "9780000000002": big, "9780000000019": big}
    monkeypatch.setattr(better_cover, "fetch_cover_by_isbn", lambda isbn, get=None: by_isbn.get(isbn))
    window = MainWindow()
    window._load_paths(books)
    cover_cells = {window.table.item(r, 1).text(): window.table.item(r, COVER_SIZE_COL).text()
                   for r in range(window.table.rowCount())}
    assert cover_cells["small.epub"] == "300×450" and cover_cells["none.epub"] == "none"
    offered = {}

    def accept(dialog):
        offered["titles"] = sorted(dialog.table.item(r, 0).text() for r in range(dialog.table.rowCount()))
        return dialog.DialogCode.Accepted

    monkeypatch.setattr(better_cover_dialog.BetterCoverDialog, "exec", accept)
    window.open_find_better_covers_dialog()
    assert offered["titles"] == ["No cover", "Small cover"]  # not the one already bigger, not the one without ISBN
    by_name = {b.path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]: b for b in window.books}
    assert cover_quality.cover_size(by_name["small.epub"]) == (1200, 1800) and by_name["small.epub"].dirty
    row = next(r for r in range(window.table.rowCount()) if window.table.item(r, 1).text() == "small.epub")
    assert window.table.item(row, COVER_SIZE_COL).text() == "1200×1800"
    window.on_undo()
    assert cover_quality.cover_size(by_name["small.epub"]) == (300, 450)
    assert by_name["none.epub"].cover_bytes is None
