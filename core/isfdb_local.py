"""
core/isfdb_local.py

Qt-free queries over the offline ISFDB database that core/isfdb_import.py
builds (Tools > ISFDB Database...): by ISBN, or by title (+ author, + year).
What ISFDB adds over Open Library is the book's SERIES and its number, so
every candidate carries them.

Field mapping (candidate -> what Apply writes; see as_dict()):
    title                  <- the book's title (works.title), else the edition's
    authors_str            <- works.authors_text ("; "-joined credited names)
    series / series_index  <- works.series / works.series_num, with the
                              "(Author)" ISFDB adds to tell series apart
                              dropped ("Voyagers (Ben Bova)" -> "Voyagers")
    publisher / pub_year / pub_month / pub_day / isbn
                           <- the matched EDITION (an ISBN match: that
                              edition; a title match: see best_edition())
    language               <- the title's language as this app's ISO 639-1 code
    tags_str (genre)       <- NOT filled: ISFDB has no genre tags in the dump
                              this app reads

Matching: an ISBN (13 or 10, hyphens fine) is an exact lookup; when several
editions share it the one whose book has a series wins. A title search
runs the prebuilt full-text index (title, and author names when given),
then ranks the rows by title similarity, author surname overlap, year
closeness and whether a series is known. How much to TRUST a match (95%
ISBN, 60% title+author, 45% title only) is the Redact step's call, exactly
as for the other sources.

The ISBN of a title match is only filled when it is safe to: an ISFDB
`ebook` edition of the book (the closest in year to the wanted one), else
a print edition from the very year the book already says. Otherwise the ISBN
stays empty -- a print ISBN on an ebook is a wrong ISBN.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Optional

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

SERVICE_NAME = "ISFDB (local database)"
KIND = "an ISFDB lookup database built by this app (Tools > ISFDB Database)"
MAX_ISBN_RESULTS = 5
CANDIDATE_POOL = 60  # rows pulled from the full-text index before ranking
EBOOK_BINDINGS = ("ebook",)

_WORK_COLUMNS = "id, title, authors_text, year, series, series_num, series_parent, language, ttype"
_EDITION_COLUMNS = "id, work_id, isbn13, isbn10, title, authors_text, publisher, year, month, day, binding, ctype, pages"


class IsfdbLocalError(LocalDatabaseError):
    """The local ISFDB database is missing, unreadable or not the right kind of file."""


class IsfdbLocalDatabase(LocalDatabase):
    def __init__(self, path: str):
        super().__init__(path, ("works", "editions"), KIND, IsfdbLocalError)
        self.has_fts = self.has_table("works_fts")


def open_database(path: str) -> IsfdbLocalDatabase:
    """The session's one opened database for `path`."""
    return open_cached(path, IsfdbLocalDatabase)


@dataclass
class IsfdbCandidate:
    title: str = ""
    authors_str: str = ""
    publisher: str = ""
    pub_year: str = ""
    isbn: str = ""
    tags_str: str = ""
    language: str = ""
    pub_month: str = ""
    pub_day: str = ""
    series: str = ""
    series_index: str = ""
    series_parent: str = ""  # the series this one is part of (shown only)
    first_year: str = ""     # the book's first publication, which may differ from this edition's year
    binding: str = ""
    pages: int = 0
    subtitle: str = ""       # ISFDB has none; the field keeps this candidate shaped like Open Library's
    cover_id: int = 0
    score: float = 0.0

    def display_label(self) -> str:
        bits = [self.title or "(untitled)"]
        if self.authors_str:
            bits.append(f"by {self.authors_str}")
        if self.series:
            bits.append(f"[{self.series}{' #' + self.series_index if self.series_index else ''}]")
        if self.pub_year or self.first_year:
            bits.append(f"({self.pub_year or self.first_year})")
        return " ".join(bits)

    def as_dict(self) -> dict:
        """Only the fields that actually came back, with keys already safe to pass straight to
        EpubBook.apply_metadata()."""
        raw = {
            "title": self.title,
            "authors_str": self.authors_str,
            "publisher": self.publisher,
            "pub_year": self.pub_year,
            "isbn": self.isbn,
            "tags_str": self.tags_str,
            "language": self.language,
            "pub_month": self.pub_month,
            "pub_day": self.pub_day,
            "series": self.series,
            "series_index": self.series_index if self.series else "",
        }
        return {k: v for k, v in raw.items() if v}


