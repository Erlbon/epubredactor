# Changelog

All notable changes to The ƎPUB Redactor, by version. Trimmed to new
functionality and real fixes — cosmetic/UX-only adjustments aren't
listed here.

## 2026-09-03#07

- Fixed the app appearing to freeze with no indicator after loading a
  large folder (thousands of files): the per-file loading step already
  had its own progress dialog, but rebuilding the table afterward to
  actually display everything didn't — a single uninterrupted loop that,
  for a genuinely large library, could run long enough to look exactly
  like a frozen, unresponsive app. Now shows progress for a large
  rebuild too, not just the loading step before it.

## 2026-09-03#06

- Load Folder now clears the current list before loading the new
  folder, rather than adding to whatever was already there — picking a
  whole new folder to work in is usually a "start fresh" action. The
  usual unsaved-changes confirmation still applies first if there's
  anything at risk. Load Files and drag-and-drop are unchanged and
  still add to the current list, since those are more often used to
  top up a working set with a few more files.

## 2026-09-03#05

- Parse Filename → Metadata and Rename/Export by Pattern both now show
  every available field code in a clickable side panel — double-click
  one to insert it into the pattern at the cursor's current position,
  rather than needing to type `%field%` names out by hand or read them
  off a single line of small gray text above the field.

## 2026-09-03#04

- Fixed saving (and a couple of related bulk operations) getting
  noticeably slower the more books were selected at once — restoring
  the table selection after an operation was scanning the *entire*
  table once per selected book, rather than once total, making it
  scale quadratically with a large library fully selected. Not related
  to validation or the crash logging added last version (which only
  ever runs when something actually crashes) — a real, now-fixed
  performance bug in the selection-restoration code itself.

## 2026-09-03#03

- Found and fixed the actual cause of the "crashes when opening a huge
  number of files" report, using the crash log added last version: a
  book with a corrupted cover image (a truncated download, bit rot —
  the compressed bytes themselves were damaged, not the zip's
  structure) crashed the *entire* batch load outright instead of just
  failing gracefully on that one file. Wasn't really about file count
  at all — more files just meant higher odds of hitting one damaged
  file, and any file like that took down the whole load. A single bad
  file is now handled the same way every other kind of corrupted file
  already was.
- Loading also now has a second, broader safety net around
  constructing each book: even a completely unanticipated failure on
  one file can no longer stop the rest of a batch from loading.

## 2026-09-03#02

- Fixed the table's selection jumping to a different book after Save
  or Rename/Export: repopulating the table after either didn't restore
  which books were actually selected, so the selection ended up
  pointing at whatever row index happened to hold a book afterward,
  not the one you'd actually selected. Fixed at the root — every
  operation that rebuilds the table now restores the selection by book
  identity, not row position.
- Save Files and Save As Copy now show a progress dialog with each
  filename as it's saved, for 3+ books — previously Save gave no
  feedback at all while it ran.
- Parse Filename → Metadata's recent patterns are now also shown as an
  always-visible, directly clickable list under the field, not only
  behind the "▼" button.
- The startup "early development" notice is no longer shown, since it
  could steal focus from a startup prompt (like "include subfolders?")
  appearing around the same time.
- Added crash logging: any otherwise-unhandled error is now saved,
  with a full timestamped traceback, to `epubredactor_crash.log` next
  to the settings file — including, on a best-effort basis, a minimal
  trace for a genuine native-level crash (via Python's own
  faulthandler), not just an ordinary Python exception. A friendly
  notice pointing at the log file is also shown when this happens,
  where possible.

## 2026-09-03#01

- Fixed Look Up via Calibre sometimes filling the whole dialog with a
  wall of text: when nothing is found, Calibre's own tool can log
  hundreds of very verbose lines to its error output, and that was
  going straight into a status label with no length limit at all — not
  a popup console window (already fixed separately), the app's own
  results area itself. Now bounded to a short excerpt, both at the
  source and as a general safeguard applied everywhere a batch
  operation summarizes per-book errors (Google Books, Open Library,
  Open with Sigil).

## 2026-09-01#12

