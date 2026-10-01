"""
core/redact_steps.py

The steps behind the "Redact" button (redactor_common's pipeline engine,
core/pipeline.py): run a recipe on each loaded/selected book with no
operator input and leave a corrected EPUB IN PLACE, the original in the
Recycle Bin. Qt-free; gui/main_window.py wires it to the menu/toolbar.

Every step wraps code the app already has (Validate / Repair, Generate
Table of Contents, Scan Content, the Google Books / Open Library lookups,
the cover generator, the rename pattern and Move into folders) without
the dialogs. How one book flows:

  1. EpubCtx loads a WORKING COPY of the book straight from disk (a
     fresh EpubBook, never the live row) -- so what Redact edits and
     saves is always the file as it is now. A book with a load error,
     unsaved edits in the list, or DRM is not processed at all: the guard
     step answers SKIPPED and the engine stops there.
  2. Steps run on the working copy. Deterministic repairs are APPLIED;
     guesses (TOC quality, language, front-matter facts, online matches,
     replacement covers) come back as SUGGESTIONs with a confidence, which
     the engine applies only at or above the recipe's threshold and lists
     as "Needs review" otherwise.
  3. The save (the engine's `finalize` hook, save_finalize below) writes
     the working copy to a temp file beside the original, verifies it
     (reopened, zip intact, every kept file present, spine/manifest
     consistent, no NEW error-severity validation issue, title/authors/
     cover as intended), then commit_in_place() swaps it in and sends the
     original to the Recycle Bin. Nothing is written when nothing changed.
  4. Rename and Move into folders are pinned last (position="last") and
     act on the finished file: they first make sure the save has
     happened (ctx.ensure_saved()), then rename/move it. Both are
     recorded in the app's RenameLog (once per run, env.flush_log()) so
     File > Undo Last Rename reverses them.

What is deliberately NOT applied automatically: orphan-file removal
(option, off), a "Section N" table of contents (low confidence), title
or author-only online matches (low confidence), any overwrite of a field
that already has a value (lookups and scans only fill EMPTY fields), and
the validator's "set language to en" fix (the language step guesses from
the text instead, with a confidence).
"""

from __future__ import annotations

import os
import re
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from redactor_common.core import rename_pattern as shared_rename
from redactor_common.core.move_plan import execute_move, plan_moves, render_relative_path
from redactor_common.core.os_utils import rename_no_clobber
from redactor_common.core.path_parser import is_path_pattern
from redactor_common.core.pipeline import (
    CommitError,
    FileReport,
    OptionSpec,
    Recipe,
    Step,
    StepResult,
    StepStatus,
    commit_in_place,
    effective_option_source,
)
from redactor_common.core.trash import move_to_trash

from core.author_clean import clean_authors
from core.better_cover import IsbnCoverError, IsbnCoverLimitError, fetch_cover_by_id, fetch_cover_by_isbn
from core.content_scan import ContentScanResult, scan_book
from core.description_html import has_html_markup, strip_html
from core.epub_metadata import EpubBook, EpubError
from core.filename_parser import (
    folder_metadata_field_counts,
    parse_book_path,
    parsed_to_metadata_kwargs,
    path_corroborator,
)
from core.google_books_lookup import (
    GoogleBooksLookupError,
    download_cover_image as download_google_cover,
    search_google_books,
    search_google_books_by_isbn,
)
from core.isbn import best_isbn13, is_valid_isbn
from core.languages import is_blank_or_unknown_language
from core.open_library_lookup import (
    OpenLibraryLookupError,
    search_open_library,
    search_open_library_by_isbn,
)
from core.openlibrary_local import (
    SERVICE_NAME as LOCAL_OPEN_LIBRARY,
    OpenLibraryLocalError,
    local_search_by_isbn,
    local_search_by_title,
)
from core.rename_pattern import placeholder_values
from core.toc_generate import generate_toc_entries, needs_toc, stage_generated_toc_for
from core.validation_issue import SEVERITY_ERROR

# Confidence of each kind of online match (see MetadataLookupStep): the
# book's own ISBN found in the catalogue is as good as it gets for a
# lookup; a title (+ author) match is a guess, so it lands below the
# default 0.9 threshold and is listed for review.
ISBN_MATCH_CONFIDENCE = 0.95
TITLE_AUTHOR_CONFIDENCE = 0.6
TITLE_ONLY_CONFIDENCE = 0.45
COVER_ISBN_CONFIDENCE = 0.95
MIN_COVER_WIDTH = 100  # px; smaller than this is a placeholder, not a cover

# Table-of-contents confidence (see GenerateTocStep).
TOC_HEADINGS_CONFIDENCE = 0.95
TOC_PARTIAL_CONFIDENCE = 0.5
TOC_FALLBACK_CONFIDENCE = 0.3

# The validator fixes Redact applies on its own. LANGUAGE_MISSING is
# left out on purpose: its fix writes "en" without looking at the book.
SAFE_FIX_CODES = {"PRIMARY_ID_MISSING", "AUTHORS_AMPERSAND", "DANGLING_SPINE_ITEMREF"}

_SECTION_TITLE_RE = re.compile(r"^(Section \d+|Cover)$")
_URL_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")
_FIELD_NAMES = {
    "authors_str": "Author(s)",
    "publisher": "Publisher",
    "pub_year": "Year",
    "pub_month": "Month",
    "pub_day": "Day",
    "isbn": "ISBN",
    "tags_str": "Genre",
    "language": "Language",
    "description": "Description",
}


# --- run environment -------------------------------------------------------


def _call_directly(fn: Callable, *args: Any, **kwargs: Any) -> Any:
    return fn(*args, **kwargs)


@dataclass
class Lookups:
    """The network calls the steps make, replaceable in tests."""

    google_by_isbn: Callable = search_google_books_by_isbn
    google_by_title: Callable = search_google_books
    openlibrary_by_isbn: Callable = search_open_library_by_isbn
    openlibrary_by_title: Callable = search_open_library
    # The offline Open Library database (RedactEnv.openlibrary_local is its path):
    # (path, isbn) and (path, title, authors, year); both read a local file.
    local_by_isbn: Callable = local_search_by_isbn
    local_by_title: Callable = local_search_by_title
    cover_by_isbn: Callable = fetch_cover_by_isbn
    cover_by_id: Callable = fetch_cover_by_id  # an Open Library cover id (from the local database match)
    download_google_cover: Callable = download_google_cover


