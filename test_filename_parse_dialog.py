"""Tests for gui/filename_parse_dialog.py's pattern-ranking behavior.

Real user complaint this replaces: the dialog used to offer a "Detect
Pattern from This Book's Current Metadata" right-click action, which
only worked if at least one loaded book already had correct metadata to
reverse-engineer a pattern from -- in practice, the exact batch that
needs fixing rarely has one lying around, so it was effectively
unusable. It's gone now; instead, every candidate (pattern history AND
a handful of built-in naming templates) is checked against the actual
loaded filenames and ranked by how many it matches, best first.

Patches gui.app_settings.load_pattern_history() directly rather than
going through the real QSettings-backed .ini file -- in dev mode that
file lives right in the project directory (see core/app_paths.py), so
writing real pattern history through it here would leak test data into
whatever a developer actually has saved locally."""

import contextlib
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(__file__))
from PyQt6.QtWidgets import QApplication  # noqa: E402

from core.epub_metadata import EpubMetadata  # noqa: E402
from gui import app_settings  # noqa: E402
from gui.filename_parse_dialog import FilenameParseDialog  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)


class _FakeBook:
    def __init__(self, path):
        self.path = path
        self.metadata = EpubMetadata()


@contextlib.contextmanager
def _fake_history(history: list[str]):
    original = app_settings.load_pattern_history
    app_settings.load_pattern_history = lambda: list(history)
    try:
        yield
    finally:
        app_settings.load_pattern_history = original


_TAGGED_EPUB_CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""


def _build_tagged_epub(path: str, title: str, author: str) -> None:
    """A minimal, REAL epub with actual saved metadata -- used to test
    the "confirmed via existing metadata" folder fallback tier, which
    needs a genuine EpubBook.metadata.authors to read, not just a
    filename."""
    opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="BookId">urn:uuid:{os.path.basename(path)}</dc:identifier>
    <dc:title>{title}</dc:title>
    <dc:language>en</dc:language>
    <dc:creator>{author}</dc:creator>
  </metadata>
  <manifest><item id="chap1" href="chap1.xhtml" media-type="application/xhtml+xml"/></manifest>
  <spine><itemref idref="chap1"/></spine>
