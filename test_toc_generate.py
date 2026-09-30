"""Tests for Repair -> Generate Table of Contents: core/toc_generate.py
(heading heuristic, nav/NCX rendering), EpubBook staging + save, and the
dialog/menu wiring."""
import os
import sys
import zipfile
from urllib.parse import unquote

import pytest
from lxml import etree

sys.path.insert(0, os.path.dirname(__file__))
from PyQt6.QtWidgets import QApplication  # noqa: E402

from core.epub_metadata import NS, EpubBook, href_to_archive_path  # noqa: E402
from core.toc_generate import (  # noqa: E402
    generate_toc_entries, needs_toc, render_toc_files, stage_generated_toc_for,
)

_app = QApplication.instance() or QApplication(sys.argv)

CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""
NCX_NS = {"n": "http://www.daisy.org/z3986/2005/ncx/"}
XHTML_NS = {"x": "http://www.w3.org/1999/xhtml"}
NAV_ITEM = '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'


def page(body, title=""):
    t = f"<title>{title}</title>" if title else ""
    return f"<html><head>{t}</head><body>{body}</body></html>"


def make_epub(tmp_path, docs, version="3.0", name="book.epub", book_title="The Book",
              extra_manifest="", extra_files=None):
    """docs: [(href_in_opf, html)]; hrefs are used verbatim in the OPF, the
    archive member is the percent-decoded name."""
    items = "".join(
        f'<item id="d{i}" href="{href}" media-type="application/xhtml+xml"/>'
        for i, (href, _h) in enumerate(docs)
    )
    spine = "".join(f'<itemref idref="d{i}"/>' for i in range(len(docs)))
    opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="{version}" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="BookId">urn:uuid:1234-abcd</dc:identifier>
    <dc:title>{book_title}</dc:title><dc:language>en</dc:language>
  </metadata>
  <manifest>{items}{extra_manifest}</manifest>
  <spine>{spine}</spine>