@dataclass
class RedactEnv:
    """What the steps of one run share: the app's rename/move settings,
    the rename log, the trash function (None = the Recycle Bin), the
    lookups and how to call them (`net` lets the GUI run them off the
    main thread), the cover renderer and image sizer the GUI provides,
    and what to record for Undo Last Rename once the run is over."""

    trash: Callable[[str], None] | None = None
    rename_log: Any = None  # anything with .record(label, pairs, created_dirs=, trashed=, root=)
    library_root: str = ""
    ascii_only: bool = False
    zero_pad: tuple[bool, int] = (False, 2)
    junk_hashes: set = field(default_factory=set)
    make_cover: Callable[[str, str, str, str], bytes] | None = None  # (title, authors, series, index) -> PNG bytes
    image_size: Callable[[bytes], tuple[int, int] | None] | None = None
    net: Callable[..., Any] = _call_directly
    lookups: Lookups = field(default_factory=Lookups)
    openlibrary_local: str = ""  # path of the offline Open Library database ("" = none set up)
    # filled during a run
    touched: dict = field(default_factory=dict)  # live book -> its final path
    renames: list = field(default_factory=list)  # (old, new) for the rename step
    moves: list = field(default_factory=list)  # (old, new) for the move step
    created_dirs: list = field(default_factory=list)
    trashed: list = field(default_factory=list)
    stopped: dict = field(default_factory=dict)  # service -> why it is not asked again this run
    _taken_rename: set = field(default_factory=set)
    _taken_move: set = field(default_factory=set)
    _cache: dict = field(default_factory=dict)

    def begin(self) -> None:
        """Call before each run."""
        self.touched.clear()
        self.renames.clear()
        self.moves.clear()
        self.created_dirs.clear()
        self.trashed.clear()
        self.stopped.clear()
        self._taken_rename.clear()
        self._taken_move.clear()
        self._cache.clear()

    def cached(self, key: tuple, fn: Callable[[], Any]) -> Any:
        """Memoized result of a lookup several steps may ask for (an
        exception is not remembered, so the next book tries again)."""
        if key not in self._cache:
            self._cache[key] = fn()
        return self._cache[key]

    def lookup(self, service: str, fn: Callable, *args: Any) -> Any:
        """One network call through `net`. A rate-limit answer stops that
        service for the rest of the run (the error is re-raised for the
        caller to turn into a note, then StoppedError for later books)."""
        if service in self.stopped:
            raise StoppedError(self.stopped[service])
        try:
            return self.net(fn, *args)
        except (GoogleBooksLookupError, OpenLibraryLookupError, IsbnCoverLimitError) as exc:
            if "rate-limit" in str(exc) or isinstance(exc, IsbnCoverLimitError):
                self.stopped[service] = str(exc)
            raise

    def flush_log(self) -> None:
        """Call once after the run: one Undo Last Rename batch for the
        renames and one for the moves (renames first, so undo reverses
        them in the opposite order they happened)."""
        if self.rename_log is None:
            return
        self.rename_log.record("Redact: rename", list(self.renames))
        self.rename_log.record(
            "Redact: move into folders", list(self.moves), created_dirs=list(self.created_dirs),
            trashed=list(self.trashed), root=os.path.abspath(self.library_root) if self.library_root else "",
        )

    def notes_text(self) -> str:
        return "\n".join(f"{service}: {why}" for service, why in self.stopped.items())


class StoppedError(Exception):
    """A lookup service was already refused earlier in this run."""


# --- per-book context ------------------------------------------------------


# commit_in_place() rolls back completely when it fails at these two points, so
# trying again is safe. On Windows a virus scanner or the search indexer often
# holds a freshly written file for a moment, which shows up as exactly these.
_TRANSIENT_COMMIT_MESSAGES = ("couldn't set the original aside", "couldn't put the new file in place")


def _retry_transient(fn: Callable, exc_type: type, only_if: Callable[[Exception], bool] | None = None,
                     attempts: int = 4, delay: float = 0.3) -> Any:
    for attempt in range(attempts):
        try:
            return fn()
        except exc_type as exc:
            if attempt == attempts - 1 or (only_if is not None and not only_if(exc)):
                raise
            time.sleep(delay)


def _unused_sibling(original: str) -> str:
    """A not-yet-existing file name next to `original` for the new copy
    (same folder, so the final swap is an atomic rename)."""
    stem, ext = os.path.splitext(original)
    while True:
        candidate = f"{stem[:200]}.redact-{uuid.uuid4().hex[:8]}{ext or '.epub'}"
        if not os.path.lexists(candidate):
            return candidate


class _SaveProblem(Exception):
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind  # "failed" | "skipped"


def _stat_of(path: str) -> tuple[int, int] | None:
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


