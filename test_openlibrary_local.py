"""Tests for core/openlibrary_local.py (queries over the built Open Library
database), its use by the Look Up dialog, the Metadata > Look Up menu entry
and the Redact step `metadata_lookup` (local database first, online only for
what is still empty). The database is built from a small synthetic dump."""

import os
import sqlite3
import sys
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(__file__))

import pytest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from core.google_books_lookup import GoogleBooksCandidate  # noqa: E402
from core.open_library_lookup import OpenLibraryCandidate, OpenLibraryLookupError  # noqa: E402
from core.openlibrary_import import build_openlibrary_database  # noqa: E402
from core.openlibrary_local import (  # noqa: E402
    OpenLibraryLocalError,
    app_language_code,
    database_ready,
    local_search_by_isbn,
    local_search_by_title,
    open_database,
    parse_publish_date,
    search_by_isbn,
    search_by_title,
)
from core.redact_steps import RedactEnv  # noqa: E402
from gui import app_settings  # noqa: E402
from redactor_common.core.dump_import import ImportCancelled  # noqa: E402,F401
from redactor_common.core.isbn_norm import isbn13_check_digit  # noqa: E402
from redactor_common.core.local_db import forget_cached  # noqa: E402
from redactor_common.core.pipeline import FileStatus  # noqa: E402
from test_openlibrary_import import author, edition, write_gz  # noqa: E402
from test_redact_steps import Trash, gb, load, make_epub, only, only_entry, quiet_lookups, run  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)


def isbn13(prefix12: str) -> str:
    return prefix12 + isbn13_check_digit(prefix12)


DUNE = isbn13("978044117271")  # 9780441172719
HOBBIT = isbn13("978026110221")
PRIDE_A = isbn13("978014143951")
PRIDE_B = isbn13("978019953556")
KAMP = isbn13("978820230011")
OTHER_DUNE = isbn13("978123456789")
DER_HOBBIT = isbn13("978342312210")
EXTRA = isbn13("978059309932")


@pytest.fixture
def olpath(tmp_path):
    editions = write_gz(tmp_path / "e.txt.gz", [
        # two records for one ISBN: the complete one must win
        edition(2, "Dune", isbn13=[DUNE], lang="eng", publishers=[]),
        edition(1, "Dune", isbn13=[DUNE, EXTRA], authors=["OL1A"], lang="eng", publish_date="1990", publishers=[],
                number_of_pages=412, subjects=["Science fiction"], subtitle=""),
        edition(4, "The Hobbit", isbn13=[HOBBIT], authors=["OL2A"], lang="eng", subtitle="or There and Back Again",
                publish_date="September 21, 1937"),
        edition(5, "Pride and Prejudice", isbn10=["0141439513"], authors=["OL3A"], lang="eng", publish_date="c1813",
                publishers=["Old House"]),
        edition(6, "Pride and Prejudice", isbn13=[PRIDE_B], authors=["OL3A"], lang="eng", publish_date="[1998?]",
                publishers=["Penguin", "Other"]),
        edition(7, "Min kamp", isbn13=[KAMP], authors=["OL4A"], lang="nob", publish_date="2009-03-04"),
        edition(8, "Dune", isbn13=[OTHER_DUNE], authors=["OL3A"], lang="eng", publish_date="2000"),
        edition(9, "Der Hobbit", isbn13=[DER_HOBBIT], authors=["OL2A"], lang="ger", publish_date="1997"),
    ])
    authors = write_gz(tmp_path / "a.txt.gz", [
        author("OL1A", "Frank Herbert"), author("OL2A", "J. R. R. Tolkien"), author("OL3A", "Jane Austen"),
        author("OL4A", "Karl Ove Knausgård"),
    ])
    path = str(tmp_path / "ol.db")
    build_openlibrary_database(editions, path, authors)
    yield path
    forget_cached(path)