# --- mapping --------------------------------------------------------------------------------


def clean_series_name(series: str, authors: str = "") -> str:
    """ISFDB disambiguates series with a trailing "(Author)" -- "Voyagers (Ben Bova)". When that bracket
    names one of the book's authors it is not part of the series name; any other bracket is kept
    ("Star Wars (Legends)", "Discworld (Death)")."""
    match = re.match(r"^(.*\S)\s*\(([^()]+)\)$", series or "")
    if not match:
        return (series or "").strip()
    inner = set(normalize_words(match.group(2)).split())
    author_words = set(normalize_words(authors).split())
    if inner and inner <= author_words:  # "(Ben Bova)", "(Bova)", "(Herbert, Frank)" for an author named so
        return match.group(1).strip()
    return series.strip()


def _year_text(value) -> str:
    return str(value) if value else ""


def _candidate(work: Optional[tuple], edition: Optional[tuple]) -> IsfdbCandidate:
    """One candidate from a works row and/or an editions row (either may be missing)."""
    (_wid, w_title, w_authors, w_year, series, series_num, series_parent, language, _ttype) = work or (None,) * 9
    e = edition or (None,) * 13
    (_eid, _ework, isbn13, _i10, e_title, e_authors, publisher, e_year, e_month, e_day, binding, _ctype, pages) = e
    authors = space_initials(w_authors or e_authors or "")
    name = clean_series_name(series or "", authors)
    return IsfdbCandidate(
        title=w_title or e_title or "", authors_str=authors, publisher=publisher or "",
        pub_year=_year_text(e_year or (None if edition else w_year)), isbn=isbn13 or "", language=language or "",
        pub_month=_year_text(e_month) if e_year else "", pub_day=_year_text(e_day) if e_year and e_month else "",
        series=name, series_index=(series_num or "") if name else "", series_parent=clean_series_name(series_parent or "", authors),
        first_year=_year_text(w_year), binding=binding or "", pages=int(pages or 0),
    )


def best_edition(editions: list[tuple], year: str = "") -> Optional[tuple]:
    """The edition whose ISBN is safe to put on a book known only by title: an ebook edition (closest in
    year to `year`), else a print edition from exactly `year`; None when neither exists or when editions
    of different publishers are equally close (the ISBN would be a guess)."""
    def unambiguous(group: list[tuple]) -> Optional[tuple]:
        # Several publishers' editions equally close: any ISBN could be the wrong one, so none is offered.
        if len({e[6] or "" for e in group}) > 1:
            return None
        return min(group, key=lambda e: e[0])

    ebooks = [e for e in editions if (e[10] or "").lower() in EBOOK_BINDINGS]
    if ebooks:
        def gap(e: tuple) -> int:
            return year_gap(year, e[7]) if year else 0
        closest = min(gap(e) for e in ebooks)
        return unambiguous([e for e in ebooks if gap(e) == closest])
    if year:
        same = [e for e in editions if str(e[7] or "") == str(year)]
        if same:
            return unambiguous(same)
    return None


# --- searches ---------------------------------------------------------------------------------


def _work(db: IsfdbLocalDatabase, work_id) -> Optional[tuple]:
    if not work_id:
        return None
    rows = db.query(f"select {_WORK_COLUMNS} from works where id = ?", (work_id,))
    return rows[0] if rows else None


