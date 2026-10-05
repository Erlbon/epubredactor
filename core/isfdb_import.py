"""
core/isfdb_import.py

Builds a compact, offline SQLite lookup database from the ISFDB (Internet
Speculative Fiction Database) backup the user downloads from isfdb.org --
a `mysqldump` .sql file, usually zipped (backup-MySQL-55-YYYY-MM-DD.zip).
This app never downloads it. ISFDB's data is licensed Creative Commons
Attribution, so the app credits it (About / Credits).

Streaming, reading and writing are redactor_common's core/dump_mysql.py
(the MySQL INSERT reader) and core/dump_import.py (SqliteBuilder); what's
here is the recipe. It is deliberately SERIES-centred: the thing ISFDB has
that Open Library hasn't is the book's series and its number.

How ISFDB's tables map (a TITLE is the abstract book, a PUBLICATION one
printing of it):

- `works`: one row per title of a book type (novel, collection, anthology,
  omnibus, non-fiction, chapbook; the ~2 million short stories, cover
  and interior art rows are not read). A translation or variant title
  points at its canonical parent (title_parent) and inherits the parent's
  series, series number and first-publication year when it has none of
  its own. Title -> author names come from canonical_author.
- `editions`: one row per publication of a book type WITH a valid ISBN
  (that is what an ebook is looked up by; many old pulps have none and
  stay reachable through `works`). Each edition links to the title it
  prints (pub_content), and carries publisher, date, binding (ISFDB's
  `ebook` among them), pages and its own credited authors.
- Series: the series name is the title's own series (a sub-series keeps
  its parent in `series_parent`); `series_num` is ISFDB's number as text
  ("3", "2.5"). The publisher's imprint line (pubs.pub_series_id, e.g. "Ace
  Double") is NOT the book series and is not read.
- Never read, on purpose: the account/contact tables of the dump (mw_user,
  emails, web_api_users...). The recipe names the tables it wants and
  everything else is skipped unread.

Because the dump is one table after another (pub_content and
canonical_author come before pubs and titles), the wanted tables are loaded
into a TEMPORARY on-disk SQLite file first ("<dest>.work.tmp", deleted at
the end or on cancel/failure), then joined there and written into the real
database. Memory stays flat.

Schema (text columns are "" when unknown; year/pages/work_id may be NULL):
    works(id, title, authors_text, year, series, series_num, series_parent,
          language, ttype, variant_of)
    editions(id, work_id, isbn13, isbn10, title, authors_text, publisher,
             year, month, day, binding, ctype, pages)
    works_fts(title, authors_text)          redactor_import_info(key, value)
Indexes: editions(isbn13), editions(isbn10), editions(work_id).
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from typing import Callable, Iterator, Optional

from redactor_common.core import languages as iso_languages
from redactor_common.core.dump_import import (
    INFO_TABLE,
    DumpImportError,
    ImportCancelled,
    SqliteBuilder,
    open_dump,
)
from redactor_common.core.dump_mysql import MysqlReadStats, iter_mysql_dump
from redactor_common.core.isbn_norm import (
    is_valid_isbn10,
    is_valid_isbn13,
    isbn10_to_13,
    isbn13_to_10,
)
from redactor_common.core.local_db import LocalDatabase, LocalDatabaseError

SOURCE_NAME = "ISFDB"
RECIPE = "isfdb-works/1"
BOOK_TYPES = ("NOVEL", "COLLECTION", "ANTHOLOGY", "OMNIBUS", "NONFICTION", "CHAPBOOK")
MAX_AUTHORS = 6  # a book credits a handful of people at most; keep the first few

# The only tables (and columns) read from the dump.
WANTED: dict[str, list[str]] = {
    "pubs": ["pub_id", "pub_title", "pub_year", "publisher_id", "pub_pages", "pub_ptype", "pub_ctype", "pub_isbn"],
    "titles": ["title_id", "title_title", "series_id", "title_seriesnum", "title_seriesnum_2", "title_copyright",
               "title_ttype", "title_parent", "title_language"],
    "authors": ["author_id", "author_canonical"],
    "pub_authors": ["pub_id", "author_id"],
    "pub_content": ["pub_id", "title_id"],
    "canonical_author": ["title_id", "author_id", "ca_status"],
    "series": ["series_id", "series_title", "series_parent"],
    "publishers": ["publisher_id", "publisher_name"],
    "languages": ["lang_id", "lang_code"],
}

TABLES = {
    "works": [
        "id integer primary key", "title text", "authors_text text", "year integer", "series text",
        "series_num text", "series_parent text", "language text", "ttype text", "variant_of integer",
    ],
    "editions": [
        "id integer primary key", "work_id integer", "isbn13 text", "isbn10 text", "title text",
        "authors_text text", "publisher text", "year integer", "month integer", "day integer", "binding text",
        "ctype text", "pages integer",
    ],
}
INDEXES = [
    "create index ed_isbn13 on editions(isbn13)",
    "create index ed_isbn10 on editions(isbn10)",
    "create index ed_work on editions(work_id)",
]

# The temporary working tables, filled straight from the reader.
_WORK_TABLES = {
    "pubs": "pub_id integer primary key, title text, date text, publisher_id integer, pages text, ptype text, "
            "ctype text, isbn text",
    "titles": "title_id integer primary key, title text, series_id integer, num text, num2 text, date text, "
              "ttype text, parent integer, language integer",
    "authors": "author_id integer primary key, name text",
    "pub_authors": "pub_id integer, author_id integer",
    "pub_content": "pub_id integer, title_id integer",
    "canonical_author": "title_id integer, author_id integer",
    "series": "series_id integer primary key, title text, parent integer",
    "publishers": "publisher_id integer primary key, name text",
    "languages": "lang_id integer primary key, code text",
}
_BATCH = 20000
_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_DUMP_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
_EXPECTED = {"pubs": 100_000, "titles": 100_000}  # fewer than this and the file is the wrong one


@dataclass
class ImportSummary:
    titles_seen: int = 0
    works: int = 0
    works_in_series: int = 0
    pubs_seen: int = 0
    editions: int = 0
    skipped_no_isbn: int = 0
    bad_lines: int = 0
    rows: dict = field(default_factory=dict)
    sizes: dict = field(default_factory=dict)

    def describe(self) -> str:
        size = self.sizes.get("(file)")
        text = (
            f"{self.works:,} books ({self.works_in_series:,} in a series) and {self.editions:,} editions with "
            f"an ISBN, out of {self.pubs_seen:,} publications read ({self.skipped_no_isbn:,} without a valid ISBN)."
        )
        if size:
            text += f" Database size {size / (1 << 20):,.0f} MB."
        if self.bad_lines:
            text += f" {self.bad_lines:,} unreadable lines were skipped."
        return text


# --- small field helpers -------------------------------------------------------------------------


def _text(value: Optional[str]) -> str:
    return " ".join(value.split()) if value else ""


def parse_date(raw: Optional[str]) -> tuple[Optional[int], Optional[int], Optional[int]]:
    """ISFDB's 'YYYY-MM-DD' with 00 for an unknown month/day -> (year, month, day), None for what is
    unknown. 0000 is unknown; 8888 is 'unpublished' and 9999 'forthcoming': no real year."""
    match = _DATE_RE.match((raw or "").strip())
    if not match:
        return None, None, None
    year, month, day = (int(g) for g in match.groups())
    if year < 1400 or year > 2100:
        return None, None, None
    return year, (month if 1 <= month <= 12 else None), (day if month and 1 <= day <= 31 else None)


def series_number(num: Optional[str], num2: Optional[str]) -> str:
    """ISFDB's series number as text: title_seriesnum plus the optional title_seriesnum_2 part
    ("5" + "1" -> "5.1"). "" when it has none."""
    base = (num or "").strip()
    if not base:
        return ""
    extra = (num2 or "").strip()
    return f"{base}.{extra}" if extra else base


def edition_isbns(raw: Optional[str]) -> tuple[str, str]:
    """(isbn13, isbn10) from a pub_isbn value, valid ones only; ("", "") when it has none. The value may
    be hyphenated; an ISBN-10 gets its 978 equivalent; isbn10 is derived for 978 numbers."""
    text = "".join(c for c in (raw or "").upper() if c.isdigit() or c == "X")
    if is_valid_isbn13(text):
        return text, isbn13_to_10(text) or ""
    if is_valid_isbn10(text):
        return isbn10_to_13(text) or "", text
    return "", ""


def _norm_title(text: str) -> str:
    return " ".join(re.sub(r"[\W_]+", " ", (text or "").casefold()).split())


def dump_date(path: str) -> str:
    """The date in the dump's file name (backup-MySQL-55-2025-12-27.zip), else the file's date."""
    found = _DUMP_DATE_RE.search(os.path.basename(path))
    if found:
        return found.group(1)
    try:
        return datetime.date.fromtimestamp(os.path.getmtime(path)).isoformat()
    except OSError:
        return ""


def _scaled(progress: Optional[Callable[[float], None]], start: float, span: float):
    if progress is None:
        return None
    return lambda fraction: progress(start + span * min(max(fraction, 0.0), 1.0))


# --- step 1: the dump into temporary tables ---------------------------------------------------------


def _load_dump(path: str, con: sqlite3.Connection, summary: ImportSummary, progress, cancelled) -> None:
    for name, columns in _WORK_TABLES.items():
        con.execute(f"create table {name} ({columns})")
    marks = {name: ",".join("?" * (columns.count(",") + 1)) for name, columns in _WORK_TABLES.items()}
    pending: dict[str, list[tuple]] = {name: [] for name in _WORK_TABLES}

    def flush(name: str) -> None:
        if pending[name]:
            con.executemany(f"insert or replace into {name} values ({marks[name]})", pending[name])
            pending[name].clear()

    def number(value: Optional[str]) -> Optional[int]:
        return int(value) if value and value.lstrip("-").isdigit() else None

    stats = MysqlReadStats()
    with open_dump(path) as dump:
        for table, row in iter_mysql_dump(dump, WANTED, progress=progress, cancelled=cancelled, stats=stats):
            if table == "pubs":
                summary.pubs_seen += 1
                if row["pub_ctype"] not in BOOK_TYPES:
                    continue
                values: tuple = (number(row["pub_id"]), _text(row["pub_title"]), row["pub_year"],
                                 number(row["publisher_id"]), row["pub_pages"], row["pub_ptype"], row["pub_ctype"],
                                 row["pub_isbn"])
            elif table == "titles":
                summary.titles_seen += 1
                if row["title_ttype"] not in BOOK_TYPES:
                    continue
                values = (number(row["title_id"]), _text(row["title_title"]), number(row["series_id"]),
                          row["title_seriesnum"], row["title_seriesnum_2"], row["title_copyright"],
                          row["title_ttype"], number(row["title_parent"]), number(row["title_language"]))
            elif table == "canonical_author":
                if row["ca_status"] != "1":
                    continue
                values = (number(row["title_id"]), number(row["author_id"]))
            elif table == "authors":
                values = (number(row["author_id"]), _text(row["author_canonical"]))
            elif table == "pub_authors":
                values = (number(row["pub_id"]), number(row["author_id"]))
            elif table == "pub_content":
                values = (number(row["pub_id"]), number(row["title_id"]))
            elif table == "series":
                values = (number(row["series_id"]), _text(row["series_title"]), number(row["series_parent"]))
            elif table == "publishers":
                values = (number(row["publisher_id"]), _text(row["publisher_name"]))
            else:  # languages
                values = (number(row["lang_id"]), (row["lang_code"] or "").strip().lower())
            pending[table].append(values)
            if len(pending[table]) >= _BATCH:
                flush(table)
    for name in _WORK_TABLES:
        flush(name)
    con.commit()
    summary.bad_lines += stats.bad
    for table, minimum in _EXPECTED.items():
        if stats.rows.get(table, 0) < minimum:
            raise DumpImportError(
                f"The dump has only {stats.rows.get(table, 0):,} rows in {table} (expected at least "
                f"{minimum:,}). Is this the full ISFDB backup?"
            )


# --- step 2: joins inside the temporary file -------------------------------------------------------------


def _prepare(con: sqlite3.Connection, cancelled) -> None:
    """Indexes and the two author-name tables (title -> names, pub -> names)."""
    for statement in (
        "create index pc_pub on pub_content(pub_id)",
        "create index ca_title on canonical_author(title_id)",
        "create index pa_pub on pub_authors(pub_id)",
        "create index ti_parent on titles(parent)",
    ):
        con.execute(statement)
        if cancelled and cancelled():
            raise ImportCancelled()
    for target, source, key in (("title_names", "canonical_author", "title_id"), ("pub_names", "pub_authors", "pub_id")):
        con.execute(f"create table {target} ({key} integer primary key, names text)")
        con.execute(
            f"insert into {target} select {key}, group_concat(name, '; ') from ("
            f"select s.{key} as {key}, a.name as name from {source} s join authors a on a.author_id = s.author_id "
            f"where a.name != '' order by s.{key}, s.rowid) group by {key}"
        )
        if cancelled and cancelled():
            raise ImportCancelled()
    con.commit()


def _limit_names(names: Optional[str]) -> str:
    """"A; B; A; C..." -> the first MAX_AUTHORS distinct names, "; "-joined."""
    out: list[str] = []
    for name in (names or "").split("; "):
        if name and name not in out:
            out.append(name)
    return "; ".join(out[:MAX_AUTHORS])


def _work_rows(con: sqlite3.Connection, summary: ImportSummary, cancelled) -> Iterator[tuple]:
    """works rows. A variant (translation, retitle) inherits its parent's series, number and first
    year when it has no series of its own, and its authors when it lists none."""
    languages = {code: _app_language(code) for (code,) in con.execute("select distinct code from languages")}
    sql = (
        "select t.title_id, t.title, t.ttype, t.parent, t.language, t.date, t.series_id, t.num, t.num2, "
        "p.title_id, p.date, p.series_id, p.num, p.num2, "
        "coalesce(tn.names, pn.names), "
        "(select code from languages where lang_id = t.language) "
        "from titles t left join titles p on p.title_id = t.parent and t.parent != 0 "
        "left join title_names tn on tn.title_id = t.title_id "
        "left join title_names pn on pn.title_id = p.title_id order by t.title_id"
    )
    series = {row[0]: (row[1], row[2]) for row in con.execute("select series_id, title, parent from series")}
    count = 0
    for (title_id, title, ttype, parent, _lang, date, own_series, own_num, own_num2, parent_id, parent_date,
         parent_series, parent_num, parent_num2, names, language_code) in con.execute(sql):
        count += 1
        if count % 20000 == 0 and cancelled and cancelled():
            raise ImportCancelled()
        if own_series:
            series_id, num, num2 = own_series, own_num, own_num2
        else:
            series_id, num, num2 = parent_series, parent_num, parent_num2
        name, parent_series_id = series.get(series_id, ("", None)) if series_id else ("", None)
        parent_name = series.get(parent_series_id, ("", None))[0] if parent_series_id else ""
        year = parse_date(parent_date if parent_id else date)[0] or parse_date(date)[0]
        yield (
            title_id, title, _limit_names(names), year, name, series_number(num, num2) if name else "", parent_name,
            languages.get(language_code or "", ""), ttype, parent_id if parent_id else None,
        )


def _app_language(code: str) -> str:
    """ISFDB's ISO 639-2 code as ISO 639-1 where there is one ("eng" -> "en"); the code itself otherwise."""
    code = (code or "").strip().lower()
    if not code:
        return ""
    known = iso_languages.lookup(code)
    return (known.alpha2 if known and known.alpha2 else "") or code


