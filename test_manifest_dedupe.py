"""Tests for duplicate manifest id detection/repair (see
EpubBook.find_duplicate_manifest_ids / dedupe_manifest_ids in
core/epub_metadata.py).

Real bug reported by a user: a badly-converted EPUB2->EPUB3 file had
TWO <item> entries with id="ncx" in its manifest -- one the genuine
toc.ncx, one a stray leftover from whatever tool produced the file --
which this app's own validation correctly flags as DUPLICATE_MANIFEST_ID,
but (until now) had no fix for."""

import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(__file__))
from core.epub_metadata import EpubBook  # noqa: E402
from core.validation_issue import STATUS_OK  # noqa: E402

TEST_DIR = "/tmp/epub_test_manifest_dedupe"
os.makedirs(TEST_DIR, exist_ok=True)

CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

# Realistic bad-conversion pattern: the genuine toc.ncx has id="ncx", but
# a stray xhtml item was ALSO given id="ncx" by whatever tool produced
# this file.
DUP_NCX_OPF = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="BookId">urn:uuid:dup-ncx-book</dc:identifier>
    <dc:title>A Book With Duplicate Manifest IDs</dc:title>
    <dc:language>en</dc:language>
    <dc:creator>Author Name</dc:creator>
  </metadata>
  <manifest>
    <item id="chap1" href="chap1.xhtml" media-type="application/xhtml+xml"/>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="ncx" href="stray.xhtml" media-type="application/xhtml+xml"/>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
  </manifest>
  <spine toc="ncx">
    <itemref idref="chap1"/>
  </spine>
</package>
"""

# A duplicate id with no semantic signal to break the tie -- must fall
# back to keeping whichever occurs first in document order.
DUP_PLAIN_OPF = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="BookId">urn:uuid:dup-plain-book</dc:identifier>
    <dc:title>Plain Duplicate</dc:title>
    <dc:language>en</dc:language>
  </metadata>
  <manifest>
    <item id="img1" href="cover.jpg" media-type="image/jpeg"/>
    <item id="img1" href="other.jpg" media-type="image/jpeg"/>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
  </manifest>
  <spine>
  </spine>
</package>
"""


def build(path, opf_text, files_to_include=("OEBPS/chap1.xhtml", "OEBPS/nav.xhtml", "OEBPS/toc.ncx",
                                             "OEBPS/stray.xhtml", "OEBPS/cover.jpg", "OEBPS/other.jpg")):
    if os.path.exists(path):
        os.remove(path)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), b"application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", opf_text)
        for f in files_to_include:
            zf.writestr(f, "x")


def test_find_duplicate_manifest_ids_reports_ncx_pair():
    path = os.path.join(TEST_DIR, "dup_ncx.epub")
    build(path, DUP_NCX_OPF)
    b = EpubBook(path)
    dups = b.find_duplicate_manifest_ids()
    assert set(dups) == {"ncx"}
    assert sorted(dups["ncx"]) == ["stray.xhtml", "toc.ncx"]
    print("PASS: find_duplicate_manifest_ids() reports the id and both hrefs")


def test_dedupe_prefers_the_real_ncx_item_to_keep_the_id():
    path = os.path.join(TEST_DIR, "dup_ncx_2.epub")
    build(path, DUP_NCX_OPF)
    b = EpubBook(path)

    renamed = b.dedupe_manifest_ids()
    assert len(renamed) == 1
    old_id, new_id = renamed[0]
    assert old_id == "ncx"
    assert new_id == "ncx-2"

    root = b._opf_tree.getroot()
    ns = {"opf": "http://www.idpf.org/2007/opf"}
    items = root.find("opf:manifest", namespaces=ns).findall("opf:item", namespaces=ns)
    by_href = {i.get("href"): i.get("id") for i in items}
    assert by_href["toc.ncx"] == "ncx"       # the real NCX kept the id
    assert by_href["stray.xhtml"] == "ncx-2"  # the stray item got renamed
    print("PASS: dedupe_manifest_ids() keeps id=\"ncx\" on the genuine NCX item, "
          "renames the stray xhtml item instead")


