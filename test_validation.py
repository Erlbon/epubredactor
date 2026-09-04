"""Tests for validation (EpubBook._validate) and fixing (apply_fixes),
using deliberately broken synthetic EPUBs for each issue type."""
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(__file__))
from core.epub_metadata import EpubBook  # noqa: E402
from core.validation_issue import STATUS_DRM, STATUS_INVALID, STATUS_ISSUES, STATUS_OK  # noqa: E402

TEST_DIR = "/tmp/epub_test_validation"
os.makedirs(TEST_DIR, exist_ok=True)

CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

GOOD_OPF = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="BookId">urn:uuid:good-book</dc:identifier>
    <dc:title>A Perfectly Fine Book</dc:title>
    <dc:language>en</dc:language>
    <dc:creator>Author Name</dc:creator>
  </metadata>
  <manifest>
    <item id="chap1" href="chap1.xhtml" media-type="application/xhtml+xml"/>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
  </manifest>
  <spine>
    <itemref idref="chap1"/>
  </spine>
</package>
"""


def build(path, opf_text, include_mimetype=True, mimetype_content=b"application/epub+zip",
          mimetype_first=True, mimetype_stored=True, extra_files=None,
          include_encryption=False, files_to_include=("OEBPS/chap1.xhtml", "OEBPS/nav.xhtml")):
    if os.path.exists(path):
        os.remove(path)
    with zipfile.ZipFile(path, "w") as zf:
        if include_mimetype and mimetype_first:
            zf.writestr(
                zipfile.ZipInfo("mimetype"),
                mimetype_content,
                zipfile.ZIP_STORED if mimetype_stored else zipfile.ZIP_DEFLATED,
            )
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        if include_encryption:
            zf.writestr("META-INF/encryption.xml", "<encryption/>")
        zf.writestr("OEBPS/content.opf", opf_text)
        for f in files_to_include:
            zf.writestr(f, "<html><body>x</body></html>")
        if include_mimetype and not mimetype_first:
            zf.writestr(
                zipfile.ZipInfo("mimetype"),
                mimetype_content,
                zipfile.ZIP_STORED if mimetype_stored else zipfile.ZIP_DEFLATED,
            )
        if extra_files:
            for name, content in extra_files.items():
                zf.writestr(name, content)


def test_clean_book_is_ok():
    path = os.path.join(TEST_DIR, "clean.epub")
    build(path, GOOD_OPF)
    b = EpubBook(path)
    assert b.load_error is None, b.load_error
    assert b.validation_status == STATUS_OK, (b.validation_status, b.validation_issues)
    assert b.validation_issues == []
    print("PASS: a well-formed book validates as OK with no issues")


def test_save_error_defaults_to_empty():
    """save_error is distinct from load_error/validation_status -- it
    tracks whether the most recent attempt to WRITE this book's file
    failed (permission denied, file locked, etc.), regardless of
    whether the book's own content is valid. Should default to "" (not
    None, and not set) for a freshly loaded book that's never been
    saved."""
    path = os.path.join(TEST_DIR, "save_error_default.epub")
    build(path, GOOD_OPF)
    b = EpubBook(path)
    assert b.save_error == ""
    print("PASS: save_error defaults to an empty string on a freshly loaded book")


def test_mimetype_wrong_content_is_warning_and_gets_corrected_on_save():
    path = os.path.join(TEST_DIR, "bad_mimetype.epub")
    build(path, GOOD_OPF, mimetype_content=b"application/epub+zip\n")  # trailing newline
    b = EpubBook(path)
    codes = {i.code for i in b.validation_issues}
    assert "MIMETYPE_CONTENT" in codes
    assert b.validation_status == STATUS_ISSUES  # warning only, not INVALID

    # Not something apply_fixes touches -- it's corrected automatically
    # by save() regardless.
    out = os.path.join(TEST_DIR, "bad_mimetype_saved.epub")
    b.apply_metadata({"title": "Trigger a save"})
    b.save(out)
    with zipfile.ZipFile(out) as zf:
        assert zf.read("mimetype") == b"application/epub+zip"
        assert zf.namelist()[0] == "mimetype"
        assert zf.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
    print("PASS: wrong mimetype content flagged as a warning, silently corrected on save")


def test_mimetype_missing_entirely():
    path = os.path.join(TEST_DIR, "no_mimetype.epub")
    build(path, GOOD_OPF, include_mimetype=False)
    b = EpubBook(path)
    codes = {i.code for i in b.validation_issues}
    assert "MIMETYPE_MISSING" in codes
    print("PASS: entirely missing mimetype detected")


def test_primary_id_missing_is_error_and_fixable():
    opf = GOOD_OPF.replace('unique-identifier="BookId"', 'unique-identifier="NoSuchId"')
    path = os.path.join(TEST_DIR, "bad_primary_id.epub")
    build(path, opf)
    b = EpubBook(path)
    codes = {i.code: i for i in b.validation_issues}
    assert "PRIMARY_ID_MISSING" in codes
    assert codes["PRIMARY_ID_MISSING"].fixable
    assert b.validation_status == STATUS_INVALID

    fixed = b.apply_fixes({"PRIMARY_ID_MISSING"})
    assert fixed, "should report a fix was made"
    assert b.dirty
    # Re-validated in place -- issue should be gone now.
    assert "PRIMARY_ID_MISSING" not in {i.code for i in b.validation_issues}
    assert b.validation_status == STATUS_OK

    out = os.path.join(TEST_DIR, "bad_primary_id_saved.epub")
    b.save(out)
    b2 = EpubBook(out)
    assert b2.validation_status == STATUS_OK
    print("PASS: broken unique-identifier detected as INVALID, fixable, and fix persists after save")


def test_language_missing_is_fixable():
    opf = GOOD_OPF.replace("<dc:language>en</dc:language>", "")
    path = os.path.join(TEST_DIR, "no_language.epub")
    build(path, opf)
    b = EpubBook(path)
    assert "LANGUAGE_MISSING" in {i.code for i in b.validation_issues}
    assert b.metadata.language == ""

    fixed = b.apply_fixes({"LANGUAGE_MISSING"})
    assert fixed
    assert b.metadata.language == "en"
    assert "LANGUAGE_MISSING" not in {i.code for i in b.validation_issues}
    print("PASS: missing language detected, fixable with a default, metadata updated live")


def test_title_missing_is_not_fixable():
    opf = GOOD_OPF.replace("<dc:title>A Perfectly Fine Book</dc:title>", "")
    path = os.path.join(TEST_DIR, "no_title.epub")
    build(path, opf)
    b = EpubBook(path)
    codes = {i.code: i for i in b.validation_issues}
    assert "TITLE_MISSING" in codes
    assert not codes["TITLE_MISSING"].fixable
    fixed = b.apply_fixes()  # apply ALL fixable issues
    assert "TITLE_MISSING" not in [f for f in fixed]  # nothing claims to fix it
    assert "TITLE_MISSING" in {i.code for i in b.validation_issues}  # still present
    print("PASS: missing title is flagged but correctly NOT offered as auto-fixable")


def test_manifest_file_missing_is_error_not_fixable():
    # chap1.xhtml is listed in the manifest but never actually included.
    path = os.path.join(TEST_DIR, "missing_file.epub")
    build(path, GOOD_OPF, files_to_include=("OEBPS/nav.xhtml",))
    b = EpubBook(path)
    codes = {i.code: i for i in b.validation_issues}
    assert "MANIFEST_FILE_MISSING" in codes
    assert not codes["MANIFEST_FILE_MISSING"].fixable
    assert b.validation_status == STATUS_INVALID
    print("PASS: manifest referencing a missing file is INVALID and correctly not auto-fixable")


def test_dangling_spine_itemref_is_fixable():
    opf = GOOD_OPF.replace(
        "<itemref idref=\"chap1\"/>",
        "<itemref idref=\"chap1\"/><itemref idref=\"ghost\"/>",
    )
    path = os.path.join(TEST_DIR, "dangling_spine.epub")
    build(path, opf)
    b = EpubBook(path)
    codes = {i.code: i for i in b.validation_issues}
    assert "DANGLING_SPINE_ITEMREF" in codes
    assert codes["DANGLING_SPINE_ITEMREF"].fixable

    fixed = b.apply_fixes({"DANGLING_SPINE_ITEMREF"})
    assert fixed
    assert "DANGLING_SPINE_ITEMREF" not in {i.code for i in b.validation_issues}

    out = os.path.join(TEST_DIR, "dangling_spine_saved.epub")
    b.save(out)
    with zipfile.ZipFile(out) as zf:
        opf_out = zf.read("OEBPS/content.opf").decode()
        assert 'idref="ghost"' not in opf_out
        assert 'idref="chap1"' in opf_out  # the valid one must survive
    print("PASS: dangling spine itemref removed, valid ones untouched, persists after save")


def test_duplicate_manifest_id_not_fixable():
    opf = GOOD_OPF.replace(
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
        '<item id="chap1" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
    )
    path = os.path.join(TEST_DIR, "dup_id.epub")
    build(path, opf)
    b = EpubBook(path)
    codes = {i.code: i for i in b.validation_issues}
    assert "DUPLICATE_MANIFEST_ID" in codes
    assert not codes["DUPLICATE_MANIFEST_ID"].fixable
    print("PASS: duplicate manifest ids detected, correctly not auto-fixed (too risky)")


def test_no_toc_detected():
    opf = GOOD_OPF.replace(
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>', ""
    )
    path = os.path.join(TEST_DIR, "no_toc.epub")
    build(path, opf)
    b = EpubBook(path)
    assert "NO_TOC" in {i.code for i in b.validation_issues}
    print("PASS: missing table of contents detected")


def test_drm_detected():
    path = os.path.join(TEST_DIR, "drm.epub")
    build(path, GOOD_OPF, include_encryption=True)
    b = EpubBook(path)
    codes = {i.code: i for i in b.validation_issues}
    assert "DRM_DETECTED" in codes
    assert not codes["DRM_DETECTED"].fixable
    assert b.validation_status == STATUS_DRM
    print("PASS: DRM-protected book gets its own DRM status, not lumped in with INVALID")


def test_drm_plus_genuine_error_is_still_invalid():
    """A book that's both DRM-protected AND has a real structural
    problem (not just "locked") should still show INVALID -- that's the
    more fundamental issue."""
    path = os.path.join(TEST_DIR, "drm_and_broken.epub")
    build(path, GOOD_OPF, include_encryption=True, files_to_include=("OEBPS/nav.xhtml",))
    b = EpubBook(path)
    codes = {i.code for i in b.validation_issues}
    assert "DRM_DETECTED" in codes
    assert "MANIFEST_FILE_MISSING" in codes
    assert b.validation_status == STATUS_INVALID
    print("PASS: DRM alongside a genuine structural error still shows INVALID (worse problem wins)")


def test_load_failure_reported_as_invalid():
    path = os.path.join(TEST_DIR, "not_a_zip.epub")
    with open(path, "w") as f:
        f.write("this is not a zip file at all")
    b = EpubBook(path)
    assert b.load_error is not None
    assert b.validation_status == STATUS_INVALID
    assert b.validation_issues and b.validation_issues[0].code == "LOAD_FAILED"
    print("PASS: a totally unreadable file reports INVALID with a LOAD_FAILED issue")


def test_apply_fixes_noop_when_nothing_fixable():
    path = os.path.join(TEST_DIR, "clean2.epub")
    build(path, GOOD_OPF)
    b = EpubBook(path)
    fixed = b.apply_fixes()
    assert fixed == []
    assert not b.dirty
    print("PASS: apply_fixes on a clean book is a harmless no-op")


def test_load_missing_file_sets_load_error_not_crash():
    """Regression test: EpubBook(path) for a file that's been deleted
    (or otherwise inaccessible) must set load_error, not raise an
    unhandled exception -- zipfile.ZipFile() on a nonexistent path
    raises FileNotFoundError (an OSError subclass), which _load()'s
    except clause didn't originally include. This matters most for
    Refresh List, which re-instantiates EpubBook for every currently
    loaded path and would previously crash outright if any one of them
    had disappeared from disk since loading."""
    path = os.path.join(TEST_DIR, "will_be_deleted.epub")
    build(path, GOOD_OPF)
    os.remove(path)
    b = EpubBook(path)  # must not raise
    assert b.load_error, "load_error should be set for a missing file"
    assert b.validation_status == STATUS_INVALID
    print("PASS: loading a path whose file no longer exists sets load_error instead of crashing")


def test_revalidate_missing_file_is_safe_noop():
    path = os.path.join(TEST_DIR, "revalidate_missing.epub")
    build(path, GOOD_OPF)
    b = EpubBook(path)
    os.remove(path)
    b.revalidate()  # must not raise
    print("PASS: revalidate() on a since-deleted file is a safe no-op, not a crash")


def test_revalidate_confirms_mimetype_promise_after_save():
    """MIMETYPE_* issues say 'will be corrected automatically on next
    save' -- revalidate() after a real save() should prove that's true,
    not just trusted blindly."""
    path = os.path.join(TEST_DIR, "revalidate_mimetype.epub")
    build(path, GOOD_OPF, mimetype_content=b"application/epub+zip\n")
    b = EpubBook(path)
    assert "MIMETYPE_CONTENT" in {i.code for i in b.validation_issues}

    b.apply_metadata({"title": "Trigger a save"})
    b.save()  # in-place overwrite -- mimetype gets corrected as part of this
    b.revalidate()

    assert "MIMETYPE_CONTENT" not in {i.code for i in b.validation_issues}
    assert "MIMETYPE_POSITION" not in {i.code for i in b.validation_issues}
    print("PASS: revalidate() after save() confirms the mimetype was actually corrected on disk")


def test_revalidate_confirms_unfixed_issues_remain():
    """revalidate() must not falsely clear an issue that's genuinely
    still there (e.g. a missing manifest file, which nothing touches)."""
    path = os.path.join(TEST_DIR, "revalidate_still_broken.epub")
    build(path, GOOD_OPF, files_to_include=("OEBPS/nav.xhtml",))  # chap1.xhtml missing
    b = EpubBook(path)
    assert "MANIFEST_FILE_MISSING" in {i.code for i in b.validation_issues}
    b.revalidate()
    assert "MANIFEST_FILE_MISSING" in {i.code for i in b.validation_issues}
    print("PASS: revalidate() correctly leaves a genuinely-unfixed issue in place")


def test_find_missing_manifest_files_reports_id_and_href():
    path = os.path.join(TEST_DIR, "manifest_missing_find.epub")
    build(path, GOOD_OPF, files_to_include=("OEBPS/nav.xhtml",))  # chap1.xhtml omitted
    b = EpubBook(path)
    missing = b.find_missing_manifest_files()
    assert missing == [("chap1", "chap1.xhtml")], missing
    print("PASS: find_missing_manifest_files() reports the (item_id, href) pair correctly")


def test_find_missing_manifest_files_empty_when_nothing_missing():
    path = os.path.join(TEST_DIR, "manifest_missing_none.epub")
    build(path, GOOD_OPF)  # both files present
    b = EpubBook(path)
    assert b.find_missing_manifest_files() == []
    print("PASS: find_missing_manifest_files() returns an empty list when nothing's missing")


def test_rebuild_manifest_removes_item_and_spine_ref():
    path = os.path.join(TEST_DIR, "manifest_rebuild_spine.epub")
    build(path, GOOD_OPF, files_to_include=("OEBPS/nav.xhtml",))  # chap1.xhtml missing
    b = EpubBook(path)
    assert not b.dirty

    removed = b.rebuild_manifest()
    assert removed == ["chap1.xhtml"], removed
    assert b.dirty
    assert b.find_missing_manifest_files() == []  # nothing left to report after rebuild

    # Confirm the manifest item AND its spine reference are both actually
    # gone from the in-memory tree, not just that revalidate() stopped
    # complaining about it.
    from core.epub_metadata import NS
    root = b._opf_tree.getroot()
    manifest_ids = {item.get("id") for item in root.find("opf:manifest", namespaces=NS).findall("opf:item", namespaces=NS)}
    assert "chap1" not in manifest_ids, manifest_ids
    spine_refs = {ir.get("idref") for ir in root.find("opf:spine", namespaces=NS).findall("opf:itemref", namespaces=NS)}
    assert "chap1" not in spine_refs, spine_refs
    print("PASS: rebuild_manifest() removes the manifest item and its spine reference")


def test_rebuild_manifest_removes_orphaned_non_spine_item():
    """A missing file that's referenced in the manifest but NOT in the
    spine (e.g. an orphaned image) -- only the manifest entry should be
    removed, there's no spine reference to clean up."""
    path = os.path.join(TEST_DIR, "manifest_rebuild_orphan.epub")
    build(path, GOOD_OPF, files_to_include=("OEBPS/chap1.xhtml",))  # nav.xhtml missing
    b = EpubBook(path)
    removed = b.rebuild_manifest()
    assert removed == ["nav.xhtml"], removed
    assert b.find_missing_manifest_files() == []
    print("PASS: rebuild_manifest() removes an orphaned (non-spine) manifest entry too")


