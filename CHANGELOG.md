# Changelog

All notable changes to The ƎPUB Redactor, by version. Trimmed to new
functionality and real fixes — cosmetic/UX-only adjustments aren't
listed here.

## 2026-09-17#07

- Fixed: several batch operations (Undo/Redo, Search/Replace, Number
  Series, Rebuild Manifest, Repair Navigation, Validate/Fix Issues, Set
  Blank/Unknown Language to Default, and more -- 14 places in total)
  refreshed each affected book's row one at a time in a way that
  re-scanned the *entire table* per book to find it, an O(n^2) cost for
  any operation touching a large share of a large library. Fixed with a
  proper bulk refresh that builds the row lookup once for the whole
  batch. This was the real cause behind reports of the app freezing
  during otherwise-ordinary batch edits on a large library.
- Fixed: 9 dialogs (Strip HTML from Description, Case Conversion,
  Author Sort Conversion, Compress Images, Rebuild Manifest, Detect
  Missing Spaces, Repair Navigation, Validate/Fix Issues, Regenerate
  Junk Covers) had no progress feedback at all while scanning a large
  library -- the window could look frozen with no indication anything
  was happening. All now show progress, consistent with the rest of
  the app.
- Fixed: identifying a book's cover as "Junk" re-hashed the full cover
  image synchronously on the main thread, once per book, on every
  table rebuild -- for a large library with real cover art, several
  real seconds of hashing blocked the UI on every Save/Undo/Refresh.
  Now computed off the main thread the same way cover icon decoding
  already was (bumped `redactor_common` to `2026-09-17-02`).

## 2026-09-17#05

- New **Repair → Strip HTML from Description**: converts a Description
  field that's literally raw HTML (some EPUBs' `dc:description` is a
  publisher's marketing page copy-pasted verbatim, tags and all) into
  clean plain text -- tags removed, entities decoded, real paragraph
  breaks kept. Same preview-then-apply shape as Case Conversion: only
  books whose description actually contains markup are listed, each
  with its own checkbox, nothing changes until you click Apply.

## 2026-09-17#04

- Fixed: a Description containing raw HTML with embedded newlines
  (e.g. imported verbatim as `<div>\n<p>...</p>\n<p></p>...`) could
  still blow a row up to several lines tall even in a "fixed row
  height" Text Wrapping mode (Truncate/Clip). Qt renders a literal
  newline in cell text as a real line break regardless of the word-wrap
  setting -- word wrap alone only controls whether one long line breaks
  to fit the column width. Truncate/Clip now collapse a Description's
  embedded newlines for display; Wrap Text still shows them as real
  paragraph breaks, same as a spreadsheet's own wrap-text behavior
  would. Only ever affects what's shown in the table -- the book's
  actual Description is never touched by this.

## 2026-09-17#03

- Fixed: "Updating list" (rebuilding the table after loading, saving,
  undoing, or deleting) could be dramatically slower than it needed to
  be for a large library -- an async cover-icon callback was scanning
  every row to find the one it applied to, once per book, an O(n^2)
  cost that dominated everything else combined (measured: ~21.5s for
  5000 books, down to ~1.5s after the fix; scales linearly now instead
  of quadratically).
- Fixed: checking whether a book's cover is flagged "Junk" re-hashed
  the full cover image on every table rebuild, for every book with a
  cover -- now cached, only re-hashed when the cover actually changes.
- Fixed: the "Loading books…"/lookup/scan/polish/etc. progress dialogs
  could visibly jump around in size as filenames of very different
  lengths scrolled through their label text. Fixed at the shared
  `redactor_common` level (bumped to `2026-09-17#01`) -- every progress
  dialog across the app now holds a steady width.

## 2026-09-17#02

- New **Repair** menu, split out of Operations: Validate/Fix Issues,
  Rebuild Manifest, and Detect Missing Spaces moved here, alongside two
  new actions below.
- New **Repair Navigation**: removes broken EPUB2 `<guide>` references
  and archive files present but referenced by no manifest item
  ("orphaned" files). Doesn't touch NCX/NAV document content itself
  (duplicate TOC entries, duplicate element ids, cross-document
  fragment links) -- a separate, larger undertaking for later.
- New **Set Blank/Unknown Language to Default**: fills in a chosen
  language for every book in the working set with no language set (or
  a placeholder like "unknown") -- applies immediately, no per-book
  review. **Settings → Blank Language Default** controls the target
  language and can disable the action outright.
- Fixed: saving no longer silently drops a book's author role
  information -- every author is now written with `opf:role="aut"`.
- New **Operations → Compress Images (Lossy)**: re-encodes JPEG
  images at a chosen quality to shrink the archive, at a real quality
  cost -- separate from Polish Book's existing lossless compression.
