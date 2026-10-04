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
<item id="c" href="img/c.png" media-type="image/png" properties="cover-image"/>
<item id="t1" href="title.xhtml" media-type="application/xhtml+xml"/>
<item id="t2" href="ch1.xhtml" media-type="application/xhtml+xml"/>
</manifest><spine><itemref idref="t1"/><itemref idref="t2"/></spine></package>"""

TITLE = '<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml"><head><style>p{display:none}</style></head><body><h1>The Hobbit</h1><p>by J. R. R. Tolkien</p></body></html>'


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
        z.writestr("img/c.png", _png(0x00FF00))
        z.writestr("title.xhtml", TITLE)
        z.writestr("ch1.xhtml", "<html><body><p>Chapter one</p></body></html>")
    return p


def test_text_pages_in_spine_order_and_read(tmp_path):
    book = EpubBook(str(_make(tmp_path)))
    assert book.list_text_pages() == ["title.xhtml", "ch1.xhtml"]
    html = book.read_text_page("title.xhtml")
    assert "The Hobbit" in html and "<style" not in html and "<?xml" not in html
    assert book.read_text_page("missing.xhtml") is None
    assert book.read_text_page("title.xhtml", max_bytes=1) is None


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
    assert panel.page_label.text() == "Page 1 / 3"
    assert panel.text_view.isHidden()
    panel.turn_page(1)
    assert panel.page_label.text() == "Page 2 / 3"
    assert not panel.text_view.isHidden() and panel.cover_preview.isHidden()
    text = panel.text_view.toPlainText()
    assert "The Hobbit" in text and "Tolkien" in text
    panel.turn_page(1)
    assert "Chapter one" in panel.text_view.toPlainText()
    assert not panel.next_page_btn.isEnabled()
    panel.turn_page(-2)
    assert panel.text_view.isHidden() and not panel.cover_preview.isHidden()
    panel.set_selection([book, book])
    assert panel.page_label.isHidden()


def test_read_book_dialog_lists_and_shows_chapters(tmp_path):
    import os, sys
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    from gui.read_book_dialog import ReadBookDialog

    _app = QApplication.instance() or QApplication(sys.argv)
    book = EpubBook(str(_make(tmp_path)))
    dlg = ReadBookDialog(book)
    assert dlg.chapter_list.count() == 2
    assert "The Hobbit" in dlg.text_view.toPlainText()
    assert not dlg.prev_btn.isEnabled() and dlg.next_btn.isEnabled()
    dlg.next_btn.click()
    assert "Chapter one" in dlg.text_view.toPlainText()
    assert not dlg.next_btn.isEnabled()