def test_rebuild_manifest_noop_when_nothing_missing():
    path = os.path.join(TEST_DIR, "manifest_rebuild_clean.epub")
    build(path, GOOD_OPF)
    b = EpubBook(path)
    removed = b.rebuild_manifest()
    assert removed == []
    assert not b.dirty
    print("PASS: rebuild_manifest() on a clean book is a harmless no-op")


def test_rebuild_manifest_with_explicit_item_ids():
    """Passing explicit item_ids restricts the rebuild to just those,
    even if other missing entries exist -- used when the user unticks
    some rows in the review dialog."""
    opf = GOOD_OPF.replace(
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>\n'
        '    <item id="img1" href="cover.jpg" media-type="image/jpeg"/>',
    )
    path = os.path.join(TEST_DIR, "manifest_rebuild_partial.epub")
    build(path, opf, files_to_include=("OEBPS/chap1.xhtml",))  # nav.xhtml AND cover.jpg both missing
    b = EpubBook(path)
    assert len(b.find_missing_manifest_files()) == 2

    removed = b.rebuild_manifest(item_ids={"img1"})  # only rebuild this one
    assert removed == ["cover.jpg"], removed
    remaining = b.find_missing_manifest_files()
    assert remaining == [("nav", "nav.xhtml")], remaining
    print("PASS: rebuild_manifest() with explicit item_ids only touches those entries")


