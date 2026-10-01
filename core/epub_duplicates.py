"""
core/epub_duplicates.py

Repair > Find Duplicates: groups the loaded books that may be the same
book, for the user to REVIEW (redactor_common's shared review dialog,
gui/duplicates_dialog.py). Nothing here changes a file, and a duplicate
is not an error: the same book can legitimately exist several times (two
editions, an omnibus, a wrongly assigned ISBN).

Three kinds of evidence, strongest first -- each becomes a tier, and every
group says in words why it matched:

1. TIER_IDENTICAL: the same content. Equal epub_fingerprint (the zip
   central directory's (name, CRC32, size) of every entry except the OPF),
   so a book whose metadata was edited, or re-saved by another tool, is
   still found. Reads no file data. Byte-identical copies are the same
   case.
2. TIER_POSSIBLE: the same normalised title AND the same normalised first
   author -- "may be a different edition". The WHOLE title has to match
   (a volume number is part of it), so "Dune" and "Dune Messiah", or
   volumes 1 and 2 of a series, are never grouped, and neither is an
   omnibus whose title only overlaps one of its parts. Books with no title
   or no author are left out of this tier.
3. TIER_WEAK: the same valid ISBN but a different title/author -- a very
   common data error ("the ISBN may be wrong"). If the books sharing an
   ISBN also share title and author, that is no separate group: it is
   added to the title group's reason instead.

Signals combine rather than repeat: groups with exactly the same members
are merged into one (strongest tier, combined reason), and a group that
sits entirely inside a stronger one is dropped. Groups that overlap only
partly stay separate -- they say different things.

Pure logic, no Qt. Metadata comes from the already-loaded EpubBooks (so
unsaved edits count), the fingerprint from the file on disk.
"""

from __future__ import annotations

import os
import zipfile
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from core.author_sort import author_sort_to_authors
from core.epub_fingerprint import entries_fingerprint
from redactor_common.core.duplicates import (
    TIER_IDENTICAL,
    TIER_POSSIBLE,
    TIER_WEAK,
    DuplicateGroup,
    DuplicateMember,
    tier_strength,
)
from redactor_common.core.isbn_norm import normalize_isbn
from redactor_common.core.local_db import normalize_words

# Leading articles ignored when comparing titles ("The Hobbit" == "Hobbit").
_ARTICLES = frozenset({"the", "a", "an", "le", "la", "les", "l", "el", "il", "der", "die", "das"})

# Column keys and labels of the review dialog's member rows.
COLUMNS = [
    ("title", "Title"), ("authors", "Authors"), ("series", "Series"), ("format", "Format"),
    ("year", "Year"), ("isbn", "ISBN"), ("language", "Language"), ("file", "File"), ("folder", "Folder"),
]


def normalize_title(title: str) -> str:
    """Case, accents, punctuation and a leading article folded away; the
    whole text (volume numbers included) is kept."""
    words = normalize_words(title).split()
    if len(words) > 1 and words[0] in _ARTICLES:
        words = words[1:]
    return " ".join(words)


def normalize_author(authors: Sequence[str], author_sort: Sequence[str] = ()) -> str:
    """The first author as an order-independent key: "Tolkien, J.R.R." and
    "J.R.R. Tolkien" both give "j r r tolkien" (an entry with a comma is
    read as "Last, First", the app's own convention; the words are then
    sorted so even a misread name -- "Smith, John, Jr." -- still agrees
    with its plain spelling). Falls back to the Author Sort field when
    there is no author."""
    first = next((a for a in authors if a and a.strip()), "") or next((a for a in author_sort if a and a.strip()), "")
    if "," in first:
        first = author_sort_to_authors(first)
    return " ".join(sorted(normalize_words(first).split()))


def read_identity(path: str, opf_path: str) -> tuple[str, str]:
    """(content fingerprint, OPF signature) of the EPUB at `path` from its
    zip central directory alone. The OPF signature (CRC32-size) tells
    "identical files" from "identical content, different metadata". Both
    "" when the file can't be read or its OPF path is unknown."""
    if not opf_path:
        return "", ""
    try:
        with zipfile.ZipFile(path, "r") as zf:
            infos = zf.infolist()
    except (zipfile.BadZipFile, OSError):
        return "", ""
    fingerprint = entries_fingerprint(((i.filename, i.CRC, i.file_size) for i in infos), opf_path)
    opf = next((i for i in infos if i.filename == opf_path), None)
    return fingerprint, (f"{opf.CRC:08x}-{opf.file_size}" if opf else "")


@dataclass
class _Info:
    book: object
    fingerprint: str
    opf_signature: str
    title_key: str
    author_key: str
    isbn: str

    @property
    def title_author(self) -> Optional[tuple[str, str]]:
        return (self.title_key, self.author_key) if self.title_key and self.author_key else None


@dataclass
class _Candidate:
    kind: str
    key: str
    tier: str
    members: tuple[int, ...]   # indexes into the infos, ascending
    reason: str                # the full sentence when this evidence leads
    short: str                 # the clause used when it only backs up a stronger one
    notes: list[str]


def _file_size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _format_size(num_bytes: int) -> str:
    if num_bytes >= 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.1f} MB"
    if num_bytes >= 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes} B"