def _link_pubs_to_titles(con: sqlite3.Connection, cancelled) -> None:
    """pub_work(pub_id, title_id): the title each publication prints. That is its content title of the
    same book type; with several (a double), the one whose title matches the publication's own title,
    else the lowest id."""
    con.execute("create table pub_work (pub_id integer primary key, title_id integer)")
    chosen: list[tuple[int, int]] = []
    group: list[tuple[int, str, str]] = []
    current: Optional[int] = None

    def settle() -> None:
        if group:
            want = _norm_title(group[0][2])
            chosen.append((current, next((t for t, text, _pub in group if _norm_title(text) == want), group[0][0])))
        group.clear()

    count = 0
    for pub_id, title_id, text, pub_title in con.execute(
        "select pc.pub_id, pc.title_id, t.title, p.title from pub_content pc "
        "join pubs p on p.pub_id = pc.pub_id join titles t on t.title_id = pc.title_id "
        "where t.ttype = p.ctype order by pc.pub_id, pc.title_id"
    ):
        count += 1
        if count % 50000 == 0 and cancelled and cancelled():
            raise ImportCancelled()
        if current is not None and pub_id != current:
            settle()
        current = pub_id
        group.append((title_id, text, pub_title))
    settle()
    con.executemany("insert into pub_work values (?, ?)", chosen)
    con.commit()