@pytest.fixture
def db(olpath):
    return open_database(olpath)


# --- by ISBN --------------------------------------------------------------------------------


def test_isbn_13_10_and_hyphenated_all_find_the_edition(db):
    for text in (DUNE, "0441172717", "978-0-441-17271-9", "0-441-17271-7", " 9780441172719 "):
        found = search_by_isbn(db, text)
        assert found and found[0].title == "Dune", text
        assert found[0].isbn == DUNE


def test_an_isbn_10_only_edition_is_found_by_either_form(db):
    for text in ("0141439513", PRIDE_A):
        assert [c.title for c in search_by_isbn(db, text)] == ["Pride and Prejudice"]


def test_a_secondary_isbn_of_an_edition_finds_it(db):
    assert search_by_isbn(db, EXTRA)[0].authors_str == "Frank Herbert"


def test_unknown_or_invalid_isbns_give_nothing(db):
    assert search_by_isbn(db, "9780306406157") == []
    assert search_by_isbn(db, "9780306406158") == []  # bad check digit
    assert search_by_isbn(db, "not an isbn") == [] and search_by_isbn(db, "") == []


def test_several_editions_with_one_isbn_pick_the_most_complete_record(db):
    found = search_by_isbn(db, DUNE)
    assert len(found) == 2
    best = found[0]
    assert (best.authors_str, best.pub_year, best.pages, best.language) == ("Frank Herbert", "1990", 412, "en")
    assert found[1].authors_str == "" and found[1].pages == 0  # the bare record comes second


# --- field mapping --------------------------------------------------------------------------


def test_candidate_fields_and_what_is_deliberately_left_out(db):
    c = search_by_isbn(db, HOBBIT)[0]
    assert c.as_dict() == {
        "title": "The Hobbit", "authors_str": "J. R. R. Tolkien", "publisher": "Ace", "isbn": HOBBIT, "language": "en",
        "pub_year": "1937", "pub_month": "9", "pub_day": "21",
    }
    assert c.subtitle == "or There and Back Again"  # compared, never written
    assert c.tags_str == "" and c.cover_id == 0  # no clean genre mapping; covers are online-only


def test_publisher_is_the_first_listed(db):
    assert search_by_isbn(db, PRIDE_B)[0].publisher == "Penguin"


@pytest.mark.parametrize("raw, expected", [
    ("1998", ("1998", "", "")),
    ("March 1998", ("1998", "3", "")),
    ("Mar. 1998", ("1998", "3", "")),
    ("1998-03-04", ("1998", "3", "4")),
    ("1998-03", ("1998", "3", "")),
    ("March 4, 1998", ("1998", "3", "4")),
    ("4 March 1998", ("1998", "3", "4")),
    ("4th March 1998", ("1998", "3", "4")),
    ("[1998-03-04]", ("1998", "3", "4")),
    ("c1998", ("1998", "", "")),
    ("c. 1998", ("1998", "", "")),
    ("ca. 1998", ("1998", "", "")),
    ("[1998?]", ("1998", "", "")),
    ("1998?", ("1998", "", "")),
    ("circa March 1998", ("1998", "", "")),  # approximate: year only
    ("03/04/1998", ("1998", "", "")),  # day-first or month-first: ambiguous
    ("1998-1999", ("1998", "", "")),  # a range
    ("1998-13", ("1998", "", "")),  # not a month
    ("1998-02-30", ("1998", "", "")),  # not a day
    ("Feb 30, 1998", ("1998", "", "")),
    ("Sometime in the 1990s", ("", "", "")),  # a decade is not a year
    ("March", ("", "", "")),
    ("12345678", ("", "", "")),
    ("", ("", "", "")),
])
def test_publish_date_parsing(raw, expected):
    assert parse_publish_date(raw) == expected