</package>
"""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), b"application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", _TAGGED_EPUB_CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/chap1.xhtml", "<html><body>x</body></html>")


def test_no_detect_from_metadata_context_menu():
    # Regression guard: the removed feature's hooks must actually be
    # gone, not just unreachable from the menu.
    with _fake_history([]):
        dlg = FilenameParseDialog([_FakeBook("/x/Author - Title.epub")])
    assert not hasattr(dlg, "_detect_pattern_from_row")
    assert not hasattr(dlg, "_show_preview_context_menu")
    print("PASS: the old 'detect pattern from a book's metadata' feature is fully removed")


def test_built_in_template_wins_with_no_history():
    books = [
        _FakeBook("/x/Patty Jansen - [Ambassador 10] - Lost Forest Secrets (2020).epub"),
        _FakeBook("/x/Richard Swan - [The Empire 1] - The Justice of Kings (2022).epub"),
    ]
    with _fake_history([]):
        dlg = FilenameParseDialog(books)
    assert dlg.pattern_edit.text() == "%authors% - [%series% %series_index%] - %title% (%year%)"
    print("PASS: with no pattern history at all, a built-in template that fits perfectly is selected")


def test_ranked_list_sorted_best_match_first():
    # "%totally% %unrelated%" is newest (history is most-recent-first)
    # but matches nothing -- must not out-rank a better-matching pattern
    # just because it's more recent.
    books = [
        _FakeBook("/x/Author One - Book One.epub"),
        _FakeBook("/x/Author Two - Book Two.epub"),
    ]
    with _fake_history(["%totally% %unrelated%", "%authors% - %title%"]):
        dlg = FilenameParseDialog(books)
        scored = dlg._scored_candidates()

    counts = [count for _pattern, count, _is_history in scored]
    assert counts == sorted(counts, reverse=True), counts
    assert scored[0][0] == "%authors% - %title%"
    assert scored[0][1] == 2
    # "%totally% %unrelated%" is the most RECENT history entry (0-index
    # in history) but matches nothing -- it must not out-rank the
    # genuinely-matching pattern just because it's more recent. Several
    # other candidates can legitimately also score 0 and tie with it;
    # what matters is it's never ranked ABOVE a real match.
    unrelated_rank = next(i for i, (p, _c, _h) in enumerate(scored) if p == "%totally% %unrelated%")
    authors_title_rank = next(i for i, (p, _c, _h) in enumerate(scored) if p == "%authors% - %title%")
    assert unrelated_rank > authors_title_rank, (unrelated_rank, authors_title_rank)
    assert scored[unrelated_rank][1] == 0
    print("PASS: candidates are ranked purely by match count -- 2/2 beats a more-recent-but-unrelated 0/2")


def test_history_pattern_labeled_differently_from_built_in():
    books = [_FakeBook("/x/Author One - Book One.epub")]
    with _fake_history(["%authors% - %title%"]):
        dlg = FilenameParseDialog(books)
        labels = dict((p, label) for p, label in dlg._candidate_pattern_labels() if p is not None)

    assert "(built-in template)" not in labels["%authors% - %title%"]
    built_in_only = [p for p in labels if p != "%authors% - %title%"]
    assert built_in_only, "expected at least one built-in template also offered"
    assert all("(built-in template)" in labels[p] for p in built_in_only)
    print("PASS: a history pattern's label doesn't say \"built-in template\"; every other suggestion does")


def test_falls_back_to_last_pattern_when_nothing_matches():
    with _fake_history(["%totally% %unrelated%"]):
        dlg = FilenameParseDialog([_FakeBook("/x/Nothing Matches At All Here.epub")])
    assert dlg._auto_detected_pattern is None
    assert dlg.pattern_edit.text() == "%totally% %unrelated%"  # load_last_pattern() fallback
    print("PASS: when nothing (history or built-in) matches anything, falls back to the last-used pattern")


# ----------------------------------------------------------------------
# Cross-book author/series confirmation (the "check against the folder"
# feature): a value that repeats across other loaded books, or other
# files in the same folder on disk, is marked "confirmed" in the
# preview -- direct evidence a pattern assigned %authors%/%series%
# correctly, since a real library commonly has several books sharing an
# author or series, while %title% normally doesn't repeat at all.
# ----------------------------------------------------------------------

def test_repeated_author_in_batch_is_confirmed():
    books = [
        _FakeBook("/x/Terry Pratchett - Mort.epub"),
        _FakeBook("/x/Terry Pratchett - Reaper Man.epub"),
        _FakeBook("/x/Neil Gaiman - American Gods.epub"),
    ]
    with _fake_history([]):
        dlg = FilenameParseDialog(books)
        dlg.pattern_edit.setText("%authors% - %title%")
    row0 = dlg.preview_table.item(0, 1).text()
    row1 = dlg.preview_table.item(1, 1).text()
    row2 = dlg.preview_table.item(2, 1).text()
    assert "confirmed" in row0 and "1 other loaded book" in row0, row0
    assert "confirmed" in row1 and "1 other loaded book" in row1, row1
    assert "confirmed" not in row2, row2  # only Gaiman book in this batch -- nothing to confirm it
    print("PASS: an author shared by two loaded books is marked confirmed on both; a one-off isn't")


def test_unconfirmed_author_falls_back_to_folder_filenames():
    tmp_dir = "/tmp/epub_test_dialog_folder_fallback2"
    os.makedirs(tmp_dir, exist_ok=True)
    for name in ["Terry Pratchett - Mort.epub", "Terry Pratchett - Guards Guards.epub"]:
        open(os.path.join(tmp_dir, name), "w").close()

    # Only ONE Pratchett book is actually loaded into the dialog --
    # "Guards Guards" exists only on disk in the same folder.
    books = [
        _FakeBook(os.path.join(tmp_dir, "Terry Pratchett - Mort.epub")),
        _FakeBook("/other/Neil Gaiman - American Gods.epub"),
    ]
    with _fake_history([]):
        dlg = FilenameParseDialog(books)
        dlg.pattern_edit.setText("%authors% - %title%")
    row0 = dlg.preview_table.item(0, 1).text()
    assert "confirmed" in row0 and "other filename(s) in this folder" in row0, row0
    print("PASS: with no support in the loaded batch, falls back to checking other filenames in the folder")


def test_unconfirmed_author_falls_back_to_folder_metadata():
    # Neither the batch nor any OTHER filename in the folder supports
    # this author -- but a sibling .epub with unrelated-looking filename
    # ALREADY has it correctly tagged in its own saved metadata. This is
    # the exact real-world case the feature is for: the book being fixed
    # has bad everything (name AND metadata), but other, previously
    # curated files often sit right next to it in the same folder.
    tmp_dir = "/tmp/epub_test_dialog_metadata_fallback2"
    os.makedirs(tmp_dir, exist_ok=True)
    for f in os.listdir(tmp_dir):
        os.remove(os.path.join(tmp_dir, f))
    _build_tagged_epub(
        os.path.join(tmp_dir, "zzz_unrelated_filename.epub"), "Guards! Guards!", "Terry Pratchett"
    )

    books = [_FakeBook(os.path.join(tmp_dir, "Terry Pratchett - Mort.epub"))]
    with _fake_history([]):
        dlg = FilenameParseDialog(books)
        dlg.pattern_edit.setText("%authors% - %title%")
    row0 = dlg.preview_table.item(0, 1).text()
    assert "confirmed via existing metadata" in row0, row0
    print("PASS: with no filename support anywhere, falls back to an already-tagged sibling's real metadata")


def test_filename_fallback_preferred_over_metadata_fallback():
    # When BOTH tier 2 (folder filenames) and tier 3 (folder metadata)
    # could confirm a value, tier 2 wins -- it's the cheaper check, and
    # is tried first.
    tmp_dir = "/tmp/epub_test_dialog_tier_order"
    os.makedirs(tmp_dir, exist_ok=True)
    for f in os.listdir(tmp_dir):
        os.remove(os.path.join(tmp_dir, f))
    open(os.path.join(tmp_dir, "Terry Pratchett - Guards Guards.epub"), "w").close()
    _build_tagged_epub(os.path.join(tmp_dir, "book2.epub"), "Small Gods", "Terry Pratchett")

    books = [_FakeBook(os.path.join(tmp_dir, "Terry Pratchett - Mort.epub"))]
    with _fake_history([]):
        dlg = FilenameParseDialog(books)
        dlg.pattern_edit.setText("%authors% - %title%")
    row0 = dlg.preview_table.item(0, 1).text()
    assert "other filename(s) in this folder" in row0, row0
    assert "existing metadata" not in row0, row0
    print("PASS: the cheaper filename-based folder check is preferred over the metadata check when both would confirm")


def test_title_is_never_marked_confirmed():
    # Titles are supposed to be different in every file -- repeating
    # them isn't evidence of anything, so they're excluded on purpose.
    books = [
        _FakeBook("/x/Author One - Same Title.epub"),
        _FakeBook("/x/Author Two - Same Title.epub"),
    ]
    with _fake_history([]):
        dlg = FilenameParseDialog(books)
        dlg.pattern_edit.setText("%authors% - %title%")
    for row in range(dlg.preview_table.rowCount()):
        text = dlg.preview_table.item(row, 1).text()
        assert "title: confirmed" not in text, text
    print("PASS: a repeated title is never marked confirmed, only authors/series are checked")


if __name__ == "__main__":
    test_no_detect_from_metadata_context_menu()
    test_built_in_template_wins_with_no_history()
    test_ranked_list_sorted_best_match_first()
    test_history_pattern_labeled_differently_from_built_in()
    test_falls_back_to_last_pattern_when_nothing_matches()
    test_repeated_author_in_batch_is_confirmed()
    test_unconfirmed_author_falls_back_to_folder_filenames()
    test_unconfirmed_author_falls_back_to_folder_metadata()
    test_filename_fallback_preferred_over_metadata_fallback()
    test_title_is_never_marked_confirmed()
    print("\nALL FILENAME PARSE DIALOG TESTS PASSED")
