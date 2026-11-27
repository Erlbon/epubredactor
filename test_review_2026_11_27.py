"""Tests for the fixes from the 2026-11-27 code review (cards numbered as on the review page)."""

from __future__ import annotations

import subprocess
import sys

import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


# Card 21: the "Download Calibre..." button in Import and Convert crashed with a NameError.
def test_card21_import_dialog_download_button_opens_the_page(monkeypatch, qapp):
    import webbrowser

    from core.calibre_tools import DOWNLOAD_URL
    from gui.ebook_convert_dialog import EbookConvertDialog

    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda url, *a, **k: opened.append(url))
    dialog = EbookConvertDialog(initial_paths=[])
    dialog.download_btn.click()
    assert opened == [DOWNLOAD_URL]


# Card 50: external tools get stdin=DEVNULL (family rule).
def test_card50_sigil_is_started_with_stdin_devnull(tmp_path):
    from core.sigil_tools import open_in_sigil

    sigil = tmp_path / "sigil.exe"
    sigil.write_bytes(b"x")
    book = tmp_path / "book.epub"
    book.write_bytes(b"x")
    seen = {}
    open_in_sigil(str(sigil), str(book), popen_fn=lambda args, **kw: seen.update(kw))
    assert seen["stdin"] is subprocess.DEVNULL


def test_card50_fetch_ebook_metadata_is_started_with_stdin_devnull():
    from core.calibre_lookup import CalibreLookupError, fetch_metadata

    seen = {}

    def fake_run(args, **kw):
        seen.update(kw)
        return subprocess.CompletedProcess(args, 1, b"", b"")

    with pytest.raises(CalibreLookupError):
        fetch_metadata("fetch-ebook-metadata", title="X", run_fn=fake_run)
    assert seen["stdin"] is subprocess.DEVNULL


# --- batch 2: the save path (core/epub_metadata.py) ---------------------------------------------

_CONTAINER = (
    '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
    '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
    "</rootfiles></container>"
)
_PAGE = '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>t</title></head><body>{}</body></html>'
_OPF_NS = "http://www.idpf.org/2007/opf"
_DC_NS = "http://purl.org/dc/elements/1.1/"


def _make_book(path, metadata, *, version="2.0", uid="BookId", items="", spine="", files=None, deflate=False):
    """A small EPUB: `metadata` is the inside of <metadata>; ch1.xhtml is always there and in the spine."""
    opf = (
        f'<?xml version="1.0"?><package xmlns="{_OPF_NS}" version="{version}" unique-identifier="{uid}">'
        f'<metadata xmlns:dc="{_DC_NS}" xmlns:opf="{_OPF_NS}">{metadata}</metadata>'
        '<manifest><item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>'
        f"{items}</manifest>"
        f'<spine><itemref idref="ch1"/>{spine}</spine></package>'
    )
    import zipfile

    files = dict(files or {})
    files.setdefault("OEBPS/ch1.xhtml", _PAGE.format("<p>" + "Chapter one text. " * 200 + "</p>").encode())
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", _CONTAINER)
        zf.writestr("OEBPS/content.opf", opf)
        for name, data in files.items():
            zf.writestr(name, data, zipfile.ZIP_DEFLATED if deflate else zipfile.ZIP_STORED)
    return str(path)


def _member(path, name):
    import zipfile

    with zipfile.ZipFile(path) as zf:
        return zf.read(name) if name in zf.namelist() else None


def _opf(path):
    from lxml import etree

    return etree.fromstring(_member(path, "OEBPS/content.opf"))


_UUID = '<dc:identifier id="BookId">urn:uuid:1234</dc:identifier><dc:title>Book</dc:title><dc:language>en</dc:language>'
_JPEG = b"\xff\xd8\xff\xe0old-cover-bytes"
_PNG = b"\x89PNG\r\n\x1a\nnew-cover-bytes"


def _cover_page_book(tmp_path, page_body='<img src="images/cover.jpg" alt=""/>'):
    """EPUB 2 whose <meta name="cover"> names the cover PAGE c1.xhtml (in the spine), not the image."""
    return _make_book(
        tmp_path / "coverpage.epub", _UUID + '<meta name="cover" content="c1"/>',
        items='<item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/>'
              '<item id="img" href="images/cover.jpg" media-type="image/jpeg"/>',
        spine='<itemref idref="c1"/>',
        files={"OEBPS/c1.xhtml": _PAGE.format(page_body).encode(), "OEBPS/images/cover.jpg": _JPEG},
    )


# Card 1: a cover meta naming a page made Set Cover overwrite, and Remove Cover delete, that page.
def test_card1_cover_meta_on_a_page_takes_the_image_the_page_shows(tmp_path):
    from core.epub_metadata import EpubBook

    path = _cover_page_book(tmp_path)
    page = _member(path, "OEBPS/c1.xhtml")
    book = EpubBook(path)
    assert book.cover_bytes == _JPEG
    assert book.set_cover(_PNG, "image/png")
    book.save()
    assert _member(path, "OEBPS/c1.xhtml") == page
    assert _member(path, "OEBPS/images/cover.jpg") == _PNG
    item = _opf(path).find(f".//{{{_OPF_NS}}}item[@id='c1']")
    assert item.get("media-type") == "application/xhtml+xml"
    assert EpubBook(path).cover_bytes == _PNG


def test_card1_remove_cover_never_deletes_the_cover_page(tmp_path):
    from core.epub_metadata import EpubBook

    path = _cover_page_book(tmp_path)
    page = _member(path, "OEBPS/c1.xhtml")
    book = EpubBook(path)
    book.remove_cover()
    book.save()
    assert _member(path, "OEBPS/c1.xhtml") == page
    assert _member(path, "OEBPS/images/cover.jpg") == _JPEG  # the page still shows it
    root = _opf(path)
    assert root.find(f".//{{{_OPF_NS}}}itemref[@idref='c1']") is not None
    assert root.find(f".//{{{_OPF_NS}}}item[@id='c1']") is not None
    assert EpubBook(path).cover_bytes is None


def test_card1_page_without_an_image_gets_a_new_cover_item(tmp_path):
    from core.epub_metadata import EpubBook

    path = _cover_page_book(tmp_path, page_body="<p>No picture here</p>")
    page = _member(path, "OEBPS/c1.xhtml")
    book = EpubBook(path)
    assert book.cover_bytes is None
    book.set_cover(_PNG, "image/png")
    book.save()
    assert _member(path, "OEBPS/c1.xhtml") == page
    root = _opf(path)
    metas = [m for m in root.iter(f"{{{_OPF_NS}}}meta") if m.get("name") == "cover"]
    assert len(metas) == 1
    new_item = root.find(f".//{{{_OPF_NS}}}item[@id='{metas[0].get('content')}']")
    assert new_item.get("media-type") == "image/png"
    reread = EpubBook(path)
    assert reread.cover_bytes == _PNG
    reread.remove_cover()
    reread.save()
    assert _member(path, "OEBPS/c1.xhtml") == page


# Card 2: a dc:date the year/month/day fields cannot show was deleted (or cut) by any save.
@pytest.mark.parametrize("date", ["May 2020", "2020/05/14", "c. 1920", "1920s", "2020-05-14T10:00:00Z"])
def test_card2_a_date_the_fields_cannot_show_survives_a_save(tmp_path, date):
    from core.epub_metadata import EpubBook

    path = _make_book(tmp_path / "d.epub", _UUID + f"<dc:date>{date}</dc:date>")
    book = EpubBook(path)
    book.apply_metadata({"title": "New title"})
    book.save()
    assert _opf(path).find(f".//{{{_DC_NS}}}date").text == date


