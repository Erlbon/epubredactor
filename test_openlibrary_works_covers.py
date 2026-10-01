"""Tests for (1) the optional WORKS dump in core/openlibrary_import.py (editions
with no authors of their own take their work's) and (2) the cover paths that
use the local database's Open Library cover id: core/better_cover.py,
Find Better Covers, the Redact `cover` step and the local lookup dialog.
Synthetic fixtures only; every fetch is injected -- no network."""

import gzip
import os
import sqlite3
import sys
import urllib.error
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(__file__))

import pytest  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from core import better_cover  # noqa: E402
from core.better_cover import (  # noqa: E402
    IsbnCoverError,
    IsbnCoverLimitError,
    fetch_cover_by_id,
    fetch_cover_for_isbn,
)
from core.open_library_lookup import OpenLibraryCandidate  # noqa: E402
from core.openlibrary_import import BuildOptions, build_openlibrary_database, database_info  # noqa: E402
from core.openlibrary_local import search_by_isbn, open_database  # noqa: E402
from core.redact_steps import RedactEnv  # noqa: E402
from gui import app_settings  # noqa: E402
from redactor_common.core.dump_import import DumpImportError, ImportCancelled  # noqa: E402
from redactor_common.core.local_db import forget_cached  # noqa: E402
from redactor_common.core.pipeline import FileStatus  # noqa: E402
from test_openlibrary_import import author, edition, line, write_gz  # noqa: E402
from test_openlibrary_local import DUNE, HOBBIT, isbn13  # noqa: E402
from test_redact_steps import PNG, Trash, load, make_epub, only, only_entry, quiet_lookups, run  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)

ISBN_A, ISBN_B, ISBN_C, ISBN_D, ISBN_E = (isbn13(f"97800000000{n}") for n in range(5))


def work(n, authors, **extra):
    return line("/type/work", f"/works/OL{n}W", {"title": f"Work {n}", "authors": authors, **extra})


def credit(key):
    return {"author": {"key": f"/authors/{key}"}, "type": {"key": "/type/author_role"}}


@pytest.fixture
def dumps(tmp_path):
    editions = write_gz(tmp_path / "e.txt.gz", [
        edition(1, "No Authors Of Its Own", isbn13=[ISBN_A], lang="eng", works=[{"key": "/works/OL1W"}]),
        edition(2, "Has Its Own", isbn13=[ISBN_B], lang="eng", authors=["OL3A"], works=[{"key": "/works/OL1W"}]),
        edition(3, "Work Has None", isbn13=[ISBN_C], lang="eng", works=[{"key": "/works/OL2W"}]),
        edition(4, "No Work", isbn13=[ISBN_D], lang="eng"),
        edition(5, "Odd Work", isbn13=[ISBN_E], lang="eng", works=[{"key": "/works/OL4W"}]),
    ])
    authors = write_gz(tmp_path / "a.txt.gz", [
        author("OL1A", "Ada One"), author("OL2A", "Bob Two"), author("OL3A", "Cy Three"), author("OL9A", "Never Used"),
    ])
    works = write_gz(tmp_path / "w.txt.gz", [
        work(1, [credit("OL1A"), credit("OL2A")]),  # several authors
        work(2, []),  # a work without authors
        line("/type/work", "/works/OL3W", {"title": "no authors key at all"}),
        # real-shape surprises: every one of these must degrade, not crash
        work(4, [{"author": {"key": "/authors/OL2A"}}, {"author": 5}, {"type": {}}, None, "junk", {"key": "/authors/OL1A"}]),
        line("/type/work", "/works/OL5W", {"authors": "not a list"}),
    ])
    return editions, authors, works


def rows(path, sql, params=()):
    con = sqlite3.connect(path)
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


def build(dumps, tmp_path, with_works=True, **kwargs):
    dest = str(tmp_path / "w.db")
    summary = build_openlibrary_database(
        dumps[0], dest, dumps[1], BuildOptions(), works_path=dumps[2] if with_works else "", **kwargs)
    return dest, summary


def authors_of(path):
    return dict(rows(path, "select title, authors_text from editions"))