class EpubCtx:
    """One book's working state for the steps (see the module docstring).
    `work` is None when the book is not processed; `skip_reason` says why."""

    def __init__(self, live: EpubBook, env: RedactEnv):
        self.live = live
        self.env = env
        self.step_options: dict = {}  # set by the engine before each step
        self.work: EpubBook | None = None
        self.skip_reason = ""
        self.current_path = live.path  # follows the rename/move steps
        self.save_problem: _SaveProblem | None = None
        self.save_result: StepResult | None = None
        self._save_done = False
        self._temp: str | None = None
        self._stat: tuple[int, int] | None = None
        self._initial_codes: set[str] = set()
        self._scan: ContentScanResult | None = None
        self._scan_done = False
        self._prepare()

    def _prepare(self) -> None:
        live = self.live
        if live.load_error:
            self.skip_reason = f"it could not be loaded ({live.load_error})"
        elif live.dirty and not live.stamp_only_dirty:
            self.skip_reason = "it has unsaved edits in the list (save or discard them, then run Redact again)"
        if self.skip_reason:
            return
        self._stat = _stat_of(live.path)
        try:
            work = EpubBook(live.path)
        except Exception as exc:  # noqa: BLE001 -- one bad file must not stop the run
            self.skip_reason = f"it could not be read ({exc})"
            return
        if work.load_error:
            self.skip_reason = f"it could not be read ({work.load_error})"
        elif any(i.code == "DRM_DETECTED" for i in work.validation_issues):
            self.skip_reason = "it is DRM-protected and left untouched"
        else:
            self.work = work
            self._initial_codes = {i.code for i in work.validation_issues}

    def scan(self) -> ContentScanResult | None:
        """The Scan Content result, computed once per book (the language
        step and the four scan steps share it)."""
        if not self._scan_done:
            self._scan_done = True
            try:
                self._scan = scan_book(self.work)
            except Exception:  # noqa: BLE001 -- a book the scanner chokes on just yields no suggestions
                self._scan = None
        return self._scan

    # -- saving ---------------------------------------------------------------

    def ensure_saved(self) -> bool:
        """Saves the working copy in place (once) if it has changes.
        False when that failed or was refused; the reason is in
        save_problem and save_finalize() reports it."""
        if self._save_done:
            return self.save_problem is None
        self._save_done = True
        # A pending validation stamp alone is not a change (the same rule as
        # cbzredactor): a book no step touched is left as it is, unstamped, until
        # the user runs Validate / Fix Issues. The stamp rides along only when the
        # book is saved anyway (any other edit clears stamp_only_dirty).
        if not self.work.dirty or self.work.stamp_only_dirty:
            return True
        if self.work._stamp_follows_save:  # noqa: SLF001
            # Later steps (dedupe, rebuild, repair...) may have fixed things since the
            # validate_fix step stamped: re-check the working tree so the stamp carries
            # the verdict of what is about to be written.
            self.work.revalidate()
            self.work.record_validation(follow_save=True)
        try:
            self.save_result = self._save()
        except _SaveProblem as problem:
            self.save_problem = problem
            return False
        return True

    def _save(self) -> StepResult:
        work, original = self.work, self.live.path
        if _stat_of(original) != self._stat:
            raise _SaveProblem("skipped", "the file was changed by something else while Redact worked on it")
        try:
            with zipfile.ZipFile(original) as zf:
                expected = set(zf.namelist()) - set(work._orphan_files_to_remove)  # noqa: SLF001
        except (zipfile.BadZipFile, OSError) as exc:
            raise _SaveProblem("failed", f"couldn't read the original again ({exc})") from exc
        temp = _unused_sibling(original)
        self._temp = temp
        try:
            _retry_transient(lambda: work.save(temp), OSError)
        except (EpubError, OSError) as exc:
            raise _SaveProblem("failed", f"couldn't write the new file ({exc})") from exc
        try:
            done = _retry_transient(
                lambda: commit_in_place(
                    original, temp, trash=self.env.trash or move_to_trash,
                    verify=lambda path: self._verify(path, expected),
                ),
                CommitError, only_if=lambda exc: any(m in str(exc) for m in _TRANSIENT_COMMIT_MESSAGES),
            )
        except CommitError as exc:
            raise _SaveProblem("failed", str(exc)) from exc
        self._temp = None
        self._stat = _stat_of(original)
        work.dirty = False
        self.env.touched[self.live] = self.current_path
        changes = ["saved in place (the original is in the Recycle Bin)"]
        if done.warning:
            return StepResult(StepStatus.APPLIED, changes=changes, note=done.warning)
        return StepResult.applied(*changes)

    def _verify(self, path: str, expected_names: set[str]) -> bool:
        """The new file must be a sound EPUB that still holds everything
        the original did (bar what was meant to go) and is no more broken
        than the original was. Raises with the reason; commit_in_place
        turns that into "original left untouched"."""
        with zipfile.ZipFile(path) as zf:
            bad = zf.testzip()
            if bad:
                raise ValueError(f"the new file has a corrupt entry ({bad})")
            names = zf.namelist()
        missing = expected_names - set(names)
        if missing:
            raise ValueError(f"the new file lost {len(missing)} file(s), e.g. {sorted(missing)[0]}")
        if names[0] != "mimetype":
            raise ValueError("the new file's mimetype entry is not first")
        book = EpubBook(path)
        if book.load_error:
            raise ValueError(f"the new file does not open again ({book.load_error})")
        new_bad = {
            i.code for i in book.validation_issues
            if (i.severity == SEVERITY_ERROR or i.code == "DANGLING_SPINE_ITEMREF")
            and i.code not in self._initial_codes
        }
        if new_bad:
            raise ValueError(f"the new file has new problems ({', '.join(sorted(new_bad))})")
        work = self.work
        if book.metadata.title != work.metadata.title or book.metadata.authors != work.metadata.authors:
            raise ValueError("the new file's title/authors are not what was written")
        if work.cover_changed and book.cover_bytes != work.cover_bytes:
            raise ValueError("the new file's cover is not the one that was written")
        if work.cover_bytes and not work.cover_changed and not book.cover_bytes:
            raise ValueError("the new file lost its cover")
        return True

    def close(self) -> None:
        """Called by the engine after each book: a temp file left behind
        by a failed save goes away (the original was never touched)."""
        if self._temp and os.path.exists(self._temp):
            try:
                os.remove(self._temp)
            except OSError:
                pass
        self._temp = None


def save_finalize(ctx: EpubCtx, file_report: FileReport) -> StepResult | None:
    """The engine's `finalize` hook: the save (unless a pinned rename/move
    step already triggered it). When the save did not happen, the changes
    listed so far were never written, so they are withdrawn from the
    report and named in the failure/skip message instead."""
    if ctx.ensure_saved():
        return ctx.save_result
    problem = ctx.save_problem
    lost = [line for line in file_report.applied]
    file_report.applied.clear()
    detail = f" (not saved: {'; '.join(lost[:3])}{'; ...' if len(lost) > 3 else ''})" if lost else ""
    if problem.kind == "skipped":
        return StepResult.skipped(f"{problem}{detail}")
    return StepResult.failed(f"{problem}{detail}")


# --- steps ------------------------------------------------------------------


class GuardStep(Step):
    """Internal, always first, not offered in the recipe editor: a book
    that must not be processed ends here as SKIPPED."""

    key = "guard"
    label = "Check the book"

    def run(self, ctx: EpubCtx) -> StepResult:
        if ctx.skip_reason:
            return StepResult.skipped(ctx.skip_reason)
        return StepResult.nothing()


class ValidateFixStep(Step):
    key = "validate_fix"
    label = "Fix validation issues"
    description = (
        "Applies the fixes Validate / Fix Issues offers: repairs a broken unique-identifier, splits "
        "'A & B' into two authors, drops spine entries that point at nothing. (The 'set a missing "
        "language to en' fix is not used; the language step guesses from the text instead.)"
    )

    def run(self, ctx: EpubCtx) -> StepResult:
        work = ctx.work
        fixable = {i.code for i in work.validation_issues if i.fixable and i.code in SAFE_FIX_CODES}
        fixed = work.apply_fixes(fixable) if fixable else []
        # The verdict after the fixes goes into the file as the validation stamp,
        # but only if the book is saved anyway (see ensure_saved). A book whose stamp already matches (same files, same verdict) is
        # left alone, so a re-run doesn't rewrite every book just to move a
        # timestamp. follow_save: later steps (cover, toc) change content files
        # before the save, so the fingerprint is taken from what gets written.
        stamp = work.scan_stamp
        if fixed or stamp is None or work.stamp_stale is not False or stamp.status != work.validation_status:
            work.record_validation(follow_save=True)
        return StepResult.applied(*fixed) if fixed else StepResult.nothing()


class DedupeManifestIdsStep(Step):
    key = "dedupe_manifest_ids"
    label = "Deduplicate manifest IDs"
    description = "Gives the second and later manifest items that share an id a fresh id (Repair > Deduplicate Manifest IDs)."

    def run(self, ctx: EpubCtx) -> StepResult:
        renames = ctx.work.dedupe_manifest_ids()
        return StepResult.applied(*(f"manifest id {old} -> {new}" for old, new in renames)) if renames else StepResult.nothing()


