"""Tests for the persisted validation stamp: the redactor:validation OPF meta
(written only on save, never duplicated, foreign metas intact), the
central-directory fingerprint (stable across metadata-only saves, changes
with any content file), the stamping rule (explicit validation stamps and
dirties; loading and the automatic check never do), the Status column text
and Redact's validate_fix step."""

import os
import sys
import zipfile

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from core.epub_fingerprint import file_fingerprint  # noqa: E402
from core.epub_metadata import STAMP_META_NAME, EpubBook  # noqa: E402
from redactor_common.core.scan_stamp import make_stamp  # noqa: E402
from test_redact_steps import (  # noqa: E402
    GEN_COVER, RedactEnv, Trash, make_epub, only, only_entry, quiet_lookups, run,
)


def load(path):
    return EpubBook(str(path))


def opf_text(path):
    with zipfile.ZipFile(path) as zf:
        return zf.read("OEBPS/content.opf").decode("utf-8")


def stamp_metas(path):
    return opf_text(path).count(f'name="{STAMP_META_NAME}"')


def rewrite(path, changes=None, opf_edit=None):
    """Rewrites the zip with `changes` ({name: bytes}) applied, optionally
    transforming the OPF text."""
    with zipfile.ZipFile(path) as zf:
        entries = [(i, zf.read(i.filename)) for i in zf.infolist()]
    with zipfile.ZipFile(path, "w") as zf:
        for info, data in entries:
            if info.filename in (changes or {}):
                data = changes[info.filename]
            if opf_edit and info.filename == "OEBPS/content.opf":
                data = opf_edit(data.decode("utf-8")).encode("utf-8")
            zf.writestr(info, data)


@pytest.fixture
def epub(tmp_path):
    return make_epub(str(tmp_path / "b.epub"), isbn="9783161484100")


# --- storage ---------------------------------------------------------------------


def test_loading_and_validating_on_load_never_stamps_or_dirties(epub):
    book = load(epub)
    assert book.scan_stamp is None and not book.dirty
    assert book.status_text == book.validation_status == "OK"


def test_the_stamp_is_written_only_on_save_and_only_once(epub):
    book = load(epub)
    assert book.record_validation()
    assert book.dirty and stamp_metas(epub) == 0  # memory only until Save
    book.save()
    book.save()
    assert stamp_metas(epub) == 1
    again = load(epub)
    assert again.scan_stamp is not None and again.scan_stamp.status == "OK"
    assert again.scan_stamp.fingerprint and not again.dirty  # loaded stamp is last-known, not an edit
    again.apply_metadata({"title": "New"})
    again.save()
    assert stamp_metas(epub) == 1 and load(epub).scan_stamp == again.scan_stamp  # preserved through _rebuild_opf


def test_foreign_metas_survive_and_a_garbled_stamp_is_ignored_then_replaced(epub):
    rewrite(epub, opf_edit=lambda t: t.replace(
        "</metadata>",
        f'<meta name="foo:bar" content="keep me"/><meta name="{STAMP_META_NAME}" content="garbage"/>'
        f'<meta name="{STAMP_META_NAME}" content="x;not-a-time"/></metadata>'))
    book = load(epub)
    assert book.scan_stamp is None and not book.dirty
    book.record_validation()
    book.save()
    text = opf_text(epub)
    assert stamp_metas(epub) == 1 and 'content="keep me"' in text and 'name="cover"' in text
    assert "garbage" not in text and load(epub).scan_stamp is not None


# --- fingerprint -----------------------------------------------------------------


def test_fingerprint_survives_a_metadata_save_and_changes_with_content(epub):
    before = file_fingerprint(epub, "OEBPS/content.opf")
    book = load(epub)
    book.apply_metadata({"title": "Different", "publisher": "P"})
    book.save()
    assert file_fingerprint(epub, "OEBPS/content.opf") == before
    rewrite(epub, {"OEBPS/ch1.xhtml": b"<html><body>edited</body></html>"})
    assert file_fingerprint(epub, "OEBPS/content.opf") != before


def test_fingerprint_changes_when_a_file_is_added_or_removed(epub):
    base = file_fingerprint(epub, "OEBPS/content.opf")
    with zipfile.ZipFile(epub, "a") as zf:
        zf.writestr("OEBPS/new.css", "p{}")
    assert file_fingerprint(epub, "OEBPS/content.opf") != base


# --- stamping rule and display ---------------------------------------------------


def test_explicit_check_stamps_and_marks_only_the_stamp_dirty(epub):
    book = load(epub)
    assert book.check_and_stamp()
    assert book.dirty and book.stamp_only_dirty
    assert " · " in book.status_text and book.status_text.startswith("OK · ")
    assert "Scanned" in book.status_tooltip()
    book.apply_metadata({"title": "Edited"})
    assert book.dirty and not book.stamp_only_dirty  # a real edit: no longer stamp-only
    book.check_and_stamp()
    assert not book.stamp_only_dirty  # stays a real edit


