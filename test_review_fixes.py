"""Regression tests for the verified code-review findings (2026-09-30),
core side: percent-encoded manifest hrefs, atomic/clean save(),
load robustness, DRM-aware cover/compress, platform-aware Kobo
discovery, and a few small hardening fixes. MainWindow-side fixes are
in test_review_fixes_gui.py."""

import os
import sys
import zipfile

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import core.epub_metadata as em  # noqa: E402
from core import better_cover, kobo_usb  # noqa: E402
from core.ebook_convert import EbookConvertError, convert_to_epub  # noqa: E402
from core.epub_metadata import EpubBook, href_to_archive_path  # noqa: E402
from core.sigil_tools import sigil_file_filter  # noqa: E402

CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""

OPF = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="BookId">urn:uuid:aaaa</dc:identifier>
    <dc:title>T</dc:title>
    <dc:language>en</dc:language>
    <meta name="cover" content="cov"/>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="c1" href="ch%201.xhtml" media-type="application/xhtml+xml"/>
    <item id="c2" href="kap%C3%ADtulo.xhtml" media-type="application/xhtml+xml"/>
    <item id="cov" href="im%20ages/cover%20art.jpg" media-type="image/jpeg"/>
  </manifest>
  <spine><itemref idref="c1"/><itemref idref="c2"/></spine>
  <guide><reference type="text" title="x" href="ch%201.xhtml#start"/></guide>