def test_card2_a_date_with_a_space_keeps_its_day_and_a_changed_year_is_written(tmp_path):
    from core.epub_metadata import EpubBook

    path = _make_book(tmp_path / "d.epub", _UUID + "<dc:date>2020-05-14 10:00</dc:date>")
    book = EpubBook(path)
    assert (book.metadata.pub_year, book.metadata.pub_month, book.metadata.pub_day) == ("2020", "05", "14")
    book.apply_metadata({"title": "Other"})
    book.save()
    assert _opf(path).find(f".//{{{_DC_NS}}}date").text == "2020-05-14 10:00"
    book.apply_metadata({"pub_year": "2021"})
    book.save()
    assert _opf(path).find(f".//{{{_DC_NS}}}date").text == "2021-05-14"


def test_card2_clearing_the_fields_of_an_unreadable_date_keeps_it(tmp_path):
    from core.epub_metadata import EpubBook

    path = _make_book(tmp_path / "d.epub", _UUID + "<dc:date>May 2020</dc:date>")
    book = EpubBook(path)
    book.apply_metadata({"pub_month": "6"})  # a month with no year can't be written; the date stays
    book.dirty = True
    book.save()
    assert _opf(path).find(f".//{{{_DC_NS}}}date").text == "May 2020"


# Card 5: a description with markup inside the element read as empty and was deleted on save.
def test_card5_description_with_markup_reads_and_survives(tmp_path):
    from core.epub_metadata import EpubBook

    path = _make_book(
        tmp_path / "desc.epub",
        _UUID + '<dc:description><p xmlns="http://www.w3.org/1999/xhtml">Hello <b>world</b></p></dc:description>',
    )
    book = EpubBook(path)
    assert book.metadata.description == "Hello world"
    book.apply_metadata({"title": "Changed"})
    book.save()
    desc = _opf(path).find(f".//{{{_DC_NS}}}description")
    assert desc is not None and "".join(desc.itertext()) == "Hello world" and len(desc) == 1
    book.apply_metadata({"description": "Plain now"})
    book.save()
    desc = _opf(path).find(f".//{{{_DC_NS}}}description")
    assert desc.text == "Plain now" and len(desc) == 0


# Card 6: an in-place save wrote the OPF read at load time into a zip changed on disk since.
def test_card6_in_place_save_refuses_a_file_changed_on_disk(tmp_path):
    import zipfile

    from core.epub_metadata import EpubBook, EpubError

    path = _make_book(tmp_path / "x.epub", _UUID)
    book = EpubBook(path)
    with zipfile.ZipFile(path, "a") as zf:  # another program adds a chapter
        zf.writestr("OEBPS/ch2.xhtml", _PAGE.format("<p>New</p>"))
    before = open(path, "rb").read()
    book.apply_metadata({"title": "Tagged"})
    with pytest.raises(EpubError, match="changed on disk since it was loaded"):
        book.save()
    assert open(path, "rb").read() == before
    assert book.dirty  # the edit is still there to be made again after a reload
    copy = str(tmp_path / "copy.epub")
    book.save(copy)  # Save As Copy is not refused
    assert EpubBook(copy).metadata.title == "Tagged"


def test_card6_repeated_in_place_saves_and_a_rename_still_work(tmp_path):
    import os

    from core.epub_metadata import EpubBook

    path = _make_book(tmp_path / "x.epub", _UUID)
    book = EpubBook(path)
    for title in ("One", "Two"):
        book.apply_metadata({"title": title})
        book.save()
    renamed = str(tmp_path / "renamed.epub")
    os.rename(path, renamed)
    book.path = renamed
    book.apply_metadata({"title": "Three"})
    book.save()
    assert EpubBook(renamed).metadata.title == "Three"


def test_card6_gui_reports_a_changed_file_as_a_save_failure(tmp_path, qapp, monkeypatch):
    import zipfile

    from core.epub_metadata import EpubBook
    from gui import main_window as mw

    path = _make_book(tmp_path / "x.epub", _UUID)
    book = EpubBook(path)
    with zipfile.ZipFile(path, "a") as zf:
        zf.writestr("OEBPS/ch2.xhtml", "x")
    book.apply_metadata({"title": "Tagged"})
    crashes = []
    monkeypatch.setattr(mw.crash_dialog, "report_exception", lambda *a, **k: crashes.append(a))
    window = mw.MainWindow.__new__(mw.MainWindow)
    errors = mw.MainWindow._save_books(window, [book], output_folder=None)
    assert crashes == []
    assert len(errors) == 1 and "changed on disk" in errors[0][1]
    assert "changed on disk" in book.save_error


# Card 11: editing the ISBN rewrote the book's unique identifier when that is the ISBN.
_EPUB3_ISBN_UID = (
    '<dc:identifier id="bookid">urn:isbn:9780141439518</dc:identifier><dc:title>Book</dc:title>'
    '<dc:language>en</dc:language><meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>'
)


def test_card11_a_new_isbn_never_changes_the_unique_identifier(tmp_path):
    from core.epub_metadata import EpubBook

    path = _make_book(tmp_path / "i.epub", _EPUB3_ISBN_UID, version="3.0", uid="bookid")
    book = EpubBook(path)
    assert book.metadata.isbn == "9780141439518"
    book.apply_metadata({"isbn": "9780306406157"})
    book.save()
    root = _opf(path)
    assert root.find(f".//{{{_DC_NS}}}identifier[@id='bookid']").text == "urn:isbn:9780141439518"
    assert EpubBook(path).metadata.isbn == "9780306406157"
    book = EpubBook(path)
    book.apply_metadata({"isbn": "9780141439518"})  # editing the separate one again
    book.save()
    assert _opf(path).find(f".//{{{_DC_NS}}}identifier[@id='bookid']").text == "urn:isbn:9780141439518"


def test_card11_clearing_an_isbn_that_is_the_unique_identifier_is_refused(tmp_path):
    from core.epub_metadata import EpubBook, EpubError

    path = _make_book(tmp_path / "i.epub", _EPUB3_ISBN_UID, version="3.0", uid="bookid")
    before = open(path, "rb").read()
    book = EpubBook(path)
    book.apply_metadata({"isbn": ""})
    with pytest.raises(EpubError, match="unique identifier"):
        book.save()
    assert open(path, "rb").read() == before


def test_card11_epub2_scheme_isbn_as_unique_identifier(tmp_path):
    from core.epub_metadata import EpubBook

    path = _make_book(
        tmp_path / "i2.epub",
        '<dc:identifier id="BookId" opf:scheme="ISBN">9780141439518</dc:identifier><dc:title>B</dc:title>',
    )
    book = EpubBook(path)
    book.apply_metadata({"isbn": "9780306406157"})
    book.save()
    assert _opf(path).find(f".//{{{_DC_NS}}}identifier[@id='BookId']").text == "9780141439518"
    assert EpubBook(path).metadata.isbn == "9780306406157"