- You can now rename a single book's file directly, without going
  through the pattern-based Rename/Export tool — double-click a
  filename in the table, or right-click → "Rename File…", type the
  corrected name, done. Acts on disk immediately. Rejects invalid
  Windows filenames and name collisions with a clear message, rather
  than silently modifying or auto-numbering what you typed — a
  single, deliberate rename should end up with exactly the name given,
  or fail clearly.

## 2026-09-01#11

- Parse Filename → Metadata now checks your pattern history against
  the actual filenames you've loaded and opens pre-filled with
  whichever past pattern fits best, instead of just whatever you used
  last (which could easily be from a completely different batch of
  books). The recent-patterns menu also now shows a match count next
  to each entry (e.g. "12/12 match"), so you can see at a glance which
  of your past patterns fits the current batch without trying them one
  by one.

## 2026-09-01#10

- Rename/Export by Pattern's "Recent patterns" is now the same "▼"
  button + full-text menu, anchored under the pattern field, that
  Parse Filename → Metadata already had — replacing the narrow
  truncating dropdown it still had of its own.

## 2026-09-01#09

- Generate Cover from Metadata moved from the Import menu to
  Operations. A new **Generate** button also sits directly under the
  cover preview in the bulk-edit panel now, alongside Add/Replace and
  Delete — applies straight to the current selection, same as those
  two, no separate dialog. The Operations menu version still opens the
  full preview-table dialog for reviewing a larger batch first.

## 2026-09-01#08

- Fixed Save Files blindly re-attempting a book that already failed to
  save, forever, even for causes that can't resolve themselves between
  attempts — most notably a file path too long for Windows to write
  to. Books already flagged "SAVE FAILED" are now skipped by the
  automatic sweep (still clearly flagged, not hidden); double-click
  that status to explicitly retry a specific book once you believe
  the problem's actually fixed. A path-too-long error is also now
  recognized specifically and explained clearly, instead of a generic
  "file could not be written" message.

## 2026-09-01#07

- A book that fails to save (permission denied, file locked by another
  program, etc.) is now flagged **SAVE FAILED** in the Status column,
  with the actual error on hover — persists between Save attempts, so
  you can see which books still need attention without re-triggering
  the same error dialog over and over. Clears automatically the next
  time that book saves successfully.

## 2026-09-01#06

- The app now remembers exactly which books were loaded when you last
  closed it, and reopens with the same set loaded automatically next
  time. Any book that's since moved or been deleted is skipped quietly
  rather than shown as a load error.

## 2026-09-01#05

- New **Generate Cover from Metadata…** (Import menu): creates a
  placeholder cover — title, author, and series if present, on a
  plain background — for selected books, to replace a missing or wrong
  cover. The background color is picked deterministically from the
  title, so the same book always gets the same color again, but a
  batch of different books looks visually distinct rather than
  identical. Preview before applying, same as everywhere else.

## 2026-09-01#04

- Fixed a misleading error when Google Books or Open Library rate-
  limits a search (HTTP 429): it was being reported as "check your
  internet connection," which is wrong — the connection is fine, the
  service is just asking you to slow down. Now retried automatically
  with a short backoff (usually clears up on its own within a few
  seconds), and if it still doesn't clear, the message says so clearly
  instead.

## 2026-09-01#03

- Fixed Parse Filename → Metadata failing outright on a stray extra
  space anywhere in a filename. Literal text between pattern fields
  (e.g. the space in "%author% - %title%") previously had to match
  character-for-character — a double space, or any other run of
  whitespace, broke the match entirely rather than just being
  tolerated. Whitespace in the pattern now matches any amount of
  whitespace in the filename.

## 2026-09-01#01

- Fixed column visibility not persisting: hiding a column only ever
  lasted for the current session — every restart quietly showed every
  column again, regardless of what you'd hidden. Only widths were
  being remembered before; visibility now is too.

## 2026-08-31#11

- Fixed Calibre lookup/convert/polish errors sometimes making the app
  unusable: Windows was popping up a visible console window for
  Calibre's command-line tools, which could steal focus entirely and,
  on a long error message, fill with text with no way back to this
  app's own Apply button until it was closed manually. Suppressed for
  all three Calibre tools at once.