def _edition_rows(con: sqlite3.Connection, summary: ImportSummary, cancelled) -> Iterator[tuple]:
    """editions rows (valid ISBN only)."""
    rows = con.execute(
        "select p.pub_id, pw.title_id, p.title, p.date, p.pages, p.ptype, p.ctype, p.isbn, "
        "(select name from publishers where publisher_id = p.publisher_id), pn.names "
        "from pubs p left join pub_work pw on pw.pub_id = p.pub_id left join pub_names pn on pn.pub_id = p.pub_id "
        "order by p.pub_id"
    )
    count = 0
    for pub_id, work_id, title, date, pages, ptype, ctype, isbn, publisher, names in rows:
        count += 1
        if count % 20000 == 0 and cancelled and cancelled():
            raise ImportCancelled()
        isbn13, isbn10 = edition_isbns(isbn)
        if not isbn13:
            summary.skipped_no_isbn += 1
            continue
        year, month, day = parse_date(date)
        page_count = None
        match = re.search(r"(\d+)\s*$", pages or "")  # "viii+304" -> 304
        if match and 0 < int(match.group(1)) < 20000:
            page_count = int(match.group(1))
        yield (
            pub_id, work_id, isbn13, isbn10, title, _limit_names(names), publisher or "", year, month, day,
            ptype or "", ctype, page_count,
        )