def test_dedupe_falls_back_to_document_order_with_no_signal():
    path = os.path.join(TEST_DIR, "dup_plain.epub")
    build(path, DUP_PLAIN_OPF)
    b = EpubBook(path)

    renamed = b.dedupe_manifest_ids()
    assert renamed == [("img1", "img1-2")]

    root = b._opf_tree.getroot()
    ns = {"opf": "http://www.idpf.org/2007/opf"}
    items = root.find("opf:manifest", namespaces=ns).findall("opf:item", namespaces=ns)
    by_href = {i.get("href"): i.get("id") for i in items}
    assert by_href["cover.jpg"] == "img1"     # first occurrence keeps the id
    assert by_href["other.jpg"] == "img1-2"   # second occurrence renamed
    print("PASS: dedupe_manifest_ids() keeps the first occurrence's id when there's no "
          "media-type/properties signal to prefer one over the other")


def test_dedupe_marks_dirty_and_revalidates_clean():
    path = os.path.join(TEST_DIR, "dup_ncx_3.epub")
    build(path, DUP_NCX_OPF)
    b = EpubBook(path)
    assert "DUPLICATE_MANIFEST_ID" in {i.code for i in b.validation_issues}

    b.dedupe_manifest_ids()

    assert b.dirty
    assert "DUPLICATE_MANIFEST_ID" not in {i.code for i in b.validation_issues}
    assert b.validation_status == STATUS_OK
    print("PASS: dedupe_manifest_ids() marks the book dirty and clears the validation issue")


def test_dedupe_noop_when_nothing_duplicated():
    path = os.path.join(TEST_DIR, "clean.epub")
    build(path, DUP_NCX_OPF.replace(
        '<item id="ncx" href="stray.xhtml" media-type="application/xhtml+xml"/>', ""
    ))
    b = EpubBook(path)
    assert b.find_duplicate_manifest_ids() == {}
    assert b.dedupe_manifest_ids() == []
    assert not b.dirty
    print("PASS: dedupe_manifest_ids() is a harmless no-op on a book with no duplicate ids")


def test_dedupe_with_explicit_ids_only_touches_those():
    path = os.path.join(TEST_DIR, "dup_ncx_4.epub")
    build(path, DUP_NCX_OPF)
    b = EpubBook(path)

    renamed = b.dedupe_manifest_ids(ids=set())  # explicitly nothing
    assert renamed == []
    assert not b.dirty
    print("PASS: dedupe_manifest_ids() with an explicit empty id set touches nothing")


def test_dedupe_persists_after_save_and_spine_toc_still_resolves():
    path = os.path.join(TEST_DIR, "dup_ncx_save.epub")
    build(path, DUP_NCX_OPF)
    b = EpubBook(path)
    b.dedupe_manifest_ids()
    out = os.path.join(TEST_DIR, "dup_ncx_save_out.epub")
    b.save(out)

    b2 = EpubBook(out)
    assert b2.find_duplicate_manifest_ids() == {}
    assert "DUPLICATE_MANIFEST_ID" not in {i.code for i in b2.validation_issues}
    root = b2._opf_tree.getroot()
    ns = {"opf": "http://www.idpf.org/2007/opf"}
    spine = root.find("opf:spine", namespaces=ns)
    assert spine.get("toc") == "ncx"  # unchanged -- still resolves to the real NCX item
    items = root.find("opf:manifest", namespaces=ns).findall("opf:item", namespaces=ns)
    by_href = {i.get("href"): i.get("id") for i in items}
    assert by_href["toc.ncx"] == "ncx"
    print("PASS: the fix persists after save(), and <spine toc=\"ncx\"> still correctly "
          "resolves to the real toc.ncx item")


if __name__ == "__main__":
    test_find_duplicate_manifest_ids_reports_ncx_pair()
    test_dedupe_prefers_the_real_ncx_item_to_keep_the_id()
    test_dedupe_falls_back_to_document_order_with_no_signal()
    test_dedupe_marks_dirty_and_revalidates_clean()
    test_dedupe_noop_when_nothing_duplicated()
    test_dedupe_with_explicit_ids_only_touches_those()
    test_dedupe_persists_after_save_and_spine_toc_still_resolves()
    print("\nALL MANIFEST DEDUPE TESTS PASSED")
