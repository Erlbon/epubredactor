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
