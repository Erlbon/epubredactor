"""Tests for core/isfdb_import.py (the recipe) and core/isfdb_local.py (the queries).

The fixture is a tiny synthetic mysqldump with the real table shapes (extra columns included, as in
the real ISFDB backup); the real 1.5 GB backup is never needed. Mini scenario:

  Dune (novel 100, series "Dune Chronicles" #1, 1965) has a Danish variant "Klit" (101, no series of its
  own, so it inherits), a print edition 1000 (1990), an ebook edition 1001 (2011) and a Danish edition
  1002. Millennium (102) is #1 of "Voyagers (Ben Bova)". A "double" publication 1006 prints novels 100
  and 102 under the title "Millennium". Title 105 is #2.5 of "Sub Series" (child of "Dune Chronicles").
"""

import os
import sys
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(__file__))

import pytest  # noqa: E402
from redactor_common.core.dump_import import DumpImportError  # noqa: E402
from redactor_common.core.isbn_norm import isbn10_check_digit, isbn13_check_digit  # noqa: E402
from redactor_common.core.pipeline import FileStatus  # noqa: E402

from core import isfdb_import, isfdb_local  # noqa: E402
from core.redact_steps import RedactEnv  # noqa: E402
from test_redact_steps import Trash, load, make_epub, only, only_entry, quiet_lookups, run  # noqa: E402
from core.isfdb_import import (
    build_isfdb_database,
    describe_database,
    edition_isbns,
    parse_date,
    series_number,
)
from core.isfdb_local import (
    IsfdbLocalError,
    best_edition,
    clean_series_name,
    local_search_by_isbn,
    local_search_by_title,
)


def isbn13(stem: str) -> str:
    return stem + isbn13_check_digit(stem)


PRINT_DUNE = isbn13("978044117271")
EBOOK_DUNE = isbn13("978147323300")
DANISH_DUNE = isbn13("978879001234")
ISBN10_ONLY = "034533968" + isbn10_check_digit("034533968")


def create(table: str, columns: list[str]) -> str:
    cols = ",\n".join(f"  `{c}` text" for c in columns)
    return f"DROP TABLE IF EXISTS `{table}`;\nCREATE TABLE `{table}` (\n{cols},\n  PRIMARY KEY (`{columns[0]}`)\n) ENGINE=MyISAM;\n"


def q(value) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def insert(table: str, rows: list[tuple]) -> str:
    return f"INSERT INTO `{table}` VALUES " + ",".join("(" + ",".join(q(v) for v in row) + ")" for row in rows) + ";\n"


