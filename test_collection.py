"""Tests for the Collection field (core/epub_metadata.py), separate from
but structurally similar to Series -- both use EPUB3's belongs-to-collection
mechanism, distinguished only by collection-type."""
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(__file__))
from core.epub_metadata import EpubBook  # noqa: E402

TEST_DIR = "/tmp/epub_test_collection"
os.makedirs(TEST_DIR, exist_ok=True)

CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

CHAP1 = "<html><body><p>x</p></body></html>"


def build(path, opf_text):
    if os.path.exists(path):
        os.remove(path)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", opf_text)
        zf.writestr("OEBPS/chap1.xhtml", CHAP1)


BASE_OPF = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="BookId">urn:uuid:coll-test</dc:identifier>
    <dc:title>Test Book</dc:title>
  </metadata>
  <manifest>
    <item id="chap1" href="chap1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="chap1"/></spine>
</package>
"""


def test_set_and_save_roundtrip():
    path = os.path.join(TEST_DIR, "basic.epub")
    build(path, BASE_OPF)
    b = EpubBook(path)
    assert b.metadata.collection == ""

    b.apply_metadata({"collection": "The Complete Anthology"})
    assert b.dirty
    out = os.path.join(TEST_DIR, "basic_saved.epub")
    b.save(out)

    b2 = EpubBook(out)
    assert b2.metadata.collection == "The Complete Anthology", b2.metadata.collection
    with zipfile.ZipFile(out) as zf:
        opf = zf.read("OEBPS/content.opf").decode()
        assert 'property="belongs-to-collection"' in opf
        assert '>set<' in opf  # collection-type value
    print("PASS: setting Collection writes belongs-to-collection with collection-type=set")


def test_collection_and_series_coexist():
    path = os.path.join(TEST_DIR, "both.epub")
    build(path, BASE_OPF)
    b = EpubBook(path)
    b.apply_metadata({
        "series": "Main Series", "series_index": "3", "collection": "Bonus Box Set",
    })
    out = os.path.join(TEST_DIR, "both_saved.epub")
    b.save(out)

    b2 = EpubBook(out)
    assert b2.metadata.series == "Main Series"
    assert b2.metadata.series_index == "3"
    assert b2.metadata.collection == "Bonus Box Set"
    print("PASS: Series and Collection coexist without clobbering each other")


def test_clearing_collection_removes_it_leaves_series():
    path = os.path.join(TEST_DIR, "clear.epub")
    build(path, BASE_OPF)
    b = EpubBook(path)
    b.apply_metadata({"series": "Keep Me", "series_index": "1", "collection": "Remove Me"})
    out1 = os.path.join(TEST_DIR, "clear_step1.epub")
    b.save(out1)

    b2 = EpubBook(out1)
    b2.apply_metadata({"collection": ""})
    out2 = os.path.join(TEST_DIR, "clear_step2.epub")
    b2.save(out2)

    b3 = EpubBook(out2)
    assert b3.metadata.collection == ""
    assert b3.metadata.series == "Keep Me"
    assert b3.metadata.series_index == "1"
    with zipfile.ZipFile(out2) as zf:
        opf = zf.read("OEBPS/content.opf").decode()
        assert opf.count('property="belongs-to-collection"') == 1  # only series' left
    print("PASS: clearing Collection removes only its own belongs-to-collection entry")


def test_existing_set_type_collection_not_misread_as_series():
    """Regression guard: before Collection existed, the series-fallback
    reader grabbed the FIRST belongs-to-collection regardless of type --
    a book with only a "set"-type collection and no calibre:series would
    have had that collection incorrectly read as its series."""
    opf = BASE_OPF.replace(
        "</metadata>",
        '<opf:meta id="c1" property="belongs-to-collection">Some Box Set</opf:meta>'
        '<opf:meta refines="#c1" property="collection-type">set</opf:meta>'
        "</metadata>",
    )
    path = os.path.join(TEST_DIR, "set_only.epub")
    build(path, opf)
    b = EpubBook(path)
    assert b.metadata.series == "", b.metadata.series
    assert b.metadata.collection == "Some Box Set", b.metadata.collection
    print("PASS: a set-type-only collection is read as Collection, not mistaken for Series")


def test_existing_series_without_explicit_type_defaults_to_series():
    """Per the EPUB3 spec, collection-type defaults to 'series' when the
    refining meta is absent entirely."""
    opf = BASE_OPF.replace(
        "</metadata>",
        '<opf:meta id="c1" property="belongs-to-collection">Untyped Series</opf:meta>'
        "</metadata>",
    )
    path = os.path.join(TEST_DIR, "untyped.epub")
    build(path, opf)
    b = EpubBook(path)
    assert b.metadata.series == "Untyped Series", b.metadata.series
    assert b.metadata.collection == ""
    print("PASS: a belongs-to-collection with no explicit type defaults to series (per spec)")


if __name__ == "__main__":
    test_set_and_save_roundtrip()
    test_collection_and_series_coexist()
    test_clearing_collection_removes_it_leaves_series()
    test_existing_set_type_collection_not_misread_as_series()
    test_existing_series_without_explicit_type_defaults_to_series()
    print("\nALL COLLECTION TESTS PASSED")
