"""Tests for the Redact recipe (core/redact_steps.py) on redactor_common's
pipeline engine: each step with mocked lookups, recipe round trip, and
end-to-end runs on synthetic EPUBs with a fake Recycle Bin (original in
the bin, file on disk valid, report text, needs-review routing, and the
DRM / load-error / unsaved / edited-elsewhere skips)."""

import base64
import os
import shutil
import sys
import zipfile

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from core.epub_metadata import EpubBook  # noqa: E402
from core.google_books_lookup import GoogleBooksCandidate  # noqa: E402
from core.open_library_lookup import OpenLibraryCandidate  # noqa: E402
from core.redact_steps import (  # noqa: E402
    EpubCtx,
    Lookups,
    RedactEnv,
    build_catalogue,
    recipe_for_run,
    recipe_from_setting,
    recipe_to_setting,
    run_catalogue,
    save_finalize,
)
from redactor_common.core.pipeline import FileStatus, Recipe, run_recipe  # noqa: E402
from redactor_common.core.rename_log import RenameLog  # noqa: E402

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)
GEN_COVER = b"\x89PNG\r\n\x1a\n-generated-"
ENGLISH = (
    "It was the best of times and it was the worst of times, and the people of the town were in the "
    "habit of going to the market with their children and their dogs, because there was nothing else "
    "that they could do when the weather was fine and the sun was out. "
) * 6
CONTAINER = (
    '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
    '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
    "</rootfiles></container>"
)


def make_epub(path, *, title="Test Book", authors=("Jane Doe",), language="en", isbn="", publisher="",
              description="", toc=True, cover=True, dup_ids=False, missing_item=False, bad_guide=False,
              orphan=False, remote_item=False, pages=None, encrypted=False):
    pages = pages or [("ch1.xhtml", "<h1>Chapter One</h1><p>Hello.</p>"), ("ch2.xhtml", "<h1>Chapter Two</h1><p>More.</p>")]
    md = ['<dc:identifier id="BookId">urn:uuid:1234-abcd</dc:identifier>', f"<dc:title>{title}</dc:title>"]
    md += [f'<dc:creator opf:role="aut">{a}</dc:creator>' for a in authors]
    if language:
        md.append(f"<dc:language>{language}</dc:language>")
    if isbn:
        md.append(f'<dc:identifier opf:scheme="ISBN">{isbn}</dc:identifier>')
    if publisher:
        md.append(f"<dc:publisher>{publisher}</dc:publisher>")
    if description:
        md.append(f"<dc:description>{description}</dc:description>")
    if cover:
        md.append('<meta name="cover" content="cover"/>')
    items = [f'<item id="p{i}" href="{h}" media-type="application/xhtml+xml"/>' for i, (h, _b) in enumerate(pages)]
    spine = [f'<itemref idref="p{i}"/>' for i in range(len(pages))]
    if toc:
        items.append('<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>')
    if cover:
        items.append('<item id="cover" href="cover.png" media-type="image/png"/>')
    if dup_ids:
        items.append('<item id="p0" href="extra.xhtml" media-type="application/xhtml+xml"/>')
    if missing_item:
        items.append('<item id="gone" href="gone.xhtml" media-type="application/xhtml+xml"/>')
        spine.append('<itemref idref="gone"/>')
    if remote_item:
        items.append('<item id="remote" href="http://example.com/x.mp3" media-type="audio/mpeg"/>')
    guide = '<guide><reference type="toc" title="T" href="nothere.xhtml"/></guide>' if bad_guide else ""
    opf = (
        '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="BookId">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">'
        + "".join(md) + "</metadata><manifest>" + "".join(items) + "</manifest>"
        f'<spine{" toc=" + chr(34) + "ncx" + chr(34) if toc else ""}>' + "".join(spine) + "</spine>" + guide + "</package>"
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER)
        zf.writestr("OEBPS/content.opf", opf)
        for href, body in pages:
            zf.writestr(f"OEBPS/{href}", f"<html><head></head><body>{body}</body></html>")
        if toc:
            zf.writestr("OEBPS/toc.ncx", "<ncx/>")
        if cover:
            zf.writestr("OEBPS/cover.png", PNG)
        if dup_ids:
            zf.writestr("OEBPS/extra.xhtml", "<html><body><p>x</p></body></html>")
        if orphan:
            zf.writestr("OEBPS/unused.css", "p{}")
        if encrypted:
            zf.writestr(
                "META-INF/encryption.xml",
                '<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                '<EncryptedData xmlns="http://www.w3.org/2001/04/xmlenc#">'
                '<EncryptionMethod Algorithm="http://www.w3.org/2001/04/xmlenc#aes128-cbc"/>'
                '<CipherData><CipherReference URI="OEBPS/ch1.xhtml"/></CipherData></EncryptedData></encryption>',
            )
    return path