def make_dump() -> str:
    parts = ["-- MySQL dump 10.13\n"]
    parts.append(create("languages", ["lang_id", "lang_name", "lang_code"]))
    parts.append(insert("languages", [(17, "English", "eng"), (15, "Danish", "dan")]))
    parts.append(create("authors", ["author_id", "author_canonical", "author_legalname"]))
    parts.append(insert("authors", [(1, "Frank Herbert", "Herbert, Frank"), (2, "Ben Bova", None), (3, "Anne Other", None)]))
    parts.append(create("series", ["series_id", "series_title", "series_parent", "series_type"]))
    parts.append(insert("series", [(10, "Dune Chronicles", None, 1), (11, "Voyagers (Ben Bova)", None, 1), (12, "Sub Series", 10, 1)]))
    parts.append(create("titles", ["title_id", "title_title", "series_id", "title_seriesnum", "title_seriesnum_2",
                                   "title_copyright", "title_ttype", "title_parent", "title_language", "title_views"]))
    parts.append(insert("titles", [
        (100, "Dune", 10, 1, None, "1965-08-00", "NOVEL", 0, 17, 5),
        (101, "Klit", None, None, None, "1980-00-00", "NOVEL", 100, 15, 1),
        (102, "Millennium", 11, 1, None, "1976-00-00", "NOVEL", 0, 17, 2),
        (103, "A Short Story", None, None, None, "1970-00-00", "SHORTFICTION", 0, 17, 1),
        (104, "Standalone Book", None, None, None, "8888-00-00", "NOVEL", 0, 17, 1),
        (105, "Sub Book", 12, 2, 5, "1999-00-00", "NOVEL", 0, 17, 1),
    ]))
    parts.append(create("canonical_author", ["ca_id", "title_id", "author_id", "ca_status"]))
    parts.append(insert("canonical_author", [(1, 100, 1, 1), (2, 102, 2, 1), (3, 104, 3, 1), (4, 100, 3, 2), (5, 105, 1, 1)]))
    parts.append(create("publishers", ["publisher_id", "publisher_name"]))
    parts.append(insert("publishers", [(1, "Ace Books"), (2, "Orion")]))
    parts.append(create("pubs", ["pub_id", "pub_title", "pub_year", "publisher_id", "pub_pages", "pub_ptype",
                                 "pub_ctype", "pub_isbn", "pub_price"]))
    parts.append(insert("pubs", [
        (1000, "Dune", "1990-09-00", 1, "533", "pb", "NOVEL", PRINT_DUNE, "$4.95"),
        (1001, "Dune", "2011-00-00", 2, "xii+592", "ebook", "NOVEL", EBOOK_DUNE, None),
        (1002, "Klit", "1981-05-14", 2, "400", "hc", "NOVEL", DANISH_DUNE, None),
        (1003, "Some Magazine", "1950-01-00", 1, "100", "digest", "MAGAZINE", isbn13("978000000000"), None),
        (1004, "Standalone Book", "8888-00-00", 1, "200", "pb", "NOVEL", None, None),
        (1005, "Millennium", "1977-00-00", 1, "300", "pb", "NOVEL", "0-" + ISBN10_ONLY[1:], None),
        (1006, "Millennium", "1980-00-00", 1, "800", "pb", "NOVEL", isbn13("978123456789"), None),
        (1007, "Junk", "1990-00-00", 1, "1", "pb", "NOVEL", "12345", None),
    ]))
    parts.append(create("pub_content", ["pubc_id", "pub_id", "title_id", "pubc_page"]))
    parts.append(insert("pub_content", [
        (1, 1000, 100, None), (2, 1001, 100, None), (3, 1002, 101, None), (4, 1005, 102, None),
        (5, 1006, 100, None), (6, 1006, 102, None), (7, 1004, 104, None), (8, 1000, 103, None),
    ]))
    parts.append(create("pub_authors", ["pa_id", "pub_id", "author_id"]))
    parts.append(insert("pub_authors", [(1, 1000, 1), (2, 1001, 1), (3, 1002, 1), (4, 1005, 2), (5, 1006, 1), (6, 1006, 2)]))
    return "".join(parts)


@pytest.fixture(autouse=True)
def small_dump_is_fine(monkeypatch):
    monkeypatch.setattr(isfdb_import, "_EXPECTED", {})


@pytest.fixture
def built(tmp_path):
    source = tmp_path / "backup-MySQL-55-2025-12-27.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("cygdrive/c/ISFDB/Backups/backup-MySQL-55-2025-12-27", make_dump())
    dest = str(tmp_path / "isfdb.db")
    summary = build_isfdb_database(str(source), dest)
    return dest, summary, tmp_path


# --- helpers ---------------------------------------------------------------------------------


def test_parse_date():
    assert parse_date("1990-09-00") == (1990, 9, None)
    assert parse_date("1981-05-14") == (1981, 5, 14)
    assert parse_date("1965-00-00") == (1965, None, None)
    assert parse_date("8888-00-00") == (None, None, None)  # unpublished
    assert parse_date("9999-00-00") == (None, None, None)  # forthcoming
    assert parse_date("0000-00-00") == (None, None, None)
    assert parse_date("date unknown") == (None, None, None)
    assert parse_date(None) == (None, None, None)


def test_series_number():
    assert series_number("3", None) == "3"
    assert series_number("5", "1") == "5.1"
    assert series_number(None, "1") == ""
    assert series_number("", "") == ""


