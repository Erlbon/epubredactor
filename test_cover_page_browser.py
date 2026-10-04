import zipfile

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtGui import QImage
from PyQt6.QtCore import QBuffer, QByteArray, QIODevice

from core.epub_metadata import EpubBook

OPF = """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>T</dc:title><dc:identifier id="id">x</dc:identifier></metadata>
<manifest>
<item id="a" href="img/a.png" media-type="image/png"/>
<item id="c" href="img/c.png" media-type="image/png" properties="cover-image"/>
<item id="s" href="s.svg" media-type="image/svg+xml"/>
<item id="x" href="t.xhtml" media-type="application/xhtml+xml"/>
</manifest><spine><itemref idref="x"/></spine></package>"""


def _png(color):
    img = QImage(4, 4, QImage.Format.Format_RGB32)
    img.fill(color)
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(ba)


def _make(tmp_path):
    p = tmp_path / "b.epub"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        z.writestr("content.opf", OPF)
        z.writestr("img/a.png", _png(0xFF0000))
        z.writestr("img/c.png", _png(0x00FF00))
    return p


def test_pages_cover_first_and_read(tmp_path, qapp=None):
    book = EpubBook(str(_make(tmp_path)))
    pages = book.list_image_pages()
    assert pages == ["img/c.png", "img/a.png"]
    assert book.read_image_page("img/a.png")
    assert book.read_image_page("img/missing.png") is None
    assert book.read_image_page("img/a.png", max_bytes=1) is None


def test_panel_turns_pages(tmp_path):
    import os, sys
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    import gui.tag_panel as tp

    _app = QApplication.instance() or QApplication(sys.argv)
    book = EpubBook(str(_make(tmp_path)))
    panel = tp.TagPanel()
    panel.set_selection([book])
    assert not panel.page_label.isHidden()
    assert panel.page_label.text() == "Image 1 / 2"
    assert not panel.prev_page_btn.isEnabled() and panel.next_page_btn.isEnabled()
    panel.turn_page(1)
    assert panel.page_label.text() == "Image 2 / 2"
    assert panel.next_page_btn.isEnabled() is False
    panel.turn_page(1)  # clamped
    assert panel.page_label.text() == "Image 2 / 2"
    panel.set_selection([book, book])
    assert panel.page_label.isHidden()
