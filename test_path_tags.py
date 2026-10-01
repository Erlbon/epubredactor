"""Tests for reading metadata back out of the folder path: the Parse Filename
dialog's path mode (gui/filename_parse_dialog.py) and the Redact step
`path_tags` (core/redact_steps.py), both on redactor_common's
core/path_parser.py. Patterns without a / or \\ are covered by the existing
filename-dialog tests and must keep behaving as they did."""

import contextlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from PyQt6.QtWidgets import QApplication  # noqa: E402

from core.epub_metadata import EpubBook, EpubMetadata  # noqa: E402
from core.filename_parser import folder_authors_to_display  # noqa: E402
from core.redact_steps import build_catalogue, recipe_from_setting, recipe_to_setting  # noqa: E402
from gui import app_settings  # noqa: E402
from gui.filename_parse_dialog import FilenameParseDialog  # noqa: E402
from redactor_common.core.pipeline import FileStatus, Recipe  # noqa: E402
from test_redact_steps import env, load, make_epub, only, only_entry, run, trash  # noqa: E402,F401

_app = QApplication.instance() or QApplication(sys.argv)

ROOT = os.path.abspath(os.path.join(os.sep, "lib"))


class _FakeBook:
    def __init__(self, path):
        self.path = path
        self.metadata = EpubMetadata()


@contextlib.contextmanager
def _fake_history(history):
    original = app_settings.load_pattern_history
    app_settings.load_pattern_history = lambda: list(history)
    try:
        yield
    finally:
        app_settings.load_pattern_history = original


def _dialog(books, pattern, history=(), root=ROOT, saved=None):
    with _fake_history(list(history)):
        dlg = FilenameParseDialog(
            books, library_root=root, on_library_root_changed=(saved.append if saved is not None else lambda p: None)
        )
        dlg.pattern_edit.setText(pattern)
        dlg.flush_pending_refresh()  # pattern edits are debounced
    return dlg


def _lib_book(*parts):
    return _FakeBook(os.path.join(ROOT, *parts))


# --- dialog: path mode --------------------------------------------------------------------


def test_author_folder_in_sort_form_becomes_a_display_name():
    assert folder_authors_to_display("Tolkien, J.R.R.") == "J.R.R. Tolkien"
    assert folder_authors_to_display("Terry Pratchett") == "Terry Pratchett"
    assert folder_authors_to_display("Pratchett, Terry & Gaiman, Neil") == "Terry Pratchett; Neil Gaiman"


def test_filename_pattern_leaves_path_mode_off():
    dlg = _dialog([_lib_book("Jane Doe - Some Book.epub")], "%authors% - %title%")
    assert not dlg.is_path_mode() and dlg.parse_results() == {}
    assert dlg.preview_table.columnCount() == 3 and dlg._root_row.isHidden()
    assert dlg.accepted_changes() == {0: {"authors_str": "Jane Doe", "title": "Some Book"}}


def test_path_pattern_reads_folders_relative_to_the_root():
    books = [_lib_book("Tolkien, J.R.R.", "The Hobbit.epub"), _lib_book("Doe, Jane", "Other.epub")]
    dlg = _dialog(books, "%authors%/%title%")
    assert dlg.is_path_mode() and not dlg._root_row.isHidden()
    assert dlg.preview_table.columnCount() == 5
    assert dlg.accepted_changes() == {
        0: {"authors_str": "J.R.R. Tolkien", "title": "The Hobbit"},
        1: {"authors_str": "Jane Doe", "title": "Other"},
    }
    result = dlg.parse_results()[0]
    assert result.matched_segments == [("%authors%", "Tolkien, J.R.R."), ("%title%", "The Hobbit")]
    assert dlg.preview_table.item(0, 2).text() == "88%"  # bare folder 0.75 + file 1.0, averaged
    assert "Tolkien, J.R.R." in dlg.preview_table.item(0, 3).text()