def test_a_current_stamp_shows_plain_then_stale_and_unverified_variants(epub):
    book = load(epub)
    book.check_and_stamp()
    book.save()
    assert load(epub).status_text.startswith("OK · ")
    assert "(" not in load(epub).status_text  # matches: no qualifier

    unverified = load(epub)
    unverified.scan_stamp = make_stamp("OK")  # no fingerprint
    unverified._refresh_stamp_staleness()
    assert unverified.status_text.endswith("(unverified)")

    rewrite(epub, {"OEBPS/ch2.xhtml": b"<html><body>changed later</body></html>"})
    assert load(epub).status_text.endswith("(changed since)")


def test_a_different_live_verdict_than_the_stamp_reads_as_changed(epub):
    book = load(epub)
    book.check_and_stamp()
    book.save()
    rewrite(epub, opf_edit=lambda t: t.replace('<item id="p0" href="ch1.xhtml"', '<item id="p0" href="gone.xhtml"'))
    changed = load(epub)
    assert changed.validation_status != "OK"
    assert changed.status_text.startswith(f"{changed.validation_status} · ")
    assert changed.status_text.endswith("(changed since)")


def test_failures_and_drm_are_never_stamped(tmp_path):
    bad = tmp_path / "bad.epub"
    bad.write_bytes(b"not a zip")
    broken = load(bad)
    assert broken.load_error
    assert not broken.record_validation() and not broken.check_and_stamp()
    assert broken.scan_stamp is None and not broken.dirty and broken.status_text == broken.validation_status

    drm = load(make_epub(str(tmp_path / "drm.epub"), encrypted=True))
    assert drm.validation_status == "DRM"
    assert not drm.check_and_stamp() and drm.scan_stamp is None and not drm.dirty


def test_a_stamp_stays_in_a_save_as_copy(epub, tmp_path):
    book = load(epub)
    book.check_and_stamp()
    copy = str(tmp_path / "copy.epub")
    book.save(copy)
    assert load(copy).scan_stamp is not None and book.dirty  # the original is still unsaved


# --- Redact -----------------------------------------------------------------------


@pytest.fixture
def redact_env(tmp_path):
    return RedactEnv(trash=Trash(str(tmp_path) + "-bin"), lookups=quiet_lookups(), make_cover=lambda *a: GEN_COVER)


def test_redact_validate_fix_stamps_the_post_fix_verdict(tmp_path, redact_env):
    path = make_epub(str(tmp_path / "r.epub"), authors=("Ann &amp; Bob",), dup_ids=True)
    report = run([load(path)], redact_env, only("validate_fix", "dedupe_manifest_ids"))
    assert only_entry(report).status.value == "changed"
    book = load(path)
    assert stamp_metas(path) == 1
    assert book.scan_stamp.status == book.validation_status  # the verdict AFTER the fixes
    assert book.stamp_stale is False


def test_redact_stamp_fingerprint_follows_later_content_changes(tmp_path, redact_env):
    path = make_epub(str(tmp_path / "c.epub"), cover=False, toc=True)
    run([load(path)], redact_env, only("validate_fix", "cover"))
    book = load(path)
    assert book.cover_bytes  # the cover step added a file after the verdict...
    assert book.scan_stamp is not None and book.stamp_stale is False  # ...and the stamp still matches


def test_redact_with_unsaved_stamp_only_book_is_not_refused(tmp_path, redact_env):
    path = make_epub(str(tmp_path / "s.epub"), dup_ids=True)
    book = load(path)
    book.check_and_stamp()
    report = run([book], redact_env, only("validate_fix", "dedupe_manifest_ids"))
    assert only_entry(report).status.value == "changed"


def test_redact_leaves_a_book_with_a_current_stamp_alone(tmp_path, redact_env):
    path = make_epub(str(tmp_path / "t.epub"))
    first = load(path)
    first.check_and_stamp()
    first.save()
    before = open(path, "rb").read()
    report = run([load(path)], redact_env, only("validate_fix"))
    assert only_entry(report).status.value == "unchanged"
    assert open(path, "rb").read() == before


def test_validation_dialog_is_an_explicit_check_that_stamps(epub, qtbot=None):
    from PyQt6.QtWidgets import QApplication
    from gui.validation_dialog import ValidationDialog
    QApplication.instance() or QApplication([])
    book = load(epub)
    dialog = ValidationDialog([book])
    assert book.scan_stamp is not None and book.stamp_only_dirty
    assert dialog.table.item(0, 1).text().startswith("OK · ")
