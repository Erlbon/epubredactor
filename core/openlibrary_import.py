"""
core/openlibrary_import.py

Builds a compact, offline SQLite lookup database from Open Library's
bulk dumps (the user downloads them from openlibrary.org/developers/dumps
-- this app never does): the EDITIONS dump (ol_dump_editions_*.txt.gz)
and, for author names, the AUTHORS dump (ol_dump_authors_*.txt.gz). The
all-types ol_dump_*.txt.gz works too -- point both pickers at it; each
pass just ignores the record types it doesn't need. The works dump is
not used yet (an edition with no author of its own would need it).

Streaming, reading and writing are redactor_common's core/dump_import.py;
what's here is the recipe:

- Only editions with at least one VALID ISBN (checksummed, via
  core/isbn_norm) are kept: that is what a book is looked up by. The
  primary key-ish column is isbn13 (an ISBN-10-only edition gets its
  978 equivalent), isbn10 sits beside it, and any further ISBNs of the
  same edition go in extra_isbns. Several editions may share an ISBN
  (Open Library has duplicates), so editions.id is the row key and the
  lookup picks the most complete one.
- Only the chosen LANGUAGES are kept (default: English, Norwegian,
  Italian, German, French) unless "all languages" is ticked, because
  the full dump is huge. An edition with no language recorded is kept
  by default (many real editions lack one); the language column holds
  the ISO 639-1 code when there is one, else Open Library's own code.
- Author names are joined in at build time: the authors dump goes
  first into a TEMPORARY on-disk SQLite table keyed by author key
  (never a Python dict -- the real file has ~10 million authors), then
  each edition looks its authors up there in batches. editions carries
  authors_text (names, "; "-joined, for display and search) and
  author_keys; the authors table holds just the authors that kept
  editions actually use.
- A prebuilt FTS5 index over title + authors_text makes title/author
  search instant (redactor_common core/local_db.fts_query).

Schema (text columns are "" when unknown; year/pages/cover_id may be NULL):
    editions(id, key, isbn13, isbn10, title, subtitle, authors_text,
             author_keys, publishers, publish_date_raw, year, language,
             pages, cover_id, subjects, work_key)
    extra_isbns(isbn13, edition_id)         authors(key, name)
    editions_fts(title, authors_text)       redactor_import_info(key, value)
Indexes: editions(isbn13), editions(isbn10), extra_isbns(isbn13), authors(key).

Size (an ESTIMATE from the format, not measured on the real dump, which
has never been read here): ~190 bytes of text per edition plus ~80 for
the indexes and FTS, so about 2 GB for ~8 million kept editions; "all
languages" can roughly double that. The build records the real sizes
(redactor_import_info 'size.*' rows) and the dialog shows the file size.

Memory: flat. One line at a time; builder batches of 5,000 rows; the
author names live on disk (temp file "<dest>.authors.tmp", deleted at the
end or on cancel/failure) behind a 64 MB page cache. Disk: about the
final size again while building, plus the temp authors file (~0.5 GB).

Every Open Library field beyond the ones its edition type definition
guarantees (covers, authors' name, ...) is read with .get() and a type
check, so a real dump that differs from what's expected degrades
(a missing value) instead of crashing; a systematically unreadable file
fails loudly (wrong type, unreadable JSON) instead of building an empty
database.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

from redactor_common.core import languages as iso_languages
from redactor_common.core.dump_import import (
    INFO_TABLE,
    DumpImportError,
    ImportCancelled,
    ReadStats,
    SqliteBuilder,
    iter_tsv_records,
    open_dump,
)
from redactor_common.core.isbn_norm import is_valid_isbn10, isbn13_to_10, normalize_isbn
from redactor_common.core.local_db import LocalDatabase, LocalDatabaseError

SOURCE_NAME = "Open Library"
RECIPE = "openlibrary-editions/1"
TYPE_EDITION = "/type/edition"
TYPE_AUTHOR = "/type/author"
COLUMNS = ["type", "key", "revision", "last_modified", "json"]

# The languages offered in the build options: (id, label, ISO 639-1 codes it covers).
# Norwegian is three codes in Open Library's data (no, nb, nn).
LANGUAGE_CHOICES: list[tuple[str, str, tuple[str, ...]]] = [
    ("en", "English", ("en",)),
    ("no", "Norwegian", ("no", "nb", "nn")),
    ("it", "Italian", ("it",)),
    ("de", "German", ("de",)),
    ("fr", "French", ("fr",)),
    ("sv", "Swedish", ("sv",)),
    ("da", "Danish", ("da",)),
    ("es", "Spanish", ("es",)),
    ("nl", "Dutch", ("nl",)),
]
DEFAULT_LANGUAGE_IDS = ("en", "no", "it", "de", "fr")

MAX_SUBJECTS = 4
MAX_SUBJECT_CHARS = 50
MAX_PUBLISHERS = 2

TABLES = {
    "editions": [
        "id integer primary key", "key text", "isbn13 text", "isbn10 text", "title text", "subtitle text",
        "authors_text text", "author_keys text", "publishers text", "publish_date_raw text", "year integer",
        "language text", "pages integer", "cover_id integer", "subjects text", "work_key text",
    ],
    "extra_isbns": ["isbn13 text", "edition_id integer"],
    "authors": ["key text", "name text"],
}
INDEXES = [
    "create index ed_isbn13 on editions(isbn13)",
    "create index ed_isbn10 on editions(isbn10)",
    "create index extra_isbn13 on extra_isbns(isbn13)",
    "create index authors_key on authors(key)",
]

_YEAR_RE = re.compile(r"(?<!\d)(1[0-9]{3}|20[0-9]{2})(?!\d)(?!s\b)")  # "1990s" is a decade, not a year
_PREFIXES = ("/books/", "/authors/", "/works/")
_NO_LANGUAGE = {"und", "zxx", "mul"}  # codes that say "no real language"
_BATCH = 2000  # editions resolved against the author table at a time
_SQL_CHUNK = 500  # keys per "in (...)" query
_SNIFF = 1000  # matching records inspected by the unreadable-JSON tripwire


@dataclass
class BuildOptions:
    """Which editions are kept. `languages`: ids from LANGUAGE_CHOICES."""

    languages: tuple[str, ...] = DEFAULT_LANGUAGE_IDS
    all_languages: bool = False
    include_unknown_language: bool = True

    def wanted_codes(self) -> set[str]:
        codes: set[str] = set()
        for lang_id, _label, covered in LANGUAGE_CHOICES:
            if lang_id in self.languages:
                codes.update(covered)
        return codes

    def describe(self) -> str:
        if self.all_languages:
            return "all languages"
        names = [label for lang_id, label, _c in LANGUAGE_CHOICES if lang_id in self.languages]
        text = ", ".join(names) or "no languages"
        return text + (" (and editions with no language recorded)" if self.include_unknown_language else "")


@dataclass
class ImportSummary:
    editions_seen: int = 0
    editions: int = 0
    skipped_no_isbn: int = 0
    skipped_language: int = 0
    authors_read: int = 0
    authors: int = 0
    bad_lines: int = 0
    rows: dict = field(default_factory=dict)
    sizes: dict = field(default_factory=dict)

    def describe(self) -> str:
        size = self.sizes.get("(file)")
        text = (
            f"{self.editions:,} editions kept out of {self.editions_seen:,} read "
            f"({self.skipped_no_isbn:,} without a valid ISBN, {self.skipped_language:,} in other languages); "
            f"{self.authors:,} author names."
        )
        if size:
            text += f" Database size {size / (1 << 20):,.0f} MB."
        if self.bad_lines:
            text += f" {self.bad_lines:,} unreadable lines were skipped."
        return text


# --- small field helpers (everything defensive: .get() and type checks) ----------------


def _text(value) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _strip_prefix(key) -> str:
    key = key if isinstance(key, str) else ""
    for prefix in _PREFIXES:
        if key.startswith(prefix):
            return key[len(prefix):]
    return key


def _key_list(items) -> list[str]:
    """Keys out of `[{"key": "/authors/OL1A"}, ...]` (also tolerates bare
    strings and the works shape `{"author": {"key": ...}}`)."""
    keys: list[str] = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict):
            inner = item.get("author") if isinstance(item.get("author"), dict) else item
            item = inner.get("key")
        key = _strip_prefix(item)
        if key and key not in keys:
            keys.append(key)
    return keys


def _string_list(items, limit: int, chars: int = 0) -> list[str]:
    out: list[str] = []
    for item in items if isinstance(items, list) else []:
        text = _text(item)
        if text and text not in out:
            out.append(text[:chars] if chars else text)
            if len(out) >= limit:
                break
    return out


def year_of(raw: str) -> Optional[int]:
    """A plausible 4-digit year inside Open Library's free-text publish_date
    ("1998", "March 1998", "c1998", "[1998?]"); the first one found."""
    match = _YEAR_RE.search(raw or "")
    return int(match.group(1)) if match else None


def edition_isbns(record: dict) -> tuple[str, str, list[str]]:
    """(isbn13, isbn10, extra isbn13s) of an edition, valid ones only; ("", "", [])
    when it has none. isbn13 is the first valid isbn_13, else the first
    valid isbn_10 converted; isbn10 is the first valid isbn_10, else derived
    from isbn13 (979 has none)."""
    thirteen: list[str] = []
    ten: list[str] = []
    values_13 = record.get("isbn_13")
    for value in values_13 if isinstance(values_13, list) else []:
        normal = normalize_isbn(value) if isinstance(value, str) else None
        if normal and normal not in thirteen:
            thirteen.append(normal)
    values_10 = record.get("isbn_10")
    for value in values_10 if isinstance(values_10, list) else []:
        if isinstance(value, str) and is_valid_isbn10(value):
            ten_text = "".join(c for c in value.upper() if c.isdigit() or c == "X")
            normal = normalize_isbn(ten_text)
            if normal and normal not in thirteen:
                thirteen.append(normal)
            if ten_text not in ten:
                ten.append(ten_text)
    if not thirteen:
        return "", "", []
    primary = thirteen[0]
    return primary, (ten[0] if ten else (isbn13_to_10(primary) or "")), thirteen[1:]


def _strip_code(key) -> str:
    key = key if isinstance(key, str) else ""
    return key.rsplit("/", 1)[-1].strip().lower()


def edition_languages(record: dict) -> list[str]:
    """The edition's languages, primary first, as ISO 639-1 codes where
    known (nor/nob/nno -> no/nb/nn), else Open Library's own code."""
    codes: list[str] = []
    items = record.get("languages")
    for item in items if isinstance(items, list) else []:
        raw = _strip_code(item.get("key") if isinstance(item, dict) else item)
        if not raw or raw in _NO_LANGUAGE:
            continue
        known = iso_languages.lookup(raw)
        code = (known.alpha2 if known else "") or raw
        if code not in codes:
            codes.append(code)
    return codes