class Trash:
    """A fake Recycle Bin: moves the file into a folder and remembers it."""

    def __init__(self, folder):
        self.folder = str(folder)
        os.makedirs(self.folder, exist_ok=True)
        self.trashed = []

    def __call__(self, path):
        dest = os.path.join(self.folder, f"{len(self.trashed)}-{os.path.basename(path)}")
        shutil.move(path, dest)
        self.trashed.append((path, dest))


def quiet_lookups(**overrides):
    base = dict(
        google_by_isbn=lambda isbn: [], google_by_title=lambda title, authors="": [],
        openlibrary_by_isbn=lambda isbn: [], openlibrary_by_title=lambda title, author="": [],
        cover_by_isbn=lambda isbn: None, download_google_cover=lambda cand: b"",
    )
    base.update(overrides)
    return Lookups(**base)


@pytest.fixture
def trash(tmp_path):
    return Trash(str(tmp_path) + "-bin")  # beside tmp_path, not inside it


@pytest.fixture
def env(trash):
    return RedactEnv(trash=trash, lookups=quiet_lookups(), make_cover=lambda *a: GEN_COVER)


def only(*keys, options=None, threshold=0.9):
    """A recipe with just these steps on (on top of the internal guard)."""
    cat = build_catalogue()
    return Recipe(
        order=[s.key for s in cat], enabled={s.key: s.key in keys for s in cat},
        options=options or {}, confidence_threshold=threshold,
    )


def run(books, env, recipe=None):
    env.begin()
    recipe = recipe if recipe is not None else Recipe.default_for(build_catalogue())
    report = run_recipe(
        books, recipe_for_run(recipe), run_catalogue(), lambda b: EpubCtx(b, env),
        describe=lambda b: os.path.basename(b.path), finalize=save_finalize, finalize_label="Save",
    )
    env.flush_log()
    return report


def load(path):
    return EpubBook(str(path))


def only_entry(report):
    assert len(report.entries) == 1
    return report.entries[0]


# --- end to end ---------------------------------------------------------------


def test_default_recipe_repairs_a_damaged_book_in_place(tmp_path, env, trash):
    path = make_epub(
        str(tmp_path / "bad.epub"), authors=("Ann &amp; Bob",), dup_ids=True, missing_item=True, bad_guide=True,
        description="&lt;p&gt;Hi&lt;/p&gt;", remote_item=True,
    )
    # the description really holds markup (escaped once in the XML = literal tags)
    book = load(path)
    assert book.metadata.description == "<p>Hi</p>"
    assert {"DUPLICATE_MANIFEST_ID", "MANIFEST_FILE_MISSING", "AUTHORS_AMPERSAND"} <= {
        i.code for i in book.validation_issues}

    report = run([book], env, only("validate_fix", "dedupe_manifest_ids", "rebuild_manifest",
                                   "repair_navigation", "strip_description_html"))

    entry = only_entry(report)
    assert entry.status is FileStatus.CHANGED, report.to_text()
    fixed = load(path)
    codes = {i.code for i in fixed.validation_issues}
    assert not codes & {"DUPLICATE_MANIFEST_ID", "AUTHORS_AMPERSAND"}
    # gone.xhtml was dropped; only the remote item (which the validator also calls "missing") remains
    assert [h for _i, h in fixed.find_missing_manifest_files()] == ["http://example.com/x.mp3"]
    assert fixed.metadata.authors == ["Ann", "Bob"]
    assert fixed.metadata.description == "Hi"
    assert fixed.find_broken_guide_references() == []
    with zipfile.ZipFile(path) as zf:
        assert zf.testzip() is None and zf.namelist()[0] == "mimetype"
        assert b"http://example.com/x.mp3" in zf.read("OEBPS/content.opf")  # remote items are not "missing"
    # the original is in the bin, and only the new file is left beside it
    assert len(trash.trashed) == 1
    assert os.path.exists(trash.trashed[0][1])
    assert os.path.exists(trash.trashed[0][1]) and sorted(os.listdir(tmp_path)) == ["bad.epub"]
    text = report.to_text()
    assert "Save: saved in place" in text and "CHANGES" in text
    assert env.touched == {book: path}


