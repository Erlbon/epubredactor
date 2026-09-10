# The ƎPUB Redactor

*(That's a genuinely-turned "E" — the reversed-E character, styled to riff
on "EPUB". The window icon uses an actual 180°-rotated E, since icons can
do real image rotation where window-title text is stuck with whatever
Unicode provides — see "Notes on the turned E" below.)*

A Windows GUI tool for bulk-editing EPUB metadata, built for prepping books
for Kobo e-readers. UX is modeled on **mp3tag**: load a folder of books into
a table, select several at once, and apply the same field changes to all of
them in one go.

> **Early development notice** — shown once each time the app starts:
> please keep copies of the files you're working with before editing them.
> No guarantees.

## Features

- **Menu bar** (File, Import, Operations, Settings, About) with a slim
  toolbar alongside it for the handful of most-frequent actions. Full
  keyboard shortcut list is in "Notes on the menu bar" below.
- **Zoom** −/+ control on the right side of the toolbar (Ctrl+Plus/Minus
  also work) adjusts the table's font size, so you can shrink it to fit
  more content or enlarge it for readability. Shows a live percentage
  relative to the default size (100%) — click the percentage to reset.
- The Google Books Lookup, Author Sort Auto, Genre, and Language field
  buttons all share one compact "▼" style now, instead of a mix of
  button widths eating into the bulk-edit panel's space.
- **Bulk-edit panel**: squeeze it down as far as you like by dragging the
  splitter, or minimize it to a slim strip with one click — the ◀/▶
  button lives right on the panel itself (top-right corner), or use the
  toolbar's "Panel" button. Its fields automatically mirror whichever
  table columns are currently visible, in whatever order you've dragged
  them to (Settings → Add/Remove Columns) — no separate field-management
  screen needed. **Apply** lives in the toolbar and Operations menu now,
  always reachable regardless of panel size or how many fields are
  ticked on. Saving (either Save Files or Save As Copy) applies any
  pending panel changes first, so you never lose an edit you typed but
  forgot to explicitly Apply.
- Cover image preview grows or shrinks to fill the available space in
  the Cover Image section. A draggable divider between it and Bulk Edit
  Tags lets you give it much more room — Bulk Edit Tags scrolls rather
  than getting crushed if you drag it down small.
- **Import to EPUB** — converts other ebook/document formats (MOBI,
  AZW/AZW3, DOCX, RTF, TXT, FB2, and more) to EPUB via your Calibre
  installation's `ebook-convert` tool, then adds the results straight
  into your working list. PDF is deliberately not offered by default —
  PDF-to-EPUB conversion quality is inconsistent, since PDFs have no
  real text-flow structure to extract.