# --- reading one dump file ---------------------------------------------------------------


class _Pass:
    """One streaming pass over a dump file, keeping only records of one
    type and parsing their JSON itself (so an all-types dump doesn't pay to
    parse the ~90% it ignores). Has its own "format changed" tripwire for
    the JSON, like the readers have for the columns."""

    def __init__(self, path: str, wanted_type: str, what: str, progress, cancelled):
        self.path, self.wanted_type, self.what = path, wanted_type, what
        self.progress, self.cancelled = progress, cancelled
        self.stats = ReadStats()
        self.matching = 0
        self.bad_json = 0

    def records(self) -> Iterable[tuple[str, dict]]:
        name = os.path.basename(self.path)
        with open_dump(self.path) as dump:
            for rec in iter_tsv_records(
                dump, COLUMNS, progress=self.progress, cancelled=self.cancelled, stats=self.stats
            ):
                if rec["type"].strip() != self.wanted_type:
                    continue
                self.matching += 1
                try:
                    data = json.loads(rec["json"])
                    if not isinstance(data, dict):
                        raise ValueError("not an object")
                except ValueError:
                    self.bad_json += 1
                    if 10 <= self.matching <= _SNIFF and self.bad_json * 5 > self.matching:
                        raise DumpImportError(
                            f"{name}: {self.bad_json} of the first {self.matching} {self.what} records have "
                            "unreadable JSON. The dump format may have changed."
                        )
                    continue
                yield rec["key"], data
        if self.matching == 0:
            raise DumpImportError(
                f"{name} has no {self.what} records ({self.wanted_type}). Is this the right Open Library dump "
                f"(the {self.what}s dump, or the all-types dump)?"
            )

    @property
    def bad(self) -> int:
        return self.stats.bad + self.bad_json