def test_a_clean_book_is_left_alone(tmp_path, env, trash):
    path = make_epub(str(tmp_path / "ok.epub"), description="Plain text.", publisher="P", isbn="9783161484100")
    steps = only("validate_fix", "dedupe_manifest_ids", "rebuild_manifest",
                 "repair_navigation", "strip_description_html", "cover")
    before = (os.path.getmtime(path), open(path, "rb").read())
    report = run([load(path)], env, steps)
    assert only_entry(report).status is FileStatus.UNCHANGED
    assert trash.trashed == [] and env.touched == {}
    assert (os.path.getmtime(path), open(path, "rb").read()) == before


def test_orphan_removal_is_off_unless_asked(tmp_path, env):
    path = make_epub(str(tmp_path / "o.epub"), orphan=True)
    run([load(path)], env, only("repair_navigation"))
    assert "OEBPS/unused.css" in zipfile.ZipFile(path).namelist()
    path2 = make_epub(str(tmp_path / "o2.epub"), orphan=True)
    run([load(path2)], env, only("repair_navigation", options={"repair_navigation": {"remove_orphans": True}}))
    assert "OEBPS/unused.css" not in zipfile.ZipFile(path2).namelist()
    assert load(path2).load_error is None


# --- skips ----------------------------------------------------------------------


def test_load_error_unsaved_and_drm_books_are_skipped_with_notes(tmp_path, env, trash):
    garbage = tmp_path / "garbage.epub"
    garbage.write_bytes(b"not a zip")
    unsaved = make_epub(str(tmp_path / "unsaved.epub"), dup_ids=True)
    drm = make_epub(str(tmp_path / "drm.epub"), dup_ids=True, encrypted=True)
    books = [load(garbage), load(unsaved), load(drm)]
    books[1].apply_metadata({"title": "Edited in the list"})
    sizes = {p: os.path.getsize(p) for p in (str(garbage), unsaved, drm)}

    report = run(books, env)

    assert [e.status for e in report.entries] == [FileStatus.SKIPPED] * 3
    text = report.to_text()
    assert "SKIPPED" in text and "could not be loaded" in text
    assert "unsaved edits" in text and "DRM-protected" in text
    assert trash.trashed == [] and env.touched == {}
    assert {p: os.path.getsize(p) for p in sizes} == sizes  # nothing rewritten
    assert books[1].dirty  # the in-memory edit is still there


def test_a_book_edited_elsewhere_during_the_run_is_skipped(tmp_path, env, trash):
    path = make_epub(str(tmp_path / "e.epub"), dup_ids=True)

    def make_context(book):
        ctx = EpubCtx(book, env)
        with zipfile.ZipFile(book.path, "a") as zf:  # someone else touches the file
            zf.writestr("OEBPS/other.txt", "changed elsewhere")
        return ctx

    env.begin()
    report = run_recipe([load(path)], recipe_for_run(Recipe.default_for(build_catalogue())), run_catalogue(),
                        make_context, finalize=save_finalize, finalize_label="Save",
                        describe=lambda b: os.path.basename(b.path))
    entry = only_entry(report)
    assert entry.status is FileStatus.SKIPPED
    assert entry.applied == [] and "changed by something else" in report.to_text()
    assert trash.trashed == []
    assert "OEBPS/other.txt" in zipfile.ZipFile(path).namelist()
    assert sorted(os.listdir(tmp_path)) == ["e.epub"]  # no temp file left


