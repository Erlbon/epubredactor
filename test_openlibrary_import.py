"""Tests for core/openlibrary_import.py (the Open Library dump -> SQLite recipe)
and the Tools > Open Library Database... settings dialog. Only small SYNTHETIC
gzip fixtures in the verified dump format (5 tab-separated columns: type, key,
revision, last_modified, JSON) -- the real dump is never read."""

import gzip
import json
import os
import sqlite3
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(__file__))

import pytest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from core import openlibrary_import as oli  # noqa: E402
from core.openlibrary_import import (  # noqa: E402
    BuildOptions,
    build_openlibrary_database,
    database_info,
    describe_database,
    edition_isbns,
    edition_languages,
    year_of,
)
from gui import app_settings  # noqa: E402
from redactor_common.core.dump_import import DumpImportError, ImportCancelled  # noqa: E402
from redactor_common.core.local_db import LocalDatabase, LocalDatabaseError, fts_query  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)

DUNE13, DUNE10 = "9780441172719", "0441172717"
HOBBIT13, HOBBIT10 = "9780261102217", "0261102214"
PRIDE10 = "0141439513"  # ISBN-10 only
PRIDE13 = "9780141439518"


def line(kind, key, data):
    return f"{kind}\t{key}\t1\t2020-01-01T00:00:00.000000\t{json.dumps(data)}"