def build_isfdb_database(
    dump_path: str,
    dest: str,
    progress: Optional[Callable[[float], None]] = None,
    cancelled: Optional[Callable[[], bool]] = None,
) -> ImportSummary:
    """Reads the ISFDB backup (.sql, .zip or .gz of it) and writes the lookup database to `dest`,
    replacing a previous build only once this one has succeeded."""
    summary = ImportSummary()
    if not dump_path or not os.path.isfile(dump_path):
        raise DumpImportError(f"ISFDB backup not found: {dump_path or '(not set)'}")
    work_path = dest + ".work.tmp"
    for leftover in (work_path, work_path + "-journal"):
        try:
            os.remove(leftover)
        except OSError:
            pass
    con: Optional[sqlite3.Connection] = None
    try:
        con = sqlite3.connect(work_path)
        for pragma in ("journal_mode = OFF", "synchronous = OFF", "cache_size = -262144", "temp_store = FILE"):
            con.execute(f"pragma {pragma}")
        _load_dump(dump_path, con, summary, _scaled(progress, 0.0, 0.70), cancelled)
        _prepare(con, cancelled)
        _link_pubs_to_titles(con, cancelled)
        if progress:
            progress(0.78)
        with SqliteBuilder(dest, TABLES, INDEXES) as out:
            for row in _work_rows(con, summary, cancelled):
                out.add("works", row)
                summary.works += 1
                if row[4]:
                    summary.works_in_series += 1
            if progress:
                progress(0.86)
            for row in _edition_rows(con, summary, cancelled):
                out.add("editions", row)
                summary.editions += 1
            if summary.works == 0 or summary.editions == 0:
                raise DumpImportError("Nothing was kept -- this doesn't look like the ISFDB backup.")
            if progress:
                progress(0.92)
            out.create_fts_index("works", ["title", "authors_text"], progress=_scaled(progress, 0.92, 0.08),
                                 cancelled=cancelled)
            summary.rows = out.finish({
                "source": SOURCE_NAME, "recipe": RECIPE, "dump_file": os.path.basename(dump_path),
                "dump_file_date": dump_date(dump_path), "titles_seen": summary.titles_seen,
                "pubs_seen": summary.pubs_seen, "skipped_no_isbn": summary.skipped_no_isbn,
                "bad_lines": summary.bad_lines, "works_in_series": summary.works_in_series,
            })
            summary.sizes = dict(out.sizes)
        _record_sizes(dest, summary.sizes)
    finally:
        if con is not None:
            con.close()
        for leftover in (work_path, work_path + "-journal"):
            try:
                os.remove(leftover)
            except OSError:
                pass
    if progress:
        progress(1.0)
    return summary