def test_a_failed_verification_leaves_the_original_and_withdraws_the_changes(tmp_path, env, trash, monkeypatch):
    path = make_epub(str(tmp_path / "v.epub"), dup_ids=True)
    original = open(path, "rb").read()

    def boom(self, new_path, expected):
        raise ValueError("boom")

    monkeypatch.setattr(EpubCtx, "_verify", boom)
    report = run([load(path)], env, only("dedupe_manifest_ids"))
    entry = only_entry(report)
    assert entry.status is FileStatus.FAILED
    assert entry.applied == []  # nothing was saved, so nothing is listed as changed
    assert "boom" in report.to_text() and "not saved" in report.to_text()
    assert open(path, "rb").read() == original and trash.trashed == []
    assert sorted(os.listdir(tmp_path)) == ["v.epub"]


def test_a_new_error_in_the_written_file_is_caught_by_verification(tmp_path, env, trash, monkeypatch):
    path = make_epub(str(tmp_path / "n.epub"), dup_ids=True)
    original = open(path, "rb").read()
    real_save = EpubBook.save

    def corrupting_save(self, output_path=None):
        real_save(self, output_path)
        with zipfile.ZipFile(output_path) as zf:  # drop a chapter the OPF still lists
            keep = {n: zf.read(n) for n in zf.namelist() if n != "OEBPS/ch1.xhtml"}
        with zipfile.ZipFile(output_path, "w") as zf:
            zf.writestr(zipfile.ZipInfo("mimetype"), keep.pop("mimetype"), zipfile.ZIP_STORED)
            for n, data in keep.items():
                zf.writestr(n, data)

    monkeypatch.setattr(EpubBook, "save", corrupting_save)
    report = run([load(path)], env, only("dedupe_manifest_ids"))
    assert only_entry(report).status is FileStatus.FAILED
    assert "lost 1 file" in report.to_text()
    assert open(path, "rb").read() == original


# --- guesses: needs review vs auto-apply ----------------------------------------------


def test_a_table_of_contents_from_headings_is_applied(tmp_path, env):
    path = make_epub(str(tmp_path / "t.epub"), toc=False)
    assert any(i.code == "NO_TOC" for i in load(path).validation_issues)
    report = run([load(path)], env, only("generate_toc"))
    assert only_entry(report).status is FileStatus.CHANGED
    assert "auto-applied at 95%" in report.to_text()
    assert not any(i.code == "NO_TOC" for i in load(path).validation_issues)


def test_a_section_n_table_of_contents_goes_to_needs_review(tmp_path, env, trash):
    pages = [("a.xhtml", "<p>no heading here</p>"), ("b.xhtml", "<p>none here either</p>")]
    path = make_epub(str(tmp_path / "s.epub"), toc=False, pages=pages)
    original = open(path, "rb").read()
    report = run([load(path)], env, only("generate_toc"))
    entry = only_entry(report)
    assert entry.status is FileStatus.NEEDS_REVIEW
    assert entry.review[0].confidence == pytest.approx(0.3)
    assert "NEEDS REVIEW" in report.to_text() and "Section 1" in report.to_text()
    assert open(path, "rb").read() == original and trash.trashed == []  # never applied


def test_language_is_a_suggestion_with_its_confidence(tmp_path, env):
    pages = [("a.xhtml", f"<p>{ENGLISH}</p>")]
    path = make_epub(str(tmp_path / "l.epub"), language="", pages=pages)
    low = run([load(path)], env, only("language", threshold=1.0))
    assert only_entry(low).status is FileStatus.NEEDS_REVIEW
    assert load(path).metadata.language == ""
    high = run([load(path)], env, only("language", threshold=0.0))
    assert only_entry(high).status is FileStatus.CHANGED, high.to_text()
    assert load(path).metadata.language == "en"


def test_language_is_not_touched_when_present(tmp_path, env):
    path = make_epub(str(tmp_path / "l2.epub"), language="de", pages=[("a.xhtml", f"<p>{ENGLISH}</p>")])
    assert only_entry(run([load(path)], env, only("language", threshold=0.0))).status is FileStatus.UNCHANGED


def test_front_matter_isbn_is_applied_and_only_into_empty_fields(tmp_path, env):
    front = "<p>First published 2001 by Some House. ISBN 978-3-16-148410-0</p><p>" + ENGLISH + "</p>"
    path = make_epub(str(tmp_path / "f.epub"), pages=[("a.xhtml", front)], publisher="Keeper Press")
    report = run([load(path)], env, only("scan_isbn", "scan_publisher", "scan_year", "scan_series"))
    meta = load(path).metadata
    assert meta.isbn == "9783161484100"
    assert meta.publisher == "Keeper Press"  # already had one: never overwritten
    assert "ISBN = " in report.to_text()