</package>
"""

FILES = {
    "OEBPS/nav.xhtml": "<html><body>nav</body></html>",
    "OEBPS/ch 1.xhtml": "<html><body><p>Chapter one text</p></body></html>",
    "OEBPS/kap\u00edtulo.xhtml": "<html><body><p>Two</p></body></html>",
    "OEBPS/im ages/cover art.jpg": b"\xff\xd8\xff old cover",
}


def build(path, opf=OPF, files=None, extra=None):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", opf)
        for name, content in (files or FILES).items():
            zf.writestr(name, content)
        for name, content in (extra or {}).items():
            zf.writestr(name, content)
    return str(path)


def names(path):
    with zipfile.ZipFile(path) as zf:
        return zf.namelist()


# --- H1: percent-encoded hrefs -------------------------------------------

def test_href_helper():
    assert href_to_archive_path("OEBPS", "ch%201.xhtml") == "OEBPS/ch 1.xhtml"
    assert href_to_archive_path("OEBPS", "a.xhtml#frag") == "OEBPS/a.xhtml"
    assert href_to_archive_path("OEBPS", "a.xhtml?x=1") == "OEBPS/a.xhtml"
    assert href_to_archive_path("", "kap%C3%ADtulo.xhtml") == "kap\u00edtulo.xhtml"
    assert href_to_archive_path("OEBPS", "../x/y.css") == "x/y.css"
    assert href_to_archive_path("OEBPS", "#only") == ""


def test_encoded_hrefs_validate_clean(tmp_path):
    book = EpubBook(build(tmp_path / "a.epub"))
    assert not book.load_error
    assert "MANIFEST_FILE_MISSING" not in {i.code for i in book.validation_issues}
    assert book.find_missing_manifest_files() == []
    assert book.find_broken_guide_references() == []
    assert book.cover_bytes == b"\xff\xd8\xff old cover"


def test_encoded_hrefs_not_orphans_and_rebuild_keeps_them(tmp_path):
    book = EpubBook(build(tmp_path / "a.epub", extra={"OEBPS/stray.txt": "x"}))
    assert book.find_orphaned_files() == ["OEBPS/stray.txt"]
    assert book.rebuild_manifest() == []  # nothing missing -> nothing removed
    book.remove_orphaned_files()
    book.save()
    assert "OEBPS/stray.txt" not in names(book.path)
    assert "OEBPS/ch 1.xhtml" in names(book.path) and "OEBPS/kap\u00edtulo.xhtml" in names(book.path)


def test_rebuild_removes_only_truly_missing_and_keeps_written_hrefs(tmp_path):
    files = {k: v for k, v in FILES.items() if "ch 1" not in k}
    book = EpubBook(build(tmp_path / "a.epub", files=files))
    assert [h for _i, h in book.find_missing_manifest_files()] == ["ch%201.xhtml"]
    book.rebuild_manifest()
    book.save()
    with zipfile.ZipFile(book.path) as zf:
        opf = zf.read("OEBPS/content.opf").decode()
    assert "kap%C3%ADtulo.xhtml" in opf and "im%20ages/cover%20art.jpg" in opf  # encoded form preserved
    assert 'id="c1"' not in opf


def test_cover_replace_overwrites_old_entry_and_keeps_encoded_href(tmp_path):
    book = EpubBook(build(tmp_path / "a.epub"))
    assert book.set_cover(b"NEWCOVER", "image/jpeg")
    book.save()
    with zipfile.ZipFile(book.path) as zf:
        assert zf.read("OEBPS/im ages/cover art.jpg") == b"NEWCOVER"
        assert "OEBPS/cover-image.jpg" not in zf.namelist()
        assert 'href="im%20ages/cover%20art.jpg"' in zf.read("OEBPS/content.opf").decode()


def test_compressible_images_found_through_encoded_href(tmp_path):
    book = EpubBook(build(tmp_path / "a.epub"))
    assert [p for p, _s in book.find_compressible_images()] == ["OEBPS/im ages/cover art.jpg"]


def test_content_scan_reads_encoded_spine_docs(tmp_path):
    from core.content_scan import extract_text_from_epub
    book = EpubBook(build(tmp_path / "a.epub"))
    assert "Chapter one text" in extract_text_from_epub(book)


# --- H2: save() ------------------------------------------------------------

def test_save_failure_removes_temp_file(tmp_path, monkeypatch):
    book = EpubBook(build(tmp_path / "a.epub"))
    book.apply_metadata({"title": "New"})

    def boom(*a, **k):
        raise OSError("locked")

    monkeypatch.setattr(em.os, "replace", boom)
    with pytest.raises(OSError):
        book.save()
    assert not os.path.exists(str(tmp_path / "a.epub") + ".tmp_write")


def test_save_uses_os_replace_and_roundtrips(tmp_path, monkeypatch):
    calls = []
    real = os.replace
    monkeypatch.setattr(em.os, "replace", lambda a, b: (calls.append((a, b)), real(a, b))[1])
    book = EpubBook(build(tmp_path / "a.epub"))
    book.apply_metadata({"title": "New"})
    book.save()
    assert len(calls) == 1 and EpubBook(book.path).metadata.title == "New"


def test_save_does_not_duplicate_entries_of_malformed_zip(tmp_path):
    path = str(tmp_path / "a.epub")
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # zipfile warns about the duplicate name it is about to write
        build(path, extra={"OEBPS/nav.xhtml": "<html><body>dup</body></html>"})
    assert names(path).count("OEBPS/nav.xhtml") == 2
    book = EpubBook(path)
    book.apply_metadata({"title": "New"})
    book.save()
    out = names(book.path)
    assert len(out) == len(set(out))


# --- M7: load robustness ---------------------------------------------------

@pytest.mark.parametrize("exc", [NotImplementedError("compression"), RuntimeError("encrypted"),
                                 ValueError("bad"), AttributeError("x"), zipfile.LargeZipFile("big")])
def test_load_catches_any_exception(tmp_path, monkeypatch, exc):
    path = build(tmp_path / "a.epub")

    def boom(zf):
        raise exc

    monkeypatch.setattr(em, "_find_opf_path", boom)
    book = EpubBook(path)
    assert book.load_error and book.validation_status != "OK"


def test_xml_parser_does_not_expand_entities(tmp_path):
    evil = OPF.replace("<package", '<!DOCTYPE package [<!ENTITY e "EXPANDED">]>\n<package', 1).replace(
        "<dc:title>T</dc:title>", "<dc:title>&e;</dc:title>")
    book = EpubBook(build(tmp_path / "a.epub", opf=evil))
    assert "EXPANDED" not in book.metadata.title


# --- M9: DRM ---------------------------------------------------------------

ENC_TEMPLATE = """<?xml version="1.0"?>
<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container" xmlns:enc="http://www.w3.org/2001/04/xmlenc#">
  <enc:EncryptedData>
    <enc:EncryptionMethod Algorithm="{alg}"/>
    <enc:CipherData><enc:CipherReference URI="{uri}"/></enc:CipherData>
  </enc:EncryptedData>
