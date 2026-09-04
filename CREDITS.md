# Credits

The ƎPUB Redactor is built on the work of a number of other projects.

## Shared foundation

- **[redactor_common](https://github.com/erlbon/redactor_common)** — the
  UI/logic package shared with its sibling tools (mp3, video). See its
  own version line above for which build is vendored here.

## Libraries

- **[PyQt6](https://www.riverbankcomputing.com/software/pyqt/)** — the
  application framework the whole GUI is built on.
- **[lxml](https://lxml.de/)** — EPUB/XHTML/OPF parsing and editing.
- **[Send2Trash](https://github.com/arsenetar/send2trash)** — moves
  files to the OS trash/recycle bin instead of deleting them outright.

## External tools

Not bundled — installed separately, and only used if present on the
system:

- **[Calibre](https://calibre-ebook.com/)** — `ebook-convert` and
  `ebook-polish`, for format conversion and EPUB cleanup.
- **[Sigil](https://sigil-ebook.com/)** — EPUB editing, launched
  directly from the app for manual fixes.

## APIs

- **[Google Books API](https://developers.google.com/books)** —
  metadata lookup by title/author/ISBN.
- **[Open Library](https://openlibrary.org/developers/api)** —
  metadata and cover-image lookup.