# Card 12: every save dropped extra collections, subject authorities and a second DDC.
_EPUB3_RICH = (
    '<dc:identifier id="uid">urn:uuid:1</dc:identifier><dc:title>Book</dc:title><dc:language>en</dc:language>'
    '<meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>'
    '<meta property="belongs-to-collection" id="outer">Outer</meta>'
    '<meta refines="#outer" property="collection-type">series</meta>'
    '<meta property="belongs-to-collection" id="inner">Inner</meta>'
    '<meta refines="#inner" property="collection-type">series</meta>'
    '<meta refines="#inner" property="group-position">3</meta>'
    '<dc:subject id="s1">History</dc:subject>'
    '<meta refines="#s1" property="authority">LCSH</meta><meta refines="#s1" property="term">sh85061212</meta>'
    '<dc:subject id="d1">599</dc:subject><meta refines="#d1" property="authority">DDC</meta>'
    '<dc:subject id="d2">500</dc:subject><meta refines="#d2" property="authority">DDC</meta>'
)


def _collections(path):
    root = _opf(path)
    return [m.text for m in root.iter(f"{{{_OPF_NS}}}meta") if m.get("property") == "belongs-to-collection"]


def test_card12_a_save_keeps_what_the_fields_do_not_show(tmp_path):
    from core.epub_metadata import EpubBook

    path = _make_book(tmp_path / "r.epub", _EPUB3_RICH, version="3.0", uid="uid")
    book = EpubBook(path)
    assert (book.metadata.series, book.metadata.ddc, book.metadata.tags) == ("Outer", "599", ["History"])
    book.apply_metadata({"title": "Changed"})
    book.save()
    assert _collections(path) == ["Outer", "Inner"]
    root = _opf(path)
    subjects = {s.get("id"): s.text for s in root.iter(f"{{{_DC_NS}}}subject")}
    assert subjects == {"s1": "History", "d1": "599", "d2": "500"}
    refines = {(m.get("refines"), m.get("property")): m.text for m in root.iter(f"{{{_OPF_NS}}}meta") if m.get("refines")}
    assert refines[("#s1", "authority")] == "LCSH" and refines[("#inner", "group-position")] == "3"


def test_card12_editing_series_tags_and_ddc_changes_only_those(tmp_path):
    from core.epub_metadata import EpubBook

    path = _make_book(tmp_path / "r.epub", _EPUB3_RICH, version="3.0", uid="uid")
    book = EpubBook(path)
    book.apply_metadata({"series": "Renamed", "series_index": "2", "tags_str": "History; Biology", "ddc": "598"})
    book.save()
    assert _collections(path) == ["Renamed", "Inner"]
    reread = EpubBook(path).metadata
    assert (reread.series, reread.series_index) == ("Renamed", "2")
    assert reread.tags == ["History", "Biology"] and reread.ddc == "598"
    root = _opf(path)
    refines = {(m.get("refines"), m.get("property")): m.text for m in root.iter(f"{{{_OPF_NS}}}meta") if m.get("refines")}
    assert refines[("#s1", "authority")] == "LCSH"  # the kept tag keeps its authority
    assert refines[("#inner", "group-position")] == "3"
    assert {s.text for s in root.iter(f"{{{_DC_NS}}}subject")} == {"History", "Biology", "598", "500"}
    book = EpubBook(path)
    book.apply_metadata({"series": "", "ddc": ""})
    book.save()
    reread = EpubBook(path).metadata
    assert reread.ddc == "" and "Renamed" not in _collections(path) and "Inner" in _collections(path)


# Card 22: a control character in a field (typed, pasted, a lookup answer) made Save fail.
def test_card22_control_characters_are_stripped_and_the_save_works(tmp_path):
    from core.epub_metadata import EpubBook

    path = _make_book(tmp_path / "c.epub", _UUID)
    book = EpubBook(path)
    book.apply_metadata({
        "title": "Bad\x0btitle", "description": "Line\x00one\ttab", "tags_str": "a\x01b; c", "authors_str": "X\x1fY",
    })
    book.save()
    md = EpubBook(path).metadata
    assert (md.title, md.description, md.tags, md.authors) == ("Badtitle", "Lineone\ttab", ["ab", "c"], ["XY"])


def test_card22_dump_importers_strip_control_characters():
    from core import isfdb_import, openlibrary_import

    assert openlibrary_import._text("A\x0bB\x00 C") == "AB C"
    assert isfdb_import._text("A\x0bB\x00 C") == "AB C"


# Card 23: a damaged entry raised BadZipFile/zlib.error out of save: a crash, and the CLI batch stopped.
def _damage_entry(path, name):
    import zipfile

    with zipfile.ZipFile(path) as zf:
        info = zf.getinfo(name)
    data = bytearray(open(path, "rb").read())
    name_len = int.from_bytes(data[info.header_offset + 26:info.header_offset + 28], "little")
    extra_len = int.from_bytes(data[info.header_offset + 28:info.header_offset + 30], "little")
    start = info.header_offset + 30 + name_len + extra_len
    data[start + 20] ^= 0xFF
    open(path, "wb").write(bytes(data))


def test_card23_a_damaged_entry_is_an_epub_error_and_the_original_is_kept(tmp_path):
    from core.epub_metadata import EpubBook, EpubError

    path = _make_book(tmp_path / "bad.epub", _UUID, deflate=True)
    _damage_entry(path, "OEBPS/ch1.xhtml")
    before = open(path, "rb").read()
    book = EpubBook(path)
    assert book.load_error is None  # load reads only the OPF
    book.apply_metadata({"publisher": "ZZZ"})
    with pytest.raises(EpubError, match="OEBPS/ch1.xhtml"):
        book.save()
    assert open(path, "rb").read() == before
    assert not (tmp_path / "bad.epub.tmp_write").exists()


def test_card23_cli_counts_a_damaged_book_as_failed_and_goes_on(tmp_path, capsys):
    from core.epub_metadata import EpubBook
    from epubcli.main import main

    folder = tmp_path / "books"
    folder.mkdir()
    bad = _make_book(folder / "a.epub", _UUID, deflate=True)
    _damage_entry(bad, "OEBPS/ch1.xhtml")
    good = _make_book(folder / "b.epub", _UUID)
    code = main(["set", str(folder), "-s", "publisher=ZZZ"])
    out = capsys.readouterr().out
    assert code != 0 and code != 70
    assert "damaged" in out
    assert EpubBook(good).metadata.publisher == "ZZZ"


# Card 39: applying the value a book already holds marked it changed (and Save All rewrote it).
def test_card39_unchanged_authors_sort_and_tags_do_not_mark_the_book_changed(tmp_path):
    from core.epub_metadata import EpubBook

    path = _make_book(
        tmp_path / "a.epub",
        _UUID + '<dc:creator opf:file-as="Doe, Jane">Jane Doe</dc:creator><dc:creator>Al Bo</dc:creator>'
                "<dc:subject>Fiction</dc:subject><dc:subject>War</dc:subject>",
    )
    book = EpubBook(path)
    book.apply_metadata({"authors_str": "Jane Doe;Al Bo", "author_sort_str": "Doe, Jane", "tags_str": "Fiction; War"})
    assert not book.dirty
    book.apply_metadata({"author_sort_str": "Doe, Jane; "})  # a trailing blank means nothing either
    assert not book.dirty
    book.apply_metadata({"tags_str": "War; Fiction"})
    assert book.dirty and book.metadata.tags == ["War", "Fiction"]