</encryption>
"""


def test_drm_encrypted_cover_is_not_replaced(tmp_path):
    enc = ENC_TEMPLATE.format(alg="http://www.w3.org/2001/04/xmlenc#aes128-cbc",
                              uri="OEBPS/im%20ages/cover%20art.jpg")
    book = EpubBook(build(tmp_path / "a.epub", extra={"META-INF/encryption.xml": enc}))
    assert book.cover_is_encrypted()
    assert book.set_cover(b"NEW", "image/jpeg") is False
    assert not book.cover_changed and not book.dirty
    assert book.find_compressible_images() == []


def test_font_obfuscation_alone_does_not_block(tmp_path):
    enc = ENC_TEMPLATE.format(alg="http://www.idpf.org/2008/embedding", uri="OEBPS/fonts/f.otf")
    book = EpubBook(build(tmp_path / "a.epub", extra={"META-INF/encryption.xml": enc}))
    assert not book.cover_is_encrypted()
    assert book.set_cover(b"NEW", "image/jpeg") is True
    assert len(book.find_compressible_images()) == 1


# --- M8: Kobo discovery ----------------------------------------------------

def test_kobo_windows_letters_unchanged():
    found = kobo_usb.find_connected_kobos(drive_letters=["D", "E"], isdir_fn=lambda p: p == "E:\\.kobo")
    assert found == ["E:\\"]


def test_kobo_non_windows_scans_mount_points(monkeypatch):
    monkeypatch.setattr(kobo_usb.sys, "platform", "linux")
    roots = ["/media/me/KOBOeReader", "/media/me/USBSTICK"]
    found = kobo_usb.find_connected_kobos(
        isdir_fn=lambda p: p == os.path.join(roots[0], ".kobo"), mount_points=roots)
    assert found == [roots[0]]


def test_kobo_mount_points_linux_and_mac(monkeypatch):
    monkeypatch.setenv("USER", "me")
    monkeypatch.setattr(kobo_usb.sys, "platform", "linux")
    listing = {"/media/me": ["A"], "/run/media/me": ["B"]}
    got = kobo_usb._mount_points(listdir_fn=lambda p: listing[p], isdir_fn=lambda p: p in listing)
    assert got == [os.path.join("/media/me", "A"), os.path.join("/run/media/me", "B")]
    monkeypatch.setattr(kobo_usb.sys, "platform", "darwin")
    got = kobo_usb._mount_points(listdir_fn=lambda p: ["KOBO"], isdir_fn=lambda p: p == "/Volumes")
    assert got == [os.path.join("/Volumes", "KOBO")]


# --- Low ---------------------------------------------------------------------

def test_better_cover_caps_response(monkeypatch):
    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n=-1):
            return b"x" * (n if n >= 0 else better_cover.MAX_COVER_BYTES * 2)

    monkeypatch.setattr(better_cover.urllib.request, "urlopen", lambda *a, **k: Resp())
    with pytest.raises(better_cover.IsbnCoverError):
        better_cover._default_get("https://example.invalid/x.jpg")


def test_failed_convert_removes_partial_output(tmp_path):
    src = tmp_path / "b.mobi"
    src.write_text("x")
    out = tmp_path / "b.epub"

    class P:
        returncode = 1
        stderr = b"bad"

    def fake_run(args, **kw):
        out.write_text("partial")
        return P()

    with pytest.raises(EbookConvertError):
        convert_to_epub("/x/ebook-convert", str(src), str(out), run_fn=fake_run)
    assert not out.exists()


def test_failed_convert_keeps_preexisting_output(tmp_path):
    src = tmp_path / "b.mobi"
    src.write_text("x")
    out = tmp_path / "b.epub"
    out.write_text("mine")

    class P:
        returncode = 1
        stderr = b"bad"

    with pytest.raises(EbookConvertError):
        convert_to_epub("/x/ebook-convert", str(src), str(out), run_fn=lambda *a, **k: P())
    assert out.read_text() == "mine"


def test_sigil_filter_is_platform_aware(monkeypatch):
    import core.sigil_tools as st
    monkeypatch.setattr(st.sys, "platform", "win32")
    assert sigil_file_filter() == "Sigil (sigil.exe)"
    monkeypatch.setattr(st.sys, "platform", "linux")
    assert ".exe" not in sigil_file_filter()