- New **Open with Sigil…** on the table's right-click menu — launches
  [Sigil](https://sigil-ebook.com), a free EPUB editor, for the
  selected book(s), for structural issues this app can't fix itself.
  Offers to locate or download Sigil if it isn't found.

## 2026-08-31#10

- Replaced **Look Up ISBNs** with **Import Metadata from Google
  Books**: the same search now also brings back title, authors,
  publisher, year, genre, language, description, and a cover thumbnail
  — previously everything but the ISBN was thrown away, even though
  it was already sitting in the same response.
- Replaced **Import Cover from Open Library** with **Import Metadata
  from Open Library**: same idea — title, authors, publisher, year,
  ISBN, and genre (subjects) alongside the cover, all from one lookup.

## 2026-08-31#08

- New **Kobo** menu; `bookdrop.cc` added as a second stored suggestion
  alongside `send.djazz.se` for the wireless eReader server list.
- New **Detect Missing Spaces…** (Operations menu): flags a period,
  comma, or similar punctuation directly followed by a letter with no
  space — a common sign of bad text extraction or scraped metadata.
  Scoped to Title and Series for now.
- New **Rebuild Manifest…** (Operations menu): for the "file
  referenced in manifest is missing from archive" validation error.
  Always lists every missing file, for every affected book, before
  anything is touched — nothing is removed without explicit
  confirmation.

## 2026-08-31#07

- Settings moved from the Windows Registry to a plain
  `epubredactor_settings.ini` file next to the executable (or the
  project root in dev mode). Registry settings weren't reliably
  surviving version upgrades; a file is also much easier to back up or
  copy to a new machine.
- Fixed a bug where a pending edit in the bulk-edit panel (a field
  ticked with a value typed in, but not yet Applied) could silently
  vanish if the panel's fields rebuilt (e.g. after a column-visibility
  change) before you clicked Apply.
- Filename-parsed Series # values now have leading zeros stripped
  ("03" → "3", "03.5" → "3.5", decimal part preserved exactly) — that
  padding is a filename-sorting artifact, not meaningful metadata.
- Fixed the bulk-edit panel showing stale or blank fields after a
  change made outside the panel itself (Save, Refresh List, Undo, or
  any metadata-importing dialog) — it previously only refreshed when
  the table selection changed.
- New: when a bulk-edit field shows "`<multiple values>`", you can now
  scroll the mouse wheel over it to cycle through the actual differing
  values in the selection and pick one.

## 2026-08-31#05

- Fixed error dialogs (from Calibre or anywhere else) sometimes
  growing absurdly wide instead of wrapping their text — a long line
  with no natural break point could make a message box stretch wider
  than the whole screen.

## 2026-08-31#03

- Added **Number Series**, under the Operations menu: assigns
  sequential Series # values across a batch of selected books at once,
  in their current table order — the thing a plain bulk-edit can't do,
  since applying one value to every selected book is the opposite of
  what you want when numbering an entire series. Set a starting number
  and a step (fractional steps work too), preview before applying.

## 2026-08-31#02

- Added the inverse of the Author Sort auto-fill guess: a new button
  on the Author(s) field guesses "First Last" back from "Last, First"
  in Author Sort, for whenever Author Sort is already filled in but
  Author(s) needs populating instead.

## 2026-08-30#15

- Fixed column widths resetting unexpectedly: the table was
  auto-fitting every column to content on every rebuild — after Save,
  Refresh, Undo, Delete, basically anything — silently overwriting any
  manual resizing each time. It now only auto-fits once, the first
  time content loads.
- Column widths now also persist across restarts.

## 2026-08-30#14

- Save Files and Save As Copy now apply any pending bulk-edit panel
  changes first. Previously, typing a value into the panel only staged
  it there — it never touched a book's actual in-memory metadata until
  Apply was clicked, so going straight to Save without clicking Apply
  first silently saved without that change.

## 2026-08-30#12

- Fixed Refresh List: it previously only re-read metadata for the
  exact same files already in the list, so if nothing about those
  specific files had changed, the table redrew identically —
  indistinguishable from the button doing nothing. It now genuinely
  re-scans the folders your loaded books live in and picks up new
  files added there.
- Fixed a related crash risk found while working on that: loading a
  file that's been deleted or otherwise become inaccessible raised an
  unhandled exception instead of showing a load error on that row.

## 2026-08-30#10

- Added right-click context menus: the table offers quick access to
  the most common per-selection actions, and column headers got a
  lighter one for hiding a column or opening Add/Remove Columns.