def test_date_edge_cases_through_the_candidate(db):
    assert search_by_isbn(db, KAMP)[0].as_dict()["pub_month"] == "3"
    pride = {c.pub_year: c for c in search_by_isbn(db, "0141439513") + search_by_isbn(db, PRIDE_B)}
    assert set(pride) == {"1813", "1998"}
    assert all(not c.pub_month and not c.pub_day for c in pride.values())  # "c1813" and "[1998?]" are year only


@pytest.mark.parametrize("stored, expected", [
    ("en", "en"), ("de", "de"), ("nb", "no"), ("nn", "no"), ("no", "no"), ("nor", "no"), ("eng", "en"),
    ("ger", "de"), ("fre", "fr"), ("", ""), ("xyz", ""), ("und", ""),
])
def test_language_mapping_to_the_apps_codes(stored, expected):
    assert app_language_code(stored) == expected


def test_languages_come_out_in_app_codes(db):
    assert search_by_isbn(db, KAMP)[0].language == "no"
    assert search_by_isbn(db, DER_HOBBIT)[0].language == "de"


# --- by title -------------------------------------------------------------------------------


def test_title_and_author_ranks_the_right_book_first(db):
    found = search_by_title(db, "Dune", "Frank Herbert")
    assert found[0].authors_str == "Frank Herbert" and found[0].isbn == DUNE
    assert found[0].score > 0.9
    # Dune by another author is not offered when an author was given
    assert all(c.authors_str == "Frank Herbert" for c in found)


def test_author_in_last_first_form_and_surname_only_fallback(db):
    assert search_by_title(db, "Dune", "Herbert, Frank")[0].isbn == DUNE
    assert search_by_title(db, "The Hobbit", "Tolkien, J.R.R.")[0].title == "The Hobbit"  # initials differ: surname
    assert search_by_title(db, "Min kamp", "Karl Ove Knausgard")[0].language == "no"  # diacritics folded


def test_no_author_gives_title_matches_and_title_only_never_substitutes_for_a_wrong_author(db):
    titles = {c.authors_str for c in search_by_title(db, "Dune")}
    assert titles == {"Frank Herbert", "Jane Austen", ""} or {"Frank Herbert", "Jane Austen"} <= titles
    assert search_by_title(db, "Dune", "Somebody Else") == []


def test_one_result_per_distinct_work_and_year_breaks_ties(db):
    found = search_by_title(db, "Pride and Prejudice", "Jane Austen", year="1998")
    assert len(found) == 1  # two editions of the same title and author collapse to one
    assert found[0].pub_year == "1998"
    found = search_by_title(db, "Pride and Prejudice", "Jane Austen", year="1813")
    assert found[0].pub_year == "1813"


def test_the_subtitle_may_be_in_the_search_text_or_not(db):
    assert search_by_title(db, "The Hobbit: or There and Back Again", "Tolkien")[0].title == "The Hobbit"
    assert search_by_title(db, "The Hobbit", "Tolkien")[0].title == "The Hobbit"


def test_prefix_and_punctuation(db):
    assert search_by_title(db, "pride & prej")[0].title == "Pride and Prejudice"
    assert search_by_title(db, "  \"Dune\"! ", "Herbert")[0].isbn == DUNE


def test_a_title_is_required(db):
    with pytest.raises(OpenLibraryLocalError, match="title is required"):
        search_by_title(db, "  ")


def test_nothing_found_is_an_empty_list(db):
    assert search_by_title(db, "A Book That Does Not Exist") == []


# --- missing / wrong database ----------------------------------------------------------------


def test_a_missing_database_is_a_clear_error_not_a_crash(tmp_path):
    missing = str(tmp_path / "gone.db")
    with pytest.raises(OpenLibraryLocalError, match="not found"):
        local_search_by_isbn(missing, DUNE)
    with pytest.raises(OpenLibraryLocalError, match="not found"):
        local_search_by_title(missing, "Dune")
    assert "not found" in database_ready(missing)
    assert "no local Open Library database" in database_ready("")