# --- online lookups -----------------------------------------------------------------------


def gb(**kw):
    base = dict(title="Test Book", authors_str="Jane Doe", publisher="Online House", pub_year="1999",
                isbn13="9783161484100", tags_str="Fiction", language="en", description="<p>From the web.</p>")
    base.update(kw)
    return GoogleBooksCandidate(**base)


def test_isbn_match_fills_only_empty_fields_at_95_percent(tmp_path, trash):
    path = make_epub(str(tmp_path / "i.epub"), isbn="9783161484100", publisher="Mine", language="")
    env = RedactEnv(trash=trash, lookups=quiet_lookups(google_by_isbn=lambda isbn: [gb()]))
    report = run([load(path)], env, only("metadata_lookup"))
    assert only_entry(report).status is FileStatus.CHANGED
    meta = load(path).metadata
    assert meta.publisher == "Mine"  # had a value
    assert meta.title == "Test Book" and meta.authors == ["Jane Doe"]
    assert (meta.pub_year, meta.tags, meta.language, meta.description) == ("1999", ["Fiction"], "en", "From the web.")
    assert "auto-applied at 95%" in report.to_text()


def test_isbn_falls_back_to_open_library(tmp_path, trash):
    path = make_epub(str(tmp_path / "o.epub"), isbn="9783161484100")
    cand = OpenLibraryCandidate(title="Test Book", publisher="OL House", pub_year="2000", isbn="9783161484100")
    env = RedactEnv(trash=trash, lookups=quiet_lookups(openlibrary_by_isbn=lambda isbn: [cand]))
    run([load(path)], env, only("metadata_lookup"))
    assert load(path).metadata.publisher == "OL House"


def test_a_title_and_author_match_is_only_suggested(tmp_path, trash):
    path = make_epub(str(tmp_path / "t.epub"))
    env = RedactEnv(trash=trash, lookups=quiet_lookups(google_by_title=lambda t, a="": [gb()]))
    original = open(path, "rb").read()
    report = run([load(path)], env, only("metadata_lookup"))
    entry = only_entry(report)
    assert entry.status is FileStatus.NEEDS_REVIEW and entry.review[0].confidence == pytest.approx(0.6)
    assert "Online House" in report.to_text()
    assert open(path, "rb").read() == original


def test_a_different_title_or_author_is_not_even_suggested(tmp_path, trash):
    path = make_epub(str(tmp_path / "d.epub"))
    wrong = [gb(title="Another Book"), gb(authors_str="Somebody Else")]
    env = RedactEnv(trash=trash, lookups=quiet_lookups(google_by_title=lambda t, a="": wrong))
    assert only_entry(run([load(path)], env, only("metadata_lookup"))).status is FileStatus.UNCHANGED


def test_a_rate_limit_stops_that_service_for_the_run_and_is_noted(tmp_path, trash):
    from core.google_books_lookup import GoogleBooksLookupError

    calls = []

    def limited(isbn):
        calls.append(isbn)
        raise GoogleBooksLookupError("Google Books is rate-limiting requests right now (HTTP 429)")

    a = make_epub(str(tmp_path / "a.epub"), isbn="9783161484100", title="A")
    b = make_epub(str(tmp_path / "b.epub"), isbn="9780306406157", title="B")
    env = RedactEnv(trash=trash, lookups=quiet_lookups(google_by_isbn=limited))
    report = run([load(a), load(b)], env, only("metadata_lookup"))
    assert len(calls) == 1  # the second book did not ask again
    assert "Google Books" in env.notes_text()
    assert all(e.status is FileStatus.UNCHANGED for e in report.entries)


# --- covers -------------------------------------------------------------------------------