def search_by_isbn(db: IsfdbLocalDatabase, isbn: str, max_results: int = MAX_ISBN_RESULTS) -> list[IsfdbCandidate]:
    """Editions carrying exactly this ISBN (13 or 10, hyphens fine); those whose book has a series
    first. [] for an invalid ISBN or no match."""
    variants = isbn_variants(isbn)
    if not variants:
        return []
    isbn13, isbn10 = variants[0], (variants[1] if len(variants) > 1 else None)
    editions = db.query(f"select {_EDITION_COLUMNS} from editions where isbn13 = ? or isbn10 = ?", (isbn13, isbn10))
    found = [(edition, _work(db, edition[1])) for edition in editions]
    found.sort(key=lambda pair: (not (pair[1] and pair[1][4]), pair[0][0]))
    return [_candidate(work, edition) for edition, work in found[:max_results]]


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
    """0..1: title similarity (60%), author surname overlap (25%), year closeness (10%), a known
    series (5%)."""
    _id, row_title, row_authors, row_year, series, *_rest = row
    title_part = _similarity(normalize_words(title), normalize_words(row_title or ""))
    if authors:
        wanted = {_surname(a) for a in authors} - {""}
        have = {_surname(a) for a in _split_authors(row_authors or "")} - {""}
        author_part = len(wanted & have) / len(wanted) if wanted else 0.5
    else:
        author_part = 0.5  # nothing to compare: neutral
    gap = year_gap(year, row_year) if year and row_year else None
    year_part = 0.5 if gap is None else max(0.0, 1.0 - min(gap, 10) / 10)
    return 0.6 * title_part + 0.25 * author_part + 0.1 * year_part + (0.05 if series else 0.0)


def _fts_rows(db: IsfdbLocalDatabase, title: str, author_words: str) -> list[tuple]:
    title_match = fts_match_string(title, prefix=True)
    if not title_match:
        return []
    match = "{title} : (" + title_match + ")"
    if author_words:
        author_match = fts_match_string(author_words, prefix=False)
        if not author_match:
            return []
        match += " AND {authors_text} : (" + author_match + ")"
    columns = ", ".join(f"w.{c.strip()}" for c in _WORK_COLUMNS.split(","))
    return db.query(
        f"select {columns} from works_fts join works w on w.id = works_fts.rowid "
        "where works_fts match ? order by works_fts.rank limit ?",
        (match, CANDIDATE_POOL),
    )


def search_by_title(
    db: IsfdbLocalDatabase, title: str, authors: str = "", year: str = "", max_results: int = 6
) -> list[IsfdbCandidate]:
    """Best title (+ author, + year) matches, best first, one per distinct title/authors (the one with
    a series). With an author the full author words are tried first, then the surname alone; there is
    deliberately no title-only fallback when an author was given."""
    title = (title or "").strip()
    if not title:
        raise IsfdbLocalError("A title is required to search ISFDB.")
    if not db.has_fts:
        raise IsfdbLocalError("This ISFDB database has no full-text index -- rebuild it under Tools > ISFDB Database.")
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
    best: list[tuple[float, tuple]] = []
    for score, row in sorted(ranked, key=lambda pair: (-pair[0], not pair[1][4], pair[1][0])):
        key = (normalize_words(row[1] or ""), normalize_words(row[2] or ""))
        if key in seen:
            continue
        seen.add(key)
        best.append((score, row))
    out = []
    for score, row in best[:max_results]:
        editions = db.query(f"select {_EDITION_COLUMNS} from editions where work_id = ?", (row[0],))
        candidate = _candidate(row, best_edition(editions, year))
        if not candidate.pub_year:  # no edition chosen: the year the book first appeared
            candidate.pub_year = candidate.first_year
        candidate.score = round(score, 4)
        out.append(candidate)
    return out


# --- path-based entry points (what the dialog and the Redact step call) ---------------------


def local_search_by_isbn(path: str, isbn: str, max_results: int = MAX_ISBN_RESULTS) -> list[IsfdbCandidate]:
    return search_by_isbn(open_database(path), isbn, max_results)


def local_search_by_title(
    path: str, title: str, authors: str = "", year: str = "", max_results: int = 6
) -> list[IsfdbCandidate]:
    return search_by_title(open_database(path), title, authors, year, max_results)


def database_ready(path: Optional[str]) -> str:
    """"" when `path` can be queried, else a short reason (for a note or hint)."""
    if not path:
        return "no local ISFDB database is set up (Tools > ISFDB Database)"
    try:
        open_database(path)
    except IsfdbLocalError as exc:
        return str(exc)
    return ""