def test_a_missing_folder_is_reported_and_low_confidence_rows_start_unticked():
    books = [_lib_book("Author - Jane Doe", "Saga", "Book One.epub"), _lib_book("Stray.epub")]
    dlg = _dialog(books, "Author - %authors%/%series%/%title%")
    results = dlg.parse_results()
    assert results[1].missing_segments == ["Author - %authors%", "%series%"]
    assert results[1].confidence < 0.5
    assert not dlg._checkboxes[1].isChecked() and dlg._checkboxes[1].isEnabled()
    assert dlg._checkboxes[0].isChecked()
    assert "(missing:" in dlg.preview_table.item(1, 3).text()


def test_folders_shared_by_several_books_raise_the_confidence():
    books = [_lib_book("Doe, Jane", "One.epub"), _lib_book("Doe, Jane", "Two.epub"), _lib_book("Roe, Rick", "Three.epub")]
    dlg = _dialog(books, "%authors%/%title%")
    results = dlg.parse_results()
    assert results[0].confidence > results[2].confidence  # two books agree on the author folder
    assert results[0].confidence == pytest.approx(0.975)  # bare folder 0.75 + 0.2 for agreeing, file 1.0


def test_folder_authors_are_corroborated_by_other_files_saved_metadata(tmp_path):
    root = tmp_path / "lib"
    folder = root / "Doe, Jane"
    folder.mkdir(parents=True)
    make_epub(str(folder / "Known.epub"), authors=("Jane Doe",))
    target = make_epub(str(folder / "New.epub"), authors=())
    lone = make_epub(str(root / "Zed" / "Solo.epub"), authors=()) if (root / "Zed").mkdir() is None else None
    dlg = _dialog([load(target), load(lone)], "%authors%/%title%", root=str(root))
    results = dlg.parse_results()
    assert results[0].confidence == pytest.approx(0.975)  # "Jane Doe" is already on the other book in that folder
    assert results[1].confidence == pytest.approx(0.875)  # nothing corroborates "Zed"


def test_library_root_change_is_persisted_and_reparses():
    saved = []
    books = [_lib_book("Doe, Jane", "One.epub")]
    dlg = _dialog(books, "%authors%/%title%", root="", saved=saved)
    assert "No library root" in dlg.status_label.text()
    dlg.set_library_root(ROOT)
    assert saved == [ROOT] and dlg.library_root() == ROOT and dlg.root_label.text() == ROOT
    assert dlg.accepted_changes()[0]["authors_str"] == "Jane Doe"


def test_library_root_defaults_to_the_saved_setting(monkeypatch):
    monkeypatch.setattr(app_settings, "load_library_root", lambda: ROOT)
    saved = []
    monkeypatch.setattr(app_settings, "save_library_root", saved.append)
    with _fake_history([]):
        dlg = FilenameParseDialog([_lib_book("Doe, Jane", "One.epub")])
    assert dlg.library_root() == ROOT
    dlg.set_library_root(os.path.join(ROOT, "x"))
    assert saved == [os.path.join(ROOT, "x")]


def test_accepted_path_changes_apply_to_real_book_metadata(tmp_path):
    root = tmp_path / "lib"
    path = make_epub(str(root / "Author - Jane Doe" / "Saga" / "Book One.epub"), authors=()) if (
        (root / "Author - Jane Doe" / "Saga").mkdir(parents=True) is None) else None
    book = load(path)
    dlg = _dialog([book], "Author - %authors%/%series%/%title%", root=str(root))
    changes = dlg.accepted_changes()
    assert changes == {0: {"authors_str": "Jane Doe", "series": "Saga", "title": "Book One"}}
    book.apply_metadata(changes[0])
    assert book.metadata.authors == ["Jane Doe"] and book.metadata.series == "Saga" and book.dirty


def test_path_and_filename_patterns_are_kept_apart_in_the_history():
    books = [_lib_book("Doe, Jane", "Jane Doe - One.epub")]
    history = ["%authors%/%title%", "%authors% - %title%"]
    with _fake_history(history):
        dlg = FilenameParseDialog(books, library_root=ROOT)
        assert dlg.pattern_edit.text() == "%authors% - %title%"  # the filename pattern, not history[0]
        assert [p for p, _c, _h in dlg._scored_candidates() if "/" in p] == []
        labels = {p: label for p, label in dlg._candidate_pattern_labels() if p}
    assert "(folder path)" in labels["%authors%/%title%"] and "(folder path)" not in labels["%authors% - %title%"]