</package>"""
    path = str(tmp_path / name)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", opf)
        for href, html in docs:
            zf.writestr("OEBPS/" + unquote(href), html)
        for n, data in (extra_files or {}).items():
            zf.writestr(n, data)
    return path


def chapters(n=3):
    return [(f"ch{i}.xhtml", page(f'<h1 id="c{i}">Chapter {i}</h1><p>text</p>')) for i in range(1, n + 1)]


# --- heuristic ----------------------------------------------------------------

def test_no_toc_detected_and_headings_become_entries(tmp_path):
    book = EpubBook(make_epub(tmp_path, chapters()))
    assert needs_toc(book)
    entries = generate_toc_entries(book)
    assert [(e.title, e.archive_path, e.fragment, e.level) for e in entries] == [
        ("Chapter 1", "OEBPS/ch1.xhtml", "c1", 1),
        ("Chapter 2", "OEBPS/ch2.xhtml", "c2", 1),
        ("Chapter 3", "OEBPS/ch3.xhtml", "c3", 1),
    ]


def test_levels_never_jump_and_idless_later_headings_are_dropped(tmp_path):
    docs = [("a.xhtml", page(
        '<h2 id="x">Part</h2><h3 id="y">Deep</h3><h1>No id later</h1><h3 id="z">After</h3>'))]
    entries = generate_toc_entries(EpubBook(make_epub(tmp_path, docs)))
    # h2 first -> normalized to level 1; h3 -> 2; the id-less non-first h1 is dropped
    assert [(e.title, e.level) for e in entries] == [("Part", 1), ("Deep", 2), ("After", 2)]
    assert entries[0].fragment == "x"


def test_first_heading_without_id_links_to_document_top(tmp_path):
    docs = [("a.xhtml", page("<h1>Intro</h1><p>x</p>")), ("b.xhtml", page('<h1 id="b">Two</h1>'))]
    entries = generate_toc_entries(EpubBook(make_epub(tmp_path, docs)))
    assert entries[0].title == "Intro" and entries[0].fragment == ""


def test_anchor_inside_heading_supplies_fragment(tmp_path):
    docs = [("a.xhtml", page('<h1><a id="anc"></a>Title <br/> Here</h1>'))]
    entries = generate_toc_entries(EpubBook(make_epub(tmp_path, docs)))
    assert (entries[0].title, entries[0].fragment) == ("Title Here", "anc")


def test_title_fallback_skips_book_title_and_filenames(tmp_path):
    docs = [
        ("a.xhtml", page("<p>x</p>", "Prologue")),
        ("b.xhtml", page("<p>x</p>", "The Book")),       # == book title
        ("c.xhtml", page("<p>x</p>", "c.xhtml")),        # filename-like
        ("d.xhtml", page("<p>x</p>")),                   # nothing
    ]
    entries = generate_toc_entries(EpubBook(make_epub(tmp_path, docs)))
    assert [e.title for e in entries] == ["Prologue"]


def test_repeated_running_header_is_ignored(tmp_path):
    docs = []
    for i in range(1, 11):
        body = '<h1 id="h">MY BOOK - PAGE HEADER</h1>'
        if i in (1, 5, 8):
            body += f'<h2 id="ch">Chapter {i}</h2>'
        docs.append((f"p{i}.xhtml", page(body + "<p>text</p>")))
    entries = generate_toc_entries(EpubBook(make_epub(tmp_path, docs)))
    assert [e.title for e in entries] == ["Chapter 1", "Chapter 5", "Chapter 8"]
    assert all(e.level == 1 for e in entries)  # h2 normalized up once the header is gone


def test_repeated_title_ignored_then_falls_back_to_sections(tmp_path):
    docs = [(f"p{i}.xhtml", page("<p>text</p>", "Scanned Volume")) for i in range(1, 8)]
    entries = generate_toc_entries(EpubBook(make_epub(tmp_path, docs)))
    assert [e.title for e in entries] == [f"Section {i}" for i in range(1, 8)]
    assert all(e.fragment == "" for e in entries)


def test_section_fallback_is_sampled_for_huge_page_books(tmp_path):
    docs = [(f"p{i}.xhtml", page("<p>text</p>")) for i in range(1, 201)]
    entries = generate_toc_entries(EpubBook(make_epub(tmp_path, docs)))
    assert 0 < len(entries) <= 40
    assert entries[0].title == "Section 1"


def test_cover_page_labeled_cover(tmp_path):
    docs = [("cover.xhtml", page('<img src="c.jpg"/>'))] + chapters(2)
    entries = generate_toc_entries(EpubBook(make_epub(tmp_path, docs)))
    assert [e.title for e in entries] == ["Cover", "Chapter 1", "Chapter 2"]


def test_many_subheadings_collapse_to_one_per_document(tmp_path):
    body = "".join(f'<h3 id="s{i}">Sub {i}</h3>' for i in range(400))
    docs = [("a.xhtml", page('<h1 id="t">Big</h1>' + body)), ("b.xhtml", page('<h1 id="u">Next</h1>'))]
    entries = generate_toc_entries(EpubBook(make_epub(tmp_path, docs)))
    assert [e.title for e in entries] == ["Big", "Next"]


def test_malformed_and_empty_docs_do_not_crash(tmp_path):
    docs = [("a.xhtml", "<h1 id=a>Unclosed <b>bold"), ("b.xhtml", ""), ("c.xhtml", "\x00\x01 not html"),
            ("d.xhtml", page('<h1 id="d">Fine</h1>'))]
    entries = generate_toc_entries(EpubBook(make_epub(tmp_path, docs)))
    assert "Fine" in [e.title for e in entries]


def test_book_with_existing_toc_does_not_need_one(tmp_path):
    assert not needs_toc(EpubBook(make_epub(tmp_path, chapters(), extra_manifest=NAV_ITEM)))


# --- rendering + save round trip ------------------------------------------------

def link_targets_exist(zf, doc_path, xpath_ns, xpath, attr):
    root = etree.fromstring(zf.read(doc_path))
    targets = root.xpath(xpath, namespaces=xpath_ns)
    assert targets
    names = set(zf.namelist())
    base = os.path.dirname(doc_path)
    for el in targets:
        assert href_to_archive_path(base, el.get(attr)) in names
    return targets


def test_epub3_round_trip_writes_nav_and_ncx(tmp_path):
    path = make_epub(tmp_path, chapters())
    book = EpubBook(path)
    stage_generated_toc_for(book, generate_toc_entries(book))
    assert book.dirty
    assert not needs_toc(book)  # cleared immediately, before any save
    book.save()
    assert not book.dirty

    reloaded = EpubBook(path)
    assert not reloaded.load_error
    codes = {i.code for i in reloaded.validation_issues}
    assert "NO_TOC" not in codes and "MANIFEST_FILE_MISSING" not in codes

    root = reloaded._opf_tree.getroot()
    items = {i.get("id"): i for i in root.find("opf:manifest", NS)}
    nav_item = [i for i in items.values() if i.get("properties") == "nav"][0]
    ncx_item = items[root.find("opf:spine", NS).get("toc")]
    assert ncx_item.get("media-type") == "application/x-dtbncx+xml"
    assert len(root.find("opf:spine", NS)) == 3  # nav not added to the spine
    with zipfile.ZipFile(path) as zf:
        nav_path = href_to_archive_path("OEBPS", nav_item.get("href"))
        links = link_targets_exist(zf, nav_path, XHTML_NS, "//x:nav//x:a", "href")
        assert [a.text for a in links] == ["Chapter 1", "Chapter 2", "Chapter 3"]
        assert b'epub:type="toc"' in zf.read(nav_path)
        ncx_path = href_to_archive_path("OEBPS", ncx_item.get("href"))
        link_targets_exist(zf, ncx_path, NCX_NS, "//n:content", "src")
        uid = etree.fromstring(zf.read(ncx_path)).xpath("//n:meta[@name='dtb:uid']/@content", namespaces=NCX_NS)
        assert uid == ["urn:uuid:1234-abcd"]
        assert zf.namelist()[0] == "mimetype"


def test_epub2_gets_only_ncx(tmp_path):
    path = make_epub(tmp_path, chapters(), version="2.0")
    book = EpubBook(path)
    stage_generated_toc_for(book, generate_toc_entries(book))
    book.save()
    root = EpubBook(path)._opf_tree.getroot()
    assert not [i for i in root.find("opf:manifest", NS) if "nav" in (i.get("properties") or "")]
    assert root.find("opf:spine", NS).get("toc")
    with zipfile.ZipFile(path) as zf:
        assert not [n for n in zf.namelist() if n.endswith("nav.xhtml")]
        assert any(n.endswith(".ncx") for n in zf.namelist())


def test_percent_encoded_hrefs_stay_encoded_and_resolve(tmp_path):
    docs = [("ch%201.xhtml", page('<h1 id="a b">One</h1>')),
            ("caf%C3%A9.xhtml", page('<h1 id="e">Two</h1>'))]
    path = make_epub(tmp_path, docs)
    book = EpubBook(path)
    entries = generate_toc_entries(book)
    assert entries[0].archive_path == "OEBPS/ch 1.xhtml"
    stage_generated_toc_for(book, entries)
    book.save()
    with zipfile.ZipFile(path) as zf:
        ncx_name = [n for n in zf.namelist() if n.endswith(".ncx")][0]
        srcs = etree.fromstring(zf.read(ncx_name)).xpath("//n:content/@src", namespaces=NCX_NS)
        assert srcs == ["ch%201.xhtml#a%20b", "caf%C3%A9.xhtml#e"]
        link_targets_exist(zf, ncx_name, NCX_NS, "//n:content", "src")
    assert "NO_TOC" not in {i.code for i in EpubBook(path).validation_issues}


def test_generated_names_and_ids_avoid_collisions(tmp_path):
    path = make_epub(
        tmp_path, chapters(2),
        extra_manifest='<item id="ncx" href="stale.css" media-type="text/css"/>'
                       '<item id="nav" href="nav.xhtml" media-type="text/css"/>'
                       '<item id="toc" href="toc.ncx" media-type="text/css"/>',
        extra_files={"OEBPS/stale.css": "", "OEBPS/nav.xhtml": "x", "OEBPS/toc.ncx": "x"})
    book = EpubBook(path)
    assert needs_toc(book)
    stage_generated_toc_for(book, generate_toc_entries(book))
    book.save()
    root = EpubBook(path)._opf_tree.getroot()
    ids = [i.get("id") for i in root.find("opf:manifest", NS)]
    assert len(ids) == len(set(ids))
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        assert len(names) == len(set(names))
        assert zf.read("OEBPS/nav.xhtml") == b"x"  # the existing file was not overwritten
        assert "OEBPS/nav-2.xhtml" in names and "OEBPS/toc-2.ncx" in names


def test_save_as_copy_then_in_place_save_adds_toc_once(tmp_path):
    path = make_epub(tmp_path, chapters())
    book = EpubBook(path)
    stage_generated_toc_for(book, generate_toc_entries(book))
    book.save(str(tmp_path / "copy.epub"))
    assert book.dirty
    book.save()
    root = EpubBook(path)._opf_tree.getroot()
    ncx_items = [i for i in root.find("opf:manifest", NS) if i.get("media-type") == "application/x-dtbncx+xml"]
    assert len(ncx_items) == 1
    with zipfile.ZipFile(tmp_path / "copy.epub") as zf:
        assert any(n.endswith(".ncx") for n in zf.namelist())


def test_nested_levels_render_nested_lists_and_navpoints(tmp_path):
    docs = [("a.xhtml", page('<h1 id="a">A</h1><h2 id="b">B</h2><h3 id="c">C</h3><h1 id="d">D</h1>'))]
    book = EpubBook(make_epub(tmp_path, docs))
    files = render_toc_files(book, generate_toc_entries(book))
    nav = etree.fromstring(files["nav"][1])
    assert len(nav.xpath("//x:nav/x:ol/x:li", namespaces=XHTML_NS)) == 2
    assert len(nav.xpath("//x:nav/x:ol/x:li/x:ol/x:li/x:ol/x:li", namespaces=XHTML_NS)) == 1
    ncx = etree.fromstring(files["ncx"][1])
    assert ncx.xpath("//n:navPoint/@playOrder", namespaces=NCX_NS) == ["1", "2", "3", "4"]
    assert ncx.xpath("//n:meta[@name='dtb:depth']/@content", namespaces=NCX_NS) == ["3"]


def test_titles_with_markup_characters_are_escaped(tmp_path):
    docs = [("a.xhtml", page('<h1 id="a">Fish &amp; &lt;Chips&gt; "quoted"</h1>'))]
    book = EpubBook(make_epub(tmp_path, docs))
    files = render_toc_files(book, generate_toc_entries(book))
    text = etree.fromstring(files["ncx"][1]).xpath("//n:navLabel/n:text/text()", namespaces=NCX_NS)
    assert text == ['Fish & <Chips> "quoted"']
    etree.fromstring(files["nav"][1])  # well-formed


def test_render_rejects_empty_entry_list(tmp_path):
    book = EpubBook(make_epub(tmp_path, chapters(1)))
    with pytest.raises(ValueError):
        render_toc_files(book, [])


# --- dialog + menu ---------------------------------------------------------------

def test_dialog_lists_only_books_without_toc_and_previews(tmp_path):
    from gui.toc_generate_dialog import PREVIEW_ENTRIES, TocGenerateDialog
    no_toc = EpubBook(make_epub(tmp_path, chapters(15), name="a.epub"))
    has_toc = EpubBook(make_epub(tmp_path, chapters(), name="b.epub", extra_manifest=NAV_ITEM))
    empty = EpubBook(make_epub(tmp_path, [], name="c.epub"))
    dialog = TocGenerateDialog([no_toc, has_toc, empty])
    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 1).text() == "15"
    lines = dialog.preview.toPlainText().splitlines()
    assert len(lines) == PREVIEW_ENTRIES + 1 and lines[-1].endswith("5 more")
    assert dialog.accepted_book_indices() == [0]
    dialog._checkboxes[0].setChecked(False)
    assert dialog.accepted_book_indices() == []


def test_menu_action_applies_and_isolates_failures(tmp_path, monkeypatch):
    from gui import main_window
    from gui.main_window import MainWindow
    good = EpubBook(make_epub(tmp_path, chapters(), name="good.epub"))
    bad = EpubBook(make_epub(tmp_path, chapters(), name="bad.epub"))
    window = MainWindow()

    real = main_window.stage_generated_toc_for

    def flaky(book, entries):
        if book is bad:
            raise RuntimeError("boom")
        real(book, entries)

    monkeypatch.setattr(main_window, "stage_generated_toc_for", flaky)
    monkeypatch.setattr(window, "_selection_or_all_books", lambda: [bad, good])
    monkeypatch.setattr(window, "_refresh_rows_full", lambda books: None)
    monkeypatch.setattr(window, "_refresh_status", lambda: None)
    monkeypatch.setattr(window, "_on_selection_changed", lambda: None)
    monkeypatch.setattr(main_window.TocGenerateDialog, "exec",
                        lambda self: main_window.TocGenerateDialog.DialogCode.Accepted)
    window.open_toc_generate_dialog()
    assert good.dirty and not needs_toc(good)
    assert needs_toc(bad) and not bad.dirty