def test_a_foreign_sqlite_file_or_one_without_the_index_is_explained(tmp_path):
    other = str(tmp_path / "other.db")
    sqlite3.connect(other).execute("create table something (x)").connection.close()
    with pytest.raises(OpenLibraryLocalError, match="doesn't look like"):
        open_database(other)
    bare = str(tmp_path / "bare.db")
    con = sqlite3.connect(bare)
    con.execute("create table editions (id integer primary key, isbn13, isbn10, title, subtitle, authors_text, "
                "publishers, publish_date_raw, year, language, pages, subjects, cover_id)")
    con.commit()
    con.close()
    try:
        with pytest.raises(OpenLibraryLocalError, match="full-text index"):
            search_by_title(open_database(bare), "Dune")
        assert search_by_isbn(open_database(bare), DUNE) == []  # ISBN lookups need no index
    finally:
        forget_cached(bare)
        forget_cached(other)


# --- the Look Up dialog's local search --------------------------------------------------------


def _dialog(path):
    from gui.open_library_dialog import OpenLibraryDialog

    dialog = OpenLibraryDialog.__new__(OpenLibraryDialog)  # only the search logic is under test
    dialog.local_path = path
    return dialog


def _book(title="", authors=None, isbn="", year=""):
    meta = SimpleNamespace(title=title, authors_str="; ".join(authors or []), isbn=isbn, pub_year=year)
    return SimpleNamespace(metadata=meta, path="book.epub", cover_bytes=None)


def test_dialog_prefers_the_books_own_isbn(olpath):
    result = _dialog(olpath)._search_one(_book("Wrong Title", ["Nobody"], isbn="0441172717"), {})
    assert result.fields["title"] == "Dune" and result.fields["isbn"] == DUNE
    assert result.cover_bytes is None


def test_dialog_falls_back_to_title_author_and_honours_a_typed_correction(olpath):
    dialog = _dialog(olpath)
    assert dialog._search_one(_book("The Hobbit", ["J. R. R. Tolkien"]), {}).fields["isbn"] == HOBBIT
    # the typed correction wins over the book's ISBN
    result = dialog._search_one(_book("x", isbn=DUNE), {"title": "Min kamp", "authors": "Knausgård"})
    assert result.fields["language"] == "no"
    assert dialog._search_one(_book("", isbn=""), {}).error == "no title set -- can't search"
    assert not dialog._search_one(_book("Nothing Like It", ["A"]), {}).found


def test_dialog_reports_a_missing_database_as_a_row_error(tmp_path):
    result = _dialog(str(tmp_path / "gone.db"))._search_one(_book("Dune"), {})
    assert "not found" in result.error


# --- menu + main window flow ------------------------------------------------------------------


def test_look_up_menu_has_the_local_entry_with_a_unique_mnemonic():
    import gui.main_window as mw
    from redactor_common.gui.menu_lint import lint_menu_bar
    from redactor_common.gui.standard_menus import get_action_registry

    window = mw.MainWindow()
    registry = get_action_registry(window)
    assert "import_open_library_local" in registry and registry.path_of("import_open_library_local")
    assert registry["import_open_library_local"].text() == "Open Library (&Local Database)…"
    assert lint_menu_bar(window) == []


def test_local_lookup_without_a_database_offers_the_settings_dialog(monkeypatch, tmp_path):
    import gui.main_window as mw

    window = mw.MainWindow()
    asked, opened = [], []
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: asked.append(a[2]) or QMessageBox.StandardButton.No))
    monkeypatch.setattr(window, "open_open_library_settings_dialog", lambda: opened.append(1))
    monkeypatch.setattr(mw, "OpenLibraryDialog", lambda *a, **k: pytest.fail("no dialog without a database"))
    window.open_open_library_local_dialog()
    assert asked and "Tools > Open Library Database" in asked[0] and not opened
    # a path to a file that doesn't exist counts as not set up too
    app_settings.save_open_library_database(str(tmp_path / "gone.db"))
    window.open_open_library_local_dialog()
    assert len(asked) == 2
    # Yes opens the settings dialog
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    window.open_open_library_local_dialog()
    assert opened == [1]