def test_saving_a_path_pattern_on_accept(monkeypatch):
    used = []
    monkeypatch.setattr(app_settings, "save_pattern_used", used.append)
    dlg = _dialog([_lib_book("Doe, Jane", "One.epub")], "%authors%/%title%")
    dlg._on_accept()
    assert used == ["%authors%/%title%"]


# --- Redact step: path_tags ------------------------------------------------------------------


def _shelve(tmp_path, *parts, **kwargs):
    root = tmp_path / "lib"
    folder = root.joinpath(*parts[:-1])
    folder.mkdir(parents=True, exist_ok=True)
    return str(root), make_epub(str(folder / parts[-1]), **kwargs)


def test_step_is_in_the_catalogue_on_by_default_and_before_the_scans():
    cat = build_catalogue()
    keys = [s.key for s in cat]
    assert keys.index("path_tags") < keys.index("scan_isbn") < keys.index("metadata_lookup")
    plain = Recipe.default_for(cat)
    assert plain.enabled["path_tags"] is True
    # the stored pattern is empty (= follow the fallback, see test_redact_pattern_trail.py)
    assert plain.options["path_tags"]["pattern"] == ""
    spec = next(s for s in cat if s.key == "path_tags").options[0]
    assert spec.fallback() == "%authors%/%series%/%title%"
    saved_cat = build_catalogue("%title%", "Author - %authors%/%title%")
    assert next(s for s in saved_cat if s.key == "path_tags").options[0].fallback() == "Author - %authors%/%title%"


def test_high_confidence_folder_match_fills_empty_fields_and_saves(tmp_path, env, trash):
    root, path = _shelve(tmp_path, "Author - Jane Doe", "Saga", "Book One.epub", authors=())
    env.library_root = root
    options = {"path_tags": {"pattern": "Author - %authors%/%series%/%title%"}}
    report = run([load(path)], env, only("path_tags", options=options))
    entry = only_entry(report)
    assert entry.status is FileStatus.CHANGED
    saved = load(path)
    assert saved.metadata.authors == ["Jane Doe"] and saved.metadata.series == "Saga"
    assert saved.metadata.title == "Test Book"  # already filled: never overwritten
    assert "from the folder path" in report.to_text()


def test_author_sort_form_folder_is_converted_to_a_display_name(tmp_path, env):
    root, path = _shelve(tmp_path, "Tolkien, J.R.R.", "Fellowship.epub", authors=())
    env.library_root = root
    options = {"path_tags": {"pattern": "%authors%/%title%"}}
    run([load(path)], env, only("path_tags", options=options, threshold=0.85))
    assert load(path).metadata.authors == ["J.R.R. Tolkien"]


def test_bare_folder_captures_score_below_the_threshold_and_need_review(tmp_path, env):
    root, path = _shelve(tmp_path, "Jane Doe", "Saga", "Book One.epub", authors=())
    env.library_root = root
    report = run([load(path)], env, only("path_tags"))  # default pattern %authors%/%series%/%title%
    entry = only_entry(report)
    assert entry.status is FileStatus.NEEDS_REVIEW
    assert entry.review[0].confidence == pytest.approx(0.8333, abs=1e-3)
    assert "Jane Doe | Saga | Book One" in entry.review[0].reason
    assert load(path).metadata.authors == []  # nothing written while it awaits review


def test_missing_segment_is_named_in_the_review_reason(tmp_path, env):
    root, path = _shelve(tmp_path, "Jane Doe", "Book One.epub", authors=())
    env.library_root = root
    options = {"path_tags": {"pattern": "Author - %authors%/%series%/%title%"}}
    report = run([load(path)], env, only("path_tags", options=options))
    entry = only_entry(report)
    assert entry.status is FileStatus.NEEDS_REVIEW
    assert "no folder for Author - %authors%" in entry.review[0].reason
    assert entry.review[0].confidence < 0.9