class RebuildManifestStep(Step):
    key = "rebuild_manifest"
    label = "Rebuild manifest"
    description = (
        "Removes manifest items whose files are missing from the book, and the spine entries that "
        "use them (Repair > Rebuild Manifest). Web addresses (remote resources) are not touched."
    )

    def run(self, ctx: EpubCtx) -> StepResult:
        missing = {
            item_id for item_id, href in ctx.work.find_missing_manifest_files()
            if item_id and not _URL_SCHEME_RE.match(href)
        }
        if not missing:
            return StepResult.nothing()
        removed = ctx.work.rebuild_manifest(missing)
        return StepResult.applied(*(f"removed missing {href}" for href in removed)) if removed else StepResult.nothing()


class RepairNavigationStep(Step):
    key = "repair_navigation"
    label = "Repair navigation"
    description = "Removes <guide> references that point at files that do not exist (Repair > Repair Navigation)."
    options = (
        OptionSpec(
            "remove_orphans", "Also remove orphaned files", "bool", False,
            tooltip="Files in the book that no manifest item refers to. Off by default: removing files is not reversible "
                    "except through the Recycle Bin copy of the original.",
        ),
    )

    def run(self, ctx: EpubCtx) -> StepResult:
        work = ctx.work
        changes = [f"removed broken guide reference {href}" for href in work.repair_guide_references()]
        if self.options_for(ctx)["remove_orphans"]:
            changes += [f"removed orphaned file {path}" for path in work.remove_orphaned_files()]
        return StepResult.applied(*changes) if changes else StepResult.nothing()


@dataclass
class TocPlan:
    entries: list
    confidence: float

    def __str__(self) -> str:
        shown = ", ".join(f'"{e.title}"' for e in self.entries[:3])
        return f"{len(self.entries)} entries: {shown}{', ...' if len(self.entries) > 3 else ''}"


class GenerateTocStep(Step):
    key = "generate_toc"
    label = "Generate table of contents"
    description = (
        "For a book with no table of contents, builds one from its headings (Repair > Generate Table of "
        "Contents). A list of headings is applied automatically; a 'Section 1, Section 2...' fallback is "
        "low confidence and goes to Needs review."
    )

    def run(self, ctx: EpubCtx) -> StepResult:
        if not needs_toc(ctx.work):
            return StepResult.nothing()
        entries = generate_toc_entries(ctx.work)
        if not entries:
            return StepResult.nothing(note="no table of contents could be built (nothing usable in the reading order)")
        generic = sum(1 for e in entries if _SECTION_TITLE_RE.match(e.title))
        if len(entries) < 2 or generic == len(entries):
            confidence, why = TOC_FALLBACK_CONFIDENCE, "no headings to build it from, only generic section labels"
        elif generic:
            confidence, why = TOC_PARTIAL_CONFIDENCE, "some parts have no heading and got a generic label"
        else:
            confidence, why = TOC_HEADINGS_CONFIDENCE, "built from the book's own headings"
        return StepResult.suggestion(TocPlan(entries, confidence), confidence, why)

    def apply_suggestion(self, ctx: EpubCtx, result: StepResult) -> str:
        stage_generated_toc_for(ctx.work, result.value.entries)
        return f"generated a table of contents ({len(result.value.entries)} entries)"


class StripDescriptionHtmlStep(Step):
    key = "strip_description_html"
    label = "Strip HTML from description"
    description = "Turns markup in the description into plain text (Repair > Strip HTML from Description)."

    def run(self, ctx: EpubCtx) -> StepResult:
        text = ctx.work.metadata.description
        if not has_html_markup(text):
            return StepResult.nothing()
        ctx.work.apply_metadata({"description": strip_html(text)})
        return StepResult.applied("description: removed HTML markup")


class CleanAuthorsStep(Step):
    key = "clean_authors"
    label = "Clean up authors"
    description = (
        "Tidies Author(s) and Author Sort with the deterministic fixes of Repair > Clean Up Authors: spacing and "
        "initials, role suffixes and 'et al.', 'Last, First' to 'First Last', duplicates, a generated or tidied "
        "sort value. Guesses (splitting 'Simon & Schuster', removing 'Dr.', a sort value that disagrees with the "
        "author) are never applied here; they are named in the report notes."
    )

    def run(self, ctx: EpubCtx) -> StepResult:
        md = ctx.work.metadata
        result = clean_authors(md.authors, md.author_sort, allow_review=False)
        held = [f"needs review: {c}" for c in result.review] + [f"flag: {f}" for f in result.flags]
        note = "authors: " + "; ".join(held) if held else ""
        if not result.changed:
            return StepResult.nothing(note=note)
        ctx.work.apply_metadata({
            "authors_str": "; ".join(result.authors),
            "author_sort_str": "; ".join(result.author_sort),
        })
        done = StepResult.applied(*(f"authors {c}" for c in result.changes))
        done.note = note
        return done


class LanguageStep(Step):
    key = "language"
    label = "Detect language"
    description = "When the language is blank or unknown, guesses it from the book's text (en, no, it, de, fr)."

    def run(self, ctx: EpubCtx) -> StepResult:
        if not is_blank_or_unknown_language(ctx.work.metadata.language):
            return StepResult.nothing()
        scan = ctx.scan()
        if scan is None or not scan.language:
            return StepResult.nothing(note="the language is blank and could not be detected")
        return StepResult.suggestion(scan.language, scan.language_confidence, scan.language_evidence)

    def apply_suggestion(self, ctx: EpubCtx, result: StepResult) -> str:
        ctx.work.apply_metadata({"language": result.value})
        return f"language = {result.value}"


@dataclass
class SeriesGuess:
    name: str
    index: str

    def __str__(self) -> str:
        return f"{self.name} #{self.index}" if self.index else self.name


class _ScanFieldStep(Step):
    """One fact from the front matter (Scan Content), filled only when
    the field is empty, at the confidence the scanner gives that fact.
    One step per fact so each can be switched off and each is judged on
    its own confidence."""

    field = ""  # the ContentScanResult / metadata attribute
    noun = ""  # how the change reads in the report

    def current(self, ctx: EpubCtx) -> str:
        return getattr(ctx.work.metadata, self.field)

    def found(self, scan: ContentScanResult) -> Any:
        return getattr(scan, self.field)

    def run(self, ctx: EpubCtx) -> StepResult:
        if self.current(ctx):
            return StepResult.nothing()
        scan = ctx.scan()
        value = self.found(scan) if scan is not None else ""
        if not value:
            return StepResult.nothing()
        return StepResult.suggestion(
            value, scan.confidence.get(self.field, 0.0), scan.source_snippets.get(self.field, "found in the front matter")
        )

    def apply_suggestion(self, ctx: EpubCtx, result: StepResult) -> str:
        ctx.work.apply_metadata({self.field: result.value})
        return f"{self.noun} = {result.value}"