def _record_sizes(dest: str, sizes: dict) -> None:
    """Adds the measured sizes (known only after the file is in place) to the info table; harmless on failure."""
    try:
        con = sqlite3.connect(dest)
        try:
            con.executemany(
                f"insert or replace into {INFO_TABLE} values (?, ?)",
                [("size." + name.strip("()"), str(size)) for name, size in sizes.items()],
            )
            con.commit()
        finally:
            con.close()
    except sqlite3.DatabaseError:
        pass


def database_info(path: str) -> dict[str, str]:
    """The import-info rows of a database built here. Raises LocalDatabaseError for a missing file, a
    non-SQLite file, or a database that isn't an ISFDB lookup database built by this recipe."""
    db = LocalDatabase(path, ("works", "editions", INFO_TABLE), "an ISFDB lookup database built by this app")
    try:
        info = dict(db.query(f"select key, value from {INFO_TABLE}"))
    finally:
        db.close()
    if not info.get("recipe", "").startswith("isfdb-works/"):
        raise LocalDatabaseError("This database wasn't built from an ISFDB backup by this app.")
    return info


def describe_database(path: str) -> str:
    """A one-line status for the settings dialog: what it was built from, when, how big."""
    info = database_info(path)
    works = int(info.get("rows.works", "0") or 0)
    editions = int(info.get("rows.editions", "0") or 0)
    date = info.get("dump_file_date", "")
    text = (f"Built from the ISFDB backup{f' of {date}' if date else ''} on {info.get('built', '')[:10] or 'an unknown date'}: "
            f"{works:,} books ({int(info.get('works_in_series', '0') or 0):,} in a series), {editions:,} editions")
    size = info.get("size.file")
    if size and size.isdigit():
        text += f". {int(size) / (1 << 20):,.0f} MB."
    return text


def main(argv: list[str]) -> int:
    """python -m core.isfdb_import <backup .zip/.sql> <output.db>"""
    if len(argv) != 2:
        print("usage: python -m core.isfdb_import <ISFDB backup> <output.db>", file=sys.stderr)
        return 2
    last = [-1]

    def show(fraction: float) -> None:
        percent = int(fraction * 100)
        if percent != last[0]:
            last[0] = percent
            print(f"\r{percent:3d}%", end="", file=sys.stderr, flush=True)

    summary = build_isfdb_database(argv[0], argv[1], show)
    print(f"\n{summary.describe()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