- Fixed: opening a large library could be noticeably slower than it
  needed to be on a fresh install (no saved column widths yet) -- a
  debounced row-height reflow (see 2026-09-17#01) was firing during the
  table's own one-time column auto-fit after loading, adding an
  unnecessary full-table re-measure pass right when it mattered most.
- `build_exe.bat` no longer waits for a keypress after a successful
  build (error paths still do, so a double-clicked build's error stays
  visible).

## 2026-09-17#01

- Fixed: a table row's height could go out of sync with its wrapped
  text after resizing a column (text overlapping or getting clipped) --
  row heights are now re-measured after every column resize. Added a
  **Settings -> Text Wrapping** menu to choose how an over-long cell
  value is shown: **Wrap Text** (grow the row, the previous behavior,
  now actually working correctly), **Truncate with "..."**, or **Clip,
  No "..."** (both keep every row a fixed single-line height instead).
  Remembered across sessions.
- Rename/Export: `%authors%` now joins multiple authors with `" & "`
  in the rendered filename (`Author A & Author B`) instead of the
  Authors field's own `"; "` separator, which read as a stray mid-
  filename character.
- New: **Import Metadata from Filename** can now detect the `%pattern%`
  for you -- right-click a book whose metadata is already correct and
  choose "Detect Pattern from This Book's Current Metadata" to
  reverse-engineer the naming convention from it, instead of typing the
  pattern out by hand.

## 2026-09-14#05

- New **per-field overwrite review** for Look Up via Calibre, Import
  Metadata from Google Books, and Import Metadata from Open Library:
  if applying a found result would actually replace a field that
  already has a different, non-blank value, a second dialog opens
  first -- every touched field, current value next to new, its own
  checkbox. A blank field starts ticked (nothing to lose); a genuine
  overwrite starts unticked, so accepting a book's good fields no
  longer means accepting every field it found, bad ones included (the
  underlying reason `file-as="Unknown"` could silently clobber a
  correct Author Sort, fixed narrowly last version). A clean batch
  (nothing would be overwritten anywhere) skips this review entirely.
  Built on `redactor_common.gui.overwrite_review_dialog`, promoted
  there from cbzredactor, where it originated. Bumped `redactor_common`
  to `2026-09-14-01`.

## 2026-09-14#04

- Fixed: Look Up via Calibre could silently overwrite a correct Author
  Sort with the literal text "Unknown" -- Calibre's own
  fetch-ebook-metadata frequently returns that as a placeholder
  `file-as` when a plugin found the author's name but couldn't work
  out a real sort form for it. That placeholder is now dropped rather
  than parsed as a real value, matching Author Sort's own "empty means
  nothing found" convention everywhere else.

## 2026-09-14#03

- Generate Cover from Metadata / Regenerate Junk Covers now show a
  progress dialog ("Generating: foo.epub") while rendering previews,
  instead of silently doing nothing on screen for however long a
  batch takes -- rendering each placeholder cover is real work
  (1200x1800 QPainter draw + PNG encode), so a batch of more than a
  couple of books could look exactly like the app had frozen. Built on
  the same shared `run_with_progress` helper as Save.

## 2026-09-14#02

- Junk Cover flag is now also available right where you're looking at
  the cover: a **Flag as Junk** / **Unflag Junk** toggle button under
  the cover preview in the bulk-edit panel, next to Add/Replace,
  Generate, and Delete (now two rows of buttons instead of one, to fit
  it). Same propagation as the table right-click version -- flagging
  flags every other loaded book sharing that exact cover image too.

## 2026-09-14#01

- New **Junk Cover** flag: right-click a book with a bad cover and
  choose Flag Cover as Junk -- every other loaded book whose cover is
  byte-for-byte the exact same image (a broken converter's generic
  placeholder, say) gets flagged too, automatically. Shows as a
  sortable Junk Cover column, and Operations > Regenerate Junk
  Covers… runs Generate Cover from Metadata against every flagged book
  at once. Not tracked by Undo and never written to the EPUB -- it's a
  standing note about a cover image, not book content, remembered
  across restarts like a column width.

## 2026-09-13#06 -- Cover icons: cached, and decoded off the UI thread

Follow-up to the discussion in `#05`'s entry about the list-rebuild
step being slow for a large library: found and fixed the actual
dominant cost. `_apply_cover_icon()` was re-decoding and re-scaling
every book's cover from raw bytes on every single table rebuild --
Save, Undo, Delete, Refresh -- even though the cover hadn't changed
since the last rebuild. For a genuinely large library that's
thousands of redundant JPEG/PNG decodes on the UI thread, every time.

Now built on `redactor_common.gui.async_icon_cache.AsyncIconCache`:
- A book's icon is cached and reused across rebuilds until its cover
  actually changes (cover add/replace/delete/generate).
- A genuine cache miss (a real new/changed cover) decodes and scales
  in a background thread pool instead of blocking table population --
  the row shows up immediately with a blank icon, and the real one
  fills in independently, whenever its own decode finishes, updating
  only that one cell. No rebuild, no re-layout, nothing else touched.
- Robust to a rebuild, sort, or removal happening while a decode is
  still in flight (re-derives the book's current row fresh via the
  existing `_find_row_for_book()`, rather than trusting a row number
  captured back when the request was made).

Bumped `redactor_common` to `2026-09-13-04`.

## 2026-09-13#05 -- Save's progress dialog now shared, not hand-rolled

`_save_books()`'s own copy of the "progress dialog with a per-file
label" pattern is retired -- now built on
`redactor_common.gui.run_with_progress`'s new `label_for` param (added
specifically so this and video's near-identical hand-rolled copy could
both go away). No behavior change: same threshold, same Cancel
button, same per-file "Saving: foo.epub" label. Bumped `redactor_common`
to `2026-09-13-03`.

