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


if __name__ == "__main__":
    test_no_detect_from_metadata_context_menu()
    test_built_in_template_wins_with_no_history()
    test_ranked_list_sorted_best_match_first()
    test_history_pattern_labeled_differently_from_built_in()
    test_falls_back_to_last_pattern_when_nothing_matches()
    print("\nALL FILENAME PARSE DIALOG TESTS PASSED")