def _scaled(progress: Optional[Callable[[float], None]], start: float, span: float):
    return (lambda fraction: progress(start + span * fraction)) if progress else None


def _file_date(path: str) -> str:
    try:
        return datetime.datetime.fromtimestamp(os.path.getmtime(path)).date().isoformat()
    except OSError:
        return ""


# --- the build ---------------------------------------------------------------------------


def _load_author_names(path: str, temp_path: str, progress, cancelled) -> tuple[sqlite3.Connection, int, int]:
    """Pass 1: author key -> name into an on-disk temp table. Returns the
    open connection, how many authors were stored and how many lines were bad."""
    for leftover in (temp_path, temp_path + "-journal"):
        if os.path.exists(leftover):
            os.remove(leftover)
    con = sqlite3.connect(temp_path)
    try:
        for pragma in ("journal_mode = OFF", "synchronous = OFF", "cache_size = -65536"):
            con.execute(f"pragma {pragma}")
        con.execute("create table names (key text primary key, name text, used integer default 0) without rowid")
        reader = _Pass(path, TYPE_AUTHOR, "author", progress, cancelled)
        batch: list[tuple[str, str]] = []
        count = 0
        for key, data in reader.records():
            name = _text(data.get("name")) or _text(data.get("personal_name"))
            short = _strip_prefix(key)
            if not name or not short:
                continue
            batch.append((short, name))
            if len(batch) >= 20000:
                con.executemany("insert or replace into names(key, name) values (?, ?)", batch)
                count += len(batch)
                batch.clear()
        if batch:
            con.executemany("insert or replace into names(key, name) values (?, ?)", batch)
            count += len(batch)
        con.commit()
        return con, count, reader.bad
    except BaseException:
        con.close()
        raise