def _member(info: _Info) -> DuplicateMember:
    book = info.book
    md = book.metadata
    series = md.series + (f" #{md.series_index}" if md.series and md.series_index else "")
    path = str(book.path)
    return DuplicateMember(
        item=book, path=path, fingerprint=info.fingerprint,
        fields={
            "title": md.title, "authors": md.authors_str, "series": series,
            "format": f"EPUB, {_format_size(_file_size(path))}", "year": md.pub_year,
            "isbn": md.isbn, "language": md.language,
            "file": os.path.basename(path), "folder": os.path.dirname(path),
        },
    )


def _candidates(infos: list[_Info]) -> list[_Candidate]:
    found: list[_Candidate] = []

    same_content: dict[str, list[int]] = {}
    same_title: dict[tuple[str, str], list[int]] = {}
    same_isbn: dict[str, list[int]] = {}
    for i, info in enumerate(infos):
        if info.fingerprint:
            same_content.setdefault(info.fingerprint, []).append(i)
        if info.title_author:
            same_title.setdefault(info.title_author, []).append(i)
        if info.isbn:
            same_isbn.setdefault(info.isbn, []).append(i)

    for fingerprint, idx in same_content.items():
        if len(idx) < 2:
            continue
        if len({infos[i].opf_signature for i in idx}) == 1:
            reason = "identical files: same content and same metadata"
        else:
            reason = "identical content: only the metadata differs"
        found.append(_Candidate("identical", fingerprint, TIER_IDENTICAL, tuple(idx), reason, "identical content", []))

    title_candidates: dict[tuple[str, str], _Candidate] = {}
    for key, idx in same_title.items():
        if len(idx) >= 2:
            cand = _Candidate(
                "title", "\0".join(key), TIER_POSSIBLE, tuple(idx),
                "same title and author — may be a different edition", "same title and author", [],
            )
            title_candidates[key] = cand
            found.append(cand)

    for isbn, idx in same_isbn.items():
        if len(idx) < 2:
            continue
        keys = {infos[i].title_author for i in idx}
        if len(keys) == 1 and None not in keys:
            # Same ISBN and same title/author: backs up the title group.
            cand = title_candidates[next(iter(keys))]
            cand.notes.append(
                f"same ISBN {isbn}" if len(cand.members) == len(idx)
                else f"{len(idx)} of them share ISBN {isbn}"
            )
            continue
        titles_differ = len({infos[i].title_key for i in idx}) > 1
        what = "title" if titles_differ else "title or author"
        found.append(_Candidate(
            "isbn", isbn, TIER_WEAK, tuple(idx),
            f"same ISBN {isbn} but different {what} — the ISBN may be wrong",
            f"same ISBN {isbn}, but the {what} differs", [],
        ))
    return found


def _merge(candidates: list[_Candidate]) -> list[_Candidate]:
    """Groups with exactly the same members become one (strongest tier
    first, the rest as "also ..."); a group inside a strictly stronger one
    is dropped."""
    by_members: dict[tuple[int, ...], list[_Candidate]] = {}
    for cand in candidates:
        by_members.setdefault(cand.members, []).append(cand)
    merged: list[_Candidate] = []
    for same in by_members.values():
        same.sort(key=lambda c: tier_strength(c.tier))
        lead = same[0]
        extra = [c.short for c in same[1:]] + lead.notes + [n for c in same[1:] for n in c.notes]
        if extra:
            lead.reason += "; also " + ", ".join(extra)
        elif lead.notes:
            lead.reason += "; " + ", ".join(lead.notes)
        merged.append(lead)
    sets = [(c, set(c.members)) for c in merged]
    return [
        c for c, members in sets
        if not any(
            tier_strength(other.tier) < tier_strength(c.tier) and members < other_members
            for other, other_members in sets
        )
    ]


def find_duplicate_groups(
    books: Sequence,
    progress: Optional[Callable[..., None]] = None,
    cancelled: Optional[Callable[[], bool]] = None,
    identity: Callable[[str, str], tuple[str, str]] = read_identity,
) -> list[DuplicateGroup]:
    """The duplicate candidates among `books` (EpubBooks; a book that
    failed to load is skipped). `progress(done, total, label)` and
    `cancelled()` are the review dialog's hooks. A cancel returns []."""
    infos: list[_Info] = []
    total = len(books)
    for n, book in enumerate(books):
        if cancelled is not None and cancelled():
            return []
        if progress is not None:
            progress(n + 1, total, f"Reading {os.path.basename(str(book.path))}")
        if book.load_error:
            continue
        md = book.metadata
        fingerprint, opf_signature = identity(str(book.path), book.opf_path)
        infos.append(_Info(
            book=book, fingerprint=fingerprint, opf_signature=opf_signature,
            title_key=normalize_title(md.title), author_key=normalize_author(md.authors, md.author_sort),
            isbn=normalize_isbn(md.isbn) or "",
        ))
    groups = []
    for cand in _merge(_candidates(infos)):
        groups.append(DuplicateGroup(
            key=f"{cand.kind}:{cand.key}", tier=cand.tier, reason=cand.reason,
            members=[_member(infos[i]) for i in cand.members],
        ))
    return groups
