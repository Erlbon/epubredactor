"""Tests for Author Sort / opf:file-as handling in core/epub_metadata.py."""
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(__file__))
from core.epub_metadata import EpubBook  # noqa: E402

TEST_DIR = "/tmp/epub_test_author_sort"
os.makedirs(TEST_DIR, exist_ok=True)

CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

OPF_SINGLE_AUTHOR = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="BookId">urn:uuid:aaaa</dc:identifier>
    <dc:title>A Book</dc:title>
    <dc:creator opf:file-as="Tolkien, J.R.R.">J.R.R. Tolkien</dc:creator>
  </metadata>
  <manifest>
    <item id="chap1" href="chap1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="chap1"/></spine>
</package>
"""

OPF_NO_SORT = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="BookId">urn:uuid:bbbb</dc:identifier>
    <dc:title>Plain Book</dc:title>
    <dc:creator>Jane Doe</dc:creator>
  </metadata>
  <manifest>
    <item id="chap1" href="chap1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="chap1"/></spine>
</package>
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


def test_read_existing_file_as():
    path = os.path.join(TEST_DIR, "single.epub")
    build(path, OPF_SINGLE_AUTHOR)
    b = EpubBook(path)
    assert b.load_error is None, b.load_error
    assert b.metadata.authors == ["J.R.R. Tolkien"]
    assert b.metadata.author_sort == ["Tolkien, J.R.R."]
    assert b.metadata.author_sort_str == "Tolkien, J.R.R."
    print("PASS: reads existing opf:file-as into author_sort")


def test_no_file_as_present():
    path = os.path.join(TEST_DIR, "plain.epub")
    build(path, OPF_NO_SORT)
    b = EpubBook(path)
    assert b.metadata.authors == ["Jane Doe"]
    assert b.metadata.author_sort == []
    assert b.metadata.author_sort_str == ""
    print("PASS: book with no file-as attribute reads an empty author_sort")


def test_set_author_sort_roundtrip():
    path = os.path.join(TEST_DIR, "set_sort.epub")
    build(path, OPF_NO_SORT)
    b = EpubBook(path)
    b.apply_metadata({"author_sort_str": "Doe, Jane"})
    assert b.dirty
    out = os.path.join(TEST_DIR, "set_sort_saved.epub")
    b.save(out)

    b2 = EpubBook(out)
    assert b2.metadata.author_sort_str == "Doe, Jane"
    with zipfile.ZipFile(out) as zf:
        opf = zf.read("OEBPS/content.opf").decode()
        assert 'file-as="Doe, Jane"' in opf
    print("PASS: setting author_sort writes opf:file-as and round-trips")


def test_multi_author_alignment():
    opf = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="BookId">urn:uuid:cccc</dc:identifier>
    <dc:title>Collab Book</dc:title>
    <dc:creator opf:file-as="Pratchett, Terry">Terry Pratchett</dc:creator>
    <dc:creator opf:file-as="Gaiman, Neil">Neil Gaiman</dc:creator>
  </metadata>
  <manifest>
    <item id="chap1" href="chap1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="chap1"/></spine>
</package>
"""
    path = os.path.join(TEST_DIR, "multi.epub")
    build(path, opf)
    b = EpubBook(path)
    assert b.metadata.authors == ["Terry Pratchett", "Neil Gaiman"]
    assert b.metadata.author_sort == ["Pratchett, Terry", "Gaiman, Neil"]
    assert b.metadata.author_sort_str == "Pratchett, Terry; Gaiman, Neil"
    print("PASS: multi-author file-as stays positionally aligned")


def test_clearing_author_sort_removes_attribute():
    path = os.path.join(TEST_DIR, "clear_sort.epub")
    build(path, OPF_SINGLE_AUTHOR)
    b = EpubBook(path)
    b.apply_metadata({"author_sort_str": ""})
    out = os.path.join(TEST_DIR, "clear_sort_saved.epub")
    b.save(out)
    b2 = EpubBook(out)
    assert b2.metadata.author_sort == []
    with zipfile.ZipFile(out) as zf:
        opf = zf.read("OEBPS/content.opf").decode()
        assert "file-as" not in opf
    print("PASS: clearing author_sort removes the file-as attribute entirely")


def test_primary_author_only_sort_set():
    """The common case: a 3-author book where only the first author gets
    a sort-name set. Must not corrupt or misalign the other two."""
    opf = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="BookId">urn:uuid:dddd</dc:identifier>
    <dc:title>Trio Book</dc:title>
    <dc:creator>Author One</dc:creator>
    <dc:creator>Author Two</dc:creator>
    <dc:creator>Author Three</dc:creator>
  </metadata>
  <manifest>
    <item id="chap1" href="chap1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="chap1"/></spine>
</package>
"""
    path = os.path.join(TEST_DIR, "trio.epub")
    build(path, opf)
    b = EpubBook(path)
    b.apply_metadata({"author_sort_str": "One, Author"})
    out = os.path.join(TEST_DIR, "trio_saved.epub")
    b.save(out)
    b2 = EpubBook(out)
    assert b2.metadata.authors == ["Author One", "Author Two", "Author Three"]
    assert b2.metadata.author_sort_str == "One, Author"
    print("PASS: setting sort-name for only the first of several authors works cleanly")


if __name__ == "__main__":
    test_read_existing_file_as()
    test_no_file_as_present()
    test_set_author_sort_roundtrip()
    test_multi_author_alignment()
    test_clearing_author_sort_removes_attribute()
    test_primary_author_only_sort_set()
    print("\nALL AUTHOR SORT TESTS PASSED")