def test_edition_isbns():
    assert edition_isbns(PRINT_DUNE)[0] == PRINT_DUNE
    assert edition_isbns("0-441-17271-7") == ("9780441172719", "0441172717")
    assert edition_isbns("12345") == ("", "")
    assert edition_isbns(None) == ("", "")
    assert edition_isbns("9780441172710") == ("", "")  # wrong check digit


def test_clean_series_name():
    assert clean_series_name("Voyagers (Ben Bova)", "Ben Bova") == "Voyagers"
    assert clean_series_name("Voyagers (Ben Bova)", "Ben Bova; Someone Else") == "Voyagers"
    assert clean_series_name("Star Wars (Legends)", "Timothy Zahn") == "Star Wars (Legends)"
    assert clean_series_name("Discworld", "Terry Pratchett") == "Discworld"
    assert clean_series_name("Voyagers (Ben Bova)", "") == "Voyagers (Ben Bova)"


# --- the build ---------------------------------------------------------------------------------


def test_build_summary_and_info(built):
    dest, summary, _ = built
    assert summary.works == 5 and summary.works_in_series == 4  # 100, 101 (inherited), 102, 105
    assert summary.editions == 5
    assert summary.skipped_no_isbn >= 2  # 1004 (none) and 1007 (invalid); the magazine is not a book at all
    assert "5 books" in summary.describe() and "5 editions" in summary.describe()
    text = describe_database(dest)
    assert "2025-12-27" in text and "5 books" in text


def test_works_inherit_series_year_authors_and_language_from_their_parent(built):
    import sqlite3

    dest, _, _ = built
    con = sqlite3.connect(dest)
    rows = {r[0]: r for r in con.execute("select id, title, authors_text, year, series, series_num, series_parent, language, variant_of from works")}
    assert set(rows) == {100, 101, 102, 104, 105}  # the short story is not a book
    assert rows[100][2:8] == ("Frank Herbert", 1965, "Dune Chronicles", "1", "", "en")
    assert rows[101] == (101, "Klit", "Frank Herbert", 1965, "Dune Chronicles", "1", "", "da", 100)
    assert rows[102][4] == "Voyagers (Ben Bova)" and rows[102][2] == "Ben Bova"
    assert rows[104][3] is None and rows[104][4] == ""  # 8888 = unpublished: no year
    assert rows[105][4:7] == ("Sub Series", "2.5", "Dune Chronicles")
    assert "Anne Other" not in rows[100][2]  # canonical_author status 2 is not read


def test_editions_have_valid_isbn_and_link_to_the_title_they_print(built):
    import sqlite3

    dest, _, _ = built
    con = sqlite3.connect(dest)
    rows = {r[0]: r for r in con.execute(
        "select id, work_id, isbn13, isbn10, publisher, year, month, day, binding, ctype, pages from editions")}
    assert set(rows) == {1000, 1001, 1002, 1005, 1006}
    assert rows[1000][:6] == (1000, 100, PRINT_DUNE, "0441172717", "Ace Books", 1990)
    assert rows[1001][8] == "ebook" and rows[1001][10] == 592  # "xii+592"
    assert rows[1002][1] == 101 and rows[1002][5:8] == (1981, 5, 14)
    assert rows[1005][2] == "978" + ISBN10_ONLY[:9] + isbn13_check_digit("978" + ISBN10_ONLY[:9])  # the ISBN-10 gets its 13
    assert rows[1006][1] == 102  # a double: the content title matching the publication's title wins


def test_no_account_tables_are_read(built):
    import sqlite3

    dest, _, _ = built
    con = sqlite3.connect(dest)
    tables = {r[0] for r in con.execute("select name from sqlite_master where type = 'table'")}
    assert not any("user" in t or "email" in t for t in tables)