def test_local_lookup_opens_the_dialog_on_the_database(monkeypatch, olpath):
    import gui.main_window as mw

    window = mw.MainWindow()
    window.books = [SimpleNamespace(path="a.epub")]
    monkeypatch.setattr(window, "_selection_or_all_books", lambda: window.books)
    app_settings.save_open_library_database(olpath)
    seen = []

    class FakeDialog:
        class DialogCode:
            Accepted = 1

        def __init__(self, books, parent=None, local_path=""):
            seen.append((books, local_path))

        def exec(self):
            return 0  # rejected

    monkeypatch.setattr(mw, "OpenLibraryDialog", FakeDialog)
    window.open_open_library_local_dialog()
    assert seen == [(window.books, olpath)]
    window.open_open_library_dialog()  # the online entry is unchanged: no local path
    assert seen[-1][1] == ""


def test_settings_adapter_carries_the_database_paths_as_machine_specific(olpath, tmp_path):
    from gui.settings_adapter import EpubSettingsAdapter
    from redactor_common.core import settings_bundle as sb

    adapter = EpubSettingsAdapter(["filename"])
    app_settings.save_open_library_database(olpath)
    app_settings.save_open_library_sources("D:/dumps/editions.txt.gz", "")
    bundle = sb.build_bundle(adapter, sb.default_selection(adapter))
    assert "folders" not in bundle.sections and olpath not in sb.dump_bundle(bundle)  # unticked by default
    bundle = sb.build_bundle(adapter, {"folders"})
    assert bundle.sections["folders"].items["open_library_database"] == olpath
    # taking it over elsewhere: only paths that exist there are applied
    app_settings.save_open_library_database("")
    app_settings.save_open_library_sources("", "")
    bundle.sections["folders"].items["open_library_editions_dump"] = "D:/dumps/editions.txt.gz"
    sb.apply_bundle(adapter, bundle, {"folders"})
    assert app_settings.load_open_library_database() == olpath
    assert app_settings.load_open_library_sources() == ("", "")


# --- the Redact step ---------------------------------------------------------------------------


@pytest.fixture
def trash(tmp_path):
    return Trash(str(tmp_path) + "-bin")


def local_env(trash, olpath, calls=None, **online):
    """An env whose online sources are stubs that record their calls (in `calls`, in order)."""
    calls = calls if calls is not None else []

    def stub(name, result):
        def call(*args):
            calls.append(name)
            if isinstance(result, Exception):
                raise result
            return result
        return call

    lookups = quiet_lookups(
        google_by_isbn=stub("google_isbn", online.get("google_isbn", [])),
        google_by_title=stub("google_title", online.get("google_title", [])),
        openlibrary_by_isbn=stub("ol_isbn", online.get("ol_isbn", [])),
        openlibrary_by_title=stub("ol_title", online.get("ol_title", [])),
    )
    real_isbn, real_title = lookups.local_by_isbn, lookups.local_by_title
    lookups.local_by_isbn = lambda *a: calls.append("local_isbn") or real_isbn(*a)
    lookups.local_by_title = lambda *a: calls.append("local_title") or real_title(*a)
    return RedactEnv(trash=trash, lookups=lookups, openlibrary_local=olpath), calls


def test_exact_isbn_in_the_local_database_is_trusted_and_asked_first(tmp_path, trash, olpath):
    path = make_epub(str(tmp_path / "a.epub"), isbn=DUNE, language="", authors=(), publisher="")
    env, calls = local_env(trash, olpath)
    report = run([load(path)], env, only("metadata_lookup"))
    assert only_entry(report).status is FileStatus.CHANGED
    meta = load(path).metadata
    assert (meta.authors, meta.pub_year, meta.language) == (["Frank Herbert"], "1990", "en")
    assert "auto-applied at 95%" in report.to_text()
    assert calls[0] == "local_isbn"
    assert calls[1:] and set(calls[1:]) <= {"google_isbn", "ol_isbn"}  # only for the still-empty tags/description


