"""Tests for publish date handling, DDC classification, and cover image
add/replace/delete -- all added to core/epub_metadata.py."""
import base64
import os
import sys
import zipfile
import zlib

sys.path.insert(0, os.path.dirname(__file__))
from core.epub_metadata import (  # noqa: E402
    EpubBook,
    format_date_parts,
    parse_date_parts,
)

TEST_DIR = "/tmp/epub_test_dates_cover"
os.makedirs(TEST_DIR, exist_ok=True)

# A real, minimal, valid 1x1 transparent PNG.
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
# A second, distinguishable tiny valid PNG (2x1, still tiny/simple) --
# doesn't need to be pixel-different in a verifiable way for these tests,
# just a different byte sequence so we can tell "old" from "new".
TINY_PNG_2 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAABCAQAAAAmkwkpAAAAC0lEQVR42mNk"
    "+M/AAAMBAQAY3oj7AAAAAElFTkSuQmCC"
)

CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

CHAP1 = "<html><body><p>Hello world</p></body></html>"


def opf_epub3_with_cover(date_value="", ddc_value=""):
    date_el = f"<dc:date>{date_value}</dc:date>" if date_value else ""
    ddc_el = (
        f'<dc:subject opf:authority="DDC">{ddc_value}</dc:subject>' if ddc_value else ""
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="BookId">urn:uuid:abcd-1234</dc:identifier>
    <dc:title>Dated Book</dc:title>
    <dc:creator>Some Author</dc:creator>
    <dc:subject>Fiction</dc:subject>
    {ddc_el}
    {date_el}
  </metadata>
  <manifest>
    <item id="chap1" href="chap1.xhtml" media-type="application/xhtml+xml"/>
    <item id="cover-img" href="cover.png" media-type="image/png" properties="cover-image"/>
  </manifest>
  <spine>
    <itemref idref="chap1"/>
  </spine>
</package>
"""


def build_epub(path, date_value="", ddc_value="", with_cover=True):
    if os.path.exists(path):
        os.remove(path)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", opf_epub3_with_cover(date_value, ddc_value))
        zf.writestr("OEBPS/chap1.xhtml", CHAP1)
        if with_cover:
            zf.writestr("OEBPS/cover.png", TINY_PNG)


def build_epub_no_cover(path, date_value="", ddc_value=""):
    build_epub(path, date_value, ddc_value, with_cover=False)
    # remove the manifest cover item too, since build_epub always includes
    # it in the OPF regardless of with_cover -- rewrite OPF without it.
    opf = opf_epub3_with_cover(date_value, ddc_value).replace(
        '\n    <item id="cover-img" href="cover.png" media-type="image/png" properties="cover-image"/>',
        "",
    )
    # rewrite zip without the cover manifest entry
    with zipfile.ZipFile(path, "r") as zf:
        entries = {n: zf.read(n) for n in zf.namelist()}
    entries["OEBPS/content.opf"] = opf.encode()
    os.remove(path)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), entries["mimetype"], zipfile.ZIP_STORED)
        for name, data in entries.items():
            if name != "mimetype":
                zf.writestr(name, data)


# ----------------------------------------------------------------------
# Date parsing/formatting (pure functions, no EPUB needed)
# ----------------------------------------------------------------------

def test_parse_date_full():
    assert parse_date_parts("2020-05-14") == ("2020", "05", "14")
    print("PASS: parses full date")


def test_parse_date_year_month():
    assert parse_date_parts("2020-05") == ("2020", "05", "")
    print("PASS: parses year-month")


def test_parse_date_year_only():
    assert parse_date_parts("2020") == ("2020", "", "")
    print("PASS: parses year only")


def test_parse_date_full_datetime():
    assert parse_date_parts("2020-05-14T00:00:00Z") == ("2020", "05", "14")
    print("PASS: strips time portion from a full datetime")


def test_parse_date_empty_and_garbage():
    assert parse_date_parts("") == ("", "", "")
    assert parse_date_parts("not a date") == ("", "", "")
    print("PASS: empty/unparseable input yields all-empty, not a crash")


def test_format_date_roundtrip():
    assert format_date_parts("2020", "05", "14") == "2020-05-14"
    assert format_date_parts("2020", "5", "4") == "2020-05-04"  # zero-pads
    assert format_date_parts("2020", "05", "") == "2020-05"
    assert format_date_parts("2020", "", "") == "2020"
    assert format_date_parts("", "05", "14") == ""  # no year -> nothing usable
    print("PASS: reassembles with only the precision actually supplied")


# ----------------------------------------------------------------------
# Full read/write round trip: date + DDC together
# ----------------------------------------------------------------------

def test_date_and_ddc_roundtrip():
    path = os.path.join(TEST_DIR, "dated.epub")
    build_epub(path, date_value="2019-03-07", ddc_value="823.912")

    b = EpubBook(path)
    assert b.load_error is None, b.load_error
    assert (b.metadata.pub_year, b.metadata.pub_month, b.metadata.pub_day) == ("2019", "03", "07")
    assert b.metadata.ddc == "823.912", b.metadata.ddc
    # DDC subject must NOT leak into the ordinary tags list
    assert "823.912" not in b.metadata.tags
    assert b.metadata.tags == ["Fiction"], b.metadata.tags
    print("PASS: reads existing date + DDC, DDC excluded from tags")

    b.apply_metadata({"pub_year": "2022", "pub_month": "11", "pub_day": "", "ddc": "813.6"})
    out = os.path.join(TEST_DIR, "dated_updated.epub")
    b.save(out)

    b2 = EpubBook(out)
    assert (b2.metadata.pub_year, b2.metadata.pub_month, b2.metadata.pub_day) == ("2022", "11", "")
    assert b2.metadata.ddc == "813.6"
    assert b2.metadata.tags == ["Fiction"], b2.metadata.tags  # untouched
    print("PASS: updating date/DDC persists correctly and leaves tags alone")

    # Clearing both should remove the elements entirely, not leave empties.
    b2.apply_metadata({"pub_year": "", "pub_month": "", "pub_day": "", "ddc": ""})
    out2 = os.path.join(TEST_DIR, "dated_cleared.epub")
    b2.save(out2)
    b3 = EpubBook(out2)
    assert b3.metadata.pub_year == "" and b3.metadata.ddc == ""
    with zipfile.ZipFile(out2) as zf:
        opf = zf.read("OEBPS/content.opf").decode()
        assert "<dc:date>" not in opf
        assert "DDC" not in opf
    print("PASS: clearing date/DDC removes the elements cleanly")


# ----------------------------------------------------------------------
# Cover image: read, replace, add-where-none-existed, delete
# ----------------------------------------------------------------------

def test_cover_read():
    path = os.path.join(TEST_DIR, "with_cover.epub")
    build_epub(path, with_cover=True)
    b = EpubBook(path)
    assert b.load_error is None, b.load_error
    assert b.cover_bytes == TINY_PNG
    assert b.cover_mime == "image/png"
    assert not b.cover_changed and not b.cover_removed
    print("PASS: reads existing cover image bytes + mime type")


def test_corrupted_zip_entry_zlib_error_sets_load_error_not_crash():
    """Regression test for a real crash reported in the field: a zip
    entry with genuinely corrupted COMPRESSED bytes (a truncated
    download, bit rot, a bad write) makes zipfile's own internal
    decompression raise zlib.error -- a different exception class from
    zipfile.BadZipFile (which is about the zip's own structure, not an
    individual entry's payload), and wasn't in the caught exception
    tuple. Previously this crashed the ENTIRE batch load outright (every
    other file in the same folder included), not just this one file.

    Reproduced here via monkeypatching zipfile.ZipFile.read rather than
    hand-crafting a byte-corrupted deflate stream: constructing one that
    reliably raises zlib.error specifically (not some other zlib/zipfile
    error) across zlib versions is genuinely fragile, whereas asserting
    "when zf.read() raises zlib.error for this entry, load_error is set
    gracefully" tests the actual contract just as directly."""
    path = os.path.join(TEST_DIR, "corrupted_cover.epub")
    build_epub(path, with_cover=True)

    original_read = zipfile.ZipFile.read

    def failing_read(self, name, *args, **kwargs):
        if name.endswith("cover.png"):
            raise zlib.error("Error -3 while decompressing data: invalid stored block lengths")
        return original_read(self, name, *args, **kwargs)

    zipfile.ZipFile.read = failing_read
    try:
        b = EpubBook(path)
    finally:
        zipfile.ZipFile.read = original_read

    assert b.load_error is not None, "a corrupted entry must set load_error, not raise"
    assert "decompress" in b.load_error.lower() or "zlib" in b.load_error.lower(), b.load_error
    print("PASS: a corrupted zip entry (zlib.error) sets load_error gracefully, doesn't crash")


def test_cover_replace_existing():
    path = os.path.join(TEST_DIR, "replace_cover.epub")
    build_epub(path, with_cover=True)
    b = EpubBook(path)

    b.set_cover(TINY_PNG_2, "image/png")
    assert b.dirty
    out = os.path.join(TEST_DIR, "replace_cover_saved.epub")
    b.save(out)

    b2 = EpubBook(out)
    assert b2.cover_bytes == TINY_PNG_2
    # The old cover href should be reused (no orphaned duplicate file).
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        assert names.count("OEBPS/cover.png") == 1
    print("PASS: replacing an existing cover overwrites its bytes in place, no orphan file")


def test_cover_add_to_book_with_none():
    path = os.path.join(TEST_DIR, "no_cover.epub")
    build_epub_no_cover(path)
    b = EpubBook(path)
    assert b.load_error is None, b.load_error
    assert b.cover_bytes is None
    print("PASS: book with no cover loads with cover_bytes=None")

    b.set_cover(TINY_PNG, "image/png")
    out = os.path.join(TEST_DIR, "cover_added.epub")
    b.save(out)

    b2 = EpubBook(out)
    assert b2.cover_bytes == TINY_PNG
    assert b2.cover_mime == "image/png"
    print("PASS: adding a cover to a book that had none creates it correctly")


def test_cover_delete():
    path = os.path.join(TEST_DIR, "delete_cover.epub")
    build_epub(path, with_cover=True)
    b = EpubBook(path)

    b.remove_cover()
    assert b.dirty
    out = os.path.join(TEST_DIR, "cover_deleted.epub")
    b.save(out)

    b2 = EpubBook(out)
    assert b2.cover_bytes is None
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        assert "OEBPS/cover.png" not in names, "cover file should be physically removed"
        opf = zf.read("OEBPS/content.opf").decode()
        assert "cover-image" not in opf
    print("PASS: deleting a cover removes the file and all manifest references")


def test_cover_delete_noop_when_none():
    path = os.path.join(TEST_DIR, "no_cover2.epub")
    build_epub_no_cover(path)
    b = EpubBook(path)
    assert not b.dirty
    b.remove_cover()
    assert not b.dirty, "removing a cover that never existed shouldn't mark dirty"
    print("PASS: removing a nonexistent cover is a harmless no-op")


def test_cover_untouched_book_saves_cleanly():
    """A book whose cover is never touched should save without any
    cover-related file changes at all (regression guard against
    accidentally always rewriting the cover file)."""
    path = os.path.join(TEST_DIR, "untouched_cover.epub")
    build_epub(path, with_cover=True)
    b = EpubBook(path)
    b.apply_metadata({"title": "Retitled"})  # unrelated change
    out = os.path.join(TEST_DIR, "untouched_cover_saved.epub")
    b.save(out)
    b2 = EpubBook(out)
    assert b2.cover_bytes == TINY_PNG
    assert b2.metadata.title == "Retitled"
    print("PASS: saving unrelated metadata changes leaves an untouched cover intact")


if __name__ == "__main__":
    test_parse_date_full()
    test_parse_date_year_month()
    test_parse_date_year_only()
    test_parse_date_full_datetime()
    test_parse_date_empty_and_garbage()
    test_format_date_roundtrip()
    test_date_and_ddc_roundtrip()
    test_cover_read()
    test_corrupted_zip_entry_zlib_error_sets_load_error_not_crash()
    test_cover_replace_existing()
    test_cover_add_to_book_with_none()
    test_cover_delete()
    test_cover_delete_noop_when_none()
    test_cover_untouched_book_saves_cleanly()
    print("\nALL DATE/DDC/COVER TESTS PASSED")