def test_rebuild_replaces_and_cancel_leaves_nothing(built, tmp_path):
    dest, _, folder = built
    source = folder / "backup-MySQL-55-2025-12-27.zip"
    from redactor_common.core.dump_import import ImportCancelled

    with pytest.raises(ImportCancelled):
        build_isfdb_database(str(source), str(folder / "other.db"), cancelled=lambda: True)
    assert not (folder / "other.db").exists() and not (folder / "other.db.partial").exists()
    assert not (folder / "other.db.work.tmp").exists()


def test_a_dump_without_the_expected_tables_fails(tmp_path):
    bad = tmp_path / "wrong.sql"
    bad.write_text("CREATE TABLE `pubs` (\n  `pub_id` int\n) ENGINE=MyISAM;\n", encoding="utf-8")
    with pytest.raises(DumpImportError):
        build_isfdb_database(str(bad), str(tmp_path / "x.db"))


def test_a_small_dump_is_refused_as_the_wrong_file(tmp_path, monkeypatch):
    monkeypatch.setattr(isfdb_import, "_EXPECTED", {"pubs": 100_000})
    source = tmp_path / "mini.sql"
    source.write_text(make_dump(), encoding="utf-8")
    with pytest.raises(DumpImportError, match="full ISFDB backup"):
        build_isfdb_database(str(source), str(tmp_path / "x.db"))


# --- lookups --------------------------------------------------------------------------------------


def test_isbn_lookup_returns_series_and_edition_fields(built):
    dest, _, _ = built
    (c,) = local_search_by_isbn(dest, PRINT_DUNE)
    assert (c.title, c.authors_str, c.series, c.series_index) == ("Dune", "Frank Herbert", "Dune Chronicles", "1")
    assert (c.publisher, c.pub_year, c.isbn, c.language) == ("Ace Books", "1990", PRINT_DUNE, "en")
    assert c.pub_month == "9" and c.pub_day == ""
    assert c.as_dict()["series"] == "Dune Chronicles" and c.as_dict()["series_index"] == "1"


def test_isbn_lookup_by_isbn10_and_hyphens(built):
    dest, _, _ = built
    assert local_search_by_isbn(dest, "0-441-17271-7")[0].isbn == PRINT_DUNE
    assert local_search_by_isbn(dest, "0441172717")[0].title == "Dune"
    assert local_search_by_isbn(dest, "not an isbn") == []
    assert local_search_by_isbn(dest, isbn13("978555555555")) == []


def test_isbn_lookup_cleans_the_author_disambiguation_from_the_series(built):
    dest, _, _ = built
    (c,) = local_search_by_isbn(dest, isbn13("978" + ISBN10_ONLY[:9]))
    assert c.title == "Millennium" and c.series == "Voyagers" and c.series_index == "1"


def test_title_search_finds_the_series_and_prefers_the_ebook_isbn(built):
    dest, _, _ = built
    (c, *_) = local_search_by_title(dest, "Dune", "Frank Herbert", "2011")
    assert (c.series, c.series_index) == ("Dune Chronicles", "1")
    assert c.isbn == EBOOK_DUNE and c.binding == "ebook" and c.publisher == "Orion" and c.pub_year == "2011"
    assert c.score > 0.8


def test_title_search_leaves_the_isbn_empty_when_no_edition_is_safe(built):
    dest, _, _ = built
    (c, *_) = local_search_by_title(dest, "Millennium", "Ben Bova", "")
    assert c.series == "Voyagers" and c.isbn == "" and c.pub_year == "1976"  # no ebook, no year to match: no ISBN
    (c, *_) = local_search_by_title(dest, "Millennium", "Ben Bova", "1977")
    assert c.isbn.startswith("978") and c.pub_year == "1977"  # a print edition from the very year it already says


def test_title_search_finds_a_translated_title_with_the_parents_series(built):
    dest, _, _ = built
    (c, *_) = local_search_by_title(dest, "Klit", "Frank Herbert", "")
    assert (c.title, c.language, c.series, c.series_index) == ("Klit", "da", "Dune Chronicles", "1")


def test_title_search_needs_the_author_to_match_when_one_is_given(built):
    dest, _, _ = built
    assert local_search_by_title(dest, "Dune", "Nobody Atall", "") == []
    assert local_search_by_title(dest, "Dune", "Herbert", "")[0].title == "Dune"  # a surname alone works