def test_local_values_win_and_online_fills_only_what_is_left(tmp_path, trash, olpath):
    path = make_epub(str(tmp_path / "b.epub"), isbn=DUNE, language="", authors=(), publisher="")
    online = gb(isbn13=DUNE, publisher="Online House", pub_year="1999", authors_str="Online Person",
                tags_str="Fiction", description="<p>From the web.</p>")
    env, calls = local_env(trash, olpath, google_isbn=[online])
    run([load(path)], env, only("metadata_lookup"))
    meta = load(path).metadata
    assert meta.authors == ["Frank Herbert"] and meta.pub_year == "1990"  # local, not the online values
    assert meta.publisher == "Online House"  # the local record has no publisher -> online fills it
    assert (meta.tags, meta.description) == (["Fiction"], "From the web.")
    assert calls.index("local_isbn") < calls.index("google_isbn")


def test_existing_values_are_never_overwritten_by_the_local_database(tmp_path, trash, olpath):
    path = make_epub(str(tmp_path / "c.epub"), isbn=DUNE, language="de", authors=("Mine Already",),
                     publisher="Keeper Press", title="Kept Title")
    env, _ = local_env(trash, olpath)
    run([load(path)], env, only("metadata_lookup"))
    meta = load(path).metadata
    assert (meta.title, meta.authors, meta.publisher, meta.language) == (
        "Kept Title", ["Mine Already"], "Keeper Press", "de")
    assert meta.pub_year == "1990"  # the one empty field


def test_month_and_day_only_come_with_their_year(tmp_path, trash, olpath):
    with_year = make_epub(str(tmp_path / "y.epub"), isbn=HOBBIT)
    env, _ = local_env(trash, olpath)
    book = load(with_year)
    book.metadata.pub_year = "1999"
    book.dirty = True
    book.save()
    run([load(with_year)], env, only("metadata_lookup"))
    meta = load(with_year).metadata
    assert (meta.pub_year, meta.pub_month, meta.pub_day) == ("1999", "", "")  # keeps its own year, no stray month
    blank = make_epub(str(tmp_path / "n.epub"), isbn=HOBBIT)
    run([load(blank)], env, only("metadata_lookup"))
    meta = load(blank).metadata
    assert (meta.pub_year, int(meta.pub_month), int(meta.pub_day)) == ("1937", 9, 21)  # saved zero-padded


def test_title_and_author_match_goes_to_review_at_60_percent(tmp_path, trash, olpath):
    path = make_epub(str(tmp_path / "t.epub"), title="Min kamp", authors=("Karl Ove Knausgård",), language="")
    env, calls = local_env(trash, olpath)
    original = open(path, "rb").read()
    report = run([load(path)], env, only("metadata_lookup"))
    entry = only_entry(report)
    assert entry.status is FileStatus.NEEDS_REVIEW and entry.review[0].confidence == pytest.approx(0.6)
    assert "local database" in report.to_text() and "no" in report.to_text()
    assert open(path, "rb").read() == original and calls[0] == "local_title"


def test_title_only_match_is_45_percent(tmp_path, trash, olpath):
    path = make_epub(str(tmp_path / "o.epub"), title="Min kamp", authors=(), language="")
    env, _ = local_env(trash, olpath)
    entry = only_entry(run([load(path)], env, only("metadata_lookup")))
    assert entry.status is FileStatus.NEEDS_REVIEW and entry.review[0].confidence == pytest.approx(0.45)