def write_gz(path, lines):
    with gzip.open(path, "wt", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")
    return str(path)


def edition(n, title, *, isbn13=None, isbn10=None, authors=(), lang=None, **extra):
    data = {"title": title, "publishers": ["Ace"], "publish_date": "March 1990"}
    if isbn13 is not None:
        data["isbn_13"] = isbn13 if isinstance(isbn13, list) else [isbn13]
    if isbn10 is not None:
        data["isbn_10"] = isbn10 if isinstance(isbn10, list) else [isbn10]
    if authors:
        data["authors"] = [{"key": f"/authors/{a}"} for a in authors]
    if lang:
        data["languages"] = [{"key": f"/languages/{lang}"}]
    data.update(extra)
    return line("/type/edition", f"/books/OL{n}M", data)


def author(key, name, **extra):
    return line("/type/author", f"/authors/{key}", {"name": name, **extra})


@pytest.fixture
def dumps(tmp_path):
    editions = write_gz(tmp_path / "ol_dump_editions.txt.gz", [
        edition(1, "Dune", isbn13=[DUNE13], isbn10=[DUNE10], authors=["OL1A"], lang="eng",
                number_of_pages=412, covers=[-1, 8231], subjects=["Science fiction", "Deserts", "Arrakis", "Fremen", "x"],
                works=[{"key": "/works/OL9W"}], subtitle="Book one"),
        edition(2, "The Hobbit", isbn13=["978-0-261-10221-7"], authors=["OL2A", "OL404A"], lang="eng"),
        edition(3, "Pride and Prejudice", isbn10=["0-14-143951-3"], authors=["OL3A"], lang="eng"),
        edition(4, "No ISBN at all", authors=["OL1A"], lang="eng"),
        edition(5, "Bad checksum", isbn13=["9780441172710"], isbn10=["0441172710"], lang="eng"),
        edition(6, "Der Herr der Ringe", isbn13=["9783608939811"], authors=["OL2A"], lang="ger"),
        edition(7, "Les Miserables", isbn13=["9782070409228"], lang="fre"),
        edition(8, "Norsk bok", isbn13=["9788202300111"], lang="nob"),
        edition(9, "Japanese book", isbn13=["9784061385184"], lang="jpn"),
        edition(10, "Languageless", isbn13=["9780306406157"]),
        edition(11, "Dune again", isbn13=[DUNE13, "9780593099322"], lang="eng"),
        line("/type/edition", "/books/OL12M", {"title": "weird", "isbn_13": "notalist", "authors": 7, "covers": ["x"],
                                                 "languages": "eng", "number_of_pages": "many"}),
    ])
    authors = write_gz(tmp_path / "ol_dump_authors.txt.gz", [
        author("OL1A", "Frank Herbert", birth_date="1920"),
        author("OL2A", "J. R. R. Tolkien"),
        author("OL3A", "Jane Austen"),
        author("OL5A", "Unused Author"),
        line("/type/author", "/authors/OL6A", {"alternate_names": ["x"]}),  # no name at all
    ])
    return editions, authors


def rows(db_path, sql, params=()):
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


def build(dumps, tmp_path, options=None, **kwargs):
    dest = str(tmp_path / "ol.db")
    summary = build_openlibrary_database(dumps[0], dest, dumps[1], options, **kwargs)
    return dest, summary


# --- field helpers --------------------------------------------------------------------------


def test_year_of_free_text_dates():
    assert [year_of(t) for t in ("1998", "March 1998", "1998-03-04", "c1998", "[1998?]", "Mar 4, 1998")] == [1998] * 6
    assert year_of("") is None and year_of("sometime") is None and year_of("12345678") is None


def test_isbn_normalisation_and_conversion():
    assert edition_isbns({"isbn_13": ["978-0-441-17271-9"]}) == (DUNE13, DUNE10, [])
    assert edition_isbns({"isbn_10": ["0-14-143951-3"]}) == (PRIDE13, PRIDE10, [])
    assert edition_isbns({"isbn_10": ["0-8044-2957-x"]})[0] == "9780804429573"  # lower-case X check digit
    assert edition_isbns({"isbn_13": ["9780441172710"], "isbn_10": ["0441172710"]}) == ("", "", [])
    # a 979 ISBN has no ISBN-10
    assert edition_isbns({"isbn_13": ["9791032305591"]}) == ("9791032305591", "", [])
    assert edition_isbns({"isbn_13": [DUNE13, HOBBIT13]})[2] == [HOBBIT13]
    assert edition_isbns({"isbn_13": "junk", "isbn_10": [5, None]}) == ("", "", [])


def test_edition_languages_map_to_iso_639_1():
    assert edition_languages({"languages": [{"key": "/languages/ger"}, {"key": "/languages/eng"}]}) == ["de", "en"]
    assert edition_languages({"languages": [{"key": "/languages/nob"}]}) == ["nb"]
    assert edition_languages({"languages": [{"key": "/languages/und"}]}) == []
    assert edition_languages({"languages": [{"key": "/languages/xyz"}]}) == ["xyz"]  # unknown: Open Library's code
    assert edition_languages({"languages": "eng"}) == [] and edition_languages({}) == []


# --- the build ------------------------------------------------------------------------------


def test_build_keeps_only_valid_isbn_editions_in_the_chosen_languages(dumps, tmp_path):
    dest, summary = build(dumps, tmp_path)
    titles = [r[0] for r in rows(dest, "select title from editions order by id")]
    assert titles == ["Dune", "The Hobbit", "Pride and Prejudice", "Der Herr der Ringe", "Les Miserables",
                      "Norsk bok", "Languageless", "Dune again"]
    assert summary.editions == 8 and summary.editions_seen == 12
    assert summary.skipped_language == 1  # the Japanese one
    assert summary.skipped_no_isbn == 3  # no ISBN, bad checksum, and the malformed record
    assert not os.path.exists(dest + ".partial") and not os.path.exists(dest + ".authors.tmp")


def test_isbn_columns_and_extra_isbns(dumps, tmp_path):
    dest, _ = build(dumps, tmp_path)
    by_title = {r[0]: r[1:] for r in rows(dest, "select title, isbn13, isbn10, key, id from editions")}
    assert by_title["Dune"][:2] == (DUNE13, DUNE10)
    assert by_title["The Hobbit"][:2] == (HOBBIT13, HOBBIT10)  # hyphenated input, isbn10 derived
    assert by_title["Pride and Prejudice"][:2] == (PRIDE13, PRIDE10)  # ISBN-10-only edition
    assert by_title["Dune"][2] == "OL1M"
    extra = rows(dest, "select isbn13 from extra_isbns where edition_id = ?", (by_title["Dune again"][3],))
    assert extra == [("9780593099322",)]
    # several editions may share an ISBN
    assert len(rows(dest, "select 1 from editions where isbn13 = ?", (DUNE13,))) == 2


def test_other_fields(dumps, tmp_path):
    dest, _ = build(dumps, tmp_path)
    row = rows(dest, "select subtitle, publishers, publish_date_raw, year, language, pages, cover_id, subjects, "
                     "work_key from editions where title = 'Dune'")[0]
    assert row == ("Book one", "Ace", "March 1990", 1990, "en", 412, 8231, "Science fiction; Deserts; Arrakis; Fremen",
                   "OL9W")
    languages = dict(rows(dest, "select title, language from editions"))
    assert languages["Norsk bok"] == "nb" and languages["Der Herr der Ringe"] == "de" and languages["Languageless"] == ""


def test_language_options(dumps, tmp_path):
    dest, _ = build(dumps, tmp_path, BuildOptions(languages=("de",), include_unknown_language=False))
    assert [r[0] for r in rows(dest, "select title from editions")] == ["Der Herr der Ringe"]
    dest, summary = build(dumps, tmp_path, BuildOptions(languages=("no",)))
    assert sorted(r[0] for r in rows(dest, "select title from editions")) == ["Languageless", "Norsk bok"]
    dest, summary = build(dumps, tmp_path, BuildOptions(all_languages=True))
    assert "Japanese book" in [r[0] for r in rows(dest, "select title from editions")]
    assert summary.skipped_language == 0
    with pytest.raises(DumpImportError, match="No languages"):
        build(dumps, tmp_path, BuildOptions(languages=(), include_unknown_language=False))


def test_author_names_are_joined_from_the_authors_dump(dumps, tmp_path):
    dest, summary = build(dumps, tmp_path)
    people = {r[0]: r[1:] for r in rows(dest, "select title, authors_text, author_keys from editions")}
    assert people["Dune"] == ("Frank Herbert", "OL1A")
    assert people["The Hobbit"] == ("J. R. R. Tolkien", "OL2A OL404A")  # OL404A isn't in the authors dump: degrades
    assert people["Les Miserables"] == ("", "")
    # only authors some kept edition uses are stored
    assert dict(rows(dest, "select key, name from authors")) == {
        "OL1A": "Frank Herbert", "OL2A": "J. R. R. Tolkien", "OL3A": "Jane Austen"}
    assert summary.authors == 3 and summary.authors_read == 4


def test_without_an_authors_dump_editions_still_build(dumps, tmp_path):
    dest = str(tmp_path / "noauthors.db")
    summary = build_openlibrary_database(dumps[0], dest)
    assert summary.editions == 8
    assert rows(dest, "select count(*) from editions where authors_text != ''") == [(0,)]
    assert rows(dest, "select count(*) from authors") == [(0,)]
    assert rows(dest, "select author_keys from editions where title = 'Dune'") == [("OL1A",)]


def test_a_combined_all_types_dump_serves_both_pickers(dumps, tmp_path):
    def raw(path):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return handle.read().splitlines()

    combined = write_gz(tmp_path / "ol_dump.txt.gz", raw(dumps[0]) + raw(dumps[1]) + [
        line("/type/work", "/works/OL9W", {"title": "Dune", "authors": [{"author": {"key": "/authors/OL1A"}}]}),
        line("/type/redirect", "/books/OL99M", {"location": "/books/OL1M"}),
    ])
    dest = str(tmp_path / "combined.db")
    summary = build_openlibrary_database(combined, dest, combined)
    assert summary.editions == 8 and summary.authors == 3
    assert rows(dest, "select authors_text from editions where title = 'Dune'") == [("Frank Herbert",)]


def test_full_text_index_is_built_and_queryable(dumps, tmp_path):
    dest, _ = build(dumps, tmp_path)
    db = LocalDatabase(dest, ("editions",))
    try:
        assert db.has_table("editions_fts")
        hits = fts_query(db, "editions_fts", "dune", key="isbn13", from_table="editions")
        assert set(hits) == {DUNE13}
        assert set(fts_query(db, "editions_fts", "tolkien", key="title", from_table="editions")) == {
            "The Hobbit", "Der Herr der Ringe"}
        assert fts_query(db, "editions_fts", "herbert", columns=["authors_text"], key="title",
                         from_table="editions").count("Dune") == 1
        assert fts_query(db, "editions_fts", "hob", key="title", from_table="editions") == ["The Hobbit"]  # prefix
    finally:
        db.close()


def test_import_info_and_status_text(dumps, tmp_path):
    dest, summary = build(dumps, tmp_path)
    info = database_info(dest)
    assert info["recipe"] == oli.RECIPE and info["source"] == "Open Library"
    assert info["editions_file"] == "ol_dump_editions.txt.gz" and info["authors_file"] == "ol_dump_authors.txt.gz"
    assert info["rows.editions"] == "8" and info["rows.authors"] == "3"
    assert "English" in info["languages"] and int(info["size.file"]) == os.path.getsize(dest)
    text = describe_database(dest)
    assert "ol_dump_editions.txt.gz" in text and "8 editions" in text and "3 authors" in text
    assert "editions kept out of 12 read" in summary.describe()


def test_a_foreign_database_is_rejected_by_the_status_check(tmp_path):
    other = str(tmp_path / "other.db")
    con = sqlite3.connect(other)
    con.execute("create table editions (id integer)")
    con.commit()
    con.close()
    with pytest.raises(LocalDatabaseError):
        describe_database(other)
    with pytest.raises(LocalDatabaseError):
        describe_database(str(tmp_path / "missing.db"))


def test_progress_reaches_one_and_never_goes_back_much(dumps, tmp_path):
    seen = []
    build(dumps, tmp_path, progress=seen.append)
    assert seen and seen[-1] == pytest.approx(1.0) and max(seen) <= 1.0 + 1e-9
    assert all(b >= a - 1e-9 for a, b in zip(seen, seen[1:]))


# --- cancel, bad input, wrong format --------------------------------------------------------


def test_cancel_removes_partial_and_temp_files_and_keeps_the_old_database(dumps, tmp_path):
    dest, _ = build(dumps, tmp_path)
    before = open(dest, "rb").read()
    calls = []

    def cancelled():
        calls.append(1)
        return len(calls) > 3  # lets the authors pass finish, stops during the editions pass

    big = write_gz(tmp_path / "big.txt.gz", [
        edition(i, f"Book {i}", isbn13=[f"978{i:09d}"[:12] + "0"], lang="eng") for i in range(1, 3000)
    ] + [edition(1, "x", isbn13=[DUNE13])])
    with pytest.raises(ImportCancelled):
        build_openlibrary_database(big, dest, dumps[1], cancelled=cancelled)
    assert not os.path.exists(dest + ".partial") and not os.path.exists(dest + ".authors.tmp")
    assert open(dest, "rb").read() == before  # the previous build is untouched


def test_cancel_with_no_previous_database_leaves_nothing(dumps, tmp_path):
    dest = str(tmp_path / "fresh.db")
    with pytest.raises(ImportCancelled):
        build_openlibrary_database(dumps[0], dest, dumps[1], cancelled=lambda: True)
    assert os.listdir(tmp_path).count("fresh.db") == 0
    assert not [f for f in os.listdir(tmp_path) if f.startswith("fresh.db")]


def test_bad_lines_are_skipped_and_counted(tmp_path):
    lines = [edition(i, f"Book {i}", isbn13=[DUNE13], lang="eng") for i in range(1, 40)]
    lines.insert(5, "/type/edition\t/books/OL500M\t1\tdate\t{this is not json")
    lines.insert(9, "just one column")
    lines.insert(20, "/type/edition\t/books/OL501M\t1\tdate\t[1, 2]")  # JSON, but not an object
    editions = write_gz(tmp_path / "e.txt.gz", lines)
    dest = str(tmp_path / "bad.db")
    summary = build_openlibrary_database(editions, dest)
    assert summary.editions == 39
    assert summary.bad_lines == 3
    assert database_info(dest)["bad_lines"] == "3"
    assert "3 unreadable lines" in summary.describe()


def test_wrong_format_fails_loudly(dumps, tmp_path):
    dest = str(tmp_path / "x.db")
    # the authors dump given as the editions dump
    with pytest.raises(DumpImportError, match="no edition records"):
        build_openlibrary_database(dumps[1], dest)
    # the editions dump given as the authors dump
    with pytest.raises(DumpImportError, match="no author records"):
        build_openlibrary_database(dumps[0], dest, dumps[0])
    # not tab-separated at all
    plain = write_gz(tmp_path / "plain.txt.gz", [f"just some text {i}" for i in range(100)])
    with pytest.raises(DumpImportError):
        build_openlibrary_database(plain, dest)
    # right columns, but the JSON column is mostly garbage
    garbage = write_gz(tmp_path / "garbage.txt.gz", [f"/type/edition\t/books/OL{i}M\t1\td\t<<{i}>>" for i in range(100)])
    with pytest.raises(DumpImportError, match="unreadable JSON"):
        build_openlibrary_database(garbage, dest)
    # missing files
    with pytest.raises(DumpImportError, match="not found"):
        build_openlibrary_database(str(tmp_path / "nope.gz"), dest)
    with pytest.raises(DumpImportError, match="Authors dump not found"):
        build_openlibrary_database(dumps[0], dest, str(tmp_path / "nope.gz"))
    assert not os.path.exists(dest) and not os.path.exists(dest + ".partial")


def test_nothing_kept_is_an_error_not_an_empty_database(tmp_path):
    editions = write_gz(tmp_path / "e.txt.gz", [edition(i, "No isbn", lang="eng") for i in range(1, 20)])
    with pytest.raises(DumpImportError, match="No editions were kept"):
        build_openlibrary_database(editions, str(tmp_path / "empty.db"))
    assert not os.path.exists(str(tmp_path / "empty.db"))


def test_an_unusual_real_sample_degrades_instead_of_crashing(tmp_path):
    odd = [
        {"title": ["a", "list"], "isbn_13": [DUNE13], "authors": [{"key": 5}, "OL1A", None, {"author": {"key": "/authors/OL1A"}}],
         "covers": [True, 0, 55], "publishers": [1, "Real House", ""], "subjects": "not a list",
         "languages": [{"key": "/languages/eng"}, None], "number_of_pages": True, "works": "none"},
        {"isbn_13": [DUNE13], "title": None, "publish_date": 1990, "languages": [{"nokey": 1}]},
    ]
    editions = write_gz(tmp_path / "o.txt.gz", [line("/type/edition", f"/books/OL{i}M", d) for i, d in enumerate(odd, 1)])
    authors = write_gz(tmp_path / "a.txt.gz", [
        line("/type/author", "/authors/OL1A", {"name": ["not", "a", "string"], "personal_name": "Frank H."}),
        line("/type/author", "/authors/OL2A", {"name": "Fine Name"}),
    ])
    dest = str(tmp_path / "odd.db")
    build_openlibrary_database(editions, dest, authors)
    first = rows(dest, "select title, authors_text, cover_id, publishers, subjects, pages, work_key from editions "
                       "order by id")
    assert first[0] == ("", "Frank H.", 55, "Real House", "", None, "")
    assert first[1][0] == "" and first[1][2] is None


# --- settings storage + dialog --------------------------------------------------------------


def test_build_options_round_trip_in_settings():
    defaults = app_settings.load_open_library_build_options()
    assert defaults.languages == oli.DEFAULT_LANGUAGE_IDS and not defaults.all_languages
    assert defaults.include_unknown_language
    app_settings.save_open_library_build_options(BuildOptions(languages=("sv", "da"), all_languages=True,
                                                              include_unknown_language=False))
    loaded = app_settings.load_open_library_build_options()
    assert loaded == BuildOptions(languages=("sv", "da"), all_languages=True, include_unknown_language=False)
    app_settings.save_open_library_build_options(BuildOptions(languages=()))
    assert app_settings.load_open_library_build_options().languages == ()


def test_dialog_shows_status_builds_and_saves(dumps, tmp_path, monkeypatch):
    import gui.open_library_settings_dialog as module
    from gui.open_library_settings_dialog import OpenLibrarySettingsDialog

    dest = str(tmp_path / "dialog.db")
    app_settings.save_open_library_database(dest)
    dialog = OpenLibrarySettingsDialog()
    assert "Not built yet" in dialog.status_label.text()
    assert dialog.build_button is not None and dialog.build_button.text() == "Build Database…"
    assert dialog.build_options().languages == oli.DEFAULT_LANGUAGE_IDS  # the user's library languages

    # Build without the editions dump: told, nothing built.
    dialog.build_button.click()
    assert not os.path.exists(dest)

    messages = []
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda p, t, text, *a: messages.append(text)))
    monkeypatch.setattr(module, "run_dump_import", lambda parent, title, label, work: work(lambda f: None, lambda: False))
    dialog.editions_edit.setText(dumps[0])
    dialog.authors_edit.setText(dumps[1])
    dialog.language_boxes["de"].setChecked(False)
    dialog.build_button.click()
    assert os.path.exists(dest)
    assert "editions kept" in messages[-1]
    assert "Built from ol_dump_editions.txt.gz" in dialog.status_label.text()
    assert "Der Herr der Ringe" not in [r[0] for r in rows(dest, "select title from editions")]  # German unticked

    dialog.accept()
    assert app_settings.load_open_library_database() == dest
    assert app_settings.load_open_library_sources() == (dumps[0], dumps[1])
    assert "de" not in app_settings.load_open_library_build_options().languages


