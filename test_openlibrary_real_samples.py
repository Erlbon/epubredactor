"""Build and query tests on REAL Open Library data: tests/fixtures holds the
first 150 lines of the 2026-08-31 editions and authors dumps, plus edition lines
picked for being odd (no title, an ISSN in isbn_13, '19uu' dates, -1 cover ids,
a very long title, non-Latin titles, several languages, invalid ISBN-10s) and
the authors they reference (Open Library data is CC0). Nothing is downloaded."""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(__file__))

import pytest  # noqa: E402

from core.openlibrary_import import BuildOptions, build_openlibrary_database, database_info  # noqa: E402
from core.openlibrary_local import (  # noqa: E402
    open_database,
    parse_publish_date,
    search_by_isbn,
    search_by_title,
)
from redactor_common.core.local_db import forget_cached  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(__file__), "tests", "fixtures")
EDITIONS = os.path.join(FIXTURES, "ol_editions_real_sample.txt.gz")
AUTHORS = os.path.join(FIXTURES, "ol_authors_real_sample.txt.gz")


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    path = str(tmp_path_factory.mktemp("olreal") / "real.db")
    summary = build_openlibrary_database(EDITIONS, path, AUTHORS, BuildOptions(all_languages=True))
    yield path, summary
    forget_cached(path)


def test_the_real_sample_builds_without_a_single_bad_line(built):
    path, summary = built
    assert summary.bad_lines == 0 and summary.editions_seen == 233
    assert summary.editions == 222  # 11 records have no valid ISBN
    assert summary.skipped_no_isbn == 11
    assert database_info(path)["recipe"].startswith("openlibrary-editions/")


def test_default_languages_drop_only_the_other_languages(tmp_path):
    path = str(tmp_path / "default.db")
    summary = build_openlibrary_database(EDITIONS, path, AUTHORS)
    assert summary.editions <= 222 and summary.skipped_language == 222 - summary.editions
    forget_cached(path)


def test_exact_isbn_lookup_returns_the_real_record(built):
    db = open_database(built[0])
    for text in ("9780226983639", "0226983633", "978-0-226-98363-9"):
        c = search_by_isbn(db, text)[0]
        assert (c.title, c.authors_str, c.publisher) == (
            "Modes of Faith", "Theodore Ziolkowski", "University Of Chicago Press")
        assert (c.pub_year, c.pub_month, c.pub_day, c.language) == ("2007", "5", "15", "en")
        assert c.cover_id == 2336119  # recorded for a later online cover fetch, never fetched here
        assert "cover_id" not in c.as_dict() and c.image_url().endswith("/2336119-L.jpg")


def test_a_year_and_month_only_date_from_the_start_of_the_dump(built):
    c = search_by_isbn(open_database(built[0]), "9780108365096")[0]
    assert c.title == "Crime and Disorder Bill [H.L.]" and c.publisher == "Stationery Office Books"
    assert (c.pub_year, c.pub_month, c.pub_day) == ("1998", "2", "12")
    assert c.authors_str == ""  # no authors on this real record
    assert c.cover_id == 0


def test_title_and_author_fuzzy_lookup_on_real_records(built):
    db = open_database(built[0])
    found = search_by_title(db, "Modes of Faith", "Ziolkowski, Theodore")
    assert found[0].isbn == "9780226983639" and found[0].score > 0.9
    assert search_by_title(db, "broken fever", "James Morrison")[0].publisher == "St. Martin's Press"
    assert search_by_title(db, "Startling Facts In Modern Spiritualism")[0].authors_str == "Napoleon Bonaparte Wolfe"
    assert search_by_title(db, "Modes of Faith", "Somebody Else") == []


def test_author_keys_missing_from_the_authors_dump_leave_the_name_out(tmp_path):
    path = str(tmp_path / "noauthors.db")
    build_openlibrary_database(EDITIONS, path, "")  # no authors dump at all
    db = open_database(path)
    try:
        c = search_by_isbn(db, "9780226983639")[0]
        assert c.title == "Modes of Faith" and c.authors_str == ""
        assert db.query("select author_keys from editions where isbn13 = '9780226983639'")[0][0].startswith("OL")
    finally:
        forget_cached(path)


def test_oddball_records_were_handled(built):
    db = open_database(built[0])
    rows = db.query("select title, publish_date_raw, year, cover_id, language from editions")
    assert any(len(r[0]) > 150 for r in rows)  # a very long real title survives
    assert any(any(ord(ch) > 127 for ch in r[0]) for r in rows)  # accented/non-ASCII titles (no RTL titles exist in these samples)
    assert all(r[3] is None or r[3] > 0 for r in rows)  # -1 cover ids never stored
    odd = {r[1]: r[2] for r in rows if r[1] in ("19uu", "194u", "2005-06-")}
    assert all(year is None or str(year).startswith("2005") for year in odd.values())


@pytest.mark.parametrize("raw, expected", [
    ("December 31, 1990", ("1990", "12", "31")),
    ("April 1998", ("1998", "4", "")),
    ("July 7, 1999", ("1999", "7", "7")),
    ("1997", ("1997", "", "")),
    ("2007-05-03", ("2007", "5", "3")),
    ("1973-09", ("1973", "9", "")),
    ("1988 December", ("1988", "12", "")),
    ("2002 May 20", ("2002", "5", "20")),
    ("2005-06-", ("2005", "6", "")),  # trailing dash, seen in real data
    ("19uu", ("", "", "")),  # unknown digits: no year
    ("194u", ("", "", "")),
])
def test_real_publish_date_formats(raw, expected):
    assert parse_publish_date(raw) == expected
