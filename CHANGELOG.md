# Changelog

All notable changes to The ƎPUB Redactor, by version. Trimmed to new
functionality and real fixes — cosmetic/UX-only adjustments aren't
listed here.

## 2026-10-04#04 -- Refresh drops files that are gone

- Refresh List (F5) now shows only the files that are still on disk: a file that was deleted or moved since it was loaded is removed from the list instead of staying as an error row. New files in the loaded folders are still picked up.

## 2026-10-04#03 -- Read Book window

- New **File > Read Book…** (also in the right-click menu, for a single selected book): the whole book as text in a window, with the chapter list (the book's text documents in reading order) on the left and Previous / Next buttons. Only the chapter you open is read from the file. Book styling is stripped and images are not shown, so it is for checking the title page, copyright page and front matter, not for reading in comfort.

## 2026-10-04#02 -- Read the book's text from the cover preview

- Replaces the image browsing of 2026-10-04#01. With one book selected, the **<** / **>** buttons under the cover preview now step from the cover (Page 1) through the book's text documents in reading order, shown as rendered text, so the title page, copyright page and other front matter are easy to spot. Only the page you turn to is read from the file; pages over 2 MB or unreadable say so. Book styling is stripped so the text uses the app's own font; images inside pages are not shown.

## 2026-10-04#01 -- Browse the book's images from the cover preview

- With one book selected, the cover preview now has **<** / **>** buttons and an "Image 3 / 12" counter to step through every image in the EPUB (the cover first, then the other images in manifest order). Only the image you turn to is read from the file. An image that is missing, unreadable or over 64 MB shows "Could not read image N". With several books (or none) selected, or a book with a single image, the controls are hidden. SVG images are skipped.

## 2026-10-01#13 -- Spaced initials in file and folder names

- Changed: file and folder names built from %authors% or %author_sort% (Rename, Export, Move into folders, the Redact rename and move steps, and the pattern previews) now space initials too: "J. R. R. Tolkien - The Hobbit.epub", "Tolkien, J. R. R/...". This is applied when the name is built, so books whose stored author was never cleaned get spaced names as well. Titles and other fields are unchanged; a trailing dot is still dropped from a name and ASCII-safe filenames still work.

## 2026-10-01#12 -- Initials always spaced

- Changed: every place that writes an author value now spaces initials ("J. R. R. Tolkien", "Tolkien, J. R. R."): Convert Author Sort (both directions and the tag panel's guess buttons), Parse Filename and folder-based authors, and the Calibre, Open Library (online and local database) and Google Books lookup results. Matching and duplicate detection are unchanged (they already ignore the spacing). File names built from %authors% still use the author exactly as stored.

## 2026-10-01#11 -- Sort-form authors become the Author Sort

- Changed: when Author(s) holds names written "Last, First" ("Tolkien, J.R.R.", "van Gogh, Vincent", "King, Martin Luther, Jr."), Clean Up Authors and the Redact step now move that text, tidied, into Author Sort and generate the display names from it ("J. R. R. Tolkien", "Vincent van Gogh", "Martin Luther King Jr."), several authors separated by ";" or " & " included. An existing Author Sort that agrees is kept; one that disagrees is kept and offered as an unticked review row. A comma list of full names ("Neil Gaiman, Terry Pratchett") is still review-only.

## 2026-10-01#10 -- Preferences dialog

- New: Tools > Preferences (Ctrl+,) gathers the everyday settings in one dialog with four pages: Filenames (ASCII-safe filenames, zero-pad numbers and width), Language (the blank-language default and its on/off switch, with your own language list), Display (how long text shows in the table, performance logging) and Tools and Paths (Calibre folder, Sigil program, Open Library database and dump files). OK or Apply changes the open window at once; Cancel writes nothing; Reset to Defaults resets the current page. The settings keep their old places in the settings file, so File > Export / Import Settings is unaffected.
- Changed: Tools > Blank Language Default is now Preferences > Language. View > Text Wrapping and Tools > Enable Performance Logging stay as shortcuts and stay in step with Preferences. redactor_common pin raised to 2026-10-01-06.

## 2026-10-01#09 -- Clean Up Authors (Repair menu and Redact)

- New: Repair > Clean Up Authors... reviews every loaded book's Author(s) and Author Sort and fixes the usual messes: stray spaces and punctuation, "J.R.R.Tolkien" / "J R R Tolkien" to "J. R. R. Tolkien", "Tolkien, J.R.R." to "J. R. R. Tolkien", role suffixes and junk ("(Editor)", ", translator", "Translated by", "et al.", life dates), "A; B" and "First Last & First Last" split into separate authors, ALL CAPS names, "Jr" to "Jr.", duplicate authors, and a missing or sloppy Author Sort generated or tidied for every author (particles stay with the surname, "King, Martin Luther, Jr.", one-word names sort as themselves). Corporate authors ("Simon & Schuster", "... Press"), "Anonymous" and non-Latin names are left alone. The review lists each book before and after; deterministic fixes are ticked, guesses are listed unticked (splitting "Simon & Schuster" or "Neil Gaiman, Terry Pratchett", removing "Dr.", all-lowercase names, an Author Sort that disagrees with the author, which is also flagged) and a flag row points out what has no proposed fix. Nothing is written until Save All, and one Undo reverts it.
- New: a "Clean up authors" Redact step (on by default) applies only the deterministic fixes; guesses are named in the report notes and never applied.
- Fixed: the duplicate finder now treats "JRR Tolkien" and "J.R.R. Tolkien" as the same author (it shares the new name comparison).

## 2026-10-01#08 -- Repair > Find Duplicates

- New: Repair > Find Duplicates... reviews all loaded books for the same book more than once, in the shared review dialog. Each group says why it matched: identical content (only the metadata differs), same title and author (maybe another edition), or same ISBN with a different title (the ISBN may be wrong). Duplicates are not treated as errors: nothing is selected, nothing changes unless you choose an action, and "Not duplicates" hides a group for good (kept in epubredactor_duplicates_dismissed.json next to the settings; it is not part of Export Settings). Moving files to the Recycle Bin from the review removes them from the list and refuses books with unsaved changes.

## 2026-10-01#07 -- Finder for possible duplicate books (core)

- New: the logic behind a coming Repair > Find Duplicates review. It groups loaded books by identical content (same files apart from the metadata), by the same title and first author (a possible other edition; the whole title must match, so series volumes and omnibus titles are not grouped), and by the same valid ISBN with a different title (the ISBN may be wrong), and states why each group matched. Nothing is changed or selected by it. redactor_common pin raised to 2026-10-01-05.

## 2026-10-01#06 -- Parse Filename preview no longer stalls while you type

- Fixed: Parse Filename → Metadata rebuilt its whole preview on every keystroke, which stalled on a large selection. The preview now refreshes once you pause typing (the first one on open is immediate), Apply always applies the up-to-date preview, and the check of other books' saved metadata in the same folders runs behind a progress dialog on a big selection and is only done once per folder.

## 2026-10-01#05 -- Accurate name for the lookup step in Redact

- Changed: Redact's "Fill empty fields online" step is now called "Fill empty fields from lookups (local database first)", which is what it does since it asks the local Open Library database before the online sources. Saved recipes keep working: only the label changed.

## 2026-10-01#04 -- Authors from works, and covers from the local Open Library database

- New: an optional third source when building the Open Library database, the works dump (or the all-types dump): editions that list no author of their own get their work's authors. Left empty it changes nothing; it adds a big extra pass (roughly 10-15 minutes and ~1 GB of temporary disk, an estimate).
- New: covers use the local database's cover id. Find Better Covers and Redact's cover step fetch the cover for a local match directly by id (no ISBN search, no per-IP ISBN limit), with the usual size cap and image checks; the "Open Library (Local Database)" lookup now shows the cover beside the current one and Apply sets it like the online lookup. Nothing is fetched except by those actions.

## 2026-10-01#03 -- Open Library database checked against real dump samples

- Fixed: publish dates like "1988 December", "2002 May 20" and "2005-06-" (seen in the real editions dump) now give their month (and day) instead of the year alone.
- Changed: a lookup result from the local Open Library database now carries Open Library's cover id (never fetched; the online cover path could use it later).
- Changed: the size note is now measured (about 290-320 bytes per kept edition, roughly 2.5 GB for 8 million editions) and the README lists what the real samples showed and what is still unverified. Tests now build from small real-data fixtures.

## 2026-10-01#02 -- Look up books in the local Open Library database

- New: Metadata > Look Up > Open Library (Local Database)... searches the database built under Tools > Open Library Database: by the book's own ISBN (13 or 10, hyphens fine; when several editions share it the most complete record wins), else by title and author. Works offline, no rate limits. It brings in title, authors, publisher, publication date (month and day only when the text is unambiguous, otherwise the year), ISBN and language; covers and genres are not taken from it. Without a database set up it offers to open the settings.
- Changed: Redact's "Fill empty fields online" step now asks the local Open Library database first when one is set up (exact ISBN 95%, title and author 60%, title only 45%, same Needs review rules), and the online sources only for what is still empty. It never changes a field that already has a value, and keeps working with no network.

## 2026-10-01#01 -- Build an offline Open Library database

- New: Tools > Open Library Database... builds a local lookup database from Open Library's bulk dumps (the editions dump, plus the authors dump for author names, or the single all-types dump). You download the dumps yourself; the app never does. Only editions with a valid ISBN are kept, in the languages you tick (English, Norwegian, Italian, German and French by default, or all languages), with a prebuilt full-text index on title and author. Building is cancellable and never leaves a half-built file. Looking books up in it comes in the next version.
- Changed: the database path and dump paths are machine-specific settings (unticked by default in Export Settings).
- Changed: adopt redactor_common 2026-10-01-01.

## 2026-09-30#18 -- Kobo USB tests no longer assume Windows

- Fixed: the Kobo drive-detection tests now pin sys.platform to win32, so they pass on Linux CI (no product change).

## 2026-09-30#17 -- Adopt redactor_common 2026-09-30-15

- Changed: Redact saves retry briefly when Windows antivirus/indexer briefly locks a file.

## 2026-09-30#16 -- Redact never rewrites a book just to stamp it

- Changed: a validation stamp alone no longer counts as a change in Redact
  (same rule as cbzredactor). Redact stamps the final verdict only into books
  it saves anyway because another step changed them; untouched books stay
  unstamped, are not rewritten and are not reported as changed, until you run
  Validate / Fix Issues. This supersedes the #15 note that the first Redact
  run rewrites every clean book.

## 2026-09-30#15 -- Validation results are stamped into the book

- New: Validate / Fix Issues now records when a book was checked and the
  result. The stamp is kept like any other metadata: held in memory (the book
  shows as unsaved) and written into the EPUB's OPF (`redactor:validation`)
  when you Save, so it follows the file when you copy it. The Status column
  shows `OK · 2026-09-30 14:05` instead of the bare status; if the book's
  files changed since, it adds "(changed since)". Loading a library never
  stamps or marks anything unsaved. Redact stamps the final verdict too (a
  book whose stamp is already current is not rewritten again). DRM and
  unreadable books are never stamped.

## 2026-09-30#14 -- Export / Import Settings

- New: File > Export Settings... / Import Settings... save your preferences
  to one `epubredactor-settings.json` and load them on another computer or
  a fresh install. Import shows every change first and applies only what you
  tick. Included by default: Redact recipe, pattern history, field defaults
  (blank-language default, ASCII and zero-pad choices), column visibility and
  widths, text wrapping, custom/hidden genres and languages, junk cover list.
  Unticked by default (this computer only): Calibre/Sigil paths, last-used and
  library folders, eReader services. After an import you can re-detect
  Calibre and Sigil. No secrets are ever exported (the app stores none).

## 2026-09-30#13 -- Shortcut fixes

- Save All (formerly Save Files) is now Ctrl+Shift+A, the family key; Ctrl+S
  still works as a second shortcut for one more release.
- Delete Files is now Shift+Delete (the Explorer key); F8 still works for one
  more release.
- F1 no longer opens About (F1 is Help contents everywhere else; About is in
  the Help menu). No replacement key, so nothing else uses F1 by accident.
- Ctrl++ / Ctrl+- / Ctrl+0 zoom from the View menu; the keys were bound
  twice before (menu and toolbar buttons), now the menu owns them.

## 2026-09-30#12 -- Command palette

- New: Ctrl+K (View > Command Palette) opens a search box over every menu
  command: type a few letters, Enter runs it. Greyed commands are listed but
  cannot be run.
- Internal: a test checks the real menu bar against the shared menu rules
  (heading order, unique mnemonics, no clashing shortcuts, canonical labels).

## 2026-09-30#11 -- New menu structure

- The menu bar now follows the shared Redactor skeleton: File, Edit, View,
  Metadata, Repair, Send, Tools, Help. Only the mouse paths changed; every
  keyboard shortcut is the same as before. Where things went:
  - Operations is gone: Undo/Redo, Apply, Redact, Edit Redact Recipe,
    Search and Replace and Change Case are under Edit; Number Series, Convert
    Author Sort and the cover tools (Cover submenu) under Metadata; Polish
    Book and Compress Images under Repair.
  - Import is gone: Parse Filename, Scan File Content and Suggest Genres are
    under Metadata, the three online sources in Metadata > Look Up (Google
    Books, Open Library, Calibre), Import to EPUB is File > Import and
    Convert.
  - Settings is gone: Columns, Genres, Languages, Blank Language Default and
    the performance-log entries are under Tools; Text Wrapping is under View.
  - Kobo is now Send (Send to Kobo, Send to eReader, and Open in Sigil, which
    used to be right-click only). Refresh List moved from File to View.
- "Save Files" is now called Save All: it always saved every changed book.
  The flag/unflag junk-cover commands also appear in Metadata > Cover.
- New: View > Show Metadata Panel (mirrors the toolbar's Panel button), Reset
  Zoom (Ctrl+0), Edit > Filter List (Ctrl+F, focuses the filter box).
- Shorter right-click menu: Look Up, Organize, Cover and Send to submenus;
  Save and Polish Book left it (Polish Book stays in Repair).
- The toolbar's Redact button is bold. Uses redactor_common 2026-09-30-13.

## 2026-09-30#10 -- Redact pattern trail

- A saved Redact recipe now keeps the rename / move / folder-path pattern
  that was saved in it: later changes to Rename/Export no longer steer
  Redact, and the recipe never has to be recreated. An empty pattern still
  follows the app's most recent one. The first time Edit Redact Recipe is
  opened (nothing saved yet) the current patterns are filled in, so OK pins
  them; "Use fallback" unpins a step again.
- The recipe editor shows each pattern as an editable drop-down of recent
  patterns, a caption "In effect: ... -- set in this recipe / follows: ...",
  and a preview on the first loaded book (or a built-in sample).
- Uses redactor_common 2026-09-30-12.

## 2026-09-30#09 -- Metadata from the folder path

- Parse Filename -> Metadata now reads folders too: a pattern with "/" in
  it (%authors%/%series%/%title%) is matched against the book's path below
  the library root (the one Move into folders uses; a Library Root row
  appears and the choice is remembered). The preview shows the fields, a
  confidence and the matched folders; rows start ticked from 50%. Folders
  that several books share, or that match the saved author/series of other
  files in the same folder, raise the confidence. An author folder in
  "Tolkien, J.R.R." form is filled as "J.R.R. Tolkien". Patterns without a
  "/" work exactly as before, and path patterns are kept apart from
  filename patterns in the pattern history.
- Redact gains "Fill empty fields from the folder path", on by default, placed
  before the scan and lookup steps. It fills only empty fields, applies a
  match at or above the confidence threshold, and lists lower ones under
  Needs review with the folders that matched or were missing. It does
  nothing without a library root or for a file outside it, and says so.
- Uses redactor_common 2026-09-30-11.

## 2026-09-30#08 -- Move into folders

- File > Rename Files (Pattern) gains a third action, Move into folders:
  pick a library root and a pattern with "/" in it
  (%authors%/%series%/%title%) and the books' files are moved into that
  folder tree, collisions numbered, nothing overwritten. The root is
  remembered. File > Undo Last Rename moves everything back and offers to
  remove the folders the move created. Rename and Export work as before.

## 2026-09-30#07 -- Redact

- New Operations > Redact (Ctrl+Shift+E, toolbar): one click repairs and
  fills in the selected books (or, after asking, all loaded ones) with no
  dialogs. Each changed book is written to a temp file, checked (reopens,
  nothing lost, no new errors), then swapped in place; the original goes
  to the Recycle Bin. A results window lists changes, notes, skipped books
  and a Needs review tab.
- Steps, in order: fix validation issues, deduplicate manifest ids,
  rebuild manifest, repair navigation (orphan-file removal is an option,
  off), generate a table of contents (a real one from headings is applied;
  a "Section N" one goes to review), strip HTML from the description,
  detect a blank language, ISBN / publisher / year / series from the front
  matter, fill EMPTY fields online by ISBN (Google Books, Open Library),
  cover (by ISBN for a missing or junk-flagged one, else a generated
  cover when there is none at all), rename by your latest pattern (on only
  if you have used one) and Move into folders (off).
- Guesses are applied only at confidence 90% or more (configurable);
  lower ones are listed, never applied. Books with unsaved edits, a load
  error or DRM are skipped and named in the report. Edit Redact Recipe
  turns steps on/off, reorders them and sets options and the threshold.
- Renames and moves done by Redact are undone with File > Undo Last Rename.
- Selecting several books is now restored properly after a reload
  (only the last one stayed selected before).
- redactor_common 2026-09-30-10.

## 2026-09-30#06 -- Scan Content: five languages, language, series

- Scan Content for Metadata now understands English, Norwegian, Italian,
  German and French front matter (Utgitt av, Verlag, Editions, Casa
  editrice, Erstausgabe, Première édition, Traduzione di, ...),
  with or without accents. It also reads the last three pages (colophon,
  about the publisher), not just the first four; front-page matches win.
- New suggestions: the book's language (from its text, en/no/it/de/fr),
  series and volume ("(The Expanse #2)", "Bind 2", "Tome 4", "Volume II",
  ...), and each one shows a confidence. Translator, editor, illustrator
  and edition are listed for information only: the app has no field to
  store them. Nothing is applied without review, as before.
- Book pages without a charset hint no longer turn "Første" into mojibake
  when scanned.

## 2026-09-30#05 -- Open in Default App

- Right-click menu gains Open in Default App (redactor_common 2026-09-30-04).

## 2026-09-30#04 -- Generate Table of Contents

- New Repair -> Generate Table of Contents: books with no table of
  contents at all (typical of badly converted scanned-PDF EPUBs) get one
  built from their h1-h3 headings (or page titles) in reading order. The
  dialog lists the affected books, previews the first entries of the
  selected one, and only ticked books are touched. An NCX is written for
  every book, plus an EPUB3 nav document for EPUB3 books; chapter files
  are never modified, and nothing is written until you save. Headings
  repeated across many files (running page headers) are ignored.

## 2026-09-30#03 -- Batch operations that can't be derailed

- Rename/Export by Pattern, Search & Replace on filenames, Delete Files
  and Generate Cover now show a progress dialog (with Cancel) on larger
  selections, and one failing book no longer aborts the rest of a rename
  or export batch.
- Save As Copy no longer overwrites a copy when two books share a file
  name (from different folders): the second gets " (2)".
- Refresh List survives a file that can't be reopened (it keeps the
  previous entry), and removing/deleting many books at once is fast.
- Files that fail to load are described accurately: only the ones that
  stay in the list are "highlighted in red".
- Books already loaded are recognised regardless of path case or
  slashes; Generate/Replace Cover warns about books whose cover is
  DRM-encrypted; a non-http(s) server address is no longer opened in
  the browser; a convert failure (including a file-name collision
  error) is reported per file instead of aborting the batch.

## 2026-09-30#02 -- Safer saving and loading

- Books whose manifest uses percent-encoded file names (`ch%201.xhtml`,
  accented names) are read correctly: no more false "files missing from
  the manifest", and Rebuild Manifest / orphan removal no longer delete
  files that are really there. Replacing the cover of such a book now
  overwrites the old image instead of adding a second one.
- Saving replaces the original atomically on Windows too, leaves no
  `.tmp_write` file behind after a failed save, and never writes the same
  entry twice.
- One unreadable or unusual file can no longer abort loading a batch
  (any error now just marks that file as failed to load).
- Books whose cover is DRM-encrypted keep it: Replace Cover, Generate
  Cover and Compress Images skip the encrypted image (font obfuscation
  alone doesn't count).
- Send to Kobo finds the reader on Linux (`/media/$USER`,
  `/run/media/$USER`) and macOS (`/Volumes`), not just Windows drives.
- Book XML is parsed without expanding entities or touching the network;
  Open Library cover downloads are capped at 10 MB; a failed
  ebook-convert run no longer leaves a half-written EPUB behind; the
  "Locate Sigil" dialog no longer insists on `sigil.exe` outside Windows.
- redactor_common 2026-09-30-02 (from 2026-09-30-01).

## 2026-09-30#01 -- Lookups in the right-click menu, zero-padding remembered

- Right-clicking a book now has a **Look Up** submenu with Google Books,
  Open Library and Calibre (only Calibre was there before).
- Rename Files (Pattern) remembers the zero-pad checkbox and width.
- redactor_common 2026-09-30-01 (from 2026-09-29-04): the shared dialogs
  that make this possible.

## 2026-09-29#05 -- Shared library update

- redactor_common 2026-09-29-04 (from 2026-09-29-03): a fix to the shared preview loader, which this app doesn't use -- no change in behavior here.

## 2026-09-29#04 -- Cover quality

- **Cover column**: each book's cover size in pixels -- yellow for a
  low-resolution cover (under 1000px tall), red when there's none;
  sortable. Reads only the image header, so it costs nothing.
- **Operations > Find Better Covers…**: for the selected books (or all)
  with an ISBN, asks Open Library for its cover and offers the larger
  ones (or any, where the book has none), current and found side by
  side with their sizes. Applied as one Undo step, written on Save.
  Open Library's covers are often modest in size, so this helps most
  with missing and very small covers; when it refuses more lookups by
  ISBN (it limits them per computer), the search stops with a message.

## 2026-09-29#03 -- Undo Last Rename

- **File > Undo Last Rename...**: renames are now logged (Rename/Export by Pattern, a filename Search/Replace, Rename File) and the newest one can be taken back -- even after restarting the app. It shows what will be renamed back first, and never overwrites: a file that has moved since, or whose old name is taken again, is skipped and reported. The in-app Undo still covers metadata edits only.
- redactor_common 2026-09-29-03 (from 2026-09-29-02).

## 2026-09-29#02 -- Small fixes

- Message boxes with several wide buttons keep their text next to the icon (on Linux the text could end up in a narrow strip far to the right).
- Delete Files uses redactor_common's shared Recycle Bin helper (same behaviour; a file that can't be moved is reported as before).
- redactor_common 2026-09-29-02 (from 2026-09-29-01).

## 2026-09-29#01 -- ASCII-safe filenames

- **Rename/Export by Pattern: "ASCII-safe filenames"** -- new names use only plain ASCII letters, digits and punctuation: accents removed (é -> e, å -> a), æ -> ae, ø -> o, ß -> ss, typographic quotes and dashes made plain, and anything with no ASCII form (other scripts, emoji, symbols) dropped. For old file systems, network shares, e-readers, car stereos and sync tools that mangle anything else. The preview updates as you tick it, and the choice is remembered.
- redactor_common 2026-09-29-01 (from 2026-09-28-07).

## 2026-09-28#08 -- Shared release notes

No change to the app. The GitHub Release notes (every CHANGELOG section since the previous release) are now built by redactor_common's shared script instead of a copy in this repo (redactor_common 2026-09-28-07, from 2026-09-28-06).

## 2026-09-28#07 -- Linux tool lookup fix

- **Linux: Sigil is found on PATH** (it looked for `sigil.exe`, the Windows name; redactor_common 2026-09-28-06). Windows is unchanged.

## 2026-09-28#06 -- Linux version

- **A Linux download** alongside the Windows one:
  `epubredactor-linux-x86_64.tar.gz`, a single self-contained program for
  64-bit desktop Linux (glibc 2.35+: Ubuntu 22.04+, Debian 12+, Fedora
  36+, Mint 21+). Built with Python 3.12 like the Windows version; the
  whole test suite runs on Linux as part of every release build.
  External tools are found on your PATH, as on Windows.
- redactor_common 2026-09-28-05 (from 2026-09-28-02): on Linux the settings live in `~/.config/epubredactor/`, the standard place, instead of next to the program (Windows unchanged).

## 2026-09-28#05

- redactor_common 2026-09-28-02 (adds the shared local metadata
  database layer used by cbzredactor's offline GCD lookup; no change
  to epubredactor's behaviour).

## 2026-09-28#04

- **Online lookups no longer freeze the window.** Google Books, Open
  Library and Calibre lookups now run in the background: the window
  keeps redrawing and the progress dialog's Cancel button responds at
  once. A progress dialog is now shown even for a single book.
  (redactor_common 2026-09-28-01.)

## 2026-09-28#03

- **Validate & Fix:** a book whose single author entry holds several
  authors ("Terry Pratchett & Neil Gaiman") is flagged on load (status
  ISSUES), and the fix splits it into separate authors, keeping the
  author-sort names when they split the same way. As with the other
  fixes, the book is marked unsaved so you know to save it. An unspaced
  "&" ("AT&T Press") is left alone.

## 2026-09-28#02

- **Parse Filename:** "Author A & Author B" in a filename now reads as
  two authors ("Author A; Author B"), the reverse of how Rename/Export
  writes `%authors%`. Only a spaced " & " splits, so "AT&T" stays one
  name.

## 2026-09-28#01

- **Suggest Genres** (Import menu): proposes genres per book from its
  folder path and bracketed filename tags, its description, catalog
  lines on its first pages (LoC CIP headings, BISAC-style
  "FICTION / Fantasy / Epic", "This is a work of fiction") and its DDC
  number, with the matched text shown on hover. Ambiguous words
  ("war", "history", "romance") only count in genre context ("a war
  novel"). Only genres on your Genre list are suggested, and it is
  add-only: existing genre tags are never replaced or removed, and
  suggestions for already-tagged books start unticked.
- **Parse Filename** now goes through the same per-field overwrite
  review as the lookups, so a `%genres%` pattern can no longer silently
  replace genres a book already has.
- The Genre "+" picker no longer adds a differently-cased duplicate
  ("Fantasy" onto "fantasy").

## 2026-09-23#02

- The cover/fields splitter in the side panel is now redactor_common's
  shared `ImagePanelSplitter` + `ImagePreviewBox` (2026-09-23-02), built
  from this panel's original. After the cover has been dragged large,
  the pane can be dragged smaller again, and a long title can no longer
  stop the side panel from collapsing.

## 2026-09-23#01

- **Parse Filename fix:** a hyphenated author no longer gets split on
  its own hyphen ("Jean-Paul Sartre - Nausea" parsed as author "Jean",
  title "Paul Sartre - Nausea"). Spaces in a pattern are matched
  strictly first and only loosened if nothing matches.
- **Look Up via Calibre / Google Books / Open Library** now show the
  book's current cover next to the found one at a readable size, and a
  wrong guess can be corrected per book (edit title/author/ISBN, then
  Search This Item) -- the shared lookup dialog cbz already used.
- **Genre and Language "+" pickers** are a searchable, fixed-size list
  instead of a menu that ran off the screen once the list grew.
- **Refresh List** shows progress (it re-read every book with none, so a
  large library looked frozen).
- **Column widths and hidden columns are saved by column name**, not
  position, so a future added column can't make a saved preference hit
  the wrong column. Existing settings are converted automatically.
- Rename/Export, single-file rename, Case Conversion, Search & Replace,
  Add/Remove Columns and table zoom use the shared redactor_common
  versions (which were built from this app's originals); the rename and
  parse engines, crash log, startup and settings lists are shared too.
  Removed the dead `gui/about_dialog.py` and six local copies.
- Tests: two tests that hung forever headless (modal message boxes) now
  run, and tests no longer write to the real `epubredactor_settings.ini`.
- redactor_common pinned to 2026-09-23-01 (was 2026-09-17-03).

## 2026-09-17#16

- `%series_index%` in **Parse Filename → Metadata** now also accepts:
  - An ordinal-style trailing period ("5." -> "5").
  - A dash-separated range for an omnibus edition collecting several
    books in one file ("1-6" -> "1-6", kept as-is; "01-06" -> "1-6",
    each side's leading zeros stripped independently). The normal
    " - " field separator (with spaces) still works exactly as before
    -- the range only kicks in when the dash sits directly against the
    digits with no space, matching the real omnibus convention.

## 2026-09-17#15

- Fixed: Parse Filename → Metadata's intro text was missing
  `setWordWrap()`, so the dialog stretched to fit that whole (now
  fairly long) sentence on one line instead of wrapping it -- on a
  smaller screen this could make the window fill the entire width.

## 2026-09-17#14

- Author/series confirmation (see 2026-09-17#13) improved based on
  real-world feedback:
  - Matching is now case- and whitespace-insensitive -- "Terry
    Pratchett", "TERRY PRATCHETT", and "Terry  Pratchett" (stray
    double space) all count as agreeing, instead of looking like three
    unrelated one-off values that don't confirm each other.
  - New third tier: when neither the loaded batch nor other filenames
    in the same folder confirm a value, it now opens sibling `.epub`
    files (up to 200 per folder) and checks their OWN already-saved
    metadata -- covers the real situation where the book being fixed
    has bad everything (name *and* metadata), but other, previously
    curated files often sit in the very same folder. Tried last since
    it's the most expensive check (it actually opens files, unlike the
    other two tiers), and only after the cheaper tiers come up empty.

## 2026-09-17#13

- **Parse Filename → Metadata** now cross-checks extracted authors and
  series against other books, to give a real signal for whether a
  pattern assigned that field correctly (rather than, say, capturing
  part of the title): checks the other books already loaded into the
  dialog first, and if none of them share the same value, falls back
  to checking the rest of that book's own folder on disk (just a
  filename listing -- no files opened). A confirmed value is marked
  right in the preview, e.g. "authors: confirmed, shared with 2 other
  loaded book(s)". Titles are deliberately never checked this way --
  they're supposed to be different in nearly every file, so repetition
  there wouldn't mean anything.

## 2026-09-17#12

- **Parse Filename → Metadata** patterns are more forgiving:
  - Spaces no longer count as meaningful characters -- a space in a
    pattern matches any amount of whitespace in the filename,
    including none at all (a missing space used to make the whole
    pattern fail to match).
  - `(...)` and `{...}` now work as optional groups exactly like
    `[...]` already did, so `(%year%)` in the built-in suggested
    templates is optional without needing to be rewritten with
    brackets.
  - `%series_index%` is now bounded to 0-999 (1-3 digits), distinct in
    shape from a 4-digit year.
  - (A bare, unwrapped field -- %year% with no surrounding punctuation
    of its own -- stays required by design: making it silently
    optional turned out to let it get skipped entirely next to a
    greedy neighbor like %series%, silently misparsing files that
    genuinely had that field. Wrap it in `()`, `[]` or `{}` to make it
    optional -- that's unambiguous.)

## 2026-09-17#11

- Reworked **Import Metadata → Parse Filename → Metadata**:
  - Removed "Detect Pattern from This Book's Current Metadata" -- it
    only worked when a batch happened to already contain one
    well-tagged book to reverse-engineer a pattern from, which in
    practice was rarely the case for the files that actually needed
    this tool.
  - New `[...]` optional-bracket pattern syntax: `[%series% %series_index%]`
    (or any bracketed field) is now dropped as a whole -- brackets
    included -- when its fields are empty, both when building
    filenames (Rename/Export) and reading them back. Handles the
    standard `%authors% - [%series% %series_index%] - %title%`
    template correctly whether or not a book has a series.
  - `%year%` now matches exactly 4 or 2 digits instead of any run of
    digits; `%month%` matches 1-2 digits or an English month
    name/abbreviation ("Jan", "January", any case), normalized to a
    plain number on import.
  - Every candidate pattern -- your own pattern history *and* a
    handful of common built-in naming templates -- is now checked
    against the actually-loaded filenames and offered ranked by match
    count, best first, so a fresh perfect match no longer loses to a
    stale, barely-matching recent pattern.

## 2026-09-17#10

- New **Repair → Deduplicate Manifest IDs…**: fixes manifest `<item>`
  entries that share the same id -- most often two items both with
  id="ncx" in a badly-converted EPUB2→EPUB3 file, one the genuine
  toc.ncx and one a stray leftover from whatever tool produced it.
  This app's own validation already caught this (`DUPLICATE_MANIFEST_ID`)
  but had no fix; found via a real user report of files showing INVALID
  after Rebuild Manifest -- Rebuild Manifest only ever removes
  references to genuinely missing files, so it correctly left this
  separate, pre-existing defect in place. The fix renames the id on
  every duplicate except one, and specifically prefers keeping the id
  on whichever item actually matches what it conventionally means (the
  real NCX document for id="ncx", the nav document for a duplicated nav
  id) rather than just picking whichever comes first, so existing
  references like `<spine toc="ncx">` keep resolving correctly.

## 2026-09-17#09

- Fixed: on a real ~15,000-book library, updating the list after
  loading/filtering/editing could take minutes, dominated almost
  entirely by decoding every single book's cover image into an icon on
  every rebuild, whether or not that row was ever actually scrolled
  into view. Two fixes, applied together:
  - `redactor_common` now decodes covers via `QImageReader` with the
    scaled size set up front, letting the image format's own decoder
    downscale while decoding instead of decoding at full resolution
    and scaling afterwards -- measured 2.67x faster per cover (bumped
    to `2026-09-17-03`).
  - The list now only decodes icons for rows actually visible (plus a
    small buffer), loading more lazily as you scroll, sort, or filter.
    Every other row shows its real icon the moment it comes into view.
  Measured on a real 15,462-book library with real cover art: table
  rebuild time dropped from ~126s to ~2.6s.
  (Note for anyone tempted to "fix" this with more worker threads:
  measured directly, PyQt6's image decoding does not release Python's
  GIL, so `QThreadPool` worker threads add no real throughput here --
  seven extra threads decoding covers measured within 4% of one.)

## 2026-09-17#08

- New **Settings → Enable Performance Logging**: writes a timing
  breakdown to a log file next to the crash log whenever a table
  rebuild or save runs, sorted by which step actually took the most
  time. For diagnosing a slowdown on a real, very large library that
  a smaller test library doesn't reproduce -- off by default, no
  measurable cost when disabled. **Settings → Open Performance Log
  File…** reveals the file once something's been logged.

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