if __name__ == "__main__":
    test_clean_book_is_ok()
    test_save_error_defaults_to_empty()
    test_mimetype_wrong_content_is_warning_and_gets_corrected_on_save()
    test_mimetype_missing_entirely()
    test_primary_id_missing_is_error_and_fixable()
    test_language_missing_is_fixable()
    test_title_missing_is_not_fixable()
    test_manifest_file_missing_is_error_not_fixable()
    test_dangling_spine_itemref_is_fixable()
    test_duplicate_manifest_id_not_fixable()
    test_no_toc_detected()
    test_drm_detected()
    test_drm_plus_genuine_error_is_still_invalid()
    test_load_failure_reported_as_invalid()
    test_apply_fixes_noop_when_nothing_fixable()
    test_load_missing_file_sets_load_error_not_crash()
    test_revalidate_missing_file_is_safe_noop()
    test_revalidate_confirms_mimetype_promise_after_save()
    test_revalidate_confirms_unfixed_issues_remain()
    test_find_missing_manifest_files_reports_id_and_href()
    test_find_missing_manifest_files_empty_when_nothing_missing()
    test_rebuild_manifest_removes_item_and_spine_ref()
    test_rebuild_manifest_removes_orphaned_non_spine_item()
    test_rebuild_manifest_noop_when_nothing_missing()
    test_rebuild_manifest_with_explicit_item_ids()
    print("\nALL VALIDATION TESTS PASSED")