def test_a_file_directly_in_the_root_has_no_folder_to_read(tmp_path, env):
    root, path = _shelve(tmp_path, "Book One.epub", authors=())
    env.library_root = root
    options = {"path_tags": {"pattern": "Author - %authors%/%title%"}}
    report = run([load(path)], env, only("path_tags", options=options))
    assert only_entry(report).status is FileStatus.UNCHANGED  # only %title% matched, and that is filled already
    assert load(path).metadata.authors == []


def test_only_empty_fields_are_filled(tmp_path, env):
    root, path = _shelve(tmp_path, "Author - Someone Else", "Book One.epub", authors=("Jane Doe",))
    env.library_root = root
    options = {"path_tags": {"pattern": "Author - %authors%/%title%"}}
    report = run([load(path)], env, only("path_tags", options=options))
    assert only_entry(report).status is FileStatus.UNCHANGED
    assert load(path).metadata.authors == ["Jane Doe"]


def test_without_a_library_root_nothing_happens_and_the_note_says_how(tmp_path, env):
    _root, path = _shelve(tmp_path, "Author - Jane Doe", "Book One.epub", authors=())
    env.library_root = ""
    options = {"path_tags": {"pattern": "Author - %authors%/%title%"}}
    report = run([load(path)], env, only("path_tags", options=options))
    assert only_entry(report).status is FileStatus.UNCHANGED
    assert "no library root is set" in report.to_text() and "Move into folders" in report.to_text()
    assert load(path).metadata.authors == []


def test_a_file_outside_the_library_root_is_left_alone(tmp_path, env):
    _root, path = _shelve(tmp_path, "Author - Jane Doe", "Book One.epub", authors=())
    other = tmp_path / "elsewhere"
    other.mkdir()
    env.library_root = str(other)
    options = {"path_tags": {"pattern": "Author - %authors%/%title%"}}
    report = run([load(path)], env, only("path_tags", options=options))
    assert only_entry(report).status is FileStatus.UNCHANGED
    assert "not under the library root" in report.to_text()
    assert load(path).metadata.authors == []


def test_a_pattern_without_a_separator_is_not_used_by_the_step(tmp_path, env):
    root, path = _shelve(tmp_path, "Jane Doe", "Book One.epub", authors=())
    env.library_root = root
    report = run([load(path)], env, only("path_tags", options={"path_tags": {"pattern": "%title%"}}))
    assert only_entry(report).status is FileStatus.UNCHANGED
    assert "needs a /" in report.to_text()


def test_siblings_with_the_same_saved_author_corroborate_a_folder(tmp_path, env):
    root, path = _shelve(tmp_path, "Doe, Jane", "New.epub", authors=())
    make_epub(os.path.join(root, "Doe, Jane", "Known.epub"), authors=("Jane Doe",))
    env.library_root = root
    options = {"path_tags": {"pattern": "%authors%/%title%"}}
    report = run([load(path)], env, only("path_tags", options=options))
    assert only_entry(report).status is FileStatus.CHANGED  # 0.975 with corroboration, 0.875 without
    assert load(path).metadata.authors == ["Jane Doe"]


def test_recipe_round_trip_keeps_the_path_step_settings():
    cat = build_catalogue("%title%", "%authors%/%title%")
    recipe = Recipe.default_for(cat)
    recipe.enabled["path_tags"] = False
    recipe.options["path_tags"]["pattern"] = "%genres%/%authors%/%title%"
    assert recipe_from_setting(recipe_to_setting(recipe), cat) == recipe
    # a recipe saved before the step existed gains it at its catalogue position, switched on
    old = Recipe.default_for(cat)
    old.order.remove("path_tags")
    del old.enabled["path_tags"], old.options["path_tags"]
    resolved = [s.key for s, _o in recipe_from_setting(recipe_to_setting(old), cat).resolve(cat)]
    assert "path_tags" in resolved and resolved.index("path_tags") < resolved.index("scan_isbn")