def test_a_title_with_a_subtitle_matches_the_local_title_plus_subtitle(tmp_path, trash, olpath):
    path = make_epub(str(tmp_path / "s.epub"), title="The Hobbit: or There and Back Again", authors=("J.R.R. Tolkien",))
    env, _ = local_env(trash, olpath)
    entry = only_entry(run([load(path)], env, only("metadata_lookup")))
    assert entry.status is FileStatus.NEEDS_REVIEW and entry.review[0].confidence == pytest.approx(0.6)


def test_a_different_title_or_wrong_author_is_not_suggested(tmp_path, trash, olpath):
    wrong_author = make_epub(str(tmp_path / "w.epub"), title="Dune", authors=("Somebody Else",))
    other_title = make_epub(str(tmp_path / "x.epub"), title="Dune Messiah", authors=("Frank Herbert",))
    env, _ = local_env(trash, olpath)
    report = run([load(wrong_author), load(other_title)], env, only("metadata_lookup"))
    assert all(e.status is FileStatus.UNCHANGED for e in report.entries)


def test_without_a_network_the_local_database_still_works(tmp_path, trash, olpath):
    path = make_epub(str(tmp_path / "off.epub"), isbn=DUNE, authors=(), publisher="", language="")
    down = OpenLibraryLookupError("Could not reach Open Library (check your internet connection)")
    env, _ = local_env(trash, olpath, google_isbn=down, ol_isbn=down)
    report = run([load(path)], env, only("metadata_lookup"))
    assert only_entry(report).status is FileStatus.CHANGED
    assert load(path).metadata.authors == ["Frank Herbert"]


def test_no_local_database_configured_behaves_exactly_as_before(tmp_path, trash):
    path = make_epub(str(tmp_path / "plain.epub"), isbn=DUNE)
    cand = OpenLibraryCandidate(title="Test Book", publisher="OL House", pub_year="2000", isbn=DUNE)
    env = RedactEnv(trash=trash, lookups=quiet_lookups(
        openlibrary_by_isbn=lambda isbn: [cand],
        local_by_isbn=lambda *a: pytest.fail("no database is configured"),
        local_by_title=lambda *a: pytest.fail("no database is configured")))
    run([load(path)], env, only("metadata_lookup"))
    assert load(path).metadata.publisher == "OL House"


def test_a_missing_database_is_a_note_and_online_still_runs(tmp_path, trash):
    path = make_epub(str(tmp_path / "m.epub"), isbn=DUNE, publisher="")
    gone = str(tmp_path / "gone.db")
    env = RedactEnv(trash=trash, openlibrary_local=gone, lookups=quiet_lookups(
        google_by_isbn=lambda isbn: [gb(isbn13=DUNE, publisher="Online House")]))
    report = run([load(path)], env, only("metadata_lookup"))
    assert only_entry(report).status is FileStatus.CHANGED and load(path).metadata.publisher == "Online House"
    # nothing online either: unchanged, with the reason in the report instead of a failure
    path2 = make_epub(str(tmp_path / "m2.epub"), isbn=DUNE, publisher="")
    env2 = RedactEnv(trash=trash, openlibrary_local=gone, lookups=quiet_lookups())
    report2 = run([load(path2)], env2, only("metadata_lookup"))
    assert only_entry(report2).status is FileStatus.UNCHANGED
    assert "Open Library (local database) lookup failed" in report2.to_text() and "not found" in report2.to_text()


def test_the_step_description_mentions_the_local_database():
    from core.redact_steps import build_catalogue

    step = next(s for s in build_catalogue() if s.key == "metadata_lookup")
    assert "local" in step.description and "Open Library" in step.description


def test_redact_env_gets_the_configured_database(olpath):
    import gui.main_window as mw

    assert mw.MainWindow()._redact_env().openlibrary_local == ""
    app_settings.save_open_library_database(olpath)
    assert mw.MainWindow()._redact_env().openlibrary_local == olpath
