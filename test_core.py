"""Quick end-to-end smoke test for core/epub_metadata.py.

Builds a minimal synthetic EPUB (epub2-style OPF, the trickiest case
since it has no epub3 collection support natively), then:
  1. reads it back and checks initial values
  2. applies new metadata (including a series + multi author/tags)
  3. saves it
  4. re-opens the saved file with a *fresh* EpubBook to confirm the
     changes actually persisted to disk correctly
  5. checks the zip is still well-formed (mimetype first & stored)
"""
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(__file__))
from core.epub_metadata import EpubBook  # noqa: E402

TEST_DIR = "/tmp/epub_test"
os.makedirs(TEST_DIR, exist_ok=True)
SAMPLE_PATH = os.path.join(TEST_DIR, "sample.epub")

CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

OPF_XML = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="BookId">urn:uuid:1234</dc:identifier>
    <dc:title>Old Title</dc:title>
    <dc:creator opf:role="aut">Old Author</dc:creator>
    <dc:language>en</dc:language>
    <dc:publisher>Old Publisher</dc:publisher>
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="chap1" href="chap1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine toc="ncx">
    <itemref idref="chap1"/>
  </spine>
</package>
"""

CHAP1 = "<html><body><p>Hello world</p></body></html>"
NCX = '<?xml version="1.0"?><ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1"></ncx>'


def build_sample_epub(path):
    if os.path.exists(path):
        os.remove(path)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", OPF_XML)
        zf.writestr("OEBPS/toc.ncx", NCX)
        zf.writestr("OEBPS/chap1.xhtml", CHAP1)


def main():
    build_sample_epub(SAMPLE_PATH)

    book = EpubBook(SAMPLE_PATH)
    assert book.load_error is None, f"load failed: {book.load_error}"
    assert book.metadata.title == "Old Title", book.metadata.title
    assert book.metadata.authors == ["Old Author"], book.metadata.authors
    assert book.metadata.publisher == "Old Publisher"
    assert book.metadata.series == ""
    print("PASS: initial read")

    book.apply_metadata({
        "title": "The New Title",
        "authors_str": "Jane Doe; John Smith",
        "series": "The Great Series",
        "series_index": "2",
        "tags_str": "Fantasy; Adventure; YA",
        "publisher": "New Publisher",
        "language": "en-GB",
        "description": "A thrilling tale of testing.",
    })
    assert book.dirty
    print("PASS: apply_metadata sets dirty + values")

    out_path = os.path.join(TEST_DIR, "sample_edited.epub")
    book.save(out_path)
    assert os.path.exists(out_path)
    # Saving to a *different* path is a copy: the original book object
    # must still consider itself dirty and still point at its own path,
    # otherwise a later "Save Changed" would think this book was already
    # saved and skip writing the actual original file.
    assert book.dirty, "book should remain dirty after save-as-copy"
    assert book.path == SAMPLE_PATH, book.path
    print("PASS: save() wrote a file")
    print("PASS: save-as-copy does not clear dirty flag or reassign path")

    # Confirm original untouched (since we used output_path)
    orig_check = EpubBook(SAMPLE_PATH)
    assert orig_check.metadata.title == "Old Title"
    print("PASS: original file untouched when saving to new path")

    # Re-open the saved copy fresh and verify everything round-tripped
    reloaded = EpubBook(out_path)
    assert reloaded.load_error is None, reloaded.load_error
    m = reloaded.metadata
    assert m.title == "The New Title", m.title
    assert m.authors == ["Jane Doe", "John Smith"], m.authors
    assert m.series == "The Great Series", m.series
    assert m.series_index == "2", m.series_index
    assert m.tags == ["Fantasy", "Adventure", "YA"], m.tags
    assert m.publisher == "New Publisher"
    assert m.language == "en-GB"
    assert m.description == "A thrilling tale of testing."
    print("PASS: reloaded saved file matches applied metadata")

    # Verify zip structural integrity: mimetype first & stored
    with zipfile.ZipFile(out_path) as zf:
        infos = zf.infolist()
        assert infos[0].filename == "mimetype", infos[0].filename
        assert infos[0].compress_type == zipfile.ZIP_STORED
        assert zf.read("mimetype") == b"application/epub+zip"
        # other files preserved
        assert zf.read("OEBPS/chap1.xhtml").decode() == CHAP1
        names = zf.namelist()
        assert "OEBPS/toc.ncx" in names
    print("PASS: zip structure valid (mimetype first, stored; other files intact)")

    # Now test in-place overwrite (output_path=None) and clearing series
    book2 = EpubBook(out_path)
    book2.apply_metadata({"series": "", "series_index": ""})
    book2.save()  # overwrite in place
    book3 = EpubBook(out_path)
    assert book3.metadata.series == "", book3.metadata.series
    assert book3.metadata.series_index == "", book3.metadata.series_index
    # ensure no leftover stale meta tags for series
    with zipfile.ZipFile(out_path) as zf:
        opf_data = zf.read("OEBPS/content.opf").decode()
        assert "calibre:series" not in opf_data
        assert "belongs-to-collection" not in opf_data
    print("PASS: clearing series removes all series meta cleanly (both conventions)")

    # Test epub3-collection-only fallback read path
    build_epub3_series_only()
    b3 = EpubBook(os.path.join(TEST_DIR, "epub3_series.epub"))
    assert b3.metadata.series == "Collection Only Series", b3.metadata
    assert b3.metadata.series_index == "3", b3.metadata
    print("PASS: reading epub3-only collection metadata (no calibre tags) works")

    test_isbn_roundtrip_and_primary_id_safety()

    print("\nALL TESTS PASSED")


def build_epub3_series_only():
    opf3 = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="BookId">urn:uuid:5678</dc:identifier>
    <dc:title>EPUB3 Book</dc:title>
    <dc:creator>Author X</dc:creator>
    <dc:language>en</dc:language>
    <opf:meta id="c1" property="belongs-to-collection">Collection Only Series</opf:meta>
    <opf:meta refines="#c1" property="collection-type">series</opf:meta>
    <opf:meta refines="#c1" property="group-position">3</opf:meta>
  </metadata>
  <manifest>
    <item id="chap1" href="chap1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="chap1"/>
  </spine>
</package>
"""
    path = os.path.join(TEST_DIR, "epub3_series.epub")
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML.replace("OEBPS/content.opf", "OEBPS/content.opf"))
        zf.writestr("OEBPS/content.opf", opf3)
        zf.writestr("OEBPS/chap1.xhtml", CHAP1)


