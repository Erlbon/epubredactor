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
- **Import Metadata from ISFDB (Local Database)** — Metadata > Look Up >
  ISFDB (Local Database)…, on an offline copy of the
  [ISFDB](https://www.isfdb.org) (Internet Speculative Fiction Database)
  you build under Tools > ISFDB Database…. The one source that knows a
  book's **series and its number**, which the Redact step fills too
  ("Fill empty fields from lookups"). By the book's own ISBN where it has
  one, else by title/author; science fiction, fantasy and horror only. See
  "Notes on the local ISFDB database" below.
- **Import Metadata from Google Books** — searches
  [Google Books](https://books.google.com) for each selected book by
  title/author and brings back title, authors, publisher, year, ISBN,
  genre, language, description, and a cover thumbnail together, in one
  review-and-apply step. One checkbox per book chooses whether to bring
  in that book's result at all; if applying it would actually overwrite
  a field that already has a different, non-blank value, a second
  per-field review opens before anything is written (see "Notes on
  Google Books and Open Library lookups" below) — a cover thumbnail
  isn't part of that per-field review, since it's a visual comparison,
  not text.
- **Import Metadata from Open Library** — the same idea via
  [Open Library](https://openlibrary.org): title, authors, publisher,
  year, ISBN, genre (subjects), and cover together. Doesn't import
  Language — Open Library's codes use a different format than this
  app's Language field expects, so it's left out rather than importing
  something that wouldn't match. Same per-field overwrite review as
  Google Books.
- **Generate Cover from Metadata** (Operations menu) — creates a
  placeholder cover (title, author, and series if present, on a plain
  background) for selected books, to replace a missing or wrong cover,
  entirely offline — no lookup, nothing fetched. A **Generate** button
  under the cover preview in the bulk-edit panel does the same thing
  straight to the current selection, no dialog — the menu version opens
  a full preview table first, for reviewing a larger batch before
  committing. See "Notes on Generate Cover" below.
- **Junk Cover flag** — right-click a book with a bad cover (a broken
  converter's generic placeholder, say) and choose **Flag Cover as
  Junk** (also a **Flag as Junk** / **Unflag Junk** toggle button under
  the cover preview in the bulk-edit panel, second row): every OTHER
  loaded book whose cover is byte-for-byte the exact same image gets
  flagged too, automatically, not just the one you clicked. Shows as a
  sortable **Junk Cover** column (click its header to group them
  together), and **Operations > Regenerate Junk Covers…** runs
  Generate Cover from Metadata against every currently-flagged book in
  one go — a freshly generated cover naturally un-flags itself, since
  it's no longer that same junk image. **Unflag Cover as Junk**
  reverses it, same propagation in reverse.
  The flag itself isn't book content — it's not written to the EPUB,
  doesn't dirty the book, and isn't part of Undo, just a standing note
  about a cover image, remembered across restarts like a column width.
- **Cover column** — each book's cover size in pixels: yellow for a
  low-resolution cover (under 1000px tall -- soft on a current
  e-reader), red when there's none. Sortable, so the problem covers
  group together. Only the image header is read, so it's instant.
- **Find Better Covers** (Operations menu) — for the selected books
  (or all) with an ISBN, looks up Open Library's cover for that ISBN
  and offers the ones LARGER than the current cover (or where there's
  none), current and found side by side with their sizes. Untick any
  that aren't the same edition; applied as one Undo step, written on
  Save. Open Library's covers are often modest in size, so this helps
  most with missing and very small covers; it limits lookups by ISBN
  per computer, and the app stops cleanly with a message when it
  refuses.
- **Case Conversion** — UPPERCASE / lowercase / Title Case / Sentence
  case for any column, with a live preview before applying. Title Case
  correctly leaves small connector words ("of", "the") lowercase except
  at the start/end, and doesn't mangle apostrophes the way `str.title()`
  would.
- **Author Sort Conversion** — batch version of the Tag panel's Author
  Sort guess buttons (see "Notes on Author Sort" below for the exact
  rule and its caveats): pick a direction, Author(s) → Author Sort or
  the reverse, and it previews every book that would actually change
  across the whole selection, each with its own checkbox before
  applying — instead of stepping through books one at a time.
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
- **Scan Content for Metadata** — reads the first and last few pages of each
  book (title/copyright page, colophon) for ISBN, publisher, author, year,
  DDC classification, language and series/volume, in English, Norwegian,
  Italian, German and French. Translator, editor, illustrator and edition
  are shown for information only. A best-guess heuristic tool, not a reliable parser —
  review the matches before applying, same as the Google Books and Open
  Library lookups.
- Load individual files, or one or more folders of `.epub` files (the
  folder picker supports Ctrl/Shift-click to select several folders at
  once, since Windows' native one can't — it's Qt's own file dialog for
  that reason, not the native folder browser; asks once, for all of
  them, whether to include subfolders); remembers the last folder you
  used across all "open a file/folder" dialogs, including the
  cover-image picker. Load Folder replaces the current list rather than
  adding to it (with the usual unsaved-changes confirmation first) —
  Load Files and drag-and-drop still add to whatever's already loaded.
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
  **Generate**, **Delete**, and a **Flag as Junk** / **Unflag Junk**
  toggle button (see "Junk Cover flag" above) that apply to every
  selected book at once. A small thumbnail also appears next to each
  book's filename in the table. Nothing touches disk until you Save,
  same as every other edit.
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
- **Import > Suggest Genres…** proposes genres for the selected books
  from their folder path (".../Fantasy/Epic/...", or a bracketed
  "[Sci-Fi]" tag in the filename), their description ("a psychological
  thriller"), catalog lines on their first pages (Library of Congress
  CIP headings, "FICTION / Fantasy / Epic", "This is a work of
  fiction") and their DDC number. Only genres on your Genre list are
  suggested. Ticked genres are **added** to the Genre field; existing
  genres are never replaced or removed, and suggestions for a book that
  already has genres start unticked. Hover "Found In" to see the text
  that matched.
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
  review-before-applying pattern as Google Books/Open Library lookup,
  including the per-field overwrite review (see "Notes on Google Books
  and Open Library lookups" below).
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

## Command line

The one exe (`epubredactor.exe`, or `python main.py` from source) is also the command line. When its first
argument is a command name, it runs that command and the window never opens; with no command, or with a file
or folder to open, the window starts as usual. `epubredactor --help` lists the commands and
`epubredactor COMMAND --help` lists the options of one.

```
epubredactor info      PATH...  [--fields LIST | --all]
epubredactor set       PATH...  -s FIELD=VALUE ... [--clear FIELD ...] [-n]
epubredactor rename    PATH...  [-p PATTERN] [--zero-pad N] [--ascii] [-n]
epubredactor move      PATH...  -p PATTERN [--root FOLDER] [--copy] [--zero-pad N] [--ascii] [-n]
epubredactor convert   PATH...  [--trash-original] [-n]
epubredactor redact    [PATH...] [--recipe FILE] [--enable STEP] [--disable STEP] [--threshold N]
                                 [--trash-dir FOLDER] [--list-steps]
epubredactor validate  PATH...  [--fix] [-n]
```

The command line uses the same code as the window, so the results are the same. It reads the same settings file
(`epubredactor_settings.ini` next to the exe: the saved Redact recipe, the library root, the offline Open Library
and ISFDB databases, the Calibre folder) and the same secret store for the API keys. Not every window function
is available from the command line; the commands above are what is.

### Options every command has

| Option | Meaning |
| --- | --- |
| `PATH...` | One or more EPUB files, folders or wildcards (`D:\Books\Dune*.epub`). A folder is searched recursively for `.epub` files (`convert` looks for the other e-book formats). A file you name is always used. A path that matches nothing is reported, and if nothing at all matches the command stops with exit code 2. A name containing `[` or `]` is taken literally, a wildcard's matches are filtered by extension like a folder's files, and a folder inside a folder that is a link or junction is not followed. |
| `-R`, `--no-recurse` | For a folder, look only at the files directly in it. |
| `--json` | Print one JSON document on stdout instead of text (see "JSON output"). Nothing else goes to stdout. |
| `-q`, `--quiet` | No progress lines and no warnings on stderr (errors are still shown). |
| `-o FILE`, `--output FILE` | Write the result (the text, or with `--json` the JSON document) to FILE instead of stdout. The file is complete when the program exits. This is the reliable way for a script to read a result. |
| `-n`, `--dry-run` | On the commands that change files (`set`, `rename`, `move`, `convert`, and `validate --fix`): show what would happen and change nothing. |
| `-h`, `--help` | Help for the program or for one command. |
| `--version` | The version (top level only). |

Progress lines (`[3/20] name.epub`) go to stderr when more than one file is processed.

### info

`epubredactor info PATH... [--fields LIST | --all]`

Shows each book's validation status (`OK`, `ISSUES`, `INVALID`, `DRM`, or the load error), whether it has a
cover, and its metadata.

| Option | Meaning |
| --- | --- |
| `--fields LIST` | Comma-separated fields to show, e.g. `--fields title,authors,series`. Default: `title, authors, series, series_index, year`. |
| `--all` | Show every field that has a value. |

Only fields with a value are listed. Exit code 1 if a book could not be read.

### set

`epubredactor set PATH... -s FIELD=VALUE [-s ...] [--clear FIELD ...] [-n]`

Sets or empties metadata fields and saves each book in place (the same save as the window's Save). Fields and
values are checked before any book is touched; a bad one stops the command with exit code 2.

| Option | Meaning |
| --- | --- |
| `-s FIELD=VALUE`, `--set FIELD=VALUE` | Set a field (repeat for several). Several authors or genres are separated by `;`: `-s "authors=Frank Herbert; Brian Herbert"`. |
| `--clear FIELD` | Empty a field (repeat for several). |
| `-n`, `--dry-run` | Show the old and new value of each field, save nothing. |

The fields are: title, isbn, authors, author_sort, series, series_index, collection, genres, publisher, year,
month, day, ddc, language, description. Field names are case-insensitive and the usual spellings work: `author`,
`Author(s)`, `genre`, `tags`, `Series #`, `series_number`, `pub_year`.

Checks: `isbn` must be a valid ISBN-10 or ISBN-13 (hyphens are removed); `series_index` is a number (`2`, `2.5`);
`year` is a four-digit year, `month` 1-12, `day` 1-31 (all written with the digits 0-9); `language` is a language
code (`en`, `eng`, `nb`, `en-GB`). A value with a control character in it is refused, and so is a line break or tab
in any field except `description`, since the OPF cannot store them. If a field is given both `-s` and `--clear`,
`--clear` wins whatever the order. A value is compared the way the book stores it (`A;B` and `A; B` are the same
authors).

The save is read back: a value the EPUB cannot hold (a `series_index` on a book with no series, a `month` or `day`
without a `year`, clearing the `isbn` that is the book's primary identifier) makes the book `failed` with the field
named in `not_stored`, instead of being claimed as changed. A DRM-protected book is edited like any other, with a
warning: its metadata is changed, the protected content is not touched.

Each book's result is `changed`, `unchanged` (nothing differed), `planned` (dry run) or `failed`.

### rename

`epubredactor rename PATH... [-p PATTERN] [--zero-pad N] [--ascii] [-n]`

Renames each book from its metadata, in its own folder, like Rename / Export / Move > Rename files in place.
Never overwrites: a name that is taken gets `(2)`, `(3)`, ... A change of letter case alone (`song` to `Song`) counts as a rename.

| Option | Meaning |
| --- | --- |
| `-p PATTERN`, `--pattern PATTERN` | The new name (without `.epub`), with `%field%` tokens, e.g. `"%series% %series_index% - %title%"` (the default). Quote it so the shell leaves the `%` signs alone. |
| `--zero-pad N` | Pad the series number to N digits (`--zero-pad 2` gives `02`). Default: the choice saved in the app's Rename window (on, with its width, or off); `--zero-pad 0` turns it off. |
| `--ascii` | ASCII-safe names (é becomes e, æ becomes ae, other symbols are dropped). Also on when the app's Rename window has it saved. |
| `-n`, `--dry-run` | Show the new names, rename nothing. |

Tokens: `%title%`, `%isbn%`, `%authors%`, `%author_sort%`, `%series%`, `%series_index%`, `%collection%`, `%genres%`,
`%publisher%`, `%year%`, `%month%`, `%day%`, `%ddc%`, `%language%` (the window's Rename dialog lists them all; `%tags%`,
`%pub_year%`, `%pub_month%` and `%pub_day%` are other spellings of `%genres%`, `%year%`, `%month%` and `%day%`). A token
that is not in that list (a typo such as `%tittle%`) is refused with exit code 2 instead of silently rendering as
nothing, and a rename pattern cannot contain `/` or `\` (`move` makes folders). A book the pattern gives no name for (all
its fields are empty) is `skipped`, not renamed to "untitled". A book that already has the name is `unchanged`. There is
no undo for the command line: preview with `--dry-run`.

In a batch file write `%%` for each `%` (`-p "%%series%% %%title%%"`): cmd expands a single `%name%` itself, and a pattern
that then reads nothing makes the book `skipped`.

### move

`epubredactor move PATH... -p PATTERN [--root FOLDER] [--copy] [--zero-pad N] [--ascii] [-n]`

Moves (or copies) each book into a folder tree under a library folder, like Rename / Export / Move > Move into
folders. The pattern may contain `/` to make sub-folders: `"%authors%/%series%/%title%"`. Missing folders are
created; nothing is overwritten (a taken name gets `(2)`); a destination outside the library folder or too long
is refused.

| Option | Meaning |
| --- | --- |
| `-p PATTERN`, `--pattern PATTERN` | Required. The path under the library folder, with `%field%` tokens. |
| `--root FOLDER` | The library folder. Default: the one saved in the app (Rename / Export / Move window). The folder must exist. |
| `--copy` | Copy instead of move, leaving the originals. |
| `--zero-pad N`, `--ascii` | As for `rename`. |
| `-n`, `--dry-run` | Show where each book would go, change nothing. |

Across volumes a move is a verified copy followed by sending the original to the Recycle Bin. A book the pattern
has no name for is `skipped`. There is no undo for a move either: preview with `--dry-run`.

### convert

`epubredactor convert PATH... [--trash-original] [-n]`

Converts MOBI, AZW, AZW3, KFX, DOCX, ODT, RTF, TXT, FB2, CBZ and the other formats Calibre reads to EPUB with
Calibre's `ebook-convert` (Calibre must be installed; the app finds it on PATH, in its usual install folders or in
the folder saved under Tools), beside the original (same name, `.epub`). Never overwrites: if the `.epub` already
exists the file is `skipped`; an EPUB is `skipped` too, and so is a file whose extension Calibre does not convert
(a named file is otherwise always used) and the second of two files in one run that would become the same `.epub`
(`--dry-run` says the same).

| Option | Meaning |
| --- | --- |
| `--trash-original` | After the `.epub` is made and read back successfully, send the original to the Recycle Bin (never deleted for good; if the new file cannot be read, or the Recycle Bin refuses, the original is kept and a warning says so). |
| `-n`, `--dry-run` | Show what would be converted, change nothing. |

Results: `converted`, `skipped`, `planned`, `failed`. The new path is in `new_path`. Without Calibre the command
stops with exit code 1 and says so.

### redact

`epubredactor redact [PATH...] [--recipe FILE] [--enable STEP] [--disable STEP] [--threshold N] [--trash-dir FOLDER] [--list-steps]`

Runs the Redact recipe on the books, the same steps as Operations > Redact: repair, clean up, tags from the path
and filename, lookups on Open Library, ISFDB and Google Books, cover, rename, move into folders. Each changed book
is saved in place and its original goes to the Recycle Bin (or `--trash-dir`). Guesses below the confidence
threshold are listed under "needs review" and not applied. There is no `--dry-run`: use `info` and `validate`
first, and `--disable` for the steps you do not want. The cover step replaces a cover only with a better one it
finds (it measures the sizes itself); a cover that has to be drawn (regenerating a junk cover) needs the window and
is skipped from the command line.

| Option | Meaning |
| --- | --- |
| `--recipe FILE` | Use this recipe (a JSON file in the format the app stores) instead of the one saved in the app. |
| `--enable STEP` | Turn a step on for this run (repeatable). |
| `--disable STEP` | Turn a step off for this run (repeatable). |
| `--threshold N` | Confidence needed to apply a guess: a fraction `0`-`1` (`0.9`, also `1`), or a percentage with at least two digits (`90`, `90%`, `100`); a number above 1 and below 5 such as `1.5` is refused as ambiguous. |
| `--trash-dir FOLDER` | Move originals into this folder (created if needed) instead of the Recycle Bin, for a machine or a task that has none. |
| `--list-steps` | Show the steps and whether the recipe has each on, then stop (no `PATH` needed). |

Steps: `validate_fix`, `dedupe_manifest_ids`, `rebuild_manifest`, `repair_navigation`, `generate_toc`,
`strip_description_html`, `language`, `path_tags`, `scan_isbn`, `scan_publisher`, `scan_year`, `scan_series`,
`metadata_lookup`, `clean_authors`, `cover`, `rename`, `move_into_folders`. Without `--recipe` the recipe saved in
the app is used (the defaults if none was saved). The offline databases, the library root and the saved patterns
come from the app's settings. A book that is DRM-protected is left untouched (`set` and `validate --fix` do edit
one, with a warning, because you named the change). A `--recipe` file that is not valid JSON or not a recipe is refused
(exit code 2) rather than replaced by the default recipe. Exit code 1 if any book failed; books that need review are
not failures.

### validate

`epubredactor validate PATH... [--fix] [-n]`

Checks each book's structure, the same checks as the Validate / Fix dialog, and lists the issues with their
severity and whether they can be repaired automatically. With `--fix` the fixable issues are repaired and the
book is saved in place; the status afterwards is what is on disk. The `mimetype` warnings count as fixable: every
save writes a correct `mimetype` entry. `fixed` lists only what reached the file; a book that could not be saved
is a `problem` with `not saved` in its message and nothing in `fixed`.

| Option | Meaning |
| --- | --- |
| `--fix` | Repair the fixable issues and save the book. |
| `-n`, `--dry-run` | With `--fix`: list what would be fixed, change nothing. |

Exit code 1 when a book still has errors or warnings (or could not be read) after the command. A DRM lock on
its own is reported (`DRM`) but is not a failure; a DRM-protected book that also has warnings or errors is one. With `--fix`
a DRM-protected book is repaired too, with a warning.

### JSON output

`--json` prints one document: `{"results": [...], <summary fields>, "warnings": [...], "errors": [...]}`. It is ASCII-only (a non-ASCII character in a path is a `\uXXXX` escape, which any JSON reader decodes). If a command fails or is interrupted after it started, the document is still printed, with what was done so far and an `error` entry, so a script reading `--output FILE` never finds an empty or half-written file.

| Command | Each entry in `results` | Summary fields |
| --- | --- | --- |
| `info` | `path`, `status`, `has_cover`, `issues` (a count), `fields` (name to value) | `files`, `failed` |
| `set` | `path`, `status`, `changes` (field to `{old, new}`), `message` | `files`, `failed`, `dry_run` |
| `rename`, `move` | `path`, `status`, `new_path`, `message` | `files`, `failed`, `dry_run`, and `pattern` or `root` |
| `convert` | `path`, `status`, `new_path`, `message` | `files`, `failed`, `dry_run` |
| `redact` | `file`, `path`, `status`, `applied`, `needs_review` (step, value, confidence, reason), `failures`, `notes`, `skipped`, `not_saved` | `files`, `failed`, `needs_review`, `cancelled`, `confidence_threshold`, `run_notes` |
| `redact --list-steps` | `step`, `label`, `enabled` | `confidence_threshold` |
| `validate` | `path`, `status`, `problem`, `issues` (code, severity, message, fixable), `fixed`, `issues_after`, `message` | `files`, `problems`, `fix`, `dry_run` |

### Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Done (files that were skipped or unchanged are not failures). |
| 1 | The command ran but some books failed (for `validate`: some books have problems), or Calibre is missing for `convert`. |
| 2 | Bad arguments, an unknown field or step, or no files found. The reason is on stderr. |
| 70 | An internal error (a bug); the traceback is on stderr. |
| 130 | Interrupted with Ctrl+C. |

### Using it from scripts and scheduled tasks (Windows)

`epubredactor.exe` is a windowed program, and Windows shells treat those differently from console programs:
typed by hand in a terminal its output appears there and `>` / `|` redirection works, but an interactive shell
does not wait for it (the prompt can come back before the output), and a script cannot read a windowed
program's output unless it is redirected. So for automation: ask for the result in a file with `--output`, wait
for the process, and read the exit code.

```
:: batch file (cmd waits for the program in a batch file; %errorlevel% is the exit code)
epubredactor.exe validate "D:\Books" --json --output "%TEMP%\validate.json"
if errorlevel 1 echo some books have problems

:: interactive cmd: start /wait waits and keeps the exit code
start /wait epubredactor.exe redact "D:\Incoming" --quiet --trash-dir "D:\Trash"

# PowerShell: wait with Start-Process, read .ExitCode
$p = Start-Process epubredactor.exe -ArgumentList 'validate','D:\Books','--json','-o','C:\Temp\validate.json' -Wait -PassThru
$p.ExitCode
(Get-Content C:\Temp\validate.json -Raw | ConvertFrom-Json).results | Where-Object problem

# PowerShell: piping to Out-Null also waits
epubredactor.exe convert "D:\Incoming" --trash-original | Out-Null; $LASTEXITCODE
```

Task Scheduler waits for the program and records its exit code as it is. On Linux and macOS there is no such
distinction: the output goes to the terminal and pipes as usual.

### Examples

```
epubredactor info "D:\Books\Herbert" --all                                  what is in a folder
epubredactor set "D:\Books\Herbert" -s series="Dune Chronicles" -n          preview a bulk edit, then run it without -n
epubredactor set dune.epub -s isbn=978-0-441-17271-9 -s series_index=1
epubredactor rename "D:\Books\Herbert" -p "%authors% - %title%" --ascii -n
epubredactor move "D:\Incoming" -p "%authors%/%series%/%series_index% - %title%" --zero-pad 2 --root "D:\Library"
epubredactor convert "D:\Incoming" --trash-original                          MOBI/AZW3/DOCX to EPUB, recycle the originals
epubredactor validate "D:\Books" --fix --json -o report.json                 repair what can be repaired, report the rest
epubredactor redact "D:\Incoming" --disable metadata_lookup --trash-dir "D:\Trash"
```

What the commands will not do: overwrite a file, delete anything for good, or ask a question. Everything that
could be a prompt in the window is a flag here or a skipped file in the report.

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
- One checkbox per book decides whether to bring in that book's result
  at all — title, authors, publisher, year, ISBN, genre, cover, and
  (Google Books only) language and description. Untick anything you
  don't trust before Apply.
- **Overwrite review**: if applying the checked results would actually
  replace a field that already has a different, non-blank value (not
  just filling in something that was blank), a second dialog opens
  first — every touched field, current value next to the new one, its
  own checkbox. A field that's currently blank starts ticked (nothing
  to lose); a genuine overwrite starts UNTICKED, so it takes a
  deliberate opt-in per field rather than accepting a whole book's
  worth of fields just to get the one you actually wanted. A totally
  clean batch (nothing would be overwritten anywhere) skips this
  review entirely. Cover images aren't part of this per-field review —
  they're a visual comparison, reviewed via the thumbnail instead.
  Same mechanism backs Look Up via Calibre, and the family's
  cbzredactor sibling, where it originated.
- Neither needs an API key for this app's usage level.
- Open Library's Language field isn't imported — it uses a different
  code format (3-letter) than this app's Language field expects
  (2-letter ISO 639-1) — see core/open_library_lookup.py for the
  reasoning if you're curious.

## Notes on the local Open Library database

Tools > Open Library Database... builds an offline lookup database from
Open Library's bulk dumps (editions, plus authors for names; you download
them, the app never does). Metadata > Look Up > Open Library (Local
Database)... and the Redact "Fill empty fields from lookups (local database first)" step then use it
before any online source. Only editions with a valid ISBN are kept, in the
languages you choose.

Measured on real samples (the first 25,000 editions and 104,000 authors of
the 2026-08-31 dumps, which are the start of the key-sorted files and not
representative of the whole): every line had the 5 columns; ~292-296 bytes
per kept edition; `languages` are MARC-style 3-letter keys (`eng`, `ger`,
`fre`, `nor`, also `cmn`, `mul`, `und`); `covers` is a list of integer ids
(sometimes `-1`, ignored); `authors` is `[{"key": ...}]` and an author
reference may not be in the authors dump, in which case the edition keeps
the key but no name; publish dates are almost always "March 14, 2001",
"April 1998", "1997" or ISO.

Optional works dump: many editions list no author while their work does.
Give the works dump (or the all-types dump) as a third source and editions
without authors of their own take their work's (the work's `authors` are
`[{"author": {"key": ...}, "type": {...}}]`, checked against one live work
record). It is an extra pass before the editions pass, storing work -> author
keys in a temporary on-disk table; ESTIMATE (no works dump has been read):
roughly 10-15 more minutes and ~1 GB more temporary disk.

Covers: a local match records Open Library's cover id. Find Better Covers
and the Redact cover step fetch `covers.openlibrary.org/b/id/<id>-L.jpg`
directly for it (same size cap and image checks as the ISBN path; no per-IP
ISBN limit), the local lookup dialog shows that cover beside the current one,
and Apply sets it exactly as for the online lookup. Nothing is fetched unless
you run one of those; ids <= 0 are skipped.

Still unverified: the full dumps (size, speed and memory at 10^7 scale),
the distribution of languages and ISBNs outside the start of the file, and
how many editions lack an author but have one on their work (the works dump
isn't used yet). Cover ids are recorded on the lookup result but never
fetched.

## Notes on the local ISFDB database

Tools > ISFDB Database... builds an offline lookup database from the ISFDB's
MySQL backup (`backup-MySQL-55-YYYY-MM-DD.zip`, from
isfdb.org/wiki/index.php/ISFDB_Downloads; you download it, the app never
does). Metadata > Look Up > ISFDB (Local Database)... and the Redact "Fill
empty fields from lookups" step use it before Open Library. Its reason to
exist is the **series and series number**; the ISFDB's own web API has no
title, author or series lookup (only by ISBN, external ID or publication
number, and no series), so a local copy is the only route to them.

Measured on the real backup of 2025-12-27 (1.5 GB of SQL, 68 tables, UTF-8
text although the tables declare latin1): the nine tables the build reads
(8.4 million rows) stream in about 70 s; the whole build took 104 s here
and gives a 154 MB database with 425,406 books (211,123 of them in a series,
97,755 variant/translated titles that inherit their parent's series) and
638,577 editions with a valid ISBN (116,684 of them ebooks), out of 921,821
publications. Lookups take milliseconds (15 lookups: 0.13 s). A title is the abstract book and a
publication one printing: `works` carries title, authors, first-publication
year, series, number and language; `editions` carries ISBN, publisher, date,
binding and pages. The account tables of the dump (`mw_user`, `emails`,
`web_api_users`) are never read.

Matching: an exact ISBN is trusted (95%) like any ISBN match; a title and
author match is a guess (60%) and goes to Needs review. A title match fills
the ISBN only when it is safe: an ISFDB ebook edition of the book (closest in
year), else a print edition from the very year the book already says, and
never when editions of different publishers are equally close. The series
name drops the "(Author)" ISFDB adds to tell series apart ("Voyagers (Ben
Bova)" becomes "Voyagers"); a series number is only taken together with its
series, or for a book that already has that very series. Numbers like 2.5
come from the ISFDB's own sub-numbering. Series names ISFDB writes with
alternatives ("Neuromancer / Sprawl Trilogy") are taken as they are.

The ISFDB's data is licensed Creative Commons Attribution; it is credited in
CREDITS.md (Help > Credits).

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
core/language_detect.py          - stopword-based en/no/it/de/fr language guess
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
core/toc_generate.py                    - heading-based table-of-contents generation (Generate Table of Contents)
core/missing_space.py                   - punctuation-adjacent-to-letter detection (Detect Missing Spaces)
core/case_conversion.py                - UPPERCASE/lowercase/Title Case/Sentence case transforms
core/series_numbering.py                - sequential Series # generator (Number Series)
core/open_library_lookup.py             - Open Library metadata + cover lookup, network call injectable for testing
core/isfdb_import.py                    - builds the offline ISFDB lookup database from its MySQL backup (Tools > ISFDB Database)
core/isfdb_local.py                     - queries over that database: by ISBN, by title/author, with series and number
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
gui/toc_generate_dialog.py           - the Generate Table of Contents dialog
gui/send_to_ereader_dialog.py        - the Send to eReader (Wireless) dialog
gui/os_utils.py                       - shared OS helpers (reveal a file in the file manager)
gui/open_library_dialog.py         - the Import Metadata from Open Library dialog
gui/isfdb_dialog.py                - the Import Metadata from ISFDB (Local Database) dialog
gui/isfdb_settings_dialog.py       - Tools > ISFDB Database: where the database is, and Build from the backup
gui/cover_render.py                   - draws the actual placeholder cover image (QPainter/QImage)
gui/cover_generator_dialog.py         - the Generate Cover from Metadata dialog
gui/case_conversion_dialog.py       - the Case Conversion dialog
gui/author_sort_dialog.py            - the Author Sort Conversion (batch) dialog
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
test_isfdb.py                             - automated test for the ISFDB build, lookups, Redact step, dialogs and menus (synthetic backup)
test_cover_generator.py                    - automated test for placeholder-cover color/text decision logic
test_validation.py                  - automated test for validation + fix-application
test_validation_issue.py             - automated test for status classification
test_filename_parser.py               - automated test for the filename parser
test_content_scan.py                   - automated test for content-scan heuristics
test_content_scan_multilingual.py       - multilingual patterns, language, series, back matter, dialog
test_rename_pattern.py              - automated test for the filename pattern engine
test_genres.py                       - automated test for the genre quick-pick logic
test_isbn.py                          - automated test for ISBN validation/conversion
test_google_books_lookup.py             - automated test for Google Books metadata + cover lookup (canned responses)
test_search_replace.py                  - automated test for the search/replace engine
test_undo.py                              - automated test for the undo stack
test_app_settings.py                       - automated test for settings persistence logic
test_main_window_overwrite.py              - automated test for the per-field overwrite-review wiring in the three metadata-lookup handlers
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