def _resolve_names(con: Optional[sqlite3.Connection], keys: set[str]) -> dict[str, str]:
    """Names for `keys` from the temp table; marks them used."""
    if con is None or not keys:
        return {}
    found: dict[str, str] = {}
    pool = sorted(keys)
    for start in range(0, len(pool), _SQL_CHUNK):
        chunk = pool[start:start + _SQL_CHUNK]
        marks = ",".join("?" * len(chunk))
        found.update(con.execute(f"select key, name from names where key in ({marks})", chunk).fetchall())
        con.execute(f"update names set used = 1 where key in ({marks})", chunk)
    return found


def build_openlibrary_database(
    editions_path: str,
    dest: str,
    authors_path: str = "",
    options: Optional[BuildOptions] = None,
    progress: Optional[Callable[[float], None]] = None,
    cancelled: Optional[Callable[[], bool]] = None,
) -> ImportSummary:
    """Reads the editions dump (and the authors dump, if given; either may
    be the all-types dump) and writes the lookup database to `dest`,
    replacing a previous build only once this one has succeeded."""
    options = options or BuildOptions()
    summary = ImportSummary()
    if not editions_path or not os.path.isfile(editions_path):
        raise DumpImportError(f"Editions dump not found: {editions_path or '(not set)'}")
    if authors_path and not os.path.isfile(authors_path):
        raise DumpImportError(f"Authors dump not found: {authors_path}")
    if not options.all_languages and not options.languages and not options.include_unknown_language:
        raise DumpImportError("No languages chosen -- tick at least one, or 'All languages'.")
    wanted = options.wanted_codes()

    # Progress budget: both passes weighted by file size, then the author
    # table and the full-text index.
    size_authors = os.path.getsize(authors_path) if authors_path else 0
    size_editions = os.path.getsize(editions_path)
    total = max(size_authors + size_editions, 1)
    span_authors = 0.83 * size_authors / total
    span_editions = 0.83 * size_editions / total
    fts_start = span_authors + span_editions + 0.03
    temp_path = dest + ".authors.tmp"
    names: Optional[sqlite3.Connection] = None
    try:
        if authors_path:
            names, summary.authors_read, bad = _load_author_names(
                authors_path, temp_path, _scaled(progress, 0.0, span_authors), cancelled
            )
            summary.bad_lines += bad

        with SqliteBuilder(dest, TABLES, INDEXES) as out:
            reader = _Pass(editions_path, TYPE_EDITION, "edition", _scaled(progress, span_authors, span_editions),
                           cancelled)
            pending: list[tuple] = []  # (row without authors_text/author_keys, author keys)
            edition_id = 0

            def flush() -> None:
                found = _resolve_names(names, {k for _row, keys in pending for k in keys})
                for row, keys in pending:
                    people = [found[k] for k in keys if k in found]
                    out.add("editions", row[:6] + ("; ".join(people), " ".join(keys)) + row[6:])
                pending.clear()

            for key, data in reader.records():
                summary.editions_seen += 1
                isbn13, isbn10, extra = edition_isbns(data)
                if not isbn13:
                    summary.skipped_no_isbn += 1
                    continue
                codes = edition_languages(data)
                if not options.all_languages:
                    if codes:
                        if not wanted.intersection(codes):
                            summary.skipped_language += 1
                            continue
                    elif not options.include_unknown_language:
                        summary.skipped_language += 1
                        continue
                edition_id += 1
                date_raw = _text(data.get("publish_date"))
                pages = data.get("number_of_pages")
                cover_list = data.get("covers")
                covers = [c for c in cover_list if isinstance(c, int) and not isinstance(c, bool) and c > 0] \
                    if isinstance(cover_list, list) else []
                works = _key_list(data.get("works"))
                row = (
                    edition_id, _strip_prefix(key), isbn13, isbn10, _text(data.get("title")),
                    _text(data.get("subtitle")),
                    # authors_text and author_keys are inserted here by flush()
                    "; ".join(_string_list(data.get("publishers"), MAX_PUBLISHERS)), date_raw, year_of(date_raw),
                    codes[0] if codes else "",
                    pages if isinstance(pages, int) and not isinstance(pages, bool) and 0 < pages < 20000 else None,
                    covers[0] if covers else None,
                    "; ".join(_string_list(data.get("subjects"), MAX_SUBJECTS, MAX_SUBJECT_CHARS)),
                    works[0] if works else "",
                )
                pending.append((row, _key_list(data.get("authors"))))
                for other in extra:
                    out.add("extra_isbns", (other, edition_id))
                if len(pending) >= _BATCH:
                    flush()
            flush()
            summary.bad_lines += reader.bad
            summary.editions = edition_id
            if edition_id == 0:
                raise DumpImportError(
                    f"No editions were kept -- none of the {summary.editions_seen:,} edition records has a "
                    "valid ISBN in the chosen languages."
                )

            used = 0
            if names is not None:
                for key, name in names.execute("select key, name from names where used = 1"):
                    out.add("authors", (key, name))
                    used += 1
                    if used % 50000 == 0 and cancelled and cancelled():
                        raise ImportCancelled()
            summary.authors = used
            if progress:
                progress(fts_start)
            out.create_fts_index(
                "editions", ["title", "authors_text"], progress=_scaled(progress, fts_start, 1.0 - fts_start),
                cancelled=cancelled,
            )
            summary.rows = out.finish({
                "source": SOURCE_NAME, "recipe": RECIPE,
                "editions_file": os.path.basename(editions_path), "editions_file_date": _file_date(editions_path),
                "authors_file": os.path.basename(authors_path) if authors_path else "",
                "authors_file_date": _file_date(authors_path) if authors_path else "",
                "languages": options.describe(), "editions_seen": summary.editions_seen,
                "skipped_no_isbn": summary.skipped_no_isbn, "skipped_language": summary.skipped_language,
                "bad_lines": summary.bad_lines,
            })
            summary.sizes = dict(out.sizes)
        _record_sizes(dest, summary.sizes)
    finally:
        if names is not None:
            names.close()
        for leftover in (temp_path, temp_path + "-journal"):
            try:
                os.remove(leftover)
            except OSError:
                pass
    if progress:
        progress(1.0)
    return summary