def test_title_search_without_a_title_is_an_error(built):
    dest, _, _ = built
    with pytest.raises(IsfdbLocalError):
        local_search_by_title(dest, "  ")


def test_subtitle_is_ignored_when_searching(built):
    dest, _, _ = built
    assert local_search_by_title(dest, "Dune: Book One", "Frank Herbert", "")[0].title == "Dune"


def test_database_ready(built, tmp_path):
    dest, _, _ = built
    assert isfdb_local.database_ready(dest) == ""
    assert "no local ISFDB database" in isfdb_local.database_ready("")
    assert isfdb_local.database_ready(str(tmp_path / "missing.db"))


def test_best_edition_rules():
    ebook = (1, 5, "x", "", "t", "", "Orion", 2011, None, None, "ebook", "NOVEL", 1)
    ebook2 = (2, 5, "y", "", "t", "", "Orion", 2015, None, None, "ebook", "NOVEL", 1)
    print_1990 = (3, 5, "z", "", "t", "", "Ace", 1990, None, None, "pb", "NOVEL", 1)
    assert best_edition([print_1990, ebook, ebook2], "2014")[0] == 2  # the ebook closest in year
    assert best_edition([print_1990], "1990")[0] == 3
    assert best_edition([print_1990], "1991") is None
    assert best_edition([print_1990], "") is None
    assert best_edition([], "2000") is None


def test_best_edition_gives_no_isbn_when_publishers_tie():
    ace = (1, 5, "x", "", "t", "", "Ace", 2011, None, None, "ebook", "NOVEL", 1)
    orion = (2, 5, "y", "", "t", "", "Orion", 2011, None, None, "ebook", "NOVEL", 1)
    orion_again = (3, 5, "z", "", "t", "", "Orion", 2011, None, None, "ebook", "NOVEL", 1)
    assert best_edition([ace, orion], "") is None  # two publishers, no year to decide
    assert best_edition([ace, orion], "2011") is None
    assert best_edition([orion, orion_again], "")[0] == 2  # one publisher: the lowest id
    ace_old = (4, 5, "w", "", "t", "", "Ace", 2001, None, None, "ebook", "NOVEL", 1)
    assert best_edition([ace_old, orion], "2010")[0] == 2  # the year decides
    pb_us = (5, 5, "a", "", "t", "", "Ace", 1990, None, None, "pb", "NOVEL", 1)
    pb_uk = (6, 5, "b", "", "t", "", "NEL", 1990, None, None, "pb", "NOVEL", 1)
    assert best_edition([pb_us, pb_uk], "1990") is None


# --- the Redact step `metadata_lookup` -------------------------------------------------------------


@pytest.fixture
def trash(tmp_path):
    return Trash(str(tmp_path) + "-bin")


def isfdb_env(trash, dest, calls=None, **kwargs):
    """An env whose ISFDB lookups record their calls and whose online sources fail the test if asked."""
    calls = calls if calls is not None else []
    lookups = quiet_lookups(
        google_by_isbn=lambda isbn: calls.append("google_isbn") or [],
        google_by_title=lambda title, authors="": calls.append("google_title") or [],
        openlibrary_by_isbn=lambda isbn: calls.append("ol_isbn") or [],
        openlibrary_by_title=lambda title, author="": calls.append("ol_title") or [],
    )
    real_isbn, real_title = lookups.isfdb_by_isbn, lookups.isfdb_by_title
    lookups.isfdb_by_isbn = lambda *a: calls.append("isfdb_isbn") or real_isbn(*a)
    lookups.isfdb_by_title = lambda *a: calls.append("isfdb_title") or real_title(*a)
    return RedactEnv(trash=trash, lookups=lookups, isfdb_local=dest, **kwargs), calls


def set_series(path, series="", index=""):
    book = load(path)
    book.metadata.series, book.metadata.series_index = series, index
    book.dirty = True
    book.save()


