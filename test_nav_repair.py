"""Tests for Repair Navigation (core/epub_metadata.py): broken <guide>
references and orphaned (on-disk but unreferenced) archive files."""
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(__file__))
from core.epub_metadata import EpubBook  # noqa: E402

TEST_DIR = "/tmp/epub_test_nav_repair"
os.makedirs(TEST_DIR, exist_ok=True)

CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

CHAP1 = "<html><body><p>Chapter 1</p></body></html>"


def build(path, opf_text, extra_files=None):
    if os.path.exists(path):
        os.remove(path)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", opf_text)
        zf.writestr("OEBPS/chap1.xhtml", CHAP1)
        for name, content in (extra_files or {}).items():
            zf.writestr(name, content)


OPF_WITH_BROKEN_GUIDE = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="BookId">urn:uuid:aaaa</dc:identifier>
    <dc:title>Guide Book</dc:title>
  </metadata>
  <manifest>
    <item id="chap1" href="chap1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="chap1"/></spine>
  <guide>
    <reference type="toc" title="Table of Contents" href="toc.xhtml"/>
    <reference type="cover" title="Cover" href="chap1.xhtml"/>
  </guide>
</package>
"""

OPF_WITH_ORPHAN = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="BookId">urn:uuid:bbbb</dc:identifier>
    <dc:title>Orphan Book</dc:title>
  </metadata>
  <manifest>
    <item id="chap1" href="chap1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="chap1"/></spine>
</package>
"""

OPF_CLEAN = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="BookId">urn:uuid:cccc</dc:identifier>
    <dc:title>Clean Book</dc:title>
  </metadata>
  <manifest>
    <item id="chap1" href="chap1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="chap1"/></spine>
</package>
"""


def test_find_broken_guide_references():
    path = os.path.join(TEST_DIR, "guide.epub")
    build(path, OPF_WITH_BROKEN_GUIDE)
    b = EpubBook(path)
    assert b.load_error is None, b.load_error
    broken = b.find_broken_guide_references()
    assert len(broken) == 1, broken
    assert broken[0][2] == "toc.xhtml", broken
    print("PASS: finds a broken guide reference, leaves the valid one alone")


def test_repair_guide_references_removes_broken_and_keeps_valid():
    path = os.path.join(TEST_DIR, "guide_fix.epub")
    build(path, OPF_WITH_BROKEN_GUIDE)
    b = EpubBook(path)
    removed = b.repair_guide_references()
    assert removed == ["toc.xhtml"], removed
    assert b.dirty
    out = os.path.join(TEST_DIR, "guide_fix_saved.epub")
    b.save(out)
    with zipfile.ZipFile(out) as zf:
        opf = zf.read("OEBPS/content.opf").decode()
        assert "toc.xhtml" not in opf, opf
        assert 'type="cover"' in opf, opf  # the valid reference survives
    print("PASS: repair_guide_references removes only the broken reference, saves correctly")


def test_no_guide_element_is_a_clean_noop():
    path = os.path.join(TEST_DIR, "no_guide.epub")
    build(path, OPF_CLEAN)
    b = EpubBook(path)
    assert b.find_broken_guide_references() == []
    assert b.repair_guide_references() == []
    assert not b.dirty
    print("PASS: a book with no <guide> element at all is a clean no-op")


def test_find_orphaned_files():
    path = os.path.join(TEST_DIR, "orphan.epub")
    build(path, OPF_WITH_ORPHAN, extra_files={"OEBPS/unused.css": "body{}"})
    b = EpubBook(path)
    orphans = b.find_orphaned_files()
    assert orphans == ["OEBPS/unused.css"], orphans
    print("PASS: finds a file present in the archive but referenced by no manifest item")


def test_orphaned_files_excludes_structural_entries():
    path = os.path.join(TEST_DIR, "clean.epub")
    build(path, OPF_CLEAN)
    b = EpubBook(path)
    # mimetype, META-INF/container.xml, and the OPF itself are all
    # legitimately unreferenced by any manifest item -- must never be
    # flagged as "orphaned".
    assert b.find_orphaned_files() == [], b.find_orphaned_files()
    print("PASS: mimetype/META-INF/the OPF itself are never flagged as orphaned")


def test_remove_orphaned_files_stages_and_saves():
    path = os.path.join(TEST_DIR, "orphan_remove.epub")
    build(path, OPF_WITH_ORPHAN, extra_files={"OEBPS/unused.css": "body{}"})
    b = EpubBook(path)
    removed = b.remove_orphaned_files()
    assert removed == ["OEBPS/unused.css"], removed
    assert b.dirty
    out = os.path.join(TEST_DIR, "orphan_remove_saved.epub")
    b.save(out)
    with zipfile.ZipFile(out) as zf:
        names = set(zf.namelist())
        assert "OEBPS/unused.css" not in names, names
        assert "OEBPS/chap1.xhtml" in names, names  # referenced file untouched
    print("PASS: remove_orphaned_files stages the file and save() actually drops it")


def test_orphan_removal_survives_save_as_copy_but_clears_on_real_save():
    path = os.path.join(TEST_DIR, "orphan_copy.epub")
    build(path, OPF_WITH_ORPHAN, extra_files={"OEBPS/unused.css": "body{}"})
    b = EpubBook(path)
    b.remove_orphaned_files()

    copy_path = os.path.join(TEST_DIR, "orphan_copy_COPY.epub")
    b.save(copy_path)  # Save As Copy -- different path
    with zipfile.ZipFile(copy_path) as zf:
        assert "OEBPS/unused.css" not in zf.namelist()
    # staged removal must still be pending against the ORIGINAL book,
    # since only a real save (to its own path) resolves it
    assert b._orphan_files_to_remove == {"OEBPS/unused.css"}
    assert b.path == path  # unchanged -- still points at the original

    b.save()  # real save -- no output_path, overwrites the book's own file in place
    assert b._orphan_files_to_remove == set()
    print("PASS: staged orphan removal survives a Save As Copy, clears only on a real save")


if __name__ == "__main__":
    test_find_broken_guide_references()
    test_repair_guide_references_removes_broken_and_keeps_valid()
    test_no_guide_element_is_a_clean_noop()
    test_find_orphaned_files()
    test_orphaned_files_excludes_structural_entries()
    test_remove_orphaned_files_stages_and_saves()
    test_orphan_removal_survives_save_as_copy_but_clears_on_real_save()
    print("\nALL NAV REPAIR TESTS PASSED")
