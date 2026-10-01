"""
core/openlibrary_local.py

Qt-free queries over the offline Open Library database that
core/openlibrary_import.py builds (Tools > Open Library Database...):
by ISBN, or by title (+ author, + year). Results are the SAME
OpenLibraryCandidate the online lookup (core/open_library_lookup.py)
produces, so the Look Up dialog and the Redact step treat both alike --
no network, no rate limits.

Field mapping (candidate -> what Apply writes; see as_dict()):
    title                  <- editions.title (the subtitle is kept on the
                              candidate for matching, never written: this
                              app has no Subtitle field)
    authors_str            <- editions.authors_text ("; "-joined names)
    publisher              <- the first of editions.publishers
    pub_year/month/day     <- parse_publish_date(publish_date_raw); the
                              month and day only when the text is
                              unambiguous, else the year alone
    isbn                   <- editions.isbn13
    language               <- the stored code mapped to this app's ISO 639-1
                              codes (nb/nn/nor -> "no"); "" when unknown
    pages                  <- kept on the candidate; no pages field here
    tags_str (genre)       <- NOT filled: Open Library's subjects are
                              fan-curated tags with no clean mapping to
                              this app's genre list
    cover_id               <- recorded on the candidate (Open Library's own cover
                              id, 0 if none) but NOT fetched: as_dict() leaves it
                              out and nothing here touches the network. The online
                              cover path (image_url()/download_cover_image) could
                              use it later.

Matching: an ISBN (13 or 10, hyphens fine) is an exact lookup; when
several editions share it the most completely filled-in record wins. A
title search runs the prebuilt full-text index (title, and author names
when given), then ranks the rows by title similarity, author surname
overlap, year closeness and completeness (score 0..1 on each candidate).
How much to TRUST a match (95% ISBN, 60% title+author, 45% title only) is
the Redact step's call, exactly as for the online sources.
"""

from __future__ import annotations

import difflib
import re
from typing import Optional

from redactor_common.core import languages as iso_languages
from redactor_common.core.filename_parser import MONTH_NAMES
from redactor_common.core.isbn_norm import isbn_variants
from redactor_common.core.local_db import (
    LocalDatabase,
    LocalDatabaseError,
    fts_match_string,
    normalize_words,
    open_cached,
    year_gap,
)

from core.author_sort import space_initials
from core.open_library_lookup import OpenLibraryCandidate

SERVICE_NAME = "Open Library (local database)"
KIND = "an Open Library lookup database built by this app (Tools > Open Library Database)"
MAX_ISBN_RESULTS = 5
CANDIDATE_POOL = 60  # rows pulled from the full-text index before ranking

_COLUMNS = (
    "id, isbn13, isbn10, title, subtitle, authors_text, publishers, publish_date_raw, year, language, pages, "
    "subjects, cover_id"
)
_NORWEGIAN = {"no", "nb", "nn", "nor", "nob", "nno"}


class OpenLibraryLocalError(LocalDatabaseError):
    """The local Open Library database is missing, unreadable or not the right kind of file."""


class OpenLibraryLocalDatabase(LocalDatabase):
    def __init__(self, path: str):
        super().__init__(path, ("editions",), KIND, OpenLibraryLocalError)
        self.has_extra_isbns = self.has_table("extra_isbns")
        self.has_fts = self.has_table("editions_fts")


def open_database(path: str) -> OpenLibraryLocalDatabase:
    """The session's one opened database for `path`."""
    return open_cached(path, OpenLibraryLocalDatabase)


# --- publish dates ----------------------------------------------------------------------------

_YEAR = r"(1[0-9]{3}|20[0-9]{2})"  # (not "1990s": a decade)
_MONTH_WORDS = "|".join(sorted(MONTH_NAMES, key=len, reverse=True))
_ISO_FULL = re.compile(rf"^{_YEAR}[-/.](\d{{1,2}})[-/.](\d{{1,2}})$")
_ISO_MONTH = re.compile(rf"^{_YEAR}[-/.](\d{{1,2}})$")
_NAME_DAY_YEAR = re.compile(rf"^({_MONTH_WORDS})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+{_YEAR}$", re.I)
_DAY_NAME_YEAR = re.compile(rf"^(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_WORDS})\.?,?\s+{_YEAR}$", re.I)
_NAME_YEAR = re.compile(rf"^({_MONTH_WORDS})\.?,?\s+{_YEAR}$", re.I)
_YEAR_NAME_DAY = re.compile(rf"^{_YEAR}\s+({_MONTH_WORDS})\.?(?:,?\s+(\d{{1,2}}))?$", re.I)  # "2002 May 20", "1988 December"
_ANY_YEAR = re.compile(rf"(?<!\d){_YEAR}(?!\d)(?!s\b)")


def _valid_day(year: int, month: int, day: int) -> bool:
    import calendar
    return 1 <= month <= 12 and 1 <= day <= calendar.monthrange(year, month)[1]