def test_an_exact_isbn_fills_the_series_and_its_number(tmp_path, trash, built):
    dest, _, _ = built
    path = make_epub(str(tmp_path / "a.epub"), isbn=PRINT_DUNE, language="", authors=(), publisher="")
    env, calls = isfdb_env(trash, dest)
    report = run([load(path)], env, only("metadata_lookup"))
    assert only_entry(report).status is FileStatus.CHANGED
    meta = load(path).metadata
    assert (meta.series, meta.series_index) == ("Dune Chronicles", "1")
    assert (meta.authors, meta.publisher, meta.language) == (["Frank Herbert"], "Ace Books", "en")
    assert "Series = Dune Chronicles (auto-applied at 95%)" in report.to_text()
    assert "Series number = 1 (auto-applied at 95%)" in report.to_text()
    assert calls[0] == "isfdb_isbn"


def test_a_book_with_everything_but_a_series_asks_only_isfdb(tmp_path, trash, built):
    dest, _, _ = built
    path = make_epub(str(tmp_path / "full.epub"), title="Unknown Title", authors=("Some One",), language="en",
                     isbn=isbn13("978999999999"), publisher="P", description="D")
    book = load(path)
    book.metadata.pub_year, book.metadata.tags = "2001", ["Fiction"]
    book.dirty = True
    book.save()
    env, calls = isfdb_env(trash, dest)
    report = run([load(path)], env, only("metadata_lookup"))
    assert only_entry(report).status is FileStatus.UNCHANGED
    assert calls == ["isfdb_isbn"]  # series is the only blank, and no online source can supply it


def test_without_an_isfdb_database_a_series_only_blank_costs_no_online_call(tmp_path, trash):
    path = make_epub(str(tmp_path / "plain.epub"), isbn=isbn13("978999999999"), publisher="P", description="D")
    book = load(path)
    book.metadata.pub_year, book.metadata.tags = "2001", ["Fiction"]
    book.dirty = True
    book.save()
    env, calls = isfdb_env(trash, "")
    run([load(path)], env, only("metadata_lookup"))
    assert calls == []


def test_isfdb_is_asked_before_the_other_sources_and_they_fill_only_the_rest(tmp_path, trash, built):
    dest, _, _ = built
    path = make_epub(str(tmp_path / "b.epub"), isbn=PRINT_DUNE, language="", authors=(), publisher="")
    env, calls = isfdb_env(trash, dest)
    run([load(path)], env, only("metadata_lookup"))
    assert calls[0] == "isfdb_isbn"
    assert set(calls[1:]) <= {"google_isbn", "ol_isbn"}  # only for the genre/description ISFDB cannot give


def test_an_existing_series_is_never_replaced(tmp_path, trash, built):
    dest, _, _ = built
    path = make_epub(str(tmp_path / "keep.epub"), isbn=PRINT_DUNE)
    set_series(path, "My Own Series", "7")
    env, _ = isfdb_env(trash, dest)
    run([load(path)], env, only("metadata_lookup"))
    meta = load(path).metadata
    assert (meta.series, meta.series_index) == ("My Own Series", "7")


def test_a_missing_number_is_filled_only_for_the_same_series(tmp_path, trash, built):
    dest, _, _ = built
    same = make_epub(str(tmp_path / "same.epub"), isbn=PRINT_DUNE)
    set_series(same, "dune chronicles", "")
    other = make_epub(str(tmp_path / "other.epub"), isbn=PRINT_DUNE)
    set_series(other, "Something Else", "")
    env, _ = isfdb_env(trash, dest)
    run([load(same), load(other)], env, only("metadata_lookup"))
    assert load(same).metadata.series_index == "1"  # the match is that very series
    assert load(other).metadata.series_index == ""  # a number from a different series would be wrong