# --- works dump -------------------------------------------------------------------------------


def test_editions_without_authors_take_their_works(dumps, tmp_path):
    dest, summary = build(dumps, tmp_path)
    people = authors_of(dest)
    assert people["No Authors Of Its Own"] == "Ada One; Bob Two"  # a work with several authors, in order
    assert people["Has Its Own"] == "Cy Three"  # its own authors are kept, not replaced
    assert people["Work Has None"] == "" and people["No Work"] == ""
    assert people["Odd Work"] == "Bob Two; Ada One"  # the usable entries of an odd record, junk skipped
    assert summary.authors_from_works == 2 and summary.works_read == 2
    keys = dict(rows(dest, "select title, author_keys from editions"))
    assert keys["No Authors Of Its Own"] == "OL1A OL2A"
    assert dict(rows(dest, "select key, name from authors")) == {
        "OL1A": "Ada One", "OL2A": "Bob Two", "OL3A": "Cy Three"}  # names resolved for borrowed authors too
    info = database_info(dest)
    assert info["works_file"] == "w.txt.gz" and info["authors_from_works"] == "2"
    assert "taken from their work" in __import__("core.openlibrary_import", fromlist=["x"]).describe_database(dest)
    assert "got their authors from their work" in summary.describe()
    assert not [f for f in os.listdir(tmp_path) if f.endswith(".tmp")]


def test_without_a_works_file_the_feature_is_off(dumps, tmp_path):
    dest, summary = build(dumps, tmp_path, with_works=False)
    assert authors_of(dest)["No Authors Of Its Own"] == ""
    assert summary.authors_from_works == 0
    assert database_info(dest)["works_file"] == ""


def test_works_without_an_authors_dump_still_record_the_keys(dumps, tmp_path):
    dest = str(tmp_path / "nn.db")
    build_openlibrary_database(dumps[0], dest, "", works_path=dumps[2])
    assert rows(dest, "select authors_text, author_keys from editions where title = 'No Authors Of Its Own'") == [
        ("", "OL1A OL2A")]


def test_a_combined_dump_serves_as_the_works_source_too(dumps, tmp_path):
    def raw(path):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return handle.read().splitlines()

    combined = write_gz(tmp_path / "all.txt.gz", raw(dumps[0]) + raw(dumps[1]) + raw(dumps[2]))
    dest = str(tmp_path / "c.db")
    build_openlibrary_database(combined, dest, combined, works_path=combined)
    assert authors_of(dest)["No Authors Of Its Own"] == "Ada One; Bob Two"


def test_wrong_works_file_fails_loudly_and_cleans_up(dumps, tmp_path):
    dest = str(tmp_path / "x.db")
    with pytest.raises(DumpImportError, match="no work records"):
        build_openlibrary_database(dumps[0], dest, dumps[1], works_path=dumps[0])  # editions as works
    with pytest.raises(DumpImportError, match="Works dump not found"):
        build_openlibrary_database(dumps[0], dest, dumps[1], works_path=str(tmp_path / "nope.gz"))
    assert not [f for f in os.listdir(tmp_path) if f.startswith("x.db")]


def test_cancel_removes_the_works_temp_file(dumps, tmp_path):
    dest = str(tmp_path / "k.db")
    with pytest.raises(ImportCancelled):
        build_openlibrary_database(dumps[0], dest, dumps[1], works_path=dumps[2], cancelled=lambda: True)
    assert not [f for f in os.listdir(tmp_path) if f.startswith("k.db")]


def test_progress_with_three_sources_is_monotonic(dumps, tmp_path):
    seen = []
    build(dumps, tmp_path, progress=seen.append)
    assert seen[-1] == pytest.approx(1.0) and all(b >= a - 1e-9 for a, b in zip(seen, seen[1:]))