def test_missing_cover_is_fetched_by_isbn(tmp_path, trash):
    path = make_epub(str(tmp_path / "c.epub"), cover=False, isbn="9783161484100")
    env = RedactEnv(trash=trash, lookups=quiet_lookups(cover_by_isbn=lambda isbn: PNG), make_cover=lambda *a: GEN_COVER)
    report = run([load(path)], env, only("cover"))
    assert only_entry(report).status is FileStatus.CHANGED
    assert load(path).cover_bytes == PNG
    assert "auto-applied at 95%" in report.to_text()


def test_missing_cover_without_a_match_is_generated(tmp_path, env):
    path = make_epub(str(tmp_path / "g.epub"), cover=False)
    report = run([load(path)], env, only("cover"))
    assert only_entry(report).status is FileStatus.CHANGED
    assert load(path).cover_bytes == GEN_COVER


def test_no_placeholder_when_the_cover_source_could_not_be_reached(tmp_path, trash):
    from core.better_cover import IsbnCoverError

    def down(isbn):
        raise IsbnCoverError("Open Library couldn't be reached")

    path = make_epub(str(tmp_path / "x.epub"), cover=False, isbn="9783161484100")
    env = RedactEnv(trash=trash, lookups=quiet_lookups(cover_by_isbn=down), make_cover=lambda *a: GEN_COVER)
    report = run([load(path)], env, only("cover"))
    assert only_entry(report).status is FileStatus.UNCHANGED
    assert "couldn't be reached" in report.to_text()


def test_a_real_cover_is_never_touched_and_a_junk_one_is_replaced_only_by_an_isbn_match(tmp_path, trash):
    good = make_epub(str(tmp_path / "good.epub"), isbn="9783161484100")
    calls = []
    env = RedactEnv(trash=trash, lookups=quiet_lookups(cover_by_isbn=lambda i: calls.append(i)),
                    make_cover=lambda *a: GEN_COVER)
    assert only_entry(run([load(good)], env, only("cover"))).status is FileStatus.UNCHANGED
    assert calls == []

    junk_path = make_epub(str(tmp_path / "junk.epub"), isbn="9783161484100")
    junk = load(junk_path)
    env.junk_hashes = {junk.cover_hash}
    report = run([junk], env, only("cover"))  # junk, nothing online: kept, never regenerated
    assert only_entry(report).status is FileStatus.UNCHANGED and "junk cover kept" in report.to_text()
    assert load(junk_path).cover_bytes == PNG

    env.lookups = quiet_lookups(cover_by_isbn=lambda i: GEN_COVER)
    run([load(junk_path)], env, only("cover"))
    assert load(junk_path).cover_bytes == GEN_COVER


# --- rename and move ------------------------------------------------------------------------


def test_rename_runs_after_the_save_and_is_logged_for_undo(tmp_path, env, trash):
    path = make_epub(str(tmp_path / "orig.epub"), dup_ids=True)
    env.rename_log = RenameLog(str(tmp_path / "log.json"))
    recipe = only("dedupe_manifest_ids", "rename", options={"rename": {"pattern": "%authors% - %title%"}})
    report = run([load(path)], env, recipe)
    new = str(tmp_path / "Jane Doe - Test Book.epub")
    assert os.path.exists(new) and not os.path.exists(path)
    assert not load(new).find_duplicate_manifest_ids()  # the save happened before the rename
    assert len(trash.trashed) == 1
    text = report.to_text()
    assert "Save: saved in place" in text and "renamed to Jane Doe - Test Book.epub" in text
    assert env.touched == {report.entries[0].item: new}
    assert env.rename_log.last_batch().renames == [(path, new)]
    env.rename_log.undo_last()
    assert os.path.exists(path) and not os.path.exists(new)


def test_rename_alone_with_nothing_else_to_save(tmp_path, env, trash):
    path = make_epub(str(tmp_path / "orig.epub"))
    report = run([load(path)], env, only("rename", options={"rename": {"pattern": "%title%"}}))
    assert os.path.exists(tmp_path / "Test Book.epub") and trash.trashed == []
    assert only_entry(report).status is FileStatus.CHANGED