def test_isbn_roundtrip_and_primary_id_safety():
    """ISBN handling gets its own focused test: reading an existing ISBN
    identifier, adding one where none existed, updating one, clearing one,
    and -- most importantly -- never disturbing the book's primary/unique
    identifier element in any of those cases."""
    # A book with a UUID as its primary id AND an existing ISBN identifier.
    opf_with_isbn = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="BookId">urn:uuid:aaaa-bbbb-cccc</dc:identifier>
    <dc:identifier opf:scheme="ISBN">9780141439518</dc:identifier>
    <dc:title>Pride and Prejudice</dc:title>
    <dc:creator>Jane Austen</dc:creator>
  </metadata>
  <manifest>
    <item id="chap1" href="chap1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="chap1"/></spine>
</package>
"""
    path = os.path.join(TEST_DIR, "isbn_book.epub")
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", opf_with_isbn.replace("OEBPS/content.opf", "OEBPS/content.opf"))
        zf.writestr("OEBPS/chap1.xhtml", CHAP1)
    # container.xml above points at OEBPS/content.opf, matching what we wrote.

    b = EpubBook(path)
    assert b.load_error is None, b.load_error
    assert b.metadata.isbn == "9780141439518", b.metadata.isbn
    print("PASS: reads existing ISBN identifier")

    # Update the ISBN and confirm the primary UUID identifier is untouched.
    b.apply_metadata({"isbn": "978-0-14-143951-8"})
    out1 = os.path.join(TEST_DIR, "isbn_book_updated.epub")
    b.save(out1)
    with zipfile.ZipFile(out1) as zf:
        opf_data = zf.read("OEBPS/content.opf").decode()
        assert "urn:uuid:aaaa-bbbb-cccc" in opf_data, "primary identifier was disturbed!"
    b2 = EpubBook(out1)
    assert b2.metadata.isbn == "978-0-14-143951-8", b2.metadata.isbn
    print("PASS: updating ISBN preserves the primary unique identifier")

    # Clear the ISBN entirely; primary id must still survive, ISBN element gone.
    b2.apply_metadata({"isbn": ""})
    out2 = os.path.join(TEST_DIR, "isbn_book_cleared.epub")
    b2.save(out2)
    b3 = EpubBook(out2)
    assert b3.metadata.isbn == "", b3.metadata.isbn
    with zipfile.ZipFile(out2) as zf:
        opf_data = zf.read("OEBPS/content.opf").decode()
        assert "urn:uuid:aaaa-bbbb-cccc" in opf_data
    print("PASS: clearing ISBN removes it while preserving the primary identifier")

    # A book with NO existing ISBN identifier at all -- adding one for the
    # first time must not disturb its (differently-shaped) primary id.
    opf_no_isbn = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="BookId" opf:scheme="uuid">1234-5678</dc:identifier>
    <dc:title>Some Other Book</dc:title>
    <dc:creator>Some Author</dc:creator>
  </metadata>
  <manifest>
    <item id="chap1" href="chap1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="chap1"/></spine>
</package>
"""
    path2 = os.path.join(TEST_DIR, "no_isbn_book.epub")
    with zipfile.ZipFile(path2, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", opf_no_isbn)
        zf.writestr("OEBPS/chap1.xhtml", CHAP1)

    b4 = EpubBook(path2)
    assert b4.metadata.isbn == ""
    b4.apply_metadata({"isbn": "0-13-468599-7"})
    out3 = os.path.join(TEST_DIR, "no_isbn_book_added.epub")
    b4.save(out3)
    b5 = EpubBook(out3)
    assert b5.metadata.isbn == "0-13-468599-7", b5.metadata.isbn
    with zipfile.ZipFile(out3) as zf:
        opf_data = zf.read("OEBPS/content.opf").decode()
        assert 'id="BookId"' in opf_data and "1234-5678" in opf_data, "primary id disturbed"
    print("PASS: adding a brand-new ISBN doesn't disturb a differently-shaped primary id")

    # A urn:isbn: style value pasted directly into the field should be
    # normalized down to the bare ISBN.
    b6 = EpubBook(path2)
    b6.apply_metadata({"isbn": "urn:isbn:9780062315007"})
    out4 = os.path.join(TEST_DIR, "urn_isbn_book.epub")
    b6.save(out4)
    b7 = EpubBook(out4)
    assert b7.metadata.isbn == "9780062315007", b7.metadata.isbn
    print("PASS: a pasted 'urn:isbn:' prefix is normalized away")


if __name__ == "__main__":
    main()
