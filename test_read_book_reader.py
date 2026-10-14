"""Tests for the read-only reader: resource path safety, size caps, SVG
rewriting, image loading from the zip, zoom, find and navigation."""

import os
import sys
import zipfile

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.epub_metadata import EpubBook, is_safe_archive_path, resolve_resource_path
from core.reader_html import prepare_reader_html
from test_cover_page_browser import OPF, _png

CH = '<html><body><h1>Title</h1><p>alpha beta</p><img src="../img/pic.png"/><p>gamma beta</p><img src="../img/big.png"/></body></html>'


def test_resolve_resource_path():
    assert resolve_resource_path("OEBPS/text/ch1.xhtml", "../img/a.png") == "OEBPS/img/a.png"
    assert resolve_resource_path("ch1.xhtml", "img/a%20b.png?x=1#f") == "img/a b.png"
    assert resolve_resource_path("a/ch1.xhtml", "/img/a.png") == "img/a.png"
    assert resolve_resource_path("ch1.xhtml", "../etc/passwd") is None
    assert resolve_resource_path("a/ch1.xhtml", "../../x.png") is None
    assert resolve_resource_path("ch1.xhtml", "http://x/y.png") is None
    assert resolve_resource_path("ch1.xhtml", "data:image/png;base64,AAAA") is None
    assert resolve_resource_path("ch1.xhtml", "C:/x.png") is None
    assert resolve_resource_path("ch1.xhtml", "a\\..\\b.png") is None
    assert resolve_resource_path("ch1.xhtml", "") is None
    assert resolve_resource_path("ch1.xhtml", "#frag") is None


def test_is_safe_archive_path():
    assert is_safe_archive_path("a/b.png")
    for bad in ("", "/a", "../a", "a/../b", "C:x", "a\\b"):
        assert not is_safe_archive_path(bad)


def test_prepare_reader_html_svg():
    wrapped = '<body><svg xmlns="x"><image width="1" xlink:href="../img/cover.jpg"/></svg></body>'
    assert '<img src="../img/cover.jpg">' in prepare_reader_html(wrapped)
    assert "SVG graphic not shown" in prepare_reader_html("<svg><rect/></svg>")
    out = prepare_reader_html('<p><img src="../i/fig.svg" alt="x"/></p>')
    assert "[SVG image not shown: fig.svg]" in out and "<img" not in out


def _make(tmp_path, big=b"not really big"):
    p = tmp_path / "r.epub"
    opf = OPF.replace("</manifest>", '<item id="t3" href="text/ch.xhtml" media-type="application/xhtml+xml"/></manifest>').replace(
        '<itemref idref="t2"/>', '<itemref idref="t2"/><itemref idref="t3"/>')
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        z.writestr("content.opf", opf)
        z.writestr("img/c.png", _png(0x00FF00))
        z.writestr("img/pic.png", _png(0xFF0000))
        z.writestr("img/big.png", big)
        z.writestr("title.xhtml", "<html><body><p>t</p></body></html>")
        z.writestr("ch1.xhtml", "<html><body><p>one</p></body></html>")
        z.writestr("text/ch.xhtml", CH)
    return p


def test_read_resource_caps_and_traversal(tmp_path):
    book = EpubBook(str(_make(tmp_path)))
    assert book.read_resource("img/pic.png")
    assert book.read_resource("img/pic.png", max_bytes=10) is None  # over cap
    assert book.read_resource("../x") is None
    assert book.read_resource("/img/pic.png") is None
    assert book.read_resource("missing.png") is None


def test_decode_image_capped():
    from PyQt6.QtGui import QGuiApplication
    from gui.read_book_dialog import decode_image_capped
    _app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    data = _png(0x123456)  # 4x4
    img = decode_image_capped(data)
    assert img is not None and img.width() == 4
    assert decode_image_capped(data, max_pixels=10) is None
    assert decode_image_capped(b"garbage") is None
    from PyQt6.QtGui import QImage
    wide = QImage(400, 10, QImage.Format.Format_RGB32)
    wide.fill(0)
    from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    wide.save(buf, "PNG")
    assert decode_image_capped(bytes(ba), max_width=100).width() == 100


_APP = None


def _dialog(tmp_path):
    global _APP
    from PyQt6.QtWidgets import QApplication
    from gui.read_book_dialog import ReadBookDialog
    _APP = QApplication.instance() or QApplication(sys.argv)
    return ReadBookDialog(EpubBook(str(_make(tmp_path))))


def test_dialog_images_navigation_zoom_find(tmp_path):
    from PyQt6.QtCore import QUrl
    from PyQt6.QtGui import QImage, QTextDocument
    dlg = _dialog(tmp_path)
    assert dlg.chapter_list.count() == 4  # cover + 3
    assert dlg.position_label.text() == "Chapter 1 / 3"
    dlg.chapter_list.setCurrentRow(0)
    assert dlg.position_label.text() == "Cover"
    assert not dlg.prev_btn.isEnabled()
    dlg.chapter_list.setCurrentRow(3)
    assert dlg.position_label.text() == "Chapter 3 / 3"
    assert not dlg.next_btn.isEnabled()
    view = dlg.text_view
    assert view.base_path == "text/ch.xhtml"
    pic = view.loadResource(QTextDocument.ResourceType.ImageResource.value, QUrl("../img/pic.png"))
    assert isinstance(pic, QImage) and not pic.isNull()
    assert view.loadResource(QTextDocument.ResourceType.ImageResource.value, QUrl("../../x.png")) is None
    assert view.loadResource(QTextDocument.ResourceType.ImageResource.value, QUrl("../img/big.png")) is None  # not an image
    assert view.loadResource(QTextDocument.ResourceType.ImageResource.value, QUrl("http://x/a.png")) is None
    # zoom
    start = dlg._point_size
    dlg.zoom(1)
    assert dlg._point_size == start + 1
    dlg.zoom(-50)
    assert dlg._point_size == 8 and not dlg.smaller_btn.isEnabled()
    dlg.zoom_reset()
    assert dlg._point_size == start
    # find
    dlg.find_edit.setText("beta")
    assert view.textCursor().selectedText() == "beta"
    dlg._find(True)
    assert view.textCursor().selectedText() == "beta"
    dlg.find_edit.setText("zzz")
    assert dlg.find_status.text() == "Not found"
    # cover entry renders an image
    dlg.chapter_list.setCurrentRow(0)
    assert view.loadResource(QTextDocument.ResourceType.ImageResource.value, QUrl("epub-cover:")) is not None


def test_dialog_book_without_text(tmp_path):
    from PyQt6.QtWidgets import QApplication
    from gui.read_book_dialog import ReadBookDialog
    _app = QApplication.instance() or QApplication(sys.argv)
    book = EpubBook(str(_make(tmp_path)))
    book.cover_bytes = None
    book.list_text_pages = lambda: []
    dlg = ReadBookDialog(book)
    assert "no readable text" in dlg.text_view.toPlainText()