def test_dialog_reports_a_failed_build_and_a_cancel(dumps, tmp_path, monkeypatch):
    import gui.open_library_settings_dialog as module
    from gui.open_library_settings_dialog import OpenLibrarySettingsDialog

    dest = str(tmp_path / "failed.db")
    app_settings.save_open_library_database(dest)
    dialog = OpenLibrarySettingsDialog()
    dialog.editions_edit.setText(dumps[1])  # the wrong dump
    warnings = []
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda p, t, text, *a: warnings.append(text)))
    monkeypatch.setattr(module, "run_dump_import", lambda parent, title, label, work: work(lambda f: None, lambda: False))
    dialog.build_button.click()
    assert warnings and "no edition records" in warnings[0]
    assert not os.path.exists(dest)

    monkeypatch.setattr(module, "run_dump_import", lambda *a: None)  # the user cancelled
    dialog.editions_edit.setText(dumps[0])
    dialog.build_button.click()
    assert not os.path.exists(dest)


def test_dialog_all_languages_disables_the_language_boxes():
    from gui.open_library_settings_dialog import OpenLibrarySettingsDialog

    dialog = OpenLibrarySettingsDialog()
    dialog.all_languages.setChecked(True)
    assert not any(box.isEnabled() for box in dialog.language_boxes.values())
    assert dialog.build_options().all_languages


def test_the_tools_menu_has_the_entry():
    import gui.main_window as mw
    from redactor_common.gui.standard_menus import get_action_registry

    registry = get_action_registry(mw.MainWindow())
    assert "open_library_settings" in registry and registry.path_of("open_library_settings")