def _record_sizes(dest: str, sizes: dict) -> None:
    """Adds the measured sizes (SqliteBuilder only knows them after the
    file is in place) to the info table; a failure here is harmless."""
    try:
        con = sqlite3.connect(dest)
        try:
            con.executemany(
                "insert or replace into redactor_import_info values (?, ?)",
                [("size." + name.strip("()"), str(size)) for name, size in sizes.items()],
            )
            con.commit()
        finally:
            con.close()
    except sqlite3.DatabaseError:
        pass


def database_info(path: str) -> dict[str, str]:
    """The import-info rows of a database built here. Raises
    LocalDatabaseError for a missing file, a non-SQLite file, or a database
    that isn't an Open Library lookup database built by this recipe."""
    db = LocalDatabase(path, ("editions", INFO_TABLE), "an Open Library lookup database built by this app")
    try:
        info = dict(db.query(f"select key, value from {INFO_TABLE}"))
    finally:
        db.close()
    if not info.get("recipe", "").startswith("openlibrary-editions/"):
        raise LocalDatabaseError("This database wasn't built from Open Library dumps by this app.")
    return info


def describe_database(path: str) -> str:
    """A one-line status for the settings dialog: what it was built from, when, how big."""
    info = database_info(path)
    editions = int(info.get("rows.editions", "0") or 0)
    source = info.get("editions_file", "") or "an Open Library dump"
    date = info.get("editions_file_date", "")
    text = (f"Built from {source}{f' ({date})' if date else ''} on {info.get('built', '')[:10] or 'an unknown date'}: "
            f"{editions:,} editions")
    if info.get("rows.authors", "0") != "0":
        text += f", {int(info['rows.authors']):,} authors"
    if info.get("languages"):
        text += f"; {info['languages']}"
    size = info.get("size.file")
    if size and size.isdigit():
        text += f". {int(size) / (1 << 20):,.0f} MB."
    return text


def main(argv: list[str]) -> int:
    """python -m core.openlibrary_import editions.txt.gz authors.txt.gz out.db [all]"""
    if len(argv) not in (3, 4):
        print("usage: python -m core.openlibrary_import <editions dump> <authors dump or ''> <output.db> [all]",
              file=sys.stderr)
        return 2
    last = [-1]

    def show(fraction: float) -> None:
        percent = int(fraction * 100)
        if percent != last[0]:
            last[0] = percent
            print(f"\r{percent:3d}%", end="", file=sys.stderr, flush=True)

    summary = build_openlibrary_database(
        argv[0], argv[2], argv[1], BuildOptions(all_languages=len(argv) == 4 and argv[3] == "all"), show
    )
    print(f"\n{summary.describe()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