def test_a_title_and_author_match_goes_to_review_with_the_series(tmp_path, trash, built):
    dest, _, _ = built
    path = make_epub(str(tmp_path / "t.epub"), title="Dune", authors=("Frank Herbert",), language="en",
                     publisher="Orion", description="D")
    book = load(path)
    book.metadata.pub_year, book.metadata.tags = "2011", ["Fiction"]
    book.dirty = True
    book.save()
    env, calls = isfdb_env(trash, dest)
    original = open(path, "rb").read()
    report = run([load(path)], env, only("metadata_lookup"))
    entry = only_entry(report)
    assert entry.status is FileStatus.NEEDS_REVIEW and entry.review[0].confidence == pytest.approx(0.6)
    assert "Dune Chronicles" in report.to_text()
    assert open(path, "rb").read() == original and calls == ["isfdb_title"]


def test_the_translated_title_finds_the_series_too(tmp_path, trash, built):
    dest, _, _ = built
    path = make_epub(str(tmp_path / "klit.epub"), title="Klit", authors=("Frank Herbert",), language="da",
                     publisher="Orion", description="D")
    env, _ = isfdb_env(trash, dest)
    report = run([load(path)], env, only("metadata_lookup"))
    assert only_entry(report).status is FileStatus.NEEDS_REVIEW
    assert "Dune Chronicles" in report.to_text()


def test_a_missing_isfdb_database_is_a_note_not_a_failure(tmp_path, trash):
    path = make_epub(str(tmp_path / "m.epub"), isbn=PRINT_DUNE, publisher="")
    env, _ = isfdb_env(trash, str(tmp_path / "gone.db"))
    report = run([load(path)], env, only("metadata_lookup"))
    assert only_entry(report).status is FileStatus.UNCHANGED
    assert "ISFDB (local database) lookup failed" in report.to_text() and "not found" in report.to_text()


def test_the_step_description_mentions_isfdb_and_series():
    from core.redact_steps import build_catalogue

    step = next(s for s in build_catalogue() if s.key == "metadata_lookup")
    assert "ISFDB" in step.description and "series" in step.description


# --- dialogs, menus and settings ---------------------------------------------------------------------

from types import SimpleNamespace  # noqa: E402

from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from gui import app_settings  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)


def _dialog(path):
    from gui.isfdb_dialog import IsfdbDialog

    dialog = IsfdbDialog.__new__(IsfdbDialog)  # only the search logic is under test
    dialog.local_path = path
    return dialog


def _book(title="", authors=None, isbn="", year=""):
    meta = SimpleNamespace(title=title, authors_str="; ".join(authors or []), isbn=isbn, pub_year=year)
    return SimpleNamespace(metadata=meta, path="book.epub", cover_bytes=None)


def test_dialog_prefers_the_books_own_isbn_and_brings_the_series(built):
    dest, _, _ = built
    result = _dialog(dest)._search_one(_book("Wrong Title", ["Nobody"], isbn=PRINT_DUNE), {})
    assert result.fields["title"] == "Dune" and result.fields["series"] == "Dune Chronicles"
    assert result.fields["series_index"] == "1" and result.cover_bytes is None


def test_dialog_falls_back_to_title_author_and_honours_a_typed_correction(built):
    dest, _, _ = built
    dialog = _dialog(dest)
    assert dialog._search_one(_book("Dune", ["Frank Herbert"]), {}).fields["series"] == "Dune Chronicles"
    result = dialog._search_one(_book("x", isbn=PRINT_DUNE), {"title": "Klit", "authors": "Frank Herbert"})
    assert result.fields["language"] == "da"  # the typed text wins over the book's ISBN
    assert dialog._search_one(_book("", isbn=""), {}).error == "no title set -- can't search"
    assert not dialog._search_one(_book("Nothing Like It", ["A"]), {}).found


def test_dialog_reports_a_missing_database_as_a_row_error(tmp_path):
    assert "not found" in _dialog(str(tmp_path / "gone.db"))._search_one(_book("Dune"), {}).error