def parse_publish_date(raw: str) -> tuple[str, str, str]:
    """Open Library's free-text publish_date as (year, month, day), unpadded
    digit strings, "" for what isn't certain. Only a form with no
    ambiguity gives a month/day: "1998-03-04", "1998-03", "March 4, 1998",
    "4 March 1998", "March 1998". Everything vague gives the first
    plausible year alone: "1998", "c1998", "[1998?]", "ca. 1998", a range
    like "1998-1999", and numeric dates like "03/04/1998" (day-first or
    month-first?). ("", "", "") when there is no year at all."""
    text = " ".join((raw or "").replace("–", "-").split()).strip()
    if not text:
        return "", "", ""
    # Cataloguing marks around an otherwise exact date don't make it vague
    # ("[1998-03-04]"), but a "?" or "c"/"ca" does.
    vague = bool(re.search(r"\?|\bca?\.?\s*\d|\bcirca\b|\bc\d|\babout\b|\bapprox", text, re.I))
    clean = text.strip("[]() ").rstrip(".-")  # "2005-06-" is seen in real data
    if not vague:
        match = _ISO_FULL.match(clean)
        if match:
            year, month, day = (int(g) for g in match.groups())
            if _valid_day(year, month, day):
                return str(year), str(month), str(day)
        match = _ISO_MONTH.match(clean)
        if match and 1 <= int(match.group(2)) <= 12:
            return match.group(1), str(int(match.group(2))), ""
        match = _NAME_DAY_YEAR.match(clean)
        if match:
            month, day, year = MONTH_NAMES[match.group(1).lower()], int(match.group(2)), int(match.group(3))
            if _valid_day(year, int(month), day):
                return str(year), month, str(day)
        match = _DAY_NAME_YEAR.match(clean)
        if match:
            day, month, year = int(match.group(1)), MONTH_NAMES[match.group(2).lower()], int(match.group(3))
            if _valid_day(year, int(month), day):
                return str(year), month, str(day)
        match = _NAME_YEAR.match(clean)
        if match:
            return match.group(2), MONTH_NAMES[match.group(1).lower()], ""
        match = _YEAR_NAME_DAY.match(clean)
        if match:
            year, month, day = int(match.group(1)), MONTH_NAMES[match.group(2).lower()], match.group(3)
            if not day:
                return str(year), month, ""
            if _valid_day(year, int(month), int(day)):
                return str(year), month, str(int(day))
    match = _ANY_YEAR.search(text)
    return (match.group(1), "", "") if match else ("", "", "")


# --- mapping ----------------------------------------------------------------------------------


def app_language_code(stored: str) -> str:
    """The database's language code as this app's Language field wants it
    (ISO 639-1; Norwegian is "no" here whatever Open Library calls it);
    "" when it is unknown or has no 2-letter code."""
    code = (stored or "").strip().lower()
    if not code:
        return ""
    if code in _NORWEGIAN:
        return "no"
    known = iso_languages.lookup(code)
    return known.alpha2 if known and known.alpha2 else ""


def _completeness(row: tuple) -> int:
    """How many of the useful fields an edition has filled in."""
    _id, _i13, _i10, title, subtitle, authors, publishers, date_raw, year, language, pages, subjects, _cover = row
    return sum(1 for value in (title, subtitle, authors, publishers, date_raw or year, language, pages, subjects)
               if value)


def row_to_candidate(row: tuple) -> OpenLibraryCandidate:
    _id, isbn13, _i10, title, subtitle, authors, publishers, date_raw, year, language, pages, _subjects, cover_id = row
    pub_year, pub_month, pub_day = parse_publish_date(date_raw or "")
    if not pub_year and year:
        pub_year = str(year)
    return OpenLibraryCandidate(
        title=title or "", authors_str=space_initials(authors or ""), publisher=(publishers or "").split("; ")[0],
        pub_year=pub_year, isbn=isbn13 or "", tags_str="", cover_id=int(cover_id or 0),
        language=app_language_code(language or ""), pub_month=pub_month, pub_day=pub_day,
        subtitle=subtitle or "", pages=int(pages or 0),
    )


# --- searches ---------------------------------------------------------------------------------


def search_by_isbn(db: OpenLibraryLocalDatabase, isbn: str, max_results: int = MAX_ISBN_RESULTS) -> list[OpenLibraryCandidate]:
    """Editions carrying exactly this ISBN (13 or 10, hyphens fine), the most
    completely filled-in first; [] for an invalid ISBN or no match."""
    variants = isbn_variants(isbn)
    if not variants:
        return []
    isbn13, isbn10 = variants[0], (variants[1] if len(variants) > 1 else None)
    sql = f"select {_COLUMNS} from editions where isbn13 = ? or isbn10 = ?"
    params: list = [isbn13, isbn10]
    if db.has_extra_isbns:
        sql += " or id in (select edition_id from extra_isbns where isbn13 = ?)"
        params.append(isbn13)
    rows = db.query(sql, params)
    rows.sort(key=lambda row: (-_completeness(row), row[0]))
    return [row_to_candidate(row) for row in rows[:max_results]]


def _split_authors(authors: str) -> list[str]:
    return [a.strip() for a in re.split(r";|&|\band\b", authors or "") if a.strip()]