def test_the_dialog_has_an_optional_works_picker(dumps, tmp_path, monkeypatch):
    import gui.open_library_settings_dialog as module
    from PyQt6.QtWidgets import QMessageBox
    from gui.open_library_settings_dialog import OpenLibrarySettingsDialog

    dest = str(tmp_path / "d.db")
    app_settings.save_open_library_database(dest)
    dialog = OpenLibrarySettingsDialog()
    assert dialog.works_edit.text() == "" and "Optional" in dialog.works_edit.placeholderText()  # off by default
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    monkeypatch.setattr(module, "run_dump_import", lambda parent, title, label, work: work(lambda f: None, lambda: False))
    dialog.editions_edit.setText(dumps[0])
    dialog.authors_edit.setText(dumps[1])
    dialog.works_edit.setText(dumps[2])
    dialog.build_button.click()
    assert authors_of(dest)["No Authors Of Its Own"] == "Ada One; Bob Two"
    dialog.accept()
    assert app_settings.load_open_library_works_dump() == dumps[2]


def test_works_dump_path_is_machine_specific_in_the_settings_bundle(dumps):
    from gui.settings_adapter import EpubSettingsAdapter
    from redactor_common.core import settings_bundle as sb

    adapter = EpubSettingsAdapter(["filename"])
    app_settings.save_open_library_works_dump(dumps[2])
    assert dumps[2] not in sb.dump_bundle(sb.build_bundle(adapter, sb.default_selection(adapter)))
    bundle = sb.build_bundle(adapter, {"folders"})
    assert bundle.sections["folders"].items["open_library_works_dump"] == dumps[2]
    app_settings.save_open_library_works_dump("")
    sb.apply_bundle(adapter, bundle, {"folders"})
    assert app_settings.load_open_library_works_dump() == dumps[2]


# --- covers: fetch_cover_by_id / fetch_cover_for_isbn ----------------------------------------


def http_error(code):
    return urllib.error.HTTPError("u", code, "x", {}, None)


def recorder(result=b"IMG"):
    urls = []

    def get(url):
        urls.append(url)
        if isinstance(result, Exception):
            raise result
        return result
    return get, urls


def test_cover_by_id_builds_the_covers_url():
    get, urls = recorder()
    assert fetch_cover_by_id(8231, get) == b"IMG"
    assert urls == ["https://covers.openlibrary.org/b/id/8231-L.jpg"]
    assert OpenLibraryCandidate(cover_id=8231).image_url() == urls[0]  # one URL shape for both paths


@pytest.mark.parametrize("bad", [0, -1, None, "5", True])
def test_cover_by_id_skips_ids_that_are_not_positive_ints(bad):
    get, urls = recorder()
    assert fetch_cover_by_id(bad, get) is None and urls == []


def test_cover_by_id_error_policy_matches_the_isbn_lookup():
    assert fetch_cover_by_id(5, recorder(http_error(404))[0]) is None
    with pytest.raises(IsbnCoverLimitError):
        fetch_cover_by_id(5, recorder(http_error(429))[0])
    with pytest.raises(IsbnCoverError):
        fetch_cover_by_id(5, recorder(http_error(500))[0])
    with pytest.raises(IsbnCoverError, match="couldn't be reached"):
        fetch_cover_by_id(5, recorder(urllib.error.URLError("down"))[0])
    assert fetch_cover_by_id(5, recorder(b"")[0]) is None  # an empty body is "none"