class ScanIsbnStep(_ScanFieldStep):
    key = "scan_isbn"
    label = "Scan ISBN"
    description = "Fills an empty ISBN from the front matter (a checksummed ISBN is certain, so it is applied)."
    field = "isbn"
    noun = "ISBN"

    def found(self, scan: ContentScanResult) -> str:
        return scan.isbn if is_valid_isbn(scan.isbn) else ""


class ScanPublisherStep(_ScanFieldStep):
    key = "scan_publisher"
    label = "Scan publisher"
    description = "Fills an empty publisher from the front matter, at the scanner's confidence."
    field = "publisher"
    noun = "Publisher"


class ScanYearStep(_ScanFieldStep):
    key = "scan_year"
    label = "Scan year"
    description = "Fills an empty publication year from the copyright/first-published line, at the scanner's confidence."
    field = "pub_year"
    noun = "Year"


class ScanSeriesStep(_ScanFieldStep):
    key = "scan_series"
    label = "Scan series"
    description = "Fills an empty series (and volume) from the front matter, at the scanner's confidence."
    field = "series"

    def found(self, scan: ContentScanResult) -> SeriesGuess | None:
        return SeriesGuess(scan.series, scan.series_index) if scan.series else None

    def apply_suggestion(self, ctx: EpubCtx, result: StepResult) -> str:
        ctx.work.apply_metadata({"series": result.value.name, "series_index": result.value.index})
        return f"Series = {result.value}"


class FieldFill(dict):
    """The fields an online match would fill, for the report."""

    def __str__(self) -> str:
        return "; ".join(f"{_FIELD_NAMES.get(k, k)}: {v[:40]}" for k, v in self.items())


def _norm_text(text: str) -> str:
    return " ".join(re.sub(r"[\W_]+", " ", (text or "").casefold()).split())


def _surnames(authors: Iterable[str]) -> set[str]:
    names = set()
    for author in authors:
        parts = _norm_text(author.split(",")[0] if "," in author else author).split()
        if parts:
            names.add(parts[0] if "," in author else parts[-1])
    return names


class MetadataLookupStep(Step):
    key = "metadata_lookup"
    # The key stays "metadata_lookup" (saved recipes refer to it); only the label changed.
    label = "Fill empty fields from lookups (local database first)"
    description = (
        "Fills EMPTY fields (author, publisher, year, ISBN, genre, language, description) from your local "
        "Open Library database first (when one is set up under Tools > Open Library Database; works offline), "
        "then Google Books and Open Library online for whatever is still empty. A match on the book's own "
        "ISBN is trusted (95%); a match on title and author is a guess and goes to Needs review. Fields that "
        "already have a value are never changed."
    )

    def run(self, ctx: EpubCtx) -> StepResult:
        meta = ctx.work.metadata
        blanks = self._blank_fields(ctx)
        if not blanks:
            return StepResult.nothing()
        isbn = best_isbn13(meta.isbn)
        if not isbn and not meta.title.strip():
            return StepResult.nothing()
        problems: list[str] = []
        fill: dict[str, str] = {}
        confidence = 1.0
        reasons: list[str] = []
        # The local database first; the online sources only for what it left empty.
        for source in (self._local_source, self._online_source):
            remaining = blanks - fill.keys()
            if not remaining:
                break
            found = source(ctx, isbn, problems)
            if found is None:
                continue
            candidate, match_confidence, reason = found
            added = {k: v for k, v in candidate.as_dict().items() if k in remaining and v}
            if "description" in added:
                added["description"] = strip_html(added["description"])
            if added:
                fill.update(added)
                confidence = min(confidence, match_confidence)
                reasons.append(reason)
        if not fill:
            return StepResult.nothing(note="; ".join(problems) if problems else "")
        return StepResult.suggestion(FieldFill(fill), confidence, "; ".join(reasons))

    def _local_source(self, ctx: EpubCtx, isbn: str, problems: list[str]):
        """The offline Open Library database, when one is set up (None otherwise)."""
        if not ctx.env.openlibrary_local:
            return None
        return self._by_isbn_local(ctx, isbn, problems) if isbn else self._by_title(ctx, problems, local=True)

    def _online_source(self, ctx: EpubCtx, isbn: str, problems: list[str]):
        return self._by_isbn(ctx, isbn, problems) if isbn else self._by_title(ctx, problems)

    @staticmethod
    def _blank_fields(ctx: EpubCtx) -> set[str]:
        m = ctx.work.metadata
        blanks = set()
        if not m.authors:
            blanks.add("authors_str")
        if not m.publisher:
            blanks.add("publisher")
        if not m.pub_year:
            blanks.add("pub_year")
            # A month/day only comes along with its year (a lone month is meaningless).
            blanks.update(k for k, v in (("pub_month", m.pub_month), ("pub_day", m.pub_day)) if not v)
        if not m.isbn:
            blanks.add("isbn")
        if not m.tags:
            blanks.add("tags_str")
        if is_blank_or_unknown_language(m.language):
            blanks.add("language")
        if not m.description.strip():
            blanks.add("description")
        return blanks

    def _ask(self, ctx: EpubCtx, service: str, fn: Callable, arg: Any, args: tuple, problems: list[str]):
        """Cached lookup; None (with a problem noted) when it failed."""
        env = ctx.env
        try:
            return env.cached((service, arg, args), lambda: env.lookup(service, fn, *((arg,) + args)))
        except StoppedError:
            return None  # said once in the report header notes (env.notes_text)
        except (GoogleBooksLookupError, OpenLibraryLookupError, OpenLibraryLocalError) as exc:
            problems.append(f"{service} lookup failed: {exc}")
            return None

    def _by_isbn_local(self, ctx: EpubCtx, isbn: str, problems: list[str]):
        env = ctx.env
        for c in self._ask(ctx, LOCAL_OPEN_LIBRARY, env.lookups.local_by_isbn, env.openlibrary_local, (isbn,), problems) or []:
            return c, ISBN_MATCH_CONFIDENCE, f"{LOCAL_OPEN_LIBRARY} lists this exact ISBN ({isbn})"
        return None

    def _by_isbn(self, ctx: EpubCtx, isbn: str, problems: list[str]):
        lookups = ctx.env.lookups
        for c in self._ask(ctx, "Google Books", lookups.google_by_isbn, isbn, (), problems) or []:
            if isbn in (best_isbn13(c.isbn13), best_isbn13(c.isbn10)):
                return c, ISBN_MATCH_CONFIDENCE, f"Google Books lists this exact ISBN ({isbn})"
        for c in self._ask(ctx, "Open Library", lookups.openlibrary_by_isbn, isbn, (), problems) or []:
            return c, ISBN_MATCH_CONFIDENCE, f"Open Library lists this exact ISBN ({isbn})"
        return None

    def _by_title(self, ctx: EpubCtx, problems: list[str], local: bool = False):
        meta, env = ctx.work.metadata, ctx.env
        lookups = env.lookups
        title, authors = meta.title.strip(), meta.authors_str
        wanted = _surnames(meta.authors)
        title_key = _norm_text(title)
        if local:  # the local functions take the database path first, and the year to rank by
            asks = [(LOCAL_OPEN_LIBRARY, lookups.local_by_title, env.openlibrary_local, (title, authors, meta.pub_year))]
        else:
            asks = [("Google Books", lookups.google_by_title, title, (authors,)),
                    ("Open Library", lookups.openlibrary_by_title, title, (authors,))]
        for service, fn, first, rest in asks:
            for c in self._ask(ctx, service, fn, first, rest, problems) or []:
                # The edition's title alone, or with its subtitle, must be the book's title.
                subtitle = getattr(c, "subtitle", "")
                if title_key not in (_norm_text(c.title), _norm_text(f"{c.title} {subtitle}") if subtitle else None):
                    continue
                got = _surnames(a for a in c.authors_str.split(";") if a.strip())
                if wanted and got & wanted:
                    return c, TITLE_AUTHOR_CONFIDENCE, f"{service} has a book with this title and author (no ISBN to confirm)"
                if not wanted:
                    return c, TITLE_ONLY_CONFIDENCE, f"{service} has a book with this title (no author or ISBN to confirm)"
        return None

    def apply_suggestion(self, ctx: EpubCtx, result: StepResult) -> list[str]:
        blanks = self._blank_fields(ctx)
        fill = {k: v for k, v in result.value.items() if k in blanks}  # never over a value set meanwhile
        ctx.work.apply_metadata(fill)
        return [f"{_FIELD_NAMES.get(k, k)} = {v[:60]}" for k, v in fill.items()]