## 2026-08-30#09

- **Send to Kobo (USB)** — detects a Kobo connected via USB (by its
  `.kobo` marker folder, same as Calibre's own device sync) and copies
  selected books straight onto it. No network involved.
- **Send to eReader (Wireless)** — manage a list of send2ereader-style
  server URLs (self-hostable), with `send.djazz.se` included as a
  starting suggestion.

## 2026-08-30#08 — v0.2 Public Beta (Caveat Emptor!)

- `%year%`/`%month%`/`%day%` are now the advertised placeholder tokens
  in Rename/Export and Parse Filename (previously `%pub_year%` etc.,
  which still work silently for backward compatibility).
- The bulk-edit panel's fields now automatically mirror whichever
  table columns are currently visible, in whatever order you've
  dragged them to, rather than needing a separate field-management
  screen.

## 2026-08-30#07

- Expanded the built-in Genre quick-pick list from ~44 to 117 entries.
  Written independently rather than sourced from BISAC, whose license
  doesn't permit redistributing its list in third-party software.

## 2026-08-30#06

- Add/Remove Genres and Add/Remove Languages can now remove built-in
  defaults too, not just custom entries you've added — removing a
  default just hides it (doesn't delete it), and "Restore Hidden
  Defaults" brings back everything hidden this way in one step.

## 2026-08-30#02

- Polish Book — applies Calibre's `ebook-polish` cleanups to selected
  books: smarten punctuation, subset/embed fonts, compress images,
  remove unused CSS, add/remove soft hyphens, insert/remove a book
  jacket page, upgrade EPUB2 → EPUB3. Books with unsaved changes are
  automatically skipped, since polishing works on the file as saved on
  disk, not on in-memory edits.

## 2026-08-29#07

- Validation now re-runs automatically after an in-place save, so the
  Status column reflects what's actually on disk.
- DRM-protected books get their own **DRM** status instead of being
  lumped in with INVALID — a DRM book is a perfectly valid EPUB, just
  off-limits to editing here.

## 2026-08-29#06

- Delete Files — sends files to the Recycle Bin (recoverable), with a
  confirmation prompt.
- Refresh List — reloads every loaded book fresh from disk.
- Import to EPUB — converts other formats (MOBI, AZW/AZW3, DOCX, RTF,
  TXT, FB2, and more) to EPUB via Calibre's `ebook-convert`. PDF is
  deliberately not offered by default (inconsistent conversion
  quality).
- Import Cover from Internet Search — via the Open Library covers API.
- Case Conversion — UPPERCASE / lowercase / Title Case / Sentence
  case.
- Add/Remove Genres and Add/Remove Languages management dialogs.
- Add/Remove Columns (show/hide table columns).

## 2026-08-29#05

- Look Up via Calibre — full metadata lookup via your own Calibre
  installation's `fetch-ebook-metadata` tool, using whichever metadata
  source plugins you have installed and enabled there.

## 2026-08-29#04

- Collection field, distinct from Series — for EPUB3's
  `belongs-to-collection` when it isn't a numbered series (box sets,
  anthologies, themed groupings).
- `%genres%` placeholder added to Rename/Export and Parse Filename
  patterns.

## 2026-08-29#03

- Path column added, showing each book's folder location.

## 2026-08-29#02 — v0.1 Public Beta

- EPUB validation on load, with a Status column (OK / ISSUES /
  INVALID) and a fix-review dialog for safely-automatable issues.
- Parse Filename → Metadata — the reverse of Rename/Export.
- Scan Content for Metadata — heuristic extraction from title/
  copyright pages (publisher, author, ISBN, year, DDC).

## 2026-08-29#01

- Search & Replace across every column, including Filename.
- Undo (last 5 changes).
- Author Sort field (`opf:file-as`).
- Remembers last-used folder across file dialogs.

## Earlier (unversioned) builds

- Initial release: bulk EPUB metadata editing (title, author, series,
  genre, publisher, language, description), mp3tag-inspired UX.
- Rename / Export by Pattern — build filenames from metadata with
  `%placeholder%` tokens.
- Genre quick-pick dropdown.
- ISBN field with checksum validation, plus "Look Up…" via Google
  Books.
- Publication Year/Month/Day, Collection cover image support, DDC
  classification field.