def _surname(name: str) -> str:
    """Last name of "Frank Herbert" or "Herbert, Frank P."."""
    head = name.split(",")[0] if "," in name else name
    words = normalize_words(head).split()
    return (words[0] if "," in name else words[-1]) if words else ""


def _title_stem(title: str) -> str:
    """The part of a title before a subtitle separator ("Dune: Book One" -> "Dune")."""
    return re.split(r"\s*[:–—]\s*|\s+-\s+", title, maxsplit=1)[0]


def _similarity(a: str, b: str) -> float:
    return 1.0 if a == b else difflib.SequenceMatcher(None, a, b).ratio()


def score_row(row: tuple, title: str, authors: list[str], year: str) -> float:
    """0..1: title similarity (60%), author surname overlap (25%), year
    closeness (10%), completeness (5%)."""
    _id, _i13, _i10, row_title, subtitle, row_authors, _p, _d, row_year, *_rest = row
    want = normalize_words(title)
    title_part = max(
        _similarity(want, normalize_words(row_title or "")),
        _similarity(want, normalize_words(f"{row_title} {subtitle}")) if subtitle else 0.0,
    )
    if authors:
        wanted = {_surname(a) for a in authors} - {""}
        have = {_surname(a) for a in _split_authors(row_authors or "")} - {""}
        author_part = len(wanted & have) / len(wanted) if wanted else 0.5
    else:
        author_part = 0.5  # nothing to compare: neutral
    gap = year_gap(year, row_year) if year and row_year else None
    year_part = 0.5 if gap is None else max(0.0, 1.0 - min(gap, 10) / 10)
    return 0.6 * title_part + 0.25 * author_part + 0.1 * year_part + 0.05 * min(_completeness(row) / 8, 1.0)


def _fts_rows(db: OpenLibraryLocalDatabase, title: str, author_words: str) -> list[tuple]:
    title_match = fts_match_string(title, prefix=True)
    if not title_match:
        return []
    match = "{title} : (" + title_match + ")"
    if author_words:
        author_match = fts_match_string(author_words, prefix=False)
        if not author_match:
            return []
        match += " AND {authors_text} : (" + author_match + ")"
    columns = ", ".join(f"e.{c.strip()}" for c in _COLUMNS.split(","))
    return db.query(
        f"select {columns} from editions_fts join editions e on e.id = editions_fts.rowid "
        "where editions_fts match ? order by editions_fts.rank limit ?",
        (match, CANDIDATE_POOL),
    )


def search_by_title(
    db: OpenLibraryLocalDatabase, title: str, authors: str = "", year: str = "", max_results: int = 6
) -> list[OpenLibraryCandidate]:
    """Best title (+ author, + year) matches, best first, one per distinct
    title/authors (the most complete edition of each). With an author the
    full author words are tried first, then the surname alone; there is
    deliberately no title-only fallback when an author was given."""
    title = (title or "").strip()
    if not title:
        raise OpenLibraryLocalError("A title is required to search Open Library.")
    if not db.has_fts:
        raise OpenLibraryLocalError(
            "This Open Library database has no full-text index -- rebuild it under Tools > Open Library Database."
        )
    names = _split_authors(authors)
    first = names[0] if names else ""
    attempts: list[str] = [""] if not first else [normalize_words(first), _surname(first)]
    rows: list[tuple] = []
    for stem in dict.fromkeys([title, _title_stem(title)]):  # the whole title, then without a subtitle
        for author_words in dict.fromkeys(attempts):
            rows = _fts_rows(db, stem, author_words) if (author_words or not first) else []
            if rows:
                break
        if rows:
            break
    ranked = sorted(((score_row(r, title, names, year), r) for r in rows), key=lambda pair: -pair[0])
    seen: set[tuple[str, str]] = set()
    best_by_work: list[tuple[float, tuple]] = []
    for score, row in sorted(ranked, key=lambda pair: (-pair[0], -_completeness(pair[1]), pair[1][0])):
        key = (normalize_words(row[3] or ""), normalize_words(row[5] or ""))
        if key in seen:
            continue
        seen.add(key)
        best_by_work.append((score, row))
    out = []
    for score, row in best_by_work[:max_results]:
        candidate = row_to_candidate(row)
        candidate.score = round(score, 4)
        out.append(candidate)
    return out


# --- path-based entry points (what the dialog and the Redact step call) ---------------------


def local_search_by_isbn(path: str, isbn: str, max_results: int = MAX_ISBN_RESULTS) -> list[OpenLibraryCandidate]:
    return search_by_isbn(open_database(path), isbn, max_results)


def local_search_by_title(
    path: str, title: str, authors: str = "", year: str = "", max_results: int = 6
) -> list[OpenLibraryCandidate]:
    return search_by_title(open_database(path), title, authors, year, max_results)


def database_ready(path: Optional[str]) -> str:
    """"" when `path` can be queried, else a short reason (for a note or hint)."""
    if not path:
        return "no local Open Library database is set up (Tools > Open Library Database)"
    try:
        open_database(path)
    except OpenLibraryLocalError as exc:
        return str(exc)
    return ""