def test_move_into_folders_uses_the_library_root_and_logs_the_created_folders(tmp_path, env, trash):
    root = tmp_path / "lib"
    root.mkdir()
    path = make_epub(str(tmp_path / "orig.epub"), dup_ids=True)
    env.library_root = str(root)
    env.rename_log = RenameLog(str(tmp_path / "log.json"))
    report = run([load(path)], env, only("dedupe_manifest_ids", "move_into_folders"))
    new = root / "Jane Doe" / "Test Book.epub"
    assert new.exists() and not os.path.exists(path)
    assert not load(str(new)).find_duplicate_manifest_ids()
    batch = env.rename_log.last_batch()
    assert batch.renames == [(path, str(new))] and batch.created_dirs
    assert "moved to Jane Doe/Test Book.epub" in report.to_text()
    env.rename_log.undo_last()
    assert os.path.exists(path)


def test_move_without_a_library_root_says_so(tmp_path, env):
    path = make_epub(str(tmp_path / "orig.epub"))
    report = run([load(path)], env, only("move_into_folders"))
    assert only_entry(report).status is FileStatus.UNCHANGED
    assert "no library root" in report.to_text() and os.path.exists(path)


def test_rename_and_move_do_not_run_for_a_book_that_could_not_be_saved(tmp_path, env, trash, monkeypatch):
    path = make_epub(str(tmp_path / "orig.epub"), dup_ids=True)
    env.library_root = str(tmp_path)
    monkeypatch.setattr(EpubCtx, "_verify", lambda self, p, e: (_ for _ in ()).throw(ValueError("no")))
    report = run([load(path)], env, only("dedupe_manifest_ids", "rename", options={"rename": {"pattern": "x"}}))
    assert only_entry(report).status is FileStatus.FAILED
    assert os.path.exists(path) and env.renames == []


# --- recipe ---------------------------------------------------------------------------------


def test_metadata_lookup_label_says_local_database_first_and_key_is_unchanged():
    step = next(s for s in build_catalogue() if s.key == "metadata_lookup")  # saved recipes use the key
    assert step.label == "Fill empty fields from lookups (local database first)"
    assert "online" not in step.label.lower() and "local" in step.description.lower()


def test_defaults_rename_on_only_with_a_pattern_and_move_off():
    plain = Recipe.default_for(build_catalogue())
    assert plain.enabled["rename"] is False and plain.enabled["move_into_folders"] is False
    with_pattern = Recipe.default_for(build_catalogue("%authors% - %title%"))
    assert with_pattern.enabled["rename"] is True
    assert with_pattern.options["rename"]["pattern"] == ""  # empty = follows the app's pattern (the fallback)
    assert with_pattern.enabled["repair_navigation"] and with_pattern.options["repair_navigation"]["remove_orphans"] is False
    assert plain.confidence_threshold == 0.9
    for key in ("validate_fix", "dedupe_manifest_ids", "rebuild_manifest", "generate_toc", "language",
                "strip_description_html", "cover", "metadata_lookup", "scan_isbn"):
        assert plain.enabled[key] is True, key


def test_recipe_round_trips_through_the_setting_and_the_settings_file():
    from gui import app_settings

    cat = build_catalogue("%title%")
    recipe = Recipe.default_for(cat)
    recipe.enabled["cover"] = False
    recipe.options["move_into_folders"]["pattern"] = "%authors%/%title%, with \"quotes\""
    recipe.confidence_threshold = 0.75
    text = recipe_to_setting(recipe)
    assert "\n" not in text
    assert recipe_from_setting(text, cat) == recipe
    app_settings.save_redact_recipe(text)
    assert recipe_from_setting(app_settings.load_redact_recipe(), cat) == recipe
    assert recipe_from_setting("", cat) == Recipe.default_for(cat)
    assert recipe_from_setting("{ not json", cat) == Recipe()  # garbage: the engine treats it as all-defaults


def test_the_guard_is_first_and_cannot_be_switched_off():
    recipe = Recipe.default_for(build_catalogue("%title%"))
    recipe.enabled["move_into_folders"] = True
    recipe.enabled["guard"] = False
    run_recipe_ = recipe_for_run(recipe)
    assert run_recipe_.order[0] == "guard" and "guard" not in run_recipe_.enabled
    steps = [s.key for s, _o in run_recipe_.resolve(run_catalogue())]
    assert steps[0] == "guard"
    assert steps[-2:] == ["rename", "move_into_folders"]  # pinned after everything else
    assert "guard" not in [s.key for s in build_catalogue()]  # not offered in the editor