If you're seeing Save look frozen on a very large batch (5000+ files):
this progress dialog has existed since `#07` on 2026-09-03 -- check
you're running a build from on or after that date. The list-rebuild
step immediately after Save finishes has had its own progress dialog
since the same date, for the same reason; a further look at *why*
rebuilding is still slow for a batch that size is a separate,
follow-up discussion, not addressed in this entry.

## 2026-09-13#04 -- Ctrl+E/Ctrl+I export/import shortcut pairing

Rename Files (Pattern)... moves from Ctrl+Shift+R (this morning's
choice) to **Ctrl+E**, and Import Metadata from Filename... from
Ctrl+E to **Ctrl+I** -- a deliberate export/import mnemonic pair for
the two directions of the filename<->metadata relationship, requested
explicitly. Applied family-wide via
`redactor_common.gui.standard_shortcuts`.

## 2026-09-13#03 -- hotkey audit: Redo, real F2, and family-wide alignment

Full audit of keyboard shortcuts across the whole Redactor family
against Qt's own Windows-standard bindings (verified via
`QKeySequence.keyBindings()`, not assumed). Real changes here:

- **New Redo** (Ctrl+Y, Operations menu and toolbar, right after Undo)
  -- `redactor_common.core.undo.UndoManager` gained real redo support.
- **F2 now directly renames the one selected file** (Explorer
  convention) -- same action the right-click "Rename File…" already
  did, now also reachable by keyboard. The pattern-based batch tool
  ("Rename Files…") moves to **Ctrl+Shift+R** to make room -- matches
  videoredactor's own existing convention for the same shape of
  feature.
- **"Save As Copy…" moves from F4 to Ctrl+Shift+S** --
  `QKeySequence::SaveAs`, and cbzredactor's own existing "Save As..."
  key; F4 had no real meaning as "Save As" anywhere.
- **Import Metadata from Filename… moves from F3 to Ctrl+E** -- F3 is
  `QKeySequence::FindNext` (search) everywhere else; a metadata tool
  had no business sitting on it.
- **Search/Replace… gains Ctrl+H** (`QKeySequence::Replace`).
- **About gains F1** (`QKeySequence::HelpContents`).
- **Exit's shortcut hint removed** (it never had one to begin with,
  now deliberately so) -- Alt+F4 already closes this (or any) app at
  the OS level, verified with a real launch-and-close test.

New shared `redactor_common.gui.standard_shortcuts` module is now the
source of truth for all of the above, imported instead of literal key
strings, so this doesn't drift again.

## 2026-09-13#02

- New **Author Sort Conversion** (Operations menu) — batch version of
  the Tag panel's per-book Author(s) ↔ Author Sort guess buttons, one
  of the most repeated single-book actions. Pick a direction, preview
  every book across the selection (or the whole list) that would
  actually change, uncheck any you don't want, then apply the rest in
  one go.

## 2026-09-13#01

- Load Folder's multi-folder picker no longer reopens serially until
  you cancel (confusing — that's not what "pick more than one" should
  feel like). It's now a single dialog where Ctrl/Shift-click selects
  several folders at once, same as any multi-select file list. Windows'
  native folder picker has no such multi-select, so this uses Qt's own
  (non-native) dialog instead — it looks like Qt's file browser rather
  than the OS one, which is the trade-off for getting real multi-select.

## 2026-09-10#02

- `core/series_numbering.py` promoted to `redactor_common` (used by
  both Operations > Number Series and the table right-click's quick
  version) -- deleted the now-redundant local copy and its test file.
  No behavior change. Bumped the pin to `2026-09-10-04`.