def test_the_size_cap_applies_to_the_id_fetch_too(monkeypatch):
    seen = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n):
            return b"x" * n

    def fake_urlopen(request, timeout=None):
        seen.append(request.full_url)
        return Response()

    monkeypatch.setattr(better_cover.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(IsbnCoverError, match="unreasonably large"):
        fetch_cover_by_id(77)  # the real _default_get, with the network call faked
    assert seen == ["https://covers.openlibrary.org/b/id/77-L.jpg"]


@pytest.fixture
def covered(tmp_path):
    editions = write_gz(tmp_path / "ce.txt.gz", [
        edition(1, "Dune", isbn13=[DUNE], lang="eng", covers=[-1, 4242]),
        edition(2, "The Hobbit", isbn13=[HOBBIT], lang="eng"),  # no cover id
    ])
    path = str(tmp_path / "cover.db")
    build_openlibrary_database(editions, path)
    yield path
    forget_cached(path)


def test_the_local_candidate_carries_the_cover_id(covered):
    assert search_by_isbn(open_database(covered), DUNE)[0].cover_id == 4242
    assert search_by_isbn(open_database(covered), HOBBIT)[0].cover_id == 0


def test_a_local_match_fetches_its_cover_by_id_not_by_isbn(covered):
    get, urls = recorder()
    assert fetch_cover_for_isbn(DUNE, covered, get) == b"IMG"
    assert urls == ["https://covers.openlibrary.org/b/id/4242-L.jpg"]


def test_without_a_cover_id_or_database_it_is_the_isbn_lookup(covered, tmp_path):
    for path, isbn in ((covered, HOBBIT), ("", DUNE), (str(tmp_path / "gone.db"), DUNE)):
        get, urls = recorder()
        fetch_cover_for_isbn(isbn, path, get)
        assert len(urls) == 1 and "/b/isbn/" in urls[0], (path, urls)


def test_a_failed_id_fetch_falls_back_to_the_isbn_but_the_limit_is_raised(covered):
    calls = []

    def get(url):
        calls.append(url)
        if "/b/id/" in url:
            raise http_error(404)
        return b"BY ISBN"

    assert fetch_cover_for_isbn(DUNE, covered, get) == b"BY ISBN"
    assert "/b/id/" in calls[0] and "/b/isbn/" in calls[1]
    with pytest.raises(IsbnCoverLimitError):
        fetch_cover_for_isbn(DUNE, covered, recorder(http_error(429))[0])


def test_find_better_covers_uses_the_local_cover_id(tmp_path, monkeypatch, covered):
    from gui import better_cover_dialog
    from gui.main_window import MainWindow
    from test_cover_quality import _epub, _jpeg

    app_settings.save_open_library_database(covered)
    books = [_epub(tmp_path / "dune.epub", DUNE, _jpeg(300, 450), "Dune")]
    big = _jpeg(1200, 1800)
    fetched = []
    monkeypatch.setattr(better_cover, "fetch_cover_by_id", lambda cover_id, get=None: fetched.append(cover_id) or big)
    monkeypatch.setattr(better_cover, "fetch_cover_by_isbn", lambda *a, **k: pytest.fail("looked up by ISBN"))
    offered = []
    monkeypatch.setattr(better_cover_dialog.BetterCoverDialog, "exec",
                        lambda dialog: offered.append(dialog.table.rowCount()) or dialog.DialogCode.Rejected)
    window = MainWindow()
    window._load_paths(books)
    window.open_find_better_covers_dialog()
    assert fetched == [4242] and offered == [1]  # only a LARGER cover is offered, as before


# --- covers: the Redact `cover` step ------------------------------------------------------------


def cover_env(trash, olpath, **lookups):
    calls = {"id": [], "isbn": []}

    def by_id(cover_id):
        calls["id"].append(cover_id)
        return lookups.get("data", PNG)

    def by_isbn(isbn):
        calls["isbn"].append(isbn)
        return None

    env = RedactEnv(trash=trash, openlibrary_local=olpath,
                    lookups=quiet_lookups(cover_by_id=by_id, cover_by_isbn=by_isbn))
    return env, calls


@pytest.fixture
def trash(tmp_path):
    return Trash(str(tmp_path) + "-bin")


def test_redact_cover_step_fetches_the_local_matchs_cover_by_id(tmp_path, trash, covered):
    path = make_epub(str(tmp_path / "c.epub"), isbn=DUNE, cover=False)
    env, calls = cover_env(trash, covered)
    report = run([load(path)], env, only("cover"))
    assert only_entry(report).status is FileStatus.CHANGED
    assert calls == {"id": [4242], "isbn": []}  # no second search
    assert load(path).cover_bytes == PNG
    assert "Open Library (local database) match (cover id 4242)" in report.to_text() or "auto-applied at 95%" in report.to_text()


def test_redact_cover_step_falls_back_when_the_match_has_no_usable_cover(tmp_path, trash, covered):
    no_id = make_epub(str(tmp_path / "n.epub"), isbn=HOBBIT, cover=False)  # in the database, no cover id
    env, calls = cover_env(trash, covered)
    run([load(no_id)], env, only("cover"))
    assert calls["id"] == [] and calls["isbn"] == [HOBBIT]
    junk = make_epub(str(tmp_path / "j.epub"), isbn=DUNE, cover=False)  # a cover id, but the bytes aren't an image
    env, calls = cover_env(trash, covered, data=b"<html>not an image</html>")
    run([load(junk)], env, only("cover"))
    assert calls["id"] == [4242] and calls["isbn"] == [DUNE]  # rejected, then the ordinary ISBN path


def test_redact_cover_step_respects_the_drm_guard_and_existing_covers(tmp_path, trash, covered, monkeypatch):
    from core.epub_metadata import EpubBook

    has_cover = make_epub(str(tmp_path / "h.epub"), isbn=DUNE, cover=True)
    env, calls = cover_env(trash, covered)
    run([load(has_cover)], env, only("cover"))
    assert calls == {"id": [], "isbn": []}  # a good cover is never replaced
    drm = make_epub(str(tmp_path / "d.epub"), isbn=DUNE, cover=False)
    monkeypatch.setattr(EpubBook, "cover_is_encrypted", lambda self: True)
    env, calls = cover_env(trash, covered)
    report = run([load(drm)], env, only("cover"))
    assert calls == {"id": [], "isbn": []} and "DRM-encrypted" in report.to_text()
    assert load(drm).cover_bytes is None
    # and the editor's own guard: set_cover stages nothing on an encrypted cover
    assert load(drm).set_cover(PNG, "image/png") is False


def test_redact_cover_step_without_a_local_database_is_unchanged(tmp_path, trash):
    path = make_epub(str(tmp_path / "p.epub"), isbn=DUNE, cover=False)
    calls = {"isbn": []}
    env = RedactEnv(trash=trash, lookups=quiet_lookups(
        cover_by_id=lambda i: pytest.fail("no database"),
        cover_by_isbn=lambda isbn: calls["isbn"].append(isbn) or None))
    run([load(path)], env, only("cover"))
    assert calls["isbn"] == [DUNE]


# --- covers: the local lookup dialog -------------------------------------------------------------


def _dialog(path, fetch):
    from gui.open_library_dialog import OpenLibraryDialog

    dialog = OpenLibraryDialog.__new__(OpenLibraryDialog)
    dialog.local_path = path
    dialog.cover_fetch = fetch
    return dialog


def _book(isbn):
    meta = SimpleNamespace(title="", authors_str="", isbn=isbn, pub_year="")
    return SimpleNamespace(metadata=meta, path="b.epub", cover_bytes=None)


def test_dialog_shows_the_cover_of_a_local_match(covered):
    urls = []
    result = _dialog(covered, lambda url: urls.append(url) or PNG)._search_one(_book(DUNE), {})
    assert result.fields["title"] == "Dune" and result.cover_bytes == PNG
    assert urls == ["https://covers.openlibrary.org/b/id/4242-L.jpg"]


def test_dialog_cover_problems_are_silent_and_cover_id_zero_fetches_nothing(covered):
    def fail(url):
        raise urllib.error.URLError("offline")

    for fetch in (fail, lambda url: b"not an image", lambda url: b""):
        result = _dialog(covered, fetch)._search_one(_book(DUNE), {})
        assert result.found and result.cover_bytes is None
    result = _dialog(covered, lambda url: pytest.fail("cover id 0"))._search_one(_book(HOBBIT), {})
    assert result.found and result.cover_bytes is None


def test_dialog_applies_covers_like_the_online_one():
    from gui.open_library_dialog import OpenLibraryDialog

    dialog = OpenLibraryDialog.__new__(OpenLibraryDialog)
    ok = SimpleNamespace(cover_bytes=PNG)
    none = SimpleNamespace(cover_bytes=None)
    dialog.accepted_rows = lambda: {0: ok, 1: none}
    assert dialog.accepted_covers() == {0: (PNG, "image/jpeg")}  # unchanged: rows with a downloaded cover only