def test_look_up_menu_has_the_isfdb_entry_with_a_unique_mnemonic():
    import gui.main_window as mw
    from redactor_common.gui.menu_lint import lint_menu_bar
    from redactor_common.gui.standard_menus import get_action_registry

    window = mw.MainWindow()
    registry = get_action_registry(window)
    assert registry["import_isfdb_local"].text() == "&ISFDB (Local Database)…"
    assert registry["isfdb_settings"].text() == "&ISFDB Database…"
    assert lint_menu_bar(window) == []


def test_isfdb_lookup_without_a_database_offers_the_settings_dialog(monkeypatch, tmp_path):
    import gui.main_window as mw

    window = mw.MainWindow()
    asked, opened = [], []
    app_settings.save_isfdb_database("")
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: asked.append(a[2]) or QMessageBox.StandardButton.No))
    monkeypatch.setattr(window, "open_isfdb_settings_dialog", lambda: opened.append(1))
    monkeypatch.setattr(mw, "IsfdbDialog", lambda *a, **k: pytest.fail("no dialog without a database"))
    window.open_isfdb_dialog()
    assert asked and "Tools > ISFDB Database" in asked[0] and not opened
    app_settings.save_isfdb_database(str(tmp_path / "gone.db"))  # a file that doesn't exist counts as not set up
    window.open_isfdb_dialog()
    assert len(asked) == 2
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    window.open_isfdb_dialog()
    assert opened == [1]


def test_isfdb_lookup_opens_the_dialog_on_the_database(monkeypatch, built):
    import gui.main_window as mw

    dest, _, _ = built
    window = mw.MainWindow()
    window.books = [SimpleNamespace(path="a.epub")]
    monkeypatch.setattr(window, "_selection_or_all_books", lambda: window.books)
    app_settings.save_isfdb_database(dest)
    seen = []

    class FakeDialog:
        class DialogCode:
            Accepted = 1

        def __init__(self, books, parent=None, local_path=""):
            seen.append((books, local_path))

        def exec(self):
            return 0  # rejected

    monkeypatch.setattr(mw, "IsfdbDialog", FakeDialog)
    window.open_isfdb_dialog()
    assert seen == [(window.books, dest)]


def test_the_settings_dialog_opens_and_shows_the_state_of_the_database(built, tmp_path):
    from gui.isfdb_settings_dialog import IsfdbSettingsDialog

    dest, _, _ = built
    app_settings.save_isfdb_database("")
    dialog = IsfdbSettingsDialog()
    assert dialog.status_label.text() == "No database yet."
    dialog.path_edit.setText(str(tmp_path / "nope.db"))
    assert "Not built yet" in dialog.status_label.text()
    dialog.path_edit.setText(dest)
    assert "5 books" in dialog.status_label.text() and "2025-12-27" in dialog.status_label.text()
    dialog.close()


def test_settings_adapter_carries_the_isfdb_paths_as_machine_specific(built, tmp_path):
    from gui.settings_adapter import EpubSettingsAdapter
    from redactor_common.core import settings_bundle as sb

    dest, _, _ = built
    backup = tmp_path / "backup-MySQL-55-2025-12-27.zip"
    assert backup.exists()
    adapter = EpubSettingsAdapter(["filename"])
    app_settings.save_isfdb_database(dest)
    app_settings.save_isfdb_backup(str(backup))
    bundle = sb.build_bundle(adapter, sb.default_selection(adapter))
    assert "folders" not in bundle.sections and dest not in sb.dump_bundle(bundle)  # unticked by default
    bundle = sb.build_bundle(adapter, {"folders"})
    assert bundle.sections["folders"].items["isfdb_database"] == dest
    assert bundle.sections["folders"].items["isfdb_backup"] == str(backup)
    app_settings.save_isfdb_database("")
    app_settings.save_isfdb_backup("")
    bundle.sections["folders"].items["isfdb_backup"] = str(tmp_path / "does-not-exist.zip")
    sb.apply_bundle(adapter, bundle, {"folders"})
    assert app_settings.load_isfdb_database() == dest  # exists here: taken over
    assert app_settings.load_isfdb_backup() == ""  # doesn't exist on this computer: left alone