## 2026-09-10#01 -- smaller download

No functional changes. The built .exe is now noticeably smaller
(~44.2MB -> ~38.6MB, about 13%) because UPX compression -- already
configured in the PyInstaller spec (`upx=True`) but never actually
installed in the build environment, so it had silently done nothing on
every release so far -- is now genuinely wired into `build_exe.bat`.
Same fix applied across the whole Redactor family.

## 2026-09-07#02

A cross-repo review of `redactor_common` adoption across all four
Redactor apps turned up several modules that were originally
generalized FROM this project's own code, but this project itself was
never actually switched onto the shared result -- so two near-
identical implementations existed to maintain instead of one. Fixed:

- **Selection color fix** (shared, `redactor_common` 2026-09-07-01):
  `colors.py`'s `TABLE_SELECTION_STYLESHEET` used to hardcode a
  selected row's own background/text color, which silently overrode
  `apply_theme()`'s WCAG-verified, light/dark-aware selection colors
  on this project's table specifically. Fixed at the source; bumping
  the pin here picks it up automatically.
- `gui/main_window.py`'s own `_make_action()` -- byte-for-byte the
  code `redactor_common.gui.action_factory.make_action()` was lifted
  from -- is now the shared one.
- The local `core/undo.py` (the code `redactor_common.core.undo.
  UndoManager` was generalized from, once cbzredactor needed the same
  behavior for its own item type) is retired; this project now uses
  the shared, generic version via two small adapter methods
  (`MainWindow._snapshot_book`/`_restore_book`).
- The local `core/save_errors.py` and `core/error_summary.py` (both
  already byte-identical to the shared versions apart from a docstring
  path) are retired in favor of the shared ones.
- The QMessageBox max-width fix now goes through the shared
  `redactor_common.gui.qmessagebox_style.apply_message_box_style()`
  instead of an inlined copy of the same stylesheet rule.

No behavior change intended anywhere in this entry -- every swap was
either byte-identical code or covered by an existing test (`test_undo.py`,
`test_save_errors.py`, `test_error_summary.py` all still pass unchanged
in shape, just importing from `redactor_common` now).

## 2026-09-07#01

- Load Folder can now add more than one folder in a single go — the
  folder picker reopens after each pick, so Cancel means "done" rather
  than "abort" once you've chosen at least one. Recurse-into-subfolders
  is still asked just once and applied to all of them.
- Fixed a literal `&Kobo` showing in the menu bar instead of the
  Kobo menu with its mnemonic underline — `extra_menus` expects the
  plain name and adds the `&` itself.

## 2026-09-06#03

- Colors now live in `redactor_common.gui.colors` instead of being
  defined locally -- this project's own scheme (already the source
  everyone else was copying by hand) is now the actual shared standard
  mp3/video import from, so there's one place to change it going
  forward. No visible change here, since the values are identical.
- Removed the "Uncheck All Fields" button from the bulk-edit panel --
  not needed.

## 2026-09-06#02

- Fixed a latent bug (reported first on mp3, same grid shape here):
  the gap between every Bulk Edit Tags field would visibly grow as the
  window was resized taller -- the fields grid had no row stretch set
  anywhere, so Qt spread the extra vertical space evenly into every
  row's gap instead of leaving it as blank space below the last field.
  Fix lives in `redactor_common` (bumped to `2026-09-06-03`).

## 2026-09-06#01

- Unified appearance with the sibling projects: window title is now
  just `The ƎPUB Redactor (2026-09-06#01)`, dropping the "v0.3 Public
  Beta (I ♥ mobilism)" tagline (`RELEASE_LABEL` is now empty, matching
  mp3/video). Removed the "Made by Pubocyno — using Claude" credit line
  from the bottom-left of the status bar.
- Bumped `redactor_common` to `2026-09-06-02` (fixes a stray leading
  comma in the About dialog for a project with no release label — now
  relevant here too).

## 2026-09-04#01

- `redactor_common` is now a real pip dependency
  ([Erlbon/redactor_common](https://github.com/Erlbon/redactor_common),
  pinned to tag `2026-09-04-10` in `requirements.txt`) instead of a
  vendored copy under `redactor_common/`. Previously each of the three
  Redactor projects hand-copied this shared code separately, so a fix
  in one place needed three separate manual resyncs and could silently
  drift out of sync -- which is exactly what happened with a real
  crash bug (`setWindowModality`, fixed just prior to this). One
  canonical source now; bumping the pin is a deliberate one-line
  `requirements.txt` diff instead of an easy-to-forget copy-paste.
  Import paths are unchanged (`from redactor_common.gui...` still
  works, just resolves from site-packages now).

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
