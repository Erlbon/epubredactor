"""Tests for core/content_scan.py."""
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(__file__))
from core.content_scan import extract_text_from_epub, guess_metadata_from_text, scan_book  # noqa: E402
from core.epub_metadata import EpubBook  # noqa: E402

TEST_DIR = "/tmp/epub_test_content_scan"
os.makedirs(TEST_DIR, exist_ok=True)

CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

OPF = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="BookId">urn:uuid:scan-test</dc:identifier>
    <dc:title>Scan Test Book</dc:title>
    <dc:language>en</dc:language>
  </metadata>
  <manifest>
    <item id="titlepage" href="titlepage.xhtml" media-type="application/xhtml+xml"/>
    <item id="chap1" href="chap1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="titlepage"/>
    <itemref idref="chap1"/>
  </spine>
</package>
"""

TITLEPAGE_HTML = """<html><body>
<h1>The Great Test Novel</h1>
<p>Copyright &#169; 2019 by Jane A. Smith</p>
<p>Published by Acme Publishing</p>
<p>ISBN: 978-0-14-143951-8</p>
<p>Dewey Decimal 813.6</p>
</body></html>"""

CHAP1_HTML = "<html><body><p>Chapter One begins here.</p></body></html>"


def build_book(path):
    if os.path.exists(path):
        os.remove(path)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", OPF)
        zf.writestr("OEBPS/titlepage.xhtml", TITLEPAGE_HTML)
        zf.writestr("OEBPS/chap1.xhtml", CHAP1_HTML)
    return EpubBook(path)


# ----------------------------------------------------------------------
# guess_metadata_from_text: pure regex heuristics, no zip needed
# ----------------------------------------------------------------------

def test_isbn_extraction():
    text = "Front matter. ISBN: 978-0-14-143951-8 More text."
    result = guess_metadata_from_text(text)
    assert result.isbn == "9780141439518", result.isbn
    print("PASS: extracts and validates ISBN from copyright-page-style text")


def test_isbn_extraction_rejects_invalid_checksum():
    text = "ISBN: 978-0-14-143951-9"  # wrong check digit
    result = guess_metadata_from_text(text)
    assert result.isbn == "", "should not accept a checksum-invalid ISBN"
    print("PASS: an ISBN-looking string with a bad checksum is rejected, not guessed")


def test_ddc_extraction():
    text = "Some text. Dewey Decimal 823.912 more text."
    result = guess_metadata_from_text(text)
    assert result.ddc == "823.912", result.ddc

    text2 = "DDC: 133"
    result2 = guess_metadata_from_text(text2)
    assert result2.ddc == "133", result2.ddc
    print("PASS: extracts DDC classification in both wordings")


def test_copyright_year_extraction():
    result = guess_metadata_from_text("Copyright \u00a9 2019 by Someone")
    assert result.pub_year == "2019", result.pub_year

    result2 = guess_metadata_from_text("First published in 1987 by a press.")
    assert result2.pub_year == "1987", result2.pub_year
    print("PASS: extracts publication year from copyright notice or 'first published'")


def test_author_extraction_from_copyright():
    result = guess_metadata_from_text("Copyright \u00a9 2019 by Jane A. Smith. All rights reserved.")
    assert result.authors_str == "Jane A. Smith", result.authors_str
    print("PASS: extracts author name from copyright notice")


def test_publisher_extraction_published_by():
    result = guess_metadata_from_text("Text. Published by Acme Publishing. More text.")
    assert result.publisher == "Acme Publishing", result.publisher
    print("PASS: extracts publisher from 'Published by'")


def test_publisher_extraction_suffix_pattern():
    result = guess_metadata_from_text("A book from Riverhead Books, all rights reserved.")
    assert "Riverhead Books" in result.publisher, result.publisher
    print("PASS: extracts publisher from a name ending in a common publisher suffix")


def test_empty_text_returns_empty_result():
    result = guess_metadata_from_text("")
    assert result.as_dict() == {}
    print("PASS: empty input produces an empty (not crashing) result")


def test_no_matches_returns_empty_fields():
    result = guess_metadata_from_text("Once upon a time there was a dragon.")
    assert result.as_dict() == {}
    print("PASS: ordinary prose with no metadata patterns yields nothing, not false positives")


def test_source_snippets_recorded():
    result = guess_metadata_from_text("Copyright \u00a9 2019 by Jane Smith")
    assert "pub_year" in result.source_snippets
    assert "2019" in result.source_snippets["pub_year"]
    print("PASS: matched snippet is recorded alongside each guessed field, for user review")


# ----------------------------------------------------------------------
# extract_text_from_epub / scan_book: full pipeline against a real epub
# ----------------------------------------------------------------------

def test_extract_text_from_epub_reads_spine_order():
    path = os.path.join(TEST_DIR, "scan.epub")
    book = build_book(path)
    text = extract_text_from_epub(book)
    assert "The Great Test Novel" in text
    assert "Jane A. Smith" in text
    assert "Chapter One begins here." in text  # 2nd spine doc also included (max_docs default >=2)
    print("PASS: extracts and concatenates text from spine documents in order")


def test_extract_text_respects_max_docs():
    path = os.path.join(TEST_DIR, "scan2.epub")
    book = build_book(path)
    text = extract_text_from_epub(book, max_docs=1)
    assert "The Great Test Novel" in text
    assert "Chapter One begins here." not in text
    print("PASS: max_docs limits how many spine documents are scanned")


def test_scan_book_full_pipeline():
    path = os.path.join(TEST_DIR, "scan3.epub")
    book = build_book(path)
    result = scan_book(book)
    assert result.isbn == "9780141439518"
    assert result.publisher == "Acme Publishing"
    assert result.pub_year == "2019"
    assert result.authors_str == "Jane A. Smith"
    assert result.ddc == "813.6"
    print("PASS: full scan_book pipeline extracts all fields from a realistic title page")


def test_scan_book_on_load_error_book_is_safe():
    path = os.path.join(TEST_DIR, "broken.epub")
    with open(path, "w") as f:
        f.write("not a zip")
    book = EpubBook(path)
    assert book.load_error is not None
    result = scan_book(book)
    assert result.as_dict() == {}
    print("PASS: scanning a book that failed to load returns an empty result, doesn't crash")


if __name__ == "__main__":
    test_isbn_extraction()
    test_isbn_extraction_rejects_invalid_checksum()
    test_ddc_extraction()
    test_copyright_year_extraction()
    test_author_extraction_from_copyright()
    test_publisher_extraction_published_by()
    test_publisher_extraction_suffix_pattern()
    test_empty_text_returns_empty_result()
    test_no_matches_returns_empty_fields()
    test_source_snippets_recorded()
    test_extract_text_from_epub_reads_spine_order()
    test_extract_text_respects_max_docs()
    test_scan_book_full_pipeline()
    test_scan_book_on_load_error_book_is_safe()
    print("\nALL CONTENT SCAN TESTS PASSED")
