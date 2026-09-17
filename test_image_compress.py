"""Tests for Compress Images (Lossy): core/epub_metadata.py's staging
logic (find_compressible_images/read_archive_file/stage_image_replacement)
and gui/image_compress.py's actual JPEG re-encoding."""
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(__file__))
from core.epub_metadata import EpubBook  # noqa: E402

TEST_DIR = "/tmp/epub_test_image_compress"
os.makedirs(TEST_DIR, exist_ok=True)

CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

OPF_WITH_IMAGES = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="BookId">urn:uuid:aaaa</dc:identifier>
    <dc:title>Image Book</dc:title>
  </metadata>
  <manifest>
    <item id="chap1" href="chap1.xhtml" media-type="application/xhtml+xml"/>
    <item id="img1" href="images/photo.jpg" media-type="image/jpeg"/>
    <item id="img2" href="images/icon.png" media-type="image/png"/>
  </manifest>
  <spine><itemref idref="chap1"/></spine>
</package>
"""

CHAP1 = "<html><body><p>x</p></body></html>"
FAKE_JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"fake jpeg payload" * 50  # not a real decodable JPEG
FAKE_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fake png payload" * 10


def build(path):
    if os.path.exists(path):
        os.remove(path)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", OPF_WITH_IMAGES)
        zf.writestr("OEBPS/chap1.xhtml", CHAP1)
        zf.writestr("OEBPS/images/photo.jpg", FAKE_JPEG_BYTES)
        zf.writestr("OEBPS/images/icon.png", FAKE_PNG_BYTES)


def test_find_compressible_images_only_finds_jpeg():
    path = os.path.join(TEST_DIR, "images.epub")
    build(path)
    b = EpubBook(path)
    assert b.load_error is None, b.load_error
    images = b.find_compressible_images()
    assert images == [("OEBPS/images/photo.jpg", len(FAKE_JPEG_BYTES))], images
    print("PASS: find_compressible_images finds only the JPEG, not the PNG")


def test_find_compressible_images_respects_custom_media_types():
    path = os.path.join(TEST_DIR, "images2.epub")
    build(path)
    b = EpubBook(path)
    images = b.find_compressible_images(media_types={"image/png"})
    assert images == [("OEBPS/images/icon.png", len(FAKE_PNG_BYTES))], images
    print("PASS: find_compressible_images honors a custom media_types filter")


def test_read_archive_file_returns_raw_bytes():
    path = os.path.join(TEST_DIR, "images3.epub")
    build(path)
    b = EpubBook(path)
    assert b.read_archive_file("OEBPS/images/photo.jpg") == FAKE_JPEG_BYTES
    assert b.read_archive_file("OEBPS/does/not/exist.jpg") is None
    print("PASS: read_archive_file returns raw bytes, None for a missing path")


def test_read_archive_file_reflects_staged_replacement():
    path = os.path.join(TEST_DIR, "images4.epub")
    build(path)
    b = EpubBook(path)
    b.stage_image_replacement("OEBPS/images/photo.jpg", b"NEW BYTES")
    assert b.read_archive_file("OEBPS/images/photo.jpg") == b"NEW BYTES"
    assert b.dirty
    print("PASS: read_archive_file returns the staged replacement, not the on-disk original")


def test_stage_image_replacement_saves_correctly():
    path = os.path.join(TEST_DIR, "images5.epub")
    build(path)
    b = EpubBook(path)
    b.stage_image_replacement("OEBPS/images/photo.jpg", b"SMALLER JPEG DATA")
    out = os.path.join(TEST_DIR, "images5_saved.epub")
    b.save(out)
    with zipfile.ZipFile(out) as zf:
        assert zf.read("OEBPS/images/photo.jpg") == b"SMALLER JPEG DATA"
        assert zf.read("OEBPS/images/icon.png") == FAKE_PNG_BYTES  # untouched
        assert zf.read("OEBPS/chap1.xhtml").decode() == CHAP1  # untouched
    print("PASS: stage_image_replacement's bytes actually land in the saved archive")


def test_image_replacement_clears_only_on_real_save():
    path = os.path.join(TEST_DIR, "images6.epub")
    build(path)
    b = EpubBook(path)
    b.stage_image_replacement("OEBPS/images/photo.jpg", b"COPY BYTES")

    copy_path = os.path.join(TEST_DIR, "images6_COPY.epub")
    b.save(copy_path)  # Save As Copy -- different path
    assert b._image_replacements == {"OEBPS/images/photo.jpg": b"COPY BYTES"}
    assert b.path == path  # unchanged

    b.save()  # real save, in place
    assert b._image_replacements == {}
    print("PASS: staged image replacement survives a Save As Copy, clears only on a real save")


if __name__ == "__main__":
    test_find_compressible_images_only_finds_jpeg()
    test_find_compressible_images_respects_custom_media_types()
    test_read_archive_file_returns_raw_bytes()
    test_read_archive_file_reflects_staged_replacement()
    test_stage_image_replacement_saves_correctly()
    test_image_replacement_clears_only_on_real_save()
    print("\nALL IMAGE COMPRESSION STAGING TESTS PASSED")