# Card 51: the temp zip was neither flushed to the disk nor read back before it replaced the book.
def test_card51_temp_file_is_synced_and_read_back_before_the_replace(tmp_path, monkeypatch):
    import os
    import zipfile

    from core import epub_metadata
    from core.epub_metadata import EpubBook, EpubError

    path = _make_book(tmp_path / "s.epub", _UUID)
    synced = []
    real_fsync = os.fsync
    monkeypatch.setattr(epub_metadata.os, "fsync", lambda fd: (synced.append(fd), real_fsync(fd)))
    book = EpubBook(path)
    book.apply_metadata({"title": "Synced"})
    book.save()
    assert synced
    before = open(path, "rb").read()
    book.apply_metadata({"title": "Never"})
    monkeypatch.setattr(zipfile.ZipFile, "testzip", lambda self: "OEBPS/ch1.xhtml")
    with pytest.raises(EpubError, match="damaged entry"):
        book.save()
    assert open(path, "rb").read() == before
    assert not (tmp_path / "s.epub.tmp_write").exists()


# --- batch 3: Redact and scans -----------------------------------------------------------------------------------

def _scan_p(text, attrs=""):
    return f"<p{attrs}>{text}</p>"


def _headers_book(tmp_path, pages, name="h.epub"):
    from test_redact_steps import make_epub

    return make_epub(str(tmp_path / name), pages=pages)


def _doc_paragraphs(book, doc):
    from core.page_headers import paragraph_blocks

    return [b.text for b in paragraph_blocks(book.read_archive_file(doc).decode("utf-8"))]


# Card 3: the empty-paragraph sweep took image-only paragraphs and anchors; removed headers took their ids along.
def test_card3_pictures_and_anchors_beside_a_header_stay_and_header_ids_move(tmp_path):
    from core.epub_metadata import EpubBook
    from core.page_headers import apply_page_furniture, find_page_furniture

    body = []
    for n in range(10, 18):
        body += [
            _scan_p("The expedition set out into the jungle and the heat was"),
            _scan_p("<span>&#160;</span>"),  # a truly empty paragraph: it still goes
            _scan_p(f"{n} THE LOST MINE", f' id="pg{n}"'),
            _scan_p('<img src="plate.jpg" alt=""/>', ' class="plate"'),
            _scan_p(f'<a id="note{n}"/>'),
            _scan_p("terrible before the night was over."),
        ]
    path = _headers_book(tmp_path, [("a.xhtml", "".join(body))])
    book = EpubBook(path)
    plan = find_page_furniture(book)
    assert plan.changed
    apply_page_furniture(book, plan)
    out = book.read_archive_file("OEBPS/a.xhtml").decode("utf-8")
    assert out.count('src="plate.jpg"') == 8
    for n in range(10, 18):
        assert f'id="pg{n}"' in out and f'id="note{n}"' in out
        assert f"{n} THE LOST MINE" not in out
    assert "&#160;" not in out
    texts = [t for t in _doc_paragraphs(book, "OEBPS/a.xhtml") if t]
    assert texts == ["The expedition set out into the jungle and the heat was terrible before the night was over."] * 8


def test_card3_a_joined_paragraph_keeps_its_id(tmp_path):
    from core.page_headers import Block, _rewrite_document, paragraph_blocks

    text = '<p>and the rain would</p><p>12 THE LOST MINE</p><p id="p13">come at night.</p>'
    blocks = paragraph_blocks(text)
    assert isinstance(blocks[0], Block)
    new, plan = _rewrite_document(text, blocks, {1: "header with page number (left)"})
    assert plan.joins == 1 and 'id="p13"' in new and "12 THE LOST MINE" not in new
    assert [b.text for b in paragraph_blocks(new)] == ["and the rain would come at night."]


# Card 4: a story title equal to the running header was removed when no "CHAPTER n" line stood before it.
def test_card4_a_story_title_that_opens_a_document_or_follows_a_rule_stays(tmp_path):
    from core.epub_metadata import EpubBook
    from core.page_headers import apply_page_furniture, find_page_furniture

    title = "THE RIVER CROSSING"
    pages, page = [], 3
    for story in range(3):
        body = [_scan_p(title)]
        for _i in range(4):
            body += [_scan_p("The water rose and they waited on the bank until"), _scan_p(f"{title} {page}"),
                     _scan_p("the morning came at last.")]
            page += 2
        # inside the last story a section break, then the title again (a second part)
        if story == 2:
            body += ["<hr/>", _scan_p(title), _scan_p("The second crossing began quietly."), _scan_p(title + " " + str(page)),
                     _scan_p(title), _scan_p("A running header without its number, mid-text, still goes.")]
        pages.append((f"s{story}.xhtml", "".join(body)))
    book = EpubBook(_headers_book(tmp_path, pages))
    plan = find_page_furniture(book)
    assert plan.changed
    apply_page_furniture(book, plan)
    for story in range(3):
        assert _doc_paragraphs(book, f"OEBPS/s{story}.xhtml")[0] == title
    last = _doc_paragraphs(book, "OEBPS/s2.xhtml")
    after_rule = last[last.index("The second crossing began quietly.") - 1]
    assert after_rule == title
    assert last.count(title) == 2  # the opening title and the one after the rule; the bare header mid-text went


# Card 55: "well-" + "known" became "wellknown" and nothing said so.
def test_card55_hyphen_joins_are_listed_and_a_hyphenated_compound_keeps_its_hyphen():
    from core.page_headers import _rewrite_document, paragraph_blocks

    text = ("<p>She was a well-</p><p>12 THE LOST MINE</p><p>known face, and her mother-in-</p>"
            "<p>13 THE LOST MINE</p><p>law was not.</p>")
    new, plan = _rewrite_document(text, paragraph_blocks(text), {1: "left", 3: "right"})
    assert [b.text for b in paragraph_blocks(new)] == ["She was a wellknown face, and her mother-in-law was not."]
    assert plan.hyphen_joins == 2 and plan.hyphen_words == ["well-known -> wellknown"]


# Cards 8 and 31: a stray "<" swallowed the text after it; comments, style and script text leaked into the result.
@pytest.mark.parametrize("text", ["He said x<y.", "if a<b and c>d then x", "I <3 it\nreally", "5 < 10"])
def test_card8_text_without_a_known_tag_is_untouched(text):
    from core.description_html import has_html_markup, strip_html

    assert strip_html(text) == text and not has_html_markup(text)


@pytest.mark.parametrize("text, expected", [
    ("<p>if a<b and c>d then x</p>", "if a<b and c>d then x"),
    ("<p>A <b>bold</b> claim: x<y.</p>", "A bold claim: x<y."),
    ("<p>Hi</p><!-- tracking id 123 --><p>there</p>", "Hi\n\nthere"),
    ("<style>p{color:red}</style><p>Text</p>", "Text"),
    ("<p>One</p><script>var a = 1 < 2;</script> after", "One\n\nafter"),
])
def test_card8_card31_html_keeps_stray_lt_and_drops_comments_style_script(text, expected):
    from core.description_html import strip_html

    assert strip_html(text) == expected


# Card 7: Redact's validator fix split "Simon & Schuster" into two authors.
def test_card7_redact_validate_fix_leaves_a_company_author_alone(tmp_path):
    from core.redact_steps import SAFE_FIX_CODES
    from test_redact_steps import Trash, make_epub, only, quiet_lookups, run
    from core.redact_steps import RedactEnv
    from core.epub_metadata import EpubBook

    assert "AUTHORS_AMPERSAND" not in SAFE_FIX_CODES
    path = make_epub(str(tmp_path / "s.epub"), authors=("Simon &amp; Schuster",))
    env = RedactEnv(trash=Trash(str(tmp_path) + "-bin"), lookups=quiet_lookups(), make_cover=lambda *a: b"")
    run([EpubBook(path)], env, only("validate_fix"))
    assert EpubBook(path).metadata.authors == ["Simon & Schuster"]