- **Import Metadata from Google Books** — searches
  [Google Books](https://books.google.com) for each selected book by
  title/author and brings back title, authors, publisher, year, ISBN,
  genre, language, description, and a cover thumbnail together, in one
  review-and-apply step. One checkbox per book — ticking a row applies
  everything found for that book.
- **Import Metadata from Open Library** — the same idea via
  [Open Library](https://openlibrary.org): title, authors, publisher,
  year, ISBN, genre (subjects), and cover together. Doesn't import
  Language — Open Library's codes use a different format than this
  app's Language field expects, so it's left out rather than importing
  something that wouldn't match.
- **Generate Cover from Metadata** (Operations menu) — creates a
  placeholder cover (title, author, and series if present, on a plain
  background) for selected books, to replace a missing or wrong cover,
  entirely offline — no lookup, nothing fetched. A **Generate** button
  under the cover preview in the bulk-edit panel does the same thing
  straight to the current selection, no dialog — the menu version opens
  a full preview table first, for reviewing a larger batch before
  committing. See "Notes on Generate Cover" below.
- **Case Conversion** — UPPERCASE / lowercase / Title Case / Sentence
  case for any column, with a live preview before applying. Title Case
  correctly leaves small connector words ("of", "the") lowercase except
  at the start/end, and doesn't mangle apostrophes the way `str.title()`
  would.
- **Number Series** — assigns sequential Series # values across a batch
  of selected books at once, in their current table order (top to
  bottom). A plain bulk-edit can't do this, since applying one value to
  every selected book is the opposite of what you want when numbering
  an entire series — set a starting number and a step (fractional steps
  work too), preview before applying. Right-click the selection for a
  quicker version that just asks for a starting value and counts up by
  one per row.
- **Polish Book** — applies Calibre's `ebook-polish` cleanups: smarten
  punctuation, subset/embed fonts, compress images, remove unused CSS,
  add/remove soft hyphens, insert/remove a book jacket page, upgrade
  EPUB2 → EPUB3. Works directly on the file on disk (a real file change,
  not staged like other edits), so books with unsaved changes are
  automatically skipped — save those first. See "Notes on Polish Book"
  below.
- **Send to Kobo (USB)** — detects a Kobo connected via USB (its
  `.kobo` folder — the same mechanism Calibre itself uses) and copies
  selected books straight onto it. No network involved. Lives under its
  own **Kobo** menu, alongside Send to eReader.
- **Send to eReader (Wireless)** — manage a list of
  [send2ereader](https://github.com/daniel-j/send2ereader)-style server
  URLs (self-hostable; `send.djazz.se` and `bookdrop.cc` are included as
  starting suggestions), then open your chosen server and the book's
  folder together, ready to drag the file in. See "Notes on Send to
  eReader" below for why this stops short of full automation.
- **Detect Missing Spaces** — flags a period, comma, or similar
  punctuation directly followed by a letter with no space (e.g.
  `Hello.World`), a common sign of bad text extraction or scraped
  metadata. Scoped to Title and Series — see "Notes on Detect Missing
  Spaces" below for why a broader check isn't included.
- **Rebuild Manifest** — for the "file referenced in manifest is
  missing from archive" validation error. A separate, manually-triggered
  action (not a one-click Validate/Fix Issues fix), since it can affect
  reading-order content — always lists every missing file first and
  requires explicit confirmation. See "Notes on Rebuild Manifest" below.
- **Rename a single file directly** — double-click a filename in the
  table, or right-click it → "Rename File…", to fix a typo or small
  mistake without going through the pattern-based Rename/Export tool.
  Acts on disk immediately. Invalid Windows filenames and name
  collisions are rejected with a clear message rather than silently
  changed or auto-numbered — a single, deliberate rename should end up
  with exactly the name given, or fail clearly.
- **Right-click menus** — the table offers quick access to the most
  common per-selection actions (Open Containing Folder, Copy Path,
  Rename File, Rename Files (pattern), Save, Remove/Delete, Validate,
  Look Up via Calibre, Polish Book, Number Series, Open with Sigil,
  Send to Kobo/eReader) without going through the menu bar.
  Right-clicking outside your current selection selects just that row
  first, same as Explorer. Column headers have a lighter menu too, for
  hiding a column or opening Add/Remove Columns directly.
- **Open with Sigil** — launches [Sigil](https://sigil-ebook.com), a
  free, open-source EPUB editor, for the selected book(s), for
  structural issues this app can't fix itself. Offers to locate or
  download Sigil if it isn't found, and warns (without blocking) if a
  selected book has unsaved changes here first, since Sigil edits the
  file on disk directly rather than through this app's own staged-edit
  model.
- **Delete Files** — sends files to the Recycle Bin (recoverable, not a
  permanent delete), with a confirmation prompt listing what's about to
  go.
- **Refresh List** — re-scans the folders your loaded books live in for
  new files, then reloads everything fresh from disk (discarding any
  unsaved in-memory edits, with confirmation first). Always tells you
  what it found, so it's clear the action ran even when nothing changed.
- **Add/Remove Columns**, **Add/Remove Genres**, and **Add/Remove
  Languages** — under the Settings menu. Both custom entries and
  built-in defaults can be removed; removing a default just hides it
  (doesn't delete it) and "Restore Hidden Defaults" brings back
  everything hidden that way in one step.
- **Validation** — every book is checked on load for structural problems
  (broken unique-identifier, missing title/language, missing manifest
  files, duplicate ids, dangling spine references, missing table of
  contents, DRM). A **Status** column shows OK / ISSUES / INVALID;
  double-click it (or use "Validate / Fix Issues…") to see details and
  apply whichever fixes are safe to automate. See "Notes on validation"
  below for what this does and doesn't check, and why.
- A book that fails to **save** (permission denied, file locked by
  another program, a path too long for Windows, etc.) is flagged
  **SAVE FAILED** in that same Status column, with the actual error on
  hover — and is skipped by future automatic Save sweeps, so a
  persistent problem (like a path that's simply too long) doesn't get
  silently re-attempted and re-fail forever. Double-click the status to
  explicitly retry that one book once you believe it's fixed; the flag
  clears automatically once it saves successfully.
- A progress dialog appears when loading 3+ files/folders at once, so
  large batches don't look like nothing's happening — and the same for
  Save Files/Save As Copy, showing each filename as it's saved. For a
  genuinely large library (500+ books), refreshing the table's display
  afterward — after loading, saving, undo, or anything else that
  rebuilds it — shows its own progress too, so that step alone can't
  make the app look frozen with no way to tell it's still working.
- **Parse Filename → Metadata** — the reverse of Rename/Export: extract
  metadata straight out of filenames using the same `%field%` pattern
  syntax (shares its pattern history with Rename/Export). Checks your
  pattern history against the filenames you've actually loaded and
  opens pre-filled with whichever past pattern fits best, rather than
  just the last one used. Recent patterns are shown both in an
  always-visible clickable list under the field and behind the "▼"
  button next to it (never truncated), each with a match
  count against the current batch. Every available field code is also
  listed in a clickable side panel — double-click one to insert it at
  the cursor's current position in the pattern.
- **Scan Content for Metadata** — reads the first few pages of each book
  (title/copyright page) for ISBN, publisher, author, year, and DDC
  classification. A best-guess heuristic tool, not a reliable parser —
  review the matches before applying, same as the Google Books and Open
  Library lookups.
- Load individual files, or one or more folders of `.epub` files (the
  folder picker reopens after each pick so you can add another — Cancel
  is how you say "done"; asks once, for all of them, whether to include
  subfolders); remembers the last folder you used across all "open a
  file/folder" dialogs, including the cover-image picker. Load Folder
  replaces the current list rather than adding to it (with the usual
  unsaved-changes confirmation first) — Load Files and drag-and-drop
  still add to whatever's already loaded.
- Remembers exactly which books were loaded when you last closed the
  app, and reopens with the same set loaded automatically — a book
  that's since moved or been deleted is skipped quietly rather than
  shown as an error.
- Drag-and-drop files/folders straight onto the window (always recursive)
- **Path** column (leftmost) shows each book's folder location, handy once
  you've loaded books from more than one place
- Editable table — tweak a single book's field directly in the grid
- **Keyboard navigation**: Tab/Shift+Tab move horizontally between fields
  (wrapping to the next/previous row at the ends), Enter moves down one
  row in the same column — spreadsheet-style. Plain arrow keys use Qt's
  normal cell-to-cell navigation.
- Strong, theme-independent highlighting for the selected row and the
  specific cell you're in (the "current cell", relevant for typing and
  Tab/Enter navigation) — it no longer blends into custom row colors
  like the dirty/status highlighting.
- **Click any column header to sort by it** (numeric columns like Series #
  and Year sort numerically, not alphabetically)
- **Drag column headers to reorder them**
- Row numbers on the left (native, always positionally accurate regardless
  of sort order)
- **Bulk Edit panel** (left side) — select multiple books, tick the fields
  you want to change, type the new value, click **Apply**. Unticked fields
  are left untouched, so partial edits across a batch are safe. When a
  field shows `<multiple values>` (the selection disagrees), scroll your
  mouse wheel over it to cycle through the actual differing values and
  pick one — blank values are never among the alternatives offered.
- Fields covered: Title, ISBN, Author(s), Author Sort, Series, Series Index,
  Collection, Genre, Publisher, Year, Month, Day, DDC (Dewey Decimal),
  Language, Description
- **Author Sort** — "Last, First" form, stored as `opf:file-as` on each
  `<dc:creator>` element (still the standard, non-deprecated way to do
  this — see "Notes on Author Sort" below). Both fields have a guess
  button: Author Sort's guesses from Author(s) (splits on the last
  space in each name), and Author(s) has the exact inverse for whenever
  Author Sort is already filled in and Author(s) needs populating
  instead (splits on the first comma). Check the result either way,
  since neither is right for every name.
- Series info is written in **both** the Calibre convention
  (`calibre:series` / `calibre:series_index`) and the native EPUB3
  `belongs-to-collection` metadata, so it's picked up regardless of how
  your specific Kobo firmware / Calibre version reads series data.
- **Collection** — a separate field for EPUB3's `belongs-to-collection`
  mechanism when it *isn't* a numbered series — box sets, anthologies,
  themed groupings with no natural ordering. Written as its own
  `belongs-to-collection` entry with `collection-type="set"`, independent
  of and coexisting with Series (`collection-type="series"`). No calibre-
  style dual-write here, since Calibre doesn't have an equivalent second
  convention for this the way it does for series.
- Publication date is split into Year/Month/Day fields but stored as a
  single standard `<dc:date>` — with only as much precision as you actually
  give it (a year-only book doesn't get a fake `-01-01` bolted on)
- Author(s) and Genre are semicolon-separated multi-value fields, same
  convention as mp3tag's genre field
- Save in place (overwrites originals) or "Save As Copies" to a separate
  folder so your originals are never touched
- Unsaved rows are highlighted; files that fail to load are flagged in red
  and skipped safely
- Filter box to narrow the list by filename or title
- **Cover image** — a preview panel in the bulk-edit panel (bottom-left)
  shows the cover of the first selected book, plus **Add/Replace**,
  **Generate**, and **Delete** buttons that apply to every selected book
  at once. A small thumbnail also appears next to each book's filename
  in the table. Nothing touches disk until you Save, same as every
  other edit.
- **Rename / Export by Pattern** — mp3tag's "Convert: Tag → Filename" feature.
  Build a filename from a pattern like `%series% %series_index% - %title%`,
  preview the result for every book, then either rename files in place or
  export renamed copies to a separate folder. Illegal Windows filename
  characters are stripped automatically, empty fields collapse cleanly
  (no stray " - " left behind), and name collisions within a batch or on
  disk are auto-numbered (`Book (2).epub`) rather than overwriting anything.
  Zero-padding a decimal series index (`5.5`) correctly pads only the
  integer part (`05.5`). A "▼" button next to the pattern field shows
  your recent patterns in full, never truncated, and the dialog opens
  pre-filled with your last-used one. Every available field code is
  also listed in a clickable side panel — double-click one to insert
  it at the cursor's current position in the pattern. Placeholders
  include `%genres%`, `%collection%`, and `%year%`/`%month%`/`%day%`
  alongside the rest (the older `%tags%` and `%pub_year%`/`%pub_month%`/
  `%pub_day%` tokens still work too, kept quietly for backward
  compatibility with patterns saved before those were renamed).
- Genre field has a compact **"+"** button — click it for a menu of over
  100 common genres, spanning fiction subgenres, nonfiction categories,
  and common formats; picking one appends it to the field without
  replacing anything you've already typed, and won't add a duplicate.
  The field stays free text at all times.
- Language field has the same **"+"** button, with a curated starting list
  (English, German, French, Spanish, Dutch, Norwegian, Italian, Swedish,
  Danish) plus an "Add custom language…" option that remembers what you add
  for future sessions. Picking a language *replaces* the field (unlike
  Genre) since a book normally has one language.
- **ISBN field** — click the "▼" button next to it to open Import
  Metadata from Google Books (brings back more than just ISBN — see
  above). ISBN validation (checksum for both ISBN-10 and ISBN-13) is
  used internally; the field itself still accepts anything typed by
  hand. Stored as its own `dc:identifier`, kept separate from the
  book's primary UUID identifier.
- **Look Up via Calibre** — full metadata lookup (title, author(s) with
  sort-names, series, publisher, date, tags, ISBN, description) via your
  own Calibre installation's `fetch-ebook-metadata` command-line tool.
  This runs whichever metadata source plugins *you* have installed and
  enabled in Calibre — including third-party ones like a
  Goodreads-replacement or FantasticFiction plugin, which Calibre
  doesn't ship by default (Goodreads shut down its public API in 2020;
  those are community plugins people add themselves). Same
  review-before-applying pattern as Google Books/Open Library lookup.
  Needs Calibre installed;
  the first time, if it can't be found automatically, you'll be asked to
  browse to it once. See "Notes on the Calibre lookup" below.
- **Search & Replace** — works across every column, including Filename.
  Plain text or regex (with `\1`, `\2`... backreferences), optional case
  sensitivity. Preview shows only books that would actually change, each
  with its own checkbox. Metadata changes are ordinary in-memory edits;
  a Filename match performs an actual on-disk rename (same collision-safe
  mechanics as Rename/Export).
- **Undo** — steps back through your last 5 in-memory edits (single-cell
  edits, bulk edits, cover changes, ISBN/Calibre lookups, metadata
  search/replace, parsed-filename or scanned-content metadata applies).
  Deliberately does **not** cover physical file operations (Rename/Export,
  Save, a Filename-mode search/replace, or applying a validation fix) —
  those are already deliberate, explicitly-confirmed actions, and undoing
  a completed rename or overwrite would mean touching the filesystem
  again in ways that could surprise you.

## Running from source (any OS with Python)

```
pip install -r requirements.txt
python main.py
```

## Building a standalone Windows .exe

You need to do this step **on a Windows machine** (PyInstaller builds for
the OS it runs on).

1. Install Python 3.10+ from python.org (check "Add to PATH" during install).
2. Copy this whole folder to the Windows machine (including the `assets/`
   folder — it holds the app icon).
3. Double-click `build_exe.bat`, or run it from a command prompt.
4. When it finishes, your standalone app is at `dist\epubredactor.exe`,
   already carrying the icon. That one file can be copied anywhere and run
   with no Python install needed.

**Icon troubleshooting:** if the taskbar/title bar still shows the plain
Python icon instead of the turned-E icon:
- Running via `python main.py` directly (not the built .exe): this is a
  known Windows quirk — the taskbar groups by the underlying `python.exe`'s
  own identity unless the process is given its own explicit
  AppUserModelID, which `main.py` now sets automatically on Windows. Pull
  the latest `main.py` if you're on an older copy.
- Running the built `.exe` and still seeing the old icon: Windows
  aggressively caches taskbar icon thumbnails. Try rebuilding after
  deleting the old `dist\epubredactor.exe`, or sign out/in (or
  restart `explorer.exe`) to clear the icon cache.

If Windows SmartScreen warns about an "unrecognized app" the first time you
run it, that's normal for unsigned homemade executables — click "More info"
→ "Run anyway".

## How the metadata is actually edited

An EPUB is a zip file containing an OPF ("package") XML document with the
book's metadata. This tool:

1. Opens the zip and locates the OPF via `META-INF/container.xml`
2. Parses the `<dc:title>`, `<dc:creator>` (plus `opf:file-as` for Author
   Sort), `<dc:publisher>`, `<dc:language>`, `<dc:description>`, `<dc:date>`,
   `<dc:subject>` elements, the series `<meta>` tags, the ISBN
   `<dc:identifier>` (kept separate from the book's primary/unique
   identifier), the DDC classification (a `<dc:subject opf:authority="DDC">`,
   kept separate from ordinary genre subjects), and the cover image
   (located via the EPUB3 `properties="cover-image"` manifest attribute or
   the EPUB2 `<meta name="cover">` convention)
3. On save, rewrites the OPF file — and the cover image file, if you
   changed it — inside a **new** zip, copying every other file
   byte-for-byte, and keeps `mimetype` as the first, uncompressed entry
   (required by the EPUB spec). A book whose cover you never touched gets
   its cover file copied byte-for-byte untouched, same as everything else.

Nothing else in the book (text, styling, etc.) is touched.

## Notes on validation

Not a full EPUB spec/accessibility validator — that's what
[epubcheck](https://github.com/w3c/epubcheck) is for, and reimplementing
it wasn't the goal here (nor was borrowing code from something like Sigil,
whose validation logic is GPLv3 C++ tightly coupled to its own app —
pulling that into this project would impose GPL's copyleft on the whole
codebase, and it isn't straightforwardly portable anyway). This checks the
structural problems that matter most for a bulk metadata-editing tool:
things that could make a book fail to open, lose its cover/TOC, or
silently resist having its metadata edited correctly. Content-document
(chapter XHTML) well-formedness is deliberately **not** checked, to keep
loading fast even for large batches.

What's checked: mimetype correctness (always silently corrected on save
regardless of source state), the package's primary identifier actually
pointing at something real, presence of title/language, manifest files
that are referenced but missing, duplicate manifest ids, spine entries
pointing at nothing, a missing table of contents, and DRM (detected only
— this tool will never attempt to remove or work around DRM).

Four statuses, not three: **OK**, **ISSUES** (warnings only), **DRM**
(protected but otherwise a perfectly valid EPUB — just off-limits to
editing here), and **INVALID** (genuinely broken or unreliable to open).
A book that's both DRM-protected and has a real structural problem still
shows INVALID, since that's the more fundamental issue. After an
in-place Save, validation automatically re-runs against what's actually
on disk, so the Status column reflects real confirmation rather than a
pre-save snapshot.

## Notes on the filename/content tools

Parse Filename → Metadata and Scan Content for Metadata are both
"best guess, review before applying" tools, not reliable parsers — real
filenames and book front matter vary too much for that. Parsing is
inherently ambiguous when two adjacent pattern fields share only a plain
space as a separator and the first field's value legitimately contains
spaces (e.g. a multi-word series name right before a numeric index) —
numeric-shaped fields (series index, pub date parts, DDC, ISBN) use a
stricter digit-only match specifically to resolve that common case, but
it can't be solved in general. Whitespace between fields is
otherwise flexible — a literal space in the pattern matches any run
of whitespace in the filename, so a stray extra space doesn't break
the match — but a *missing* space where the pattern expects one still
won't match, since allowing that would reintroduce the same field-
boundary ambiguity. A parsed Series # additionally has any leading
zeros stripped ("03" → "3", "03.5" → "3.5") — filenames often
zero-pad a series number purely for correct sort order, and that
padding isn't meaningful metadata. Content scanning only looks at the
first few spine documents (title/copyright page territory) and stops
early once it's read enough text, to keep it fast across a whole batch.

Parse Filename's starting pattern is chosen by checking every pattern
in your history against the actual loaded filenames and picking
whichever matches the most of them — not just whatever was used last,
since that could easily be left over from a completely different
batch of books. A tie is broken toward the more recently used pattern.
If nothing in history matches anything here, it falls back to the
last-used pattern as before.

## Notes on Detect Missing Spaces

Only checks for a period, comma, semicolon, colon, `!`, or `?`
immediately followed by a letter with no space — this essentially never
misfires on ordinary text, since abbreviations and decimals are
followed by a space or a digit, not directly by a letter. A broader
heuristic (a lowercase letter directly followed by an uppercase one,
catching concatenations like `TheGreatGatsby`) would find more genuine
issues, but it flags legitimate names with an internal capital just as
readily — McDonald, DiCaprio, MacArthur, LeBron — so it's deliberately
left out rather than shipped as a noisy, unreliable check. Scoped to
Title and Series for the same reason; nothing is applied without
review.

## Notes on Author Sort / opf:file-as

`opf:file-as` (an attribute directly on `<dc:creator>`) is **not**
outdated — it's still the most broadly-compatible way to record a sort
name, and it's exactly what Calibre itself writes. EPUB3's own alternative
(a `<meta refines="..." property="file-as">` element) is more "native" to
EPUB3 specifically, but `opf:file-as` remains valid in EPUB3 for backward
compatibility and is what this tool uses, matching the same
maximize-compatibility approach used for series info.

Multiple authors: sort-names are matched to authors by position. If you
only set a sort-name for the first of several authors (by far the most
common real-world case), that's exactly what gets written — the others are
left with no `file-as` at all, not a wrong guess.

## Notes on the turned E

Unicode doesn't actually have a true "turned" (180°-rotated) capital E as
its own character — only Ǝ (U+018E, "LATIN CAPITAL LETTER REVERSED E",
officially a left-right *mirror*, not a rotation) and ǝ (U+01DD, lowercase,
which genuinely is a 180° turn). Since a window title bar can only display
real Unicode text — it can't rotate an arbitrary glyph — the app name uses
Ǝ, the conventional practical choice for this kind of "turned E" branding.
The app **icon**, being an actual image, uses a genuinely 180°-rotated E.

## Notes on Google Books and Open Library lookups

- Both require an internet connection; if either fails, the dialog
  tells you clearly (rather than silently returning nothing) and offers
  Search Again. Being rate-limited (HTTP 429 — searching many books in
  a row can trigger this on either service's free, unauthenticated
  quota) is retried automatically with a short backoff before being
  reported as an error, since it usually clears up within a few
  seconds on its own.
- Matching is done by title/author text search, so both are "probably
  right, please glance and confirm" tools, not guaranteed exact —
  that's why nothing is written until you review and click Apply.
- One checkbox per book, not per field: ticking a row applies
  everything found for that book — title, authors, publisher, year,
  ISBN, genre, cover, and (Google Books only) language and description.
  Untick anything you don't trust before Apply.
- Neither needs an API key for this app's usage level.
- Open Library's Language field isn't imported — it uses a different
  code format (3-letter) than this app's Language field expects
  (2-letter ISO 639-1) — see core/open_library_lookup.py for the
  reasoning if you're curious.

## Notes on Generate Cover

- Entirely offline — no network request, no external lookup. It draws
  a plain background plus title/author/series text using Qt's own
  QPainter/QImage, not a new image library (Pillow, etc.); PyQt6 is
  already this app's only dependency, and Qt's text rendering handles
  this fine on its own.
- The background color is picked deterministically from the title
  (via a hash, not randomly), so the same book's title always produces
  the same color if you regenerate it later, while a batch of
  different books gets visually distinct colors rather than all
  looking identical.
- A book with no title set gets a literal "(Untitled)" placeholder
  rather than a blank cover — there's always something to look at, and
  it's an obvious cue that the title itself needs filling in too.

## Notes on the menu bar

Keyboard shortcuts:

| Action | Shortcut |
|---|---|
| Load Files | Ctrl+O |
| Load Folder | Ctrl+Shift+O |
| Save Files | Ctrl+S |
| Save As Copy | F4 |
| Rename Files (Rename/Export by Pattern) | F2 |
| Import Metadata from Filename | F3 |
| Remove Files (from the list only) | Delete |
| Delete Files (to Recycle Bin) | F8 |
| Refresh List | F5 or Ctrl+R |
| Undo | Ctrl+Z |
| Exit | Alt+F4 (native Windows close, not a custom binding) |

A couple of deliberate departures from your first-draft suggestions,
to avoid colliding with strong existing Windows conventions: Load Files
uses Ctrl+O instead of F1 (which is near-universally "Help"), Save uses
only Ctrl+S (F3 is near-universally "Find Next"), and Remove Files uses
the Delete key instead of Ctrl+X (which is near-universally "Cut").

## Notes on the Calibre lookup

- Requires Calibre to be installed on your machine (this tool doesn't
  bundle or embed Calibre in any way).
- Deliberately does **not** load or run Calibre plugins directly inside
  this app. It shells out to Calibre's own `fetch-ebook-metadata`
  command-line tool as a separate process and parses the OPF it prints
  out. Three reasons: a "plugin" is arbitrary Python code, and running
  third-party plugin code inside this app's own process would be a real
  security risk this design avoids entirely; Calibre is GPLv3, and
  shelling out to its CLI (rather than importing its internals) avoids
  any copyleft entanglement; and Calibre's plugin API is internal and
  shifts between versions, while its CLI is the stable, documented
  surface to build against.
- Which metadata sources actually get used is entirely up to your own
  Calibre configuration — this app has no say in it beyond triggering
  the fetch. Calibre's *default* plugin set is Google, Google Images,
  Amazon.com, Edelweiss, and Open Library; Goodreads and FantasticFiction
  are **not** included by default (Goodreads shut down its public API in
  2020) — if you want those, install the corresponding community plugin
  in Calibre itself first, via Calibre's own Preferences → Plugins.
- Each lookup can take up to Calibre's own timeout (~30 seconds), since
  it may be querying multiple sources — for a large batch, that adds up,
  which is why the dialog warns before starting on more than a handful
  of books.
- Same review-before-applying pattern as everywhere else that fetches
  external data: nothing is written until you check the results and
  click Apply.
- Calibre's tools are console programs; launched from this windowed
  app, Windows would otherwise pop up a visible console window for
  each one that can steal focus entirely (worse on an error, which
  fills that console with raw text and blocks reaching anything in this
  app's own dialog, including its Apply button, until it's closed by
  hand). Suppressed for all three Calibre integrations — see
  `core.calibre_tools.no_console_window_kwargs()`.
- A separate problem from that console window: when a search finds
  nothing, Calibre's own tool can log hundreds of very verbose lines
  to its error output (every metadata plugin's search attempts, URLs
  queried, and so on). That's bounded to a short excerpt before it
  ever becomes an error message shown in this app, rather than dumped
  in full into a status label with no length limit — see
  `core.error_summary.summarize_errors()`, applied everywhere a batch
  operation summarizes per-book errors, not just here.
- If Calibre isn't found, every dialog that needs it offers both
  "Change/Locate Calibre Location…" (if you already have it, just not
  in a place this app checks automatically) and "Download Calibre…"
  (opens the official download page — it's free) side by side.

## Notes on Open with Sigil

[Sigil](https://sigil-ebook.com) is a free, open-source (GPLv3) EPUB
editor that can fix some structural issues this app deliberately
doesn't attempt to (it edits raw EPUB markup directly, closer to a code
editor than a metadata tool). Same relationship to this app as Calibre:
launched as a completely separate process, never linked or embedded —
see "Notes on the Calibre lookup" above for the fuller reasoning, which
applies equally here. If Sigil isn't found automatically, you're
offered the choice to locate an existing install or download it fresh
(it's free), the same as for Calibre. Opening a book with unsaved
changes in this app first shows a warning, not a block — Sigil edits
the file on disk directly, so whichever of the two you save last wins.

## Notes on Polish Book

- Also requires Calibre (shares the same install-folder setting as the
  metadata lookup and Import to EPUB — set it once, all three use it).
- Unlike everything else in this app, polishing isn't a staged
  in-memory edit — Calibre's `ebook-polish` operates on the actual file
  on disk. That means a book with unsaved changes can't be polished
  safely (the pending edits would be silently ignored, then lost once
  the book gets reloaded afterward), so those are automatically skipped
  with a clear note — save them first, then polish separately.
- "Polish in place" writes to a temporary file next to the original and
  atomically swaps it in, so an interrupted or failed polish can't
  corrupt the original. The book is then reloaded fresh from disk
  (same as Refresh List, and for the same reason — this is a real file
  rewrite), which also clears the Undo stack, since its entries would
  no longer correspond to anything real.
- Deliberately doesn't expose `ebook-polish`'s own `--cover`/`--opf`
  options (it can also update a book's cover/metadata) — this app's own
  metadata engine already does both with more precision than routing
  through an external tool would give us.

## Notes on Send to Kobo (USB)

- Detects a connected Kobo by looking for its `.kobo` folder at the
  root of each drive letter — the same marker every Kobo firmware
  creates, and the same detection method Calibre itself relies on for
  device sync.
- Files go straight into the drive's root. Kobo scans its whole
  filesystem for supported formats on its next library refresh, so
  there's no specific folder they need to land in.
- A filename collision on the device is auto-numbered (`Book (2).epub`),
  same collision-safe logic as Rename/Export and Import to EPUB — it
  will never silently overwrite something already on the device.

## Notes on Send to eReader (Wireless)

- Built around [send2ereader](https://github.com/daniel-j/send2ereader)
  (MIT licensed, self-hostable): your e-reader's own browser shows a
  short-lived key, and a paired browser session elsewhere uploads a
  file using that key. `send.djazz.se` and `bookdrop.cc` are included
  as starting suggestions — add your own self-hosted instance (or any
  other compatible one) via "Add…".
- This deliberately stops short of fully automating the upload.
  send2ereader has no documented API — even people trying to self-host
  it report there's no README or spec for the actual upload
  endpoint/key exchange (confirmed by checking the project's own issue
  tracker before building this). Guessing at that and shipping it as if
  verified would risk silent, confusing failures, so instead this opens
  your chosen server in the browser and the selected book's folder in
  Explorer at the same time — the only manual step left is entering the
  key your e-reader shows and dragging the file in, same as using the
  site directly, just without hunting for the file first.

## Notes on Rebuild Manifest

- Fixes the "file referenced in manifest is missing from archive"
  validation error — the book's internal file listing points at a
  file (usually an image, stylesheet, or chapter document) that
  genuinely isn't in the archive anymore.
- Deliberately a separate, manually-triggered action rather than a
  one-click Validate/Fix Issues fix. The other automated fixes only
  ever touch structural bookkeeping (a dangling cross-reference, a
  missing language tag); this one can affect actual reading-order
  content, if the missing file happened to be a spine document rather
  than an orphaned image. It always lists every missing file, for
  every affected book, before anything happens, and only acts on what
  you explicitly confirm.
- Worth understanding: since the file is genuinely gone from the
  archive, rebuilding doesn't lose you anything further — the content
  was already inaccessible to any reader before this ever ran. All
  this does is remove the broken pointer to it (and, if that entry was
  referenced in the spine, its reading-order slot too), which can only
  help compatibility with reading apps that handle a dangling manifest
  entry poorly. It cannot restore the missing file itself — if you
  have the original elsewhere, you'd need to re-add it by hand.

## Notes on settings

Everything this app remembers between runs — pattern history, custom
genres/languages, the last folder you used, the last set of books you
had loaded, column widths, the Calibre install location, eReader
servers — lives in one plain file: `epubredactor_settings.ini`, next
to the executable (or at the project root if you're running from
source). Not the Windows Registry: registry settings turned out not to
reliably survive an in-place version upgrade, and a plain file is much
easier to back up, copy to a new machine, or open and inspect directly
than exporting registry keys.

## Notes on crash logging

If something goes wrong that this app didn't already anticipate and
handle gracefully, a full timestamped traceback is saved to
`epubredactor_crash.log`, right next to the settings file — appended
to, not overwritten, so a pattern across multiple crashes is still
visible, not just the most recent one (capped in size so this can't
grow without bound on a machine that crashes repeatedly). A friendly
notice pointing at the log file is shown too, where that's possible.
This also enables Python's own `faulthandler` on a best-effort basis,
which can capture at least a minimal trace even for a genuine
native-level crash (inside Qt's own underlying code, for instance) —
something an ordinary Python exception handler can never see at all,
since it isn't a Python exception in the first place. If you hit a
crash, that log file is the most useful thing to share when reporting
it.

This is genuinely how one real bug got tracked down and fixed: a
crash log pointed straight at a book with a corrupted cover image
(damaged compressed data inside the zip, not a bad zip structure) that
was crashing the entire batch load, not just failing on that one book
— every corrupted file loaded before it in a given session had been
handled fine, this specific kind of corruption just wasn't one of the
ones being caught yet.

## Notes on renaming a single file

- Distinct from Rename/Export by Pattern: that tool builds a filename
  from metadata using a pattern, for a whole batch at once. This is
  for typing an exact replacement name for one file, directly — a
  typo fix, not a systematic rename.
- Acts on disk immediately, the moment you confirm — not staged until
  Save, the same as Rename/Export's own "rename in place" mode. Not
  tracked by Undo either, for the same reason: Undo only ever covers
  in-memory metadata edits, never file operations.
- The extension is always preserved exactly as it was, regardless of
  what you type in the name field — there's no way to accidentally
  change or drop it.
- If the name you type isn't a valid Windows filename (illegal
  characters, a reserved name like `CON`, too long, a trailing space
  or dot) or would collide with a file that already exists in the same
  folder, the rename is rejected with a clear reason and nothing is
  touched — it's never silently modified or auto-numbered the way a
  batch Rename/Export collision would be. A single, deliberate rename
  should end up with exactly the name given, or fail clearly.

## Notes on sorting & column reordering

Clicking a column header sorts the table by that column (click again to
reverse); dragging a header reorders columns. Neither ever changes which
book is which — every row carries a direct reference to its own book
object (not a row-index lookup), so sorting, reordering, filtering, and
bulk edits all stay correctly matched to the right book no matter how the
table currently looks.

Column **widths** are remembered across restarts, and only ever
auto-fit to content once — the very first time you load books with
nothing saved yet. After that, resizing a column (by dragging its edge)
sticks, both for the rest of the session and the next time you open the
app. Column **visibility** (Settings → Add/Remove Columns, or a column
header's own quick-hide) is remembered the same way.

## Project layout

```
main.py                       - entry point
core/epub_metadata.py         - the metadata read/write engine, validation + fixes (no GUI code)
core/validation_issue.py       - validation issue/status data types
core/fields.py                 - shared list of editable fields
core/rename_pattern.py         - "Tag to Filename" pattern engine (no GUI code)
core/author_sort.py             - Author(s) <-> Author Sort naive guess conversions, both directions
core/filename_parser.py         - "Filename to Tag" parser, the reverse (no GUI code)
core/content_scan.py             - heuristic metadata extraction from book content
core/genres.py                  - common genre list + quick-pick merge logic
core/languages.py                - default language list for the quick-pick menu
core/isbn.py                      - ISBN-10/13 validation, normalization, conversion
core/google_books_lookup.py           - Google Books metadata + cover lookup, network call injectable for testing
core/calibre_tools.py               - shared Calibre install-folder/tool-path discovery, console-window suppression
core/sigil_tools.py                     - Sigil detection + launch (Open with Sigil)
core/calibre_lookup.py               - Calibre fetch-ebook-metadata integration, subprocess call injectable for testing
core/ebook_convert.py                 - Calibre ebook-convert integration (Import to EPUB)
core/ebook_polish.py                   - Calibre ebook-polish integration (Polish Book)
core/kobo_usb.py                        - USB Kobo detection + file copy (Send to Kobo)
core/save_errors.py                     - recognizes+explains common save failures (esp. Windows path-length limit)
core/error_summary.py                   - bounds a batch of per-book error messages into a short, safe-to-display preview
core/app_paths.py                       - where this app's persistent files live (settings, crash log)
core/crash_log.py                       - global crash logging + faulthandler for native-level crashes
core/missing_space.py                   - punctuation-adjacent-to-letter detection (Detect Missing Spaces)
core/case_conversion.py                - UPPERCASE/lowercase/Title Case/Sentence case transforms
core/series_numbering.py                - sequential Series # generator (Number Series)
core/open_library_lookup.py             - Open Library metadata + cover lookup, network call injectable for testing
core/cover_generator.py                 - placeholder-cover color/text decision logic (Generate Cover from Metadata)
core/search_replace.py                   - search/replace engine (plain text + regex)
core/undo.py                               - bounded undo stack for in-memory edits
core/version.py                             - app name + version string
gui/main_window.py             - main window, menu bar, toolbar, file table, save logic
gui/tag_panel.py               - the bulk-edit side panel (incl. cover preview)
gui/rename_dialog.py           - the Rename/Export by Pattern dialog
gui/filename_parse_dialog.py    - the Parse Filename to Metadata dialog
gui/content_scan_dialog.py       - the Scan Content for Metadata dialog
gui/validation_dialog.py          - the Validate/Fix Issues dialog
gui/google_books_dialog.py       - the Import Metadata from Google Books dialog
gui/calibre_lookup_dialog.py     - the Calibre metadata lookup/review dialog
gui/ebook_convert_dialog.py       - the Import to EPUB dialog
gui/polish_book_dialog.py          - the Polish Book dialog
gui/send_to_kobo_dialog.py          - the Send to Kobo (USB) dialog
gui/missing_space_dialog.py          - the Detect Missing Spaces dialog
gui/manifest_rebuild_dialog.py       - the Rebuild Manifest dialog
gui/send_to_ereader_dialog.py        - the Send to eReader (Wireless) dialog
gui/os_utils.py                       - shared OS helpers (reveal a file in the file manager)
gui/open_library_dialog.py         - the Import Metadata from Open Library dialog
gui/cover_render.py                   - draws the actual placeholder cover image (QPainter/QImage)
gui/cover_generator_dialog.py         - the Generate Cover from Metadata dialog
gui/case_conversion_dialog.py       - the Case Conversion dialog
gui/series_number_dialog.py          - the Number Series dialog
gui/manage_list_dialog.py            - reusable Add/Remove dialog (genres, languages)
gui/column_settings_dialog.py         - the Add/Remove Columns dialog
gui/about_dialog.py                    - About and Changelog viewer dialogs
gui/search_replace_dialog.py     - the Search & Replace dialog
gui/app_settings.py               - persisted pattern history, last directory, custom genres/languages, Calibre location, column widths -- see "Notes on settings" below
assets/icon.ico, icon.png          - the app icon (turned E)
assets/ai_badge.png                 - small badge for the credit line
CHANGELOG.md                          - version history, also shown in-app via About -> Changelog
ABOUT.md                               - the author's note shown in-app via About -> About The ƎPUB Redactor
test_core.py                     - automated test for the metadata engine
test_dates_ddc_cover.py           - automated test for pub date / DDC / cover image
test_author_sort.py                - automated test for Author Sort / opf:file-as
test_author_sort_convert.py         - automated test for the Author(s) <-> Author Sort guess conversions
test_collection.py                  - automated test for the Collection field
test_calibre_lookup.py               - automated test for the Calibre metadata lookup (fake subprocess calls)
test_calibre_tools.py                 - automated test for Calibre install-folder discovery
test_sigil_tools.py                     - automated test for Sigil detection + launch
test_ebook_convert.py                  - automated test for Import to EPUB (fake subprocess calls)
test_ebook_polish.py                    - automated test for Polish Book (fake subprocess calls)
test_kobo_usb.py                         - automated test for Send to Kobo (USB)
test_save_errors.py                      - automated test for save-error diagnosis (path-length detection)
test_error_summary.py                    - automated test for the bounded per-book error preview helper
test_app_paths.py                        - automated test for the shared app-data-directory logic
test_crash_log.py                        - automated test for crash logging (append/trim/hook-chaining)
test_missing_space.py                    - automated test for Detect Missing Spaces
test_case_conversion.py                 - automated test for case conversion transforms
test_series_numbering.py                 - automated test for the Number Series generator
test_open_library_lookup.py               - automated test for Open Library metadata + cover lookup (canned responses)
test_cover_generator.py                    - automated test for placeholder-cover color/text decision logic
test_validation.py                  - automated test for validation + fix-application
test_validation_issue.py             - automated test for status classification
test_filename_parser.py               - automated test for the filename parser
test_content_scan.py                   - automated test for content-scan heuristics
test_rename_pattern.py              - automated test for the filename pattern engine
test_genres.py                       - automated test for the genre quick-pick logic
test_isbn.py                          - automated test for ISBN validation/conversion
test_google_books_lookup.py             - automated test for Google Books metadata + cover lookup (canned responses)
test_search_replace.py                  - automated test for the search/replace engine
test_undo.py                              - automated test for the undo stack
test_app_settings.py                       - automated test for settings persistence logic
requirements.txt
build_exe.bat                                - Windows build script
bump_version.py                               - maintainer utility: bumps APP_VERSION from the real system clock
```

## Possible extensions (not included in this version)

- Export/import a CSV of metadata for spreadsheet-based bulk editing
- Content-document (chapter XHTML) well-formedness checking as part of
  validation — deliberately left out of this version to keep loading fast

## License

Licensed under the [GNU General Public License v3.0 or later](LICENSE).
The GUI is built on PyQt6, which Riverbank Computing licenses under GPL
v3 (or a paid commercial license) -- this project ships under
GPL-compatible terms to match.