def _sniff_mime(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return ""


@dataclass
class CoverCandidate:
    data: bytes
    mime: str
    source: str
    size: tuple[int, int] | None = None

    def __str__(self) -> str:
        dims = f"{self.size[0]}x{self.size[1]}, " if self.size else ""
        return f"cover from {self.source} ({dims}{len(self.data) // 1024} KB)"


class CoverStep(Step):
    key = "cover"
    label = "Cover"
    description = (
        "For a book with no cover, or one flagged as a junk cover: fetches the cover for the book's own ISBN "
        "(the local Open Library database's cover id first when one is set up, then Open Library by ISBN, then "
        "Google Books; a match on the ISBN is applied). A book with no cover at all that "
        "has no online match gets a generated placeholder cover from its metadata. A flagged junk cover with "
        "no match is left as it is."
    )

    def run(self, ctx: EpubCtx) -> StepResult:
        work, env = ctx.work, ctx.env
        has_cover = bool(work.cover_bytes)
        junk = has_cover and work.cover_hash in env.junk_hashes
        if has_cover and not junk:
            return StepResult.nothing()
        if work.cover_is_encrypted():
            return StepResult.nothing(note="the cover is DRM-encrypted and left alone")
        isbn = best_isbn13(work.metadata.isbn)
        problem = ""
        if isbn:
            candidate, problem = self._fetch(ctx, isbn)
            if candidate is not None:
                return StepResult.suggestion(candidate, COVER_ISBN_CONFIDENCE, f"{candidate.source} has a cover for this exact ISBN ({isbn})")
        if junk:
            return StepResult.nothing(note="flagged junk cover kept: " + (problem or "no cover found for its ISBN"))
        if problem:
            return StepResult.nothing(note=f"no cover added: {problem}")  # retry next time rather than a placeholder
        if env.make_cover is None:
            return StepResult.nothing(note="no cover, and no way to generate one here")
        m = work.metadata
        image = env.make_cover(m.title, m.authors_str, m.series, m.series_index)
        if not work.set_cover(image, "image/png"):
            return StepResult.nothing(note="the cover is DRM-encrypted and left alone")
        return StepResult.applied("generated a cover from the metadata")

    def _usable(self, env: RedactEnv, data: bytes | None) -> tuple[str, tuple[int, int] | None]:
        mime = _sniff_mime(data or b"")
        if not mime:
            return "", None
        size = env.image_size(data) if env.image_size else None
        if env.image_size and (size is None or size[0] < MIN_COVER_WIDTH):
            return "", None
        return mime, size

    def _local_cover(self, ctx: EpubCtx, isbn: str) -> CoverCandidate | None:
        """With a local Open Library database: its exact-ISBN match's cover id,
        fetched straight from covers.openlibrary.org/b/id/<id> (the same size
        cap, validity and minimum-width checks as any other cover) instead of
        searching again. Any problem just falls through to the ordinary sources."""
        env, lookups = ctx.env, ctx.env.lookups
        if not env.openlibrary_local:
            return None
        try:
            matches = env.cached(
                (LOCAL_OPEN_LIBRARY, env.openlibrary_local, (isbn,)),
                lambda: env.lookup(LOCAL_OPEN_LIBRARY, lookups.local_by_isbn, env.openlibrary_local, isbn),
            )
        except (StoppedError, OpenLibraryLocalError):
            return None  # the metadata step notes a broken database; covers just carry on
        for match in matches or []:
            if match.cover_id > 0:
                try:
                    data = env.cached(
                        ("ol cover id", match.cover_id),
                        lambda: env.lookup("Open Library covers", lookups.cover_by_id, match.cover_id),
                    )
                except (StoppedError, IsbnCoverError):
                    return None
                mime, size = self._usable(env, data)
                if mime:
                    return CoverCandidate(data, mime, f"{LOCAL_OPEN_LIBRARY} match (cover id {match.cover_id})", size)
                return None
        return None

    def _fetch(self, ctx: EpubCtx, isbn: str) -> tuple[CoverCandidate | None, str]:
        """(candidate, "") when found; (None, "") when the sources
        definitively have none; (None, why) when a source could not be asked."""
        env, lookups = ctx.env, ctx.env.lookups
        why = ""
        local = self._local_cover(ctx, isbn)
        if local is not None:
            return local, ""
        try:
            data = env.cached(("ol cover", isbn), lambda: env.lookup("Open Library covers", lookups.cover_by_isbn, isbn))
            mime, size = self._usable(env, data)
            if mime:
                return CoverCandidate(data, mime, "Open Library", size), ""
        except StoppedError as exc:
            why = str(exc)
        except IsbnCoverError as exc:
            why = str(exc)
        try:
            cands = env.cached(
                ("Google Books", isbn, ()), lambda: env.lookup("Google Books", lookups.google_by_isbn, isbn)
            )
            for c in cands:
                if c.cover_url and isbn in (best_isbn13(c.isbn13), best_isbn13(c.isbn10)):
                    data = env.lookup("Google Books", lookups.download_google_cover, c)
                    mime, size = self._usable(env, data)
                    if mime:
                        return CoverCandidate(data, mime, "Google Books", size), ""
        except StoppedError as exc:
            why = why or str(exc)
        except GoogleBooksLookupError as exc:
            why = why or str(exc)
        return None, why

    def apply_suggestion(self, ctx: EpubCtx, result: StepResult) -> str:
        cand: CoverCandidate = result.value
        if not ctx.work.set_cover(cand.data, cand.mime):
            raise RuntimeError("the cover is DRM-encrypted")
        return f"cover replaced ({cand.source})"


DEFAULT_PATH_PATTERN = "%authors%/%series%/%title%"

# Pattern trail (redactor_common 2026-09-30-12): a recipe keeps the pattern
# that was saved in it; an EMPTY stored pattern follows the app's current
# one. So every pattern option's spec default is "" and the app's pattern
# is its `fallback`; resolve with effective_option_source(), never
# options_for() alone.
SAMPLE_VALUES = {
    "title": "The Long Way Home", "authors": "Jane Author", "series": "Sample Saga",
    "series_index": "2", "year": "2019", "publisher": "Example Press",
}


def _sample_values(sample: Callable[[], dict[str, str] | None] | None) -> dict[str, str]:
    """The first loaded book's placeholder values when the app gives
    them, else a built-in sample; never raises."""
    try:
        values = sample() if sample is not None else None
    except Exception:  # noqa: BLE001 - a preview must never break the editor
        values = None
    return values if values else dict(SAMPLE_VALUES)


def _pattern_spec(
    tooltip: str, fallback: Callable[[], str], label: str, history: Callable[[], list[str]] | None,
    sample: Callable[[], dict[str, str] | None] | None, as_path: bool,
) -> OptionSpec:
    def preview(pattern: str) -> str:
        try:
            values = _sample_values(sample)
            if as_path:
                return "/".join(render_relative_path(values, pattern)) + ".epub"
            return shared_rename.render_filename(values, pattern) + ".epub"
        except Exception:  # noqa: BLE001
            return ""

    return OptionSpec(
        "pattern", "Pattern", "str", "", max_length=300, tooltip=tooltip,
        suggestions=history if history is not None else (lambda: []),
        fallback=fallback, fallback_label=label, preview=preview,
    )


def _effective_pattern(step: Step, ctx: EpubCtx) -> str:
    """The pattern this step runs with: the recipe's stored one, or the
    fallback while it is empty."""
    value, _source = effective_option_source(step.options[0], step.options_for(ctx)["pattern"])
    return value.strip()


def pin_pattern_options(recipe: Recipe, catalogue: list[Step]) -> Recipe:
    """First-save pinning: a copy of `recipe` where every EMPTY pattern
    option holds its current effective value, so saving the recipe keeps
    today's patterns instead of following later changes."""
    options = {k: dict(v) for k, v in recipe.options.items()}
    for step in catalogue:
        for spec in step.options:
            if spec.kind != "str" or spec.fallback is None:
                continue
            current = options.setdefault(step.key, {})
            if not current.get(spec.key):
                pinned, _source = effective_option_source(spec, "")
                if pinned:
                    current[spec.key] = pinned
    return Recipe(
        order=list(recipe.order), enabled=dict(recipe.enabled), options=options,
        confidence_threshold=recipe.confidence_threshold,
    )


def _is_under(path: str, root: str) -> bool:
    try:
        root_abs = os.path.normcase(os.path.abspath(root))
        return os.path.commonpath([root_abs, os.path.normcase(os.path.abspath(path))]) == root_abs
    except ValueError:  # different drives
        return False


class PathTagsStep(Step):
    key = "path_tags"
    label = "Fill empty fields from the folder path"
    description = (
        "Fills EMPTY fields from the folders the file sits in, read against the library root chosen in "
        "File > Rename Files (Pattern) > Move into folders (the reverse of Move into folders). Needs a library "
        "root and a file under it. Applied at or above the confidence threshold, else listed for review."
    )

    def __init__(self, pattern: str = "", default_enabled: bool | None = None, history=None, sample=None):
        # While the recipe's pattern is empty it follows the most recent
        # saved PATH pattern (else the built-in one).
        self.options = (
            _pattern_spec(
                "Folders and file name under the library root, e.g. %authors%/%series%/%title%",
                lambda: pattern or DEFAULT_PATH_PATTERN,
                "the last folder pattern used in Rename/Export" if pattern else "the built-in folder pattern",
                history, sample, as_path=True,
            ),
        )
        super().__init__(default_enabled=True if default_enabled is None else default_enabled)

    def run(self, ctx: EpubCtx) -> StepResult:
        pattern = _effective_pattern(self, ctx)
        env = ctx.env
        if not is_path_pattern(pattern):
            return StepResult.nothing(note="the folder pattern needs a / between folder and file name parts")
        if not env.library_root or not os.path.isdir(env.library_root):
            return StepResult.nothing(
                note="no library root is set (choose one in File > Rename Files (Pattern) > Move into folders)"
            )
        if not _is_under(ctx.live.path, env.library_root):
            return StepResult.nothing(note="not under the library root, so its folders were not read")

        def metadata_counts(directory: str, field: str) -> dict[str, int]:
            return env.cached(
                ("folder_metadata", directory, field), lambda: folder_metadata_field_counts(directory, field)
            )

        parsed = parse_book_path(
            ctx.live.path, pattern, env.library_root,
            path_corroborator(ctx.live.path, None, metadata_counts, ctx.live.metadata),
        )
        if not parsed.matched:
            return StepResult.nothing(note="folder pattern: " + " ".join(parsed.notes[:1]))
        current = placeholder_values(ctx.work.metadata)
        fills = {k: v for k, v in parsed.values.items() if v and k in current and not current[k]}
        if not fills:
            return StepResult.nothing()
        found = " | ".join(text for _seg, text in parsed.matched_segments)
        reason = f"folders: {found}"
        if parsed.missing_segments:
            reason += f" (no folder for {', '.join(parsed.missing_segments)})"
        return StepResult.suggestion(FieldFill(parsed_to_metadata_kwargs(fills)), parsed.confidence, reason)

    def apply_suggestion(self, ctx: EpubCtx, result: StepResult) -> str:
        ctx.work.apply_metadata(dict(result.value))
        return f"from the folder path: {result.value}"


# --- rename and move (pinned last) -------------------------------------------


def _values_for(ctx: EpubCtx) -> dict[str, str]:
    values = placeholder_values(ctx.work.metadata)
    enabled, width = ctx.env.zero_pad
    if enabled and values.get("series_index"):
        values["series_index"] = shared_rename.zero_pad_numeric_value(values["series_index"], width)
    return values


def _same(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


class RenameStep(Step):
    key = "rename"
    label = "Rename by pattern"
    description = "Renames the finished file by the pattern below (File > Rename Files (Pattern)). Undo with File > Undo Last Rename."
    position = "last"

    def __init__(self, pattern: str = "", default_enabled: bool | None = None, history=None, sample=None):
        # Off unless the user has used a rename pattern before; while the
        # recipe's pattern is empty it follows the most recent one.
        self.options = (
            _pattern_spec(
                "%title%, %authors%, %series% ...", lambda: pattern, "the last Rename/Export pattern",
                history, sample, as_path=False,
            ),
        )
        super().__init__(default_enabled=bool(pattern) if default_enabled is None else default_enabled)

    def run(self, ctx: EpubCtx) -> StepResult:
        pattern = _effective_pattern(self, ctx)
        if not pattern:
            return StepResult.nothing(note="no rename pattern is set")
        if not ctx.ensure_saved():
            return StepResult.nothing()  # the save's own failure is reported
        env, old = ctx.env, ctx.current_path
        stem = shared_rename.render_filename(_values_for(ctx), pattern, ascii_only=env.ascii_only)
        ext = os.path.splitext(old)[1]
        new = shared_rename.unique_path(os.path.dirname(old), stem, ext, env._taken_rename, old)  # noqa: SLF001
        env._taken_rename.add(os.path.normcase(os.path.abspath(new)))  # noqa: SLF001
        if _same(old, new):
            return StepResult.nothing()
        try:
            rename_no_clobber(old, new)
        except OSError as exc:
            return StepResult.failed(f"couldn't rename to {os.path.basename(new)}: {exc}")
        env.renames.append((old, new))
        env.touched[ctx.live] = new
        ctx.current_path = new
        return StepResult.applied(f"renamed to {os.path.basename(new)}")


class MoveIntoFoldersStep(Step):
    key = "move_into_folders"
    label = "Move into folders"
    description = (
        "Moves the finished file into a folder tree under the library root chosen in File > Rename Files "
        "(Pattern) > Move into folders. The pattern may contain / to make sub-folders. Off by default."
    )
    position = "last"
    default_enabled = False

    def __init__(self, pattern: str = "", default_enabled: bool | None = None, history=None, sample=None):
        # While the recipe's pattern is empty it follows the most recent
        # saved folder pattern (else the built-in one).
        self.options = (
            _pattern_spec(
                "Folders and file name under the library root, e.g. %authors%/%series%/%title%",
                lambda: pattern or DEFAULT_PATH_PATTERN,
                "the last folder pattern used in Rename/Export" if pattern else "the built-in folder pattern",
                history, sample, as_path=True,
            ),
        )
        super().__init__(default_enabled=False if default_enabled is None else default_enabled)

    def run(self, ctx: EpubCtx) -> StepResult:
        pattern = _effective_pattern(self, ctx)
        env = ctx.env
        if not pattern:
            return StepResult.nothing(note="no move pattern is set")
        if not env.library_root or not os.path.isdir(env.library_root):
            return StepResult.nothing(
                note="no library root is set (choose one in File > Rename Files (Pattern) > Move into folders)"
            )
        if not ctx.ensure_saved():
            return StepResult.nothing()
        plan = plan_moves(
            [ctx], env.library_root, pattern, lambda c: _values_for(c), lambda c: c.current_path,
            taken=env._taken_move, ascii_only=env.ascii_only,  # noqa: SLF001
        )[0]
        if plan.blocking:
            return StepResult.nothing(note=f"not moved: {plan.warning}")
        if plan.is_noop:
            return StepResult.nothing()
        try:
            result = execute_move(plan.old_path, plan.new_path, copy=False, trash=env.trash or move_to_trash)
        except OSError as exc:
            return StepResult.failed(f"couldn't move to {plan.relative_path()}: {exc}")
        env.created_dirs.extend(result.created_dirs)
        env.touched[ctx.live] = result.new_path
        ctx.current_path = result.new_path
        if result.original_kept:  # copied across volumes but the original could not be trashed: nothing to undo
            return StepResult(StepStatus.APPLIED, changes=[f"copied to {plan.relative_path()}"], note=result.warning)
        env.moves.append((plan.old_path, result.new_path))
        if result.original_trashed:
            env.trashed.append((plan.old_path, result.new_path))
        return StepResult.applied(f"moved to {plan.relative_path()}")


# --- catalogue and recipe storage ---------------------------------------------


def build_catalogue(
    rename_pattern: str = "", path_pattern: str = "", history: Callable[[], list[str]] | None = None,
    sample: Callable[[], dict[str, str] | None] | None = None,
) -> list[Step]:
    """The steps the recipe editor offers, in default order.
    `rename_pattern` (the most recent saved one) is the Rename step's
    fallback and turns it on. `path_pattern` (the most recent saved
    pattern with a / in it) is the folder-path steps' fallback while the
    recipe's pattern is empty. `history` (pattern history, newest first)
    and `sample` (first loaded book's placeholder values) feed the editor's
    pattern trail. The folder-path and scan steps come before the online lookups so what
    they find can feed them."""
    return [
        ValidateFixStep(),
        DedupeManifestIdsStep(),
        RebuildManifestStep(),
        RepairNavigationStep(),
        GenerateTocStep(),
        StripDescriptionHtmlStep(),
        LanguageStep(),
        PathTagsStep(path_pattern, history=history, sample=sample),
        ScanIsbnStep(),
        ScanPublisherStep(),
        ScanYearStep(),
        ScanSeriesStep(),
        MetadataLookupStep(),
        CleanAuthorsStep(),
        CoverStep(),
        RenameStep(rename_pattern, history=history, sample=sample),
        MoveIntoFoldersStep(path_pattern, history=history, sample=sample),
    ]


def run_catalogue(rename_pattern: str = "", path_pattern: str = "") -> list[Step]:
    """build_catalogue() plus the internal guard step, for the engine."""
    return [GuardStep()] + build_catalogue(rename_pattern, path_pattern)


def recipe_for_run(recipe: Recipe) -> Recipe:
    """The recipe as the engine runs it: the guard first and always on,
    whatever a hand-edited settings file says."""
    order = ["guard"] + [k for k in recipe.order if k != "guard"]
    enabled = {k: v for k, v in recipe.enabled.items() if k != "guard"}
    return Recipe(
        order=order, enabled=enabled, options={k: dict(v) for k, v in recipe.options.items()},
        confidence_threshold=recipe.confidence_threshold,
    )


def recipe_to_setting(recipe: Recipe) -> str:
    """One-line JSON for the settings file."""
    import json

    return json.dumps(recipe.to_dict(), separators=(",", ":"))


def recipe_from_setting(text: str, catalogue: list[Step]) -> Recipe:
    """The saved recipe; nothing saved (or unreadable) means the defaults."""
    if not (text or "").strip():
        return Recipe.default_for(catalogue)
    return Recipe.from_json(text)