# Card 9: an ISBN found only in the back matter reached the 0.9 auto-apply threshold.
def test_card9_a_back_matter_isbn_lands_below_the_threshold():
    from core.content_scan import guess_metadata_from_text

    scan = guess_metadata_from_text("Chapter One. It was a dark night.", "Also by Jane Doe: The Other Book, ISBN 978-0-306-40615-7")
    assert scan.isbn == "9780306406157" and scan.confidence["isbn"] < 0.9
    front = guess_metadata_from_text("Copyright 2001. ISBN 978-0-306-40615-7", "")
    assert front.confidence["isbn"] >= 0.9  # a front-matter ISBN is still certain


# Card 32: one source's year was joined with another edition's month and day.
def test_card32_month_and_day_only_come_with_their_year(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from core.epub_metadata import EpubBook
    from core.redact_steps import MetadataLookupStep

    class Cand:
        def __init__(self, **kw):
            self.series = ""
            self._d = kw

        def as_dict(self):
            return dict(self._d)

    def make(first, second):
        monkeypatch.setattr(MetadataLookupStep, "_isfdb_source", lambda self, ctx, isbn, problems: (first, 0.95, "ISFDB"))
        monkeypatch.setattr(MetadataLookupStep, "_local_source", lambda self, ctx, isbn, problems: (second, 0.95, "OL"))
        monkeypatch.setattr(MetadataLookupStep, "_online_source", lambda self, ctx, isbn, problems: None)
        path = _make_book(tmp_path / "y.epub", _UUID + "<dc:creator>A B</dc:creator>")
        ctx = SimpleNamespace(work=EpubBook(path), env=None)
        return dict(MetadataLookupStep().run(ctx).value)

    fields = make(Cand(pub_year="1965"), Cand(pub_year="2011", pub_month="03", pub_day="14", publisher="P"))
    assert fields["pub_year"] == "1965" and "pub_month" not in fields and "pub_day" not in fields
    assert fields["publisher"] == "P"
    fields = make(Cand(pub_year="1965"), Cand(pub_year="1965", pub_month="03", pub_day="14"))
    assert (fields["pub_year"], fields["pub_month"], fields["pub_day"]) == ("1965", "03", "14")


# Card 38: the temp name was cut on the whole path, so a long folder put the temp file in a parent folder.
def test_card38_temp_file_stays_in_the_books_folder(tmp_path):
    import os

    from core.redact_steps import _unused_sibling

    folder = os.path.join(str(tmp_path), "f" * 230)  # never created: only the name is built
    original = os.path.join(folder, "n" * 250 + ".epub")
    temp = _unused_sibling(original)
    assert os.path.dirname(temp) == folder and temp.endswith(".epub") and ".redact-" in temp


# Card 52: a zip name in NFD (macOS) or another case than the href counted as missing; Rebuild Manifest dropped it.
def test_card52_nfd_or_case_different_zip_names_are_not_missing(tmp_path):
    import unicodedata

    from core.epub_metadata import EpubBook

    nfc = unicodedata.normalize("NFC", "café.xhtml")
    nfd = unicodedata.normalize("NFD", nfc)
    assert nfc != nfd
    items = (f'<item id="c" href="{nfc}" media-type="application/xhtml+xml"/>'
             '<item id="d" href="Chap2.xhtml" media-type="application/xhtml+xml"/>'
             '<item id="gone" href="gone.xhtml" media-type="application/xhtml+xml"/>')
    page = _PAGE.format("<p>text</p>").encode()
    path = _make_book(tmp_path / "u.epub", _UUID, items=items,
                      spine='<itemref idref="c"/><itemref idref="d"/><itemref idref="gone"/>',
                      files={f"OEBPS/{nfd}": page, "OEBPS/chap2.xhtml": page})
    book = EpubBook(path)
    assert [i for i, _h in book.find_missing_manifest_files()] == ["gone"]
    assert book.rebuild_manifest() == ["gone.xhtml"]
    spine = [r.get("idref") for r in book._opf_tree.getroot().iter("{http://www.idpf.org/2007/opf}itemref")]
    assert spine == ["ch1", "c", "d"]


# Card 73: a damaged deflate stream raised zlib.error out of the page readers and the header scan.
def test_card73_a_damaged_deflate_stream_reads_as_unreadable(tmp_path):
    from core.epub_metadata import EpubBook
    from core.page_headers import find_page_furniture

    path = _make_book(tmp_path / "z.epub", _UUID, deflate=True)
    _damage_entry(path, "OEBPS/ch1.xhtml")
    book = EpubBook(path)
    assert book.read_text_page("OEBPS/ch1.xhtml") is None
    assert book.read_resource("OEBPS/ch1.xhtml") is None
    assert book.read_archive_file("OEBPS/ch1.xhtml") is None
    assert not find_page_furniture(book).changed


# --- batch 4: tools and conversion -----------------------------------------------------------------


def _fake_polish_writing(data_for):
    """A stand-in for core.ebook_polish.polish_book that writes data_for(src) to the output."""

    def fake(tool, src, dst, options, run_fn=None, **_kw):
        with open(dst, "wb") as f:
            f.write(data_for(src))

    return fake


# Card 15: Polish in place replaced the original with whatever ebook-polish wrote, unchecked, without a backup.
def test_card15_a_damaged_polish_result_never_replaces_the_original(tmp_path, monkeypatch):
    import gui.polish_book_dialog as pbd
    from core.ebook_polish import EbookPolishError

    path = _make_book(tmp_path / "p.epub", _UUID)
    before = open(path, "rb").read()
    binned = []
    monkeypatch.setattr(pbd, "polish_book", _fake_polish_writing(lambda src: b"PK not really a zip"))
    tmp = pbd.polish_temp_path(path)
    with pytest.raises(EbookPolishError):
        pbd.polish_in_place("ebook-polish", path, tmp, None, trash=binned.append)
    assert open(path, "rb").read() == before and binned == []


def test_card15_a_sound_polish_result_goes_in_and_the_original_to_the_bin(tmp_path, monkeypatch):
    import os

    import gui.polish_book_dialog as pbd

    path = _make_book(tmp_path / "p.epub", _UUID)
    other = _make_book(tmp_path / "other.epub", _UUID.replace("Book<", "Polished<"))
    monkeypatch.setattr(pbd, "polish_book", _fake_polish_writing(lambda src: open(other, "rb").read()))
    binned = []

    def trash(p):
        binned.append(open(p, "rb").read())
        os.remove(p)

    assert pbd.polish_in_place("ebook-polish", path, pbd.polish_temp_path(path), None, trash=trash) == ""
    assert open(path, "rb").read() == open(other, "rb").read()
    assert len(binned) == 1  # the original, sent to the Recycle Bin (the backup)
    assert sorted(os.listdir(tmp_path)) == ["other.epub", "p.epub"]


# Card 20: the temp name was not a family temp name, a failed remove after Cancel was swallowed, and an existing
# file of that name was overwritten.
def test_card20_polish_temp_name_is_a_family_temp_name_and_never_overwrites(tmp_path):
    import os

    import gui.polish_book_dialog as pbd
    from redactor_common.core.temp_names import is_app_temp_name

    book = str(tmp_path / "Foo.epub")
    first = pbd.polish_temp_path(book)
    assert first == str(tmp_path / "Foo.partial.epub") and is_app_temp_name("Foo.partial.epub")
    (tmp_path / "Foo.partial.epub").write_bytes(b"somebody's file")
    second = pbd.polish_temp_path(book)
    assert second != first and is_app_temp_name(os.path.basename(second))


def test_card20_temp_remove_is_retried_while_locked(tmp_path, monkeypatch):
    import os

    import gui.polish_book_dialog as pbd

    target = tmp_path / "Foo.partial.epub"
    target.write_bytes(b"x")
    real_remove, calls = os.remove, []

    def locked_twice(p):
        calls.append(p)
        if len(calls) < 3:
            raise PermissionError(32, "in use")
        real_remove(p)

    monkeypatch.setattr(pbd.os, "remove", locked_twice)
    assert pbd.remove_with_retry(str(target), delay=0) is True
    assert len(calls) == 3 and not target.exists()


def test_card20_failed_polish_leaves_no_temp_file(tmp_path, monkeypatch, qapp):
    import os

    import gui.polish_book_dialog as pbd
    from core.ebook_polish import EbookPolishError
    from core.epub_metadata import EpubBook

    book = EpubBook(_make_book(tmp_path / "Foo.epub", _UUID))
    written = []

    def failing(tool, src, dst, options, run_fn=None, **_kw):
        written.append(dst)
        with open(dst, "wb") as f:
            f.write(b"half")
        raise EbookPolishError("ebook-polish failed")

    monkeypatch.setattr(pbd, "polish_book", failing)
    monkeypatch.setattr(pbd, "move_to_trash", os.remove)
    dialog = pbd.PolishBookDialog([book])
    dialog._tool_path = "ebook-polish"
    monkeypatch.setattr(dialog, "_collect_options", lambda: type("O", (), {"any_selected": lambda self: True})())
    dialog._run_polish()
    assert [os.path.basename(p) for p in written] == ["Foo.partial.epub"]
    assert sorted(os.listdir(tmp_path)) == ["Foo.epub"]


# Card 19: the quarantine move ran before the undo log was written; a log failure was reported as "NOT touched".
def test_card19_undo_log_failure_leaves_the_original_in_place(tmp_path):
    import os
    import zipfile
    from datetime import date

    from core import conversion_safety as cs
    from redactor_common.core import conversion_policy as pm

    source = tmp_path / "a.mobi"
    source.write_bytes(b"mobi")
    result = tmp_path / "a.epub"
    with zipfile.ZipFile(result, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", "<container/>")
    blocker = tmp_path / "logs-is-a-file"
    blocker.write_bytes(b"x")  # the undo-log folder cannot be made below a file
    policy = pm.ConversionPolicy(on_open=pm.ON_OPEN_ASK, originals=pm.ORIGINALS_QUARANTINE, recent_minutes=0,
                                 dry_run_first=False, undo_log_folder=str(blocker / "sub"))
    outcome = cs.settle_original(str(source), str(result), policy, today=date(2026, 11, 27))
    assert outcome.action == "failed" and "undo log" in outcome.note
    assert source.read_bytes() == b"mobi"  # really not touched
    assert not os.path.exists(tmp_path / "converted originals 2026-11-27" / "a.mobi")


def test_card19_a_log_write_failure_after_the_move_says_where_the_original_went(tmp_path, monkeypatch):
    import builtins
    import zipfile
    from datetime import date

    from core import conversion_safety as cs
    from redactor_common.core import conversion_policy as pm

    source = tmp_path / "a.mobi"
    source.write_bytes(b"mobi")
    result = tmp_path / "a.epub"
    with zipfile.ZipFile(result, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", "<container/>")
    real_open = builtins.open

    class _Broken:
        def write(self, _text):
            raise OSError(5, "drive gone")

        def flush(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(cs, "open", lambda p, *a, **k: _Broken() if str(p).endswith(".tsv") else real_open(p, *a, **k),
                        raising=False)
    policy = pm.ConversionPolicy(on_open=pm.ON_OPEN_ASK, originals=pm.ORIGINALS_QUARANTINE, recent_minutes=0,
                                 dry_run_first=False)
    outcome = cs.settle_original(str(source), str(result), policy, today=date(2026, 11, 27))
    assert outcome.action == "quarantined" and not source.exists()
    assert "undo log" in outcome.note and outcome.destination in outcome.line()


# Card 24: Open Folder converted the same files again on every open.
def test_card24_folder_scan_skips_converted_books_and_quarantine_folders(tmp_path):
    from gui.main_window import find_convertible_books

    for name in ("Book.mobi", "Book.epub", "New.azw3", "converted originals 2026-11-27/Old.mobi",
                 "sub/Converted Originals 2026-01-02/deep/X.fb2"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    found = [p.replace(str(tmp_path), "").lstrip("/\\") for p in find_convertible_books([str(tmp_path)])]
    assert found == ["New.azw3"]
    # A file named directly is taken as meant.
    assert find_convertible_books([str(tmp_path / "Book.mobi")]) == [str(tmp_path / "Book.mobi")]


def test_card24_automatic_conversion_skips_instead_of_numbering(tmp_path, monkeypatch, qapp):
    import os

    import gui.ebook_convert_dialog as ecd

    for name in ("Book.mobi", "Book.epub", "Two.mobi", "Two.azw3"):
        (tmp_path / name).write_bytes(b"x")
    made = []

    def fake_convert(tool, src, dst, run_fn=None):
        made.append(os.path.basename(dst))
        open(dst, "wb").close()

    monkeypatch.setattr(ecd, "convert_to_epub", fake_convert)
    dialog = ecd.EbookConvertDialog(None, initial_paths=[str(tmp_path / n) for n in ("Book.mobi", "Two.azw3", "Two.mobi")])
    dialog._tool_path = "ebook-convert"
    dialog.convert_all(show_report=False, skip_existing=True)
    assert made == ["Two.epub"]
    assert "Book.mobi: skipped" in dialog.report_text and "Two.mobi: skipped" in dialog.report_text
    assert not any("(2)" in name for name in os.listdir(tmp_path))


# Card 16: Send to Kobo wrote straight to the final name, left a partial file on error, numbered re-sends and copied
# on the GUI thread.
def test_card16_failed_copy_leaves_nothing_on_the_kobo(tmp_path):
    import os

    from core.kobo_usb import KoboSendError, send_to_kobo

    source = tmp_path / "Book.epub"
    source.write_bytes(b"new book")
    kobo = tmp_path / "kobo"
    kobo.mkdir()
    (kobo / "Book.epub").write_bytes(b"the Kobo's good copy")

    def unplugged(src, dst):
        with open(dst, "wb") as f:
            f.write(b"half")
        raise OSError(5, "device not ready")

    with pytest.raises(KoboSendError):
        send_to_kobo(str(kobo), str(source), copy_fn=unplugged)
    assert os.listdir(kobo) == ["Book.epub"] and (kobo / "Book.epub").read_bytes() == b"the Kobo's good copy"


def test_card16_cancel_removes_the_partial_copy_and_part_names_are_temp_names(tmp_path):
    import os
    import threading

    from core.kobo_usb import KoboSendCancelled, part_path, send_to_kobo
    from redactor_common.core.temp_names import is_app_temp_name

    source = tmp_path / "Book.epub"
    source.write_bytes(b"x" * 3_000_000)
    kobo = tmp_path / "kobo"
    kobo.mkdir()
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(KoboSendCancelled):
        send_to_kobo(str(kobo), str(source), cancel=cancel)
    assert os.listdir(kobo) == []
    assert is_app_temp_name(os.path.basename(part_path(str(kobo / "Book.epub"))))
    assert send_to_kobo(str(kobo), str(source)) == str(kobo / "Book.epub")
    assert (kobo / "Book.epub").stat().st_size == 3_000_000 and os.listdir(kobo) == ["Book.epub"]


def _kobo_dialog(monkeypatch, tmp_path, books, save_books=None):
    import gui.send_to_kobo_dialog as skd

    kobo = tmp_path / "kobo"
    kobo.mkdir(exist_ok=True)
    monkeypatch.setattr(skd, "find_connected_kobos", lambda: [str(kobo)])
    return skd.SendToKoboDialog(books, save_books=save_books), kobo


def test_card16_dialog_copies_off_the_gui_thread_with_a_working_cancel(tmp_path, monkeypatch, qapp):
    import threading

    import gui.send_to_kobo_dialog as skd
    from core.epub_metadata import EpubBook

    book = EpubBook(_make_book(tmp_path / "Book.epub", _UUID))
    dialog, kobo = _kobo_dialog(monkeypatch, tmp_path, [book])
    seen, calls = {}, []
    real_send, real_progress = skd.send_to_kobo, skd.run_with_progress

    def spy_send(*args, **kwargs):
        seen["thread"] = threading.current_thread()
        seen["cancel"] = kwargs.get("cancel")
        return real_send(*args, **kwargs)

    def spy_progress(parent, items, step, label, **kwargs):
        calls.append(kwargs)
        return real_progress(parent, items, step, label, **kwargs)

    monkeypatch.setattr(skd, "send_to_kobo", spy_send)
    monkeypatch.setattr(skd, "run_with_progress", spy_progress)
    dialog._run_send()
    assert seen["thread"] is not threading.main_thread() and seen["cancel"] is not None
    assert calls and calls[0].get("on_cancel") is not None
    assert dialog.sent_count() == 1 and (kobo / "Book.epub").exists()


# Card 25: Send to Kobo sent the file on disk and ignored unsaved edits.
def test_card25_unsaved_books_save_and_send(tmp_path, monkeypatch, qapp):
    from core.epub_metadata import EpubBook
    import gui.send_to_kobo_dialog as skd

    clean = EpubBook(_make_book(tmp_path / "Clean.epub", _UUID))
    dirty = EpubBook(_make_book(tmp_path / "Dirty.epub", _UUID))
    dirty.dirty = True
    saved = []

    def save_books(books):
        saved.extend(books)
        for b in books:
            b.dirty = False
        return []

    dialog, kobo = _kobo_dialog(monkeypatch, tmp_path, [clean, dirty], save_books=save_books)
    asked = []
    monkeypatch.setattr(dialog, "_ask_about_unsaved", lambda unsaved: asked.append(unsaved) or skd.UNSAVED_SAVE)
    dialog._run_send()
    assert asked == [[dirty]] and saved == [dirty] and dialog.saved_any
    assert sorted(p.name for p in kobo.iterdir()) == ["Clean.epub", "Dirty.epub"]


def test_card25_a_failed_save_is_not_sent_and_cancel_sends_nothing(tmp_path, monkeypatch, qapp):
    from core.epub_metadata import EpubBook
    import gui.send_to_kobo_dialog as skd

    dirty = EpubBook(_make_book(tmp_path / "Dirty.epub", _UUID))
    dirty.dirty = True
    dialog, kobo = _kobo_dialog(monkeypatch, tmp_path, [dirty], save_books=lambda books: [(books[0].path, "disk full")])
    monkeypatch.setattr(dialog, "_ask_about_unsaved", lambda unsaved: skd.UNSAVED_CANCEL)
    dialog._run_send()
    assert list(kobo.iterdir()) == []
    monkeypatch.setattr(dialog, "_ask_about_unsaved", lambda unsaved: skd.UNSAVED_SAVE)
    dialog._run_send()
    assert list(kobo.iterdir()) == [] and dialog.sent_count() == 0
    monkeypatch.setattr(dialog, "_ask_about_unsaved", lambda unsaved: skd.UNSAVED_SEND_ANYWAY)
    dialog._run_send()
    assert [p.name for p in kobo.iterdir()] == ["Dirty.epub"]


# Card 46: Cancel in the Calibre lookup abandoned the worker but left fetch-ebook-metadata running.
def test_card46_cancel_kills_the_calibre_lookup(tmp_path, monkeypatch, qapp):
    import threading
    import time
    from types import SimpleNamespace

    from PyQt6.QtWidgets import QProgressDialog

    import gui.calibre_lookup_dialog as cld
    from core.calibre_tools import ToolCancelled
    from core.epub_metadata import EpubBook

    monkeypatch.setattr(cld, "find_tool", lambda *a, **k: None)
    book = EpubBook(_make_book(tmp_path / "b.epub", _UUID))
    dialog = cld.CalibreLookupDialog([book])
    seen = {}

    def fake_fetch(*_a, run_fn=None, **_k):
        seen["run_fn"] = run_fn
        raise cld.CalibreLookupError("nothing")

    monkeypatch.setattr(cld, "fetch_metadata", fake_fetch)
    progress = QProgressDialog()
    dialog._cancel_signal(SimpleNamespace(dialog=progress))
    dialog._search_one(book, {})
    run_fn = seen["run_fn"]
    outcome = {}

    def worker():  # the lookup runs on a worker thread; Cancel is clicked on the GUI thread
        try:
            run_fn([sys.executable, "-c", "import time; time.sleep(30)"], capture_output=True, timeout=60)
        except ToolCancelled:
            outcome["cancelled"] = True

    thread = threading.Thread(target=worker, daemon=True)
    started = time.monotonic()
    thread.start()
    time.sleep(0.5)
    progress.canceled.emit()
    thread.join(15)
    assert outcome.get("cancelled") and time.monotonic() - started < 10
    progress.deleteLater()


# Card 58: Cancel killed only Calibre's launcher; a child it started kept running.
def test_card58_cancel_kills_the_whole_process_tree(tmp_path):
    import threading
    import time

    from core.calibre_tools import ToolCancelled, cancellable_run

    beat = tmp_path / "beat.txt"
    beat.write_text("")
    grandchild = ("import sys, time, itertools; f = open(sys.argv[1], 'a'); "
                  "[(f.write('x'), f.flush(), time.sleep(0.05)) for _ in itertools.count()]")
    parent = ("import subprocess, sys, time; "
              "subprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2]], "
              "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(60)")
    cancel = threading.Event()

    def cancel_once_beating():
        deadline = time.monotonic() + 20
        while beat.stat().st_size == 0 and time.monotonic() < deadline:
            time.sleep(0.05)
        cancel.set()

    threading.Thread(target=cancel_once_beating, daemon=True).start()
    with pytest.raises(ToolCancelled):
        cancellable_run(cancel, poll_seconds=0.05)(
            [sys.executable, "-c", parent, grandchild, str(beat)], capture_output=True, timeout=60)
    assert beat.stat().st_size > 0
    time.sleep(0.5)
    size = beat.stat().st_size
    time.sleep(0.6)
    assert beat.stat().st_size == size, "the grandchild is still writing"


# --- batch 5: main window and dialogs ------------------------------------------------------------

def _window_with(tmp_path, names, metadata=_UUID):
    from core.epub_metadata import EpubBook
    from gui import main_window as mw

    window = mw.MainWindow()
    window.books = [EpubBook(_make_book(tmp_path / name, metadata)) for name in names]
    window._rebuild_table()
    return window


# Card 10: Undo wrote back the old "unsaved" flag.
def test_card10_undo_after_a_save_leaves_the_book_unsaved(tmp_path, qapp):
    window = _window_with(tmp_path, ["a.epub"])
    book = window.books[0]
    window._push_undo("Edit Title", [book])
    book.apply_metadata({"title": "New"})
    book.save()
    assert not book.dirty
    window.on_undo()
    assert book.metadata.title == "Book" and book.dirty
    window.on_redo()  # back to what the file holds
    assert book.metadata.title == "New" and not book.dirty


def test_card10_undo_keeps_a_staged_repair_unsaved_and_a_plain_undo_is_clean(tmp_path, qapp):
    from core.epub_metadata import EpubBook
    from gui.main_window import MainWindow

    path = _make_book(tmp_path / "o.epub", _UUID, files={"OEBPS/stray.txt": b"x"})
    book = EpubBook(path)
    snap = MainWindow._snapshot_book(book)
    book.apply_metadata({"title": "New"})
    MainWindow._restore_book(book, snap)
    assert not book.dirty  # back to exactly what the file holds

    snap = MainWindow._snapshot_book(book)
    book.apply_metadata({"title": "New"})
    assert book.remove_orphaned_files(["OEBPS/stray.txt"])
    MainWindow._restore_book(book, snap)
    assert book.metadata.title == "Book" and book.dirty  # the staged removal still has to be saved


def test_card10_undo_keeps_removed_running_headers(tmp_path, qapp):
    from core.epub_metadata import EpubBook
    from gui.main_window import MainWindow

    book = EpubBook(_make_book(tmp_path / "h.epub", _UUID))
    snap = MainWindow._snapshot_book(book)
    book.apply_metadata({"title": "New"})
    book.stage_content_replacement("OEBPS/ch1.xhtml", b"<html/>")
    MainWindow._restore_book(book, snap)
    assert book._image_replacements == {"OEBPS/ch1.xhtml": b"<html/>"} and book.dirty


# Card 14: Author Sort -> Author(s) dropped co-authors, ticked by default.
def test_card14_author_sort_with_fewer_names_starts_unticked(qapp):
    from types import SimpleNamespace

    from gui.author_sort_dialog import AuthorSortDialog

    def fake(name, authors, sort):
        return SimpleNamespace(path=name, load_error=None,
                               metadata=SimpleNamespace(authors_str=authors, author_sort_str=sort))

    books = [fake("a.epub", "Frank Herbert; Brian Herbert", "Herbert, Frank"),
             fake("b.epub", "Jane Doe", "Smith, Ann")]
    dialog = AuthorSortDialog(books)
    dialog.direction_combo.setCurrentIndex(1)  # Author Sort -> Author(s)
    assert not dialog._checkboxes[0].isChecked()
    assert dialog._checkboxes[1].isChecked()
    assert dialog.accepted_changes() == {1: "Ann Smith"}
    assert "unticked" in dialog.status_label.text()


# Card 17: editing a Description cell in Clip/Ellipsis saved the flattened text.
def test_card17_description_cell_is_not_edited_in_place_outside_wrap(tmp_path, qapp):
    from PyQt6.QtWidgets import QAbstractItemView

    from gui import main_window as mw

    window = _window_with(tmp_path, ["a.epub"])
    keys = [key for key, _label, _multiline in mw.FIELDS]
    col = mw.FIRST_FIELD_COL + keys.index("description")
    title_col = mw.FIRST_FIELD_COL + keys.index("title")
    trigger = QAbstractItemView.EditTrigger.DoubleClicked
    window.set_text_overflow_mode("clip")
    assert window.table.edit(window.table.model().index(0, col), trigger, None) is False
    assert "side panel" in window.status.currentMessage()
    assert window.table.locked_columns == frozenset({col})
    window.set_text_overflow_mode("ellipsis")
    assert window.table.locked_columns == frozenset({col})
    window.set_text_overflow_mode("wrap")
    assert window.table.locked_columns == frozenset()
    assert title_col not in window.table.locked_columns


# Card 18: the wheel over a side-panel field picked a value without the field having focus.
def test_card18_wheel_over_an_unfocused_field_scrolls_instead_of_picking(qapp):
    from PyQt6.QtCore import QPoint, QPointF, Qt
    from PyQt6.QtGui import QWheelEvent

    from gui.tag_panel import MultiValueLineEdit

    edit = MultiValueLineEdit()
    edit.set_alternatives(["A", "B"])
    picked = []
    edit.valuePicked.connect(lambda: picked.append(edit.text()))
    event = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, 120),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    edit.wheelEvent(event)
    assert picked == [] and edit.text() == "" and not event.isAccepted()


# Card 26: Search & Replace on Filename numbered a case-only change and let the extension change.
def test_card26_filename_replace_case_only_and_extension_kept(tmp_path, qapp):
    import os

    folder = tmp_path / "books"
    folder.mkdir()
    window = _window_with(folder, ["my book.epub", "other.epub"])
    books = list(window.books)
    window._apply_filename_search_replace(books, {0: "My Book.epub", 1: "other.zip"})
    assert sorted(os.listdir(folder)) == ["My Book.epub", "other.epub"]


# Card 33: Detect Missing Spaces "fixed" initials, acronyms and web addresses.
@pytest.mark.parametrize("text", ["R.U.R.", "P.S. I Love You", "e.g. this", "U.S.A.", "see example.com", "www.Site.org"])
def test_card33_initials_acronyms_and_addresses_are_left_alone(text):
    from core.missing_space import find_missing_spaces, suggest_fix

    assert find_missing_spaces(text) == [] and suggest_fix(text) == text


def test_card33_a_real_missing_space_after_initials_is_still_found():
    from core.missing_space import suggest_fix

    assert suggest_fix("J.R.R.Tolkien") == "J.R.R. Tolkien"
    assert suggest_fix("Hello.World") == "Hello. World"


# Card 34: Number Series numbered books with no series (the save drops the number).
def test_card34_books_without_a_series_are_skipped(qapp):
    from types import SimpleNamespace

    from gui.series_number_dialog import SeriesNumberDialog

    def fake(name, series):
        return SimpleNamespace(path=name, metadata=SimpleNamespace(series=series, series_index=""))

    dialog = SeriesNumberDialog([fake("a.epub", "Dune"), fake("b.epub", ""), fake("c.epub", "Dune")])
    assert dialog.result_values() == {0: "1", 2: "2"}
    assert "skipped" in dialog.table.item(1, 2).text()
    assert "1 book(s) have no Series" in dialog.skipped_label.text()


# Card 37: Save All left out books that failed before without saying so.
def test_card37_save_all_names_books_skipped_for_an_earlier_failure(tmp_path, qapp, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox

    window = _window_with(tmp_path, ["a.epub", "b.epub"])
    for book in window.books:
        book.apply_metadata({"title": "Changed"})
    window.books[1].save_error = "locked yesterday"
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a[2])))
    window._save_changed_among(list(window.books))
    assert not window.books[0].dirty
    assert any("1 book(s) skipped because they failed to save earlier" in w and "b.epub" in w for w in warnings)
    assert "skipped (failed to save earlier)" in window.status.currentMessage()
