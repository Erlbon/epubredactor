"""The History journal (core/history.py, redactor_common.core.journal) on real small EPUBs: Save records old/new
values, Restore writes them back, failed / no-change / Redact / copy saves, long descriptions, a broken journal
never blocks a save, the command line, and the Tools > History wiring."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from PyQt6.QtWidgets import QApplication  # noqa: E402

from core import epub_metadata, history  # noqa: E402
from core.epub_metadata import EpubBook, EpubError  # noqa: E402
from redactor_common.core.journal import MAX_VALUE_CHARS, Journal  # noqa: E402
from redactor_common.gui.standard_menus import get_action_registry  # noqa: E402
from test_redact_steps import env, make_epub, only, run, trash  # noqa: E402,F401

from gui import app_settings  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)


def entries():
    return history.get_journal().entries()


@pytest.fixture
def history_on():
    """The history is opt-in: the round-trip tests switch it on the way the app does (QSettings ini key)."""
    app_settings.save_history_enabled(True)
    assert history.history_enabled()


# --- opt-in: off by default ---------------------------------------------------------------------


def test_history_is_off_by_default_and_nothing_is_written(tmp_path, env):
    assert not history.history_enabled() and not app_settings.load_history_enabled()
    path = make_epub(str(tmp_path / "a.epub"), title="Dune", authors=("Ann &amp; Bob",))
    book = EpubBook(path)
    book.apply_metadata({"title": "Changed"})
    book.save()  # Save / Save All
    run([EpubBook(path)], env, only("validate_fix"))  # Redact
    from epubcli.main import main
    assert main(["set", path, "-s", "title=Arrakis"]) == 0  # command line
    assert EpubBook(path).metadata.title == "Arrakis"
    assert not os.path.exists(history.get_journal().path) and not history.journal_exists()


def test_turning_it_on_records_and_off_stops_again(tmp_path):
    path = make_epub(str(tmp_path / "a.epub"), title="Dune")
    app_settings.save_history_enabled(True)
    book = EpubBook(path)
    book.apply_metadata({"title": "One"})
    book.save()
    assert len(entries()) == 1
    app_settings.save_history_enabled(False)
    assert not history.history_enabled()
    book.apply_metadata({"title": "Two"})
    book.save()
    assert len(entries()) == 1


@pytest.mark.parametrize("text", ["", "[history]\nenabled=garbage\n", "[history\nenabled=true\n", "\x00\xff", "[other]\nenabled=true\n"])
def test_a_missing_or_garbled_setting_is_off(tmp_path, text):
    (tmp_path / "settings.ini").write_text(text, encoding="latin-1")
    assert history.history_enabled() is False


def test_the_setting_is_read_among_other_qsettings_lines(tmp_path):
    (tmp_path / "settings.ini").write_text(
        "[General]\nodd line without equals\nx=@Variant(\\0\\0)\n\n[history]\nenabled=true\n", encoding="utf-8",
    )
    assert history.history_enabled() is True


def test_preferences_checkbox_round_trips_and_cancel_changes_nothing():
    from gui import preferences

    dialog = preferences.make_dialog()
    box = dialog.control(preferences.KEY_HISTORY_ENABLED)
    assert box.isChecked() is False and "90 days" in preferences.history_help()
    assert history.journal_path() in preferences.history_help()
    box.setChecked(True)
    dialog.reject()
    assert not history.history_enabled()
    dialog = preferences.make_dialog()
    dialog.control(preferences.KEY_HISTORY_ENABLED).setChecked(True)
    dialog.accept()
    assert history.history_enabled()
    dialog = preferences.make_dialog()
    assert dialog.control(preferences.KEY_HISTORY_ENABLED).isChecked() is True
    dialog.control(preferences.KEY_HISTORY_ENABLED).setChecked(False)
    dialog.apply()
    assert not history.history_enabled()


def test_delete_history_asks_and_removes_the_file(tmp_path, history_on, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox

    from gui import preferences

    book = EpubBook(make_epub(str(tmp_path / "a.epub"), title="Dune"))
    book.apply_metadata({"title": "X"})
    book.save()
    journal_file = history.get_journal().path
    assert os.path.isfile(journal_file)
    binned = []
    monkeypatch.setattr("redactor_common.core.trash.move_to_trash", lambda p: (binned.append(p), os.remove(p)))
    dialog = preferences.make_dialog()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Cancel)
    dialog.delete_history_button.click()
    assert os.path.isfile(journal_file)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    dialog.delete_history_button.click()
    assert not os.path.exists(journal_file) and binned == [journal_file]
    assert history.history_enabled()  # deleting the file does not change the setting


def test_tools_history_asks_first_when_off_and_nothing_recorded(monkeypatch):
    from PyQt6.QtWidgets import QMessageBox

    import gui.main_window as mw

    asked, opened = [], []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: (asked.append(a[2]), QMessageBox.StandardButton.No)[1])
    monkeypatch.setattr(mw, "HistoryDialog", lambda j, f, p, title: opened.append(title))
    window = mw.MainWindow()
    window.open_history_dialog()
    assert asked and "History is off. Turn it on?" in asked[0] and opened == []
    assert not history.history_enabled()

    class Shown:
        def exec(self):
            return 0

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(mw, "HistoryDialog", lambda j, f, p, title: (opened.append(title), Shown())[1])
    window.open_history_dialog()
    assert history.history_enabled() and opened == ["History"]


def test_tools_history_when_off_with_a_journal_says_recording_is_off(tmp_path, history_on, monkeypatch):
    import gui.main_window as mw

    book = EpubBook(make_epub(str(tmp_path / "a.epub"), title="Dune"))
    book.apply_metadata({"title": "X"})
    book.save()
    app_settings.save_history_enabled(False)
    opened = []

    class Shown:
        def exec(self):
            return 0

    monkeypatch.setattr(mw, "HistoryDialog", lambda j, f, p, title: (opened.append(title), Shown())[1])
    mw.MainWindow().open_history_dialog()
    assert opened == ["History (recording is off)"]


# --- round trips (history on) --------------------------------------------------------------------


def test_baseline_is_taken_on_load_and_has_no_cover(tmp_path):
    book = EpubBook(make_epub(str(tmp_path / "a.epub"), title="Dune", publisher="Chilton"))
    assert book.baseline["Title"] == "Dune" and book.baseline["Publisher"] == "Chilton"
    assert book.baseline["Author(s)"] == "Jane Doe"
    assert not any("cover" in name.lower() for name in book.baseline)


def test_save_records_old_and_new_and_restore_writes_the_old_back(tmp_path, history_on):
    path = make_epub(str(tmp_path / "a.epub"), title="Dune", publisher="Chilton")
    book = EpubBook(path)
    book.apply_metadata({"title": "Dune Messiah", "publisher": "", "tags_str": "SF; Classic"})
    book.save()
    [entry] = entries()
    assert entry.kind == "save" and entry.status == "ok" and entry.path == path
    assert entry.changes == {
        "Title": ("Dune", "Dune Messiah"), "Publisher": ("Chilton", ""), "Genre": ("", "SF; Classic"),
    }
    assert book.baseline["Title"] == "Dune Messiah"  # the next save compares with what is on disk now

    values, skipped = Journal.restore_values(entry)
    assert history.apply_restore(path, values) == "" and skipped == []
    back = EpubBook(path).metadata
    assert (back.title, back.publisher, back.tags) == ("Dune", "Chilton", [])
    assert len(entries()) == 1  # apply_restore itself records nothing (the History dialog does)


def test_a_save_with_no_real_change_records_nothing(tmp_path, history_on):
    book = EpubBook(make_epub(str(tmp_path / "a.epub"), title="Dune"))
    book.apply_metadata({"title": "Dune"})
    book.dirty = True
    book.save()
    book.apply_metadata({"title": "Other"})
    book.apply_metadata({"title": "Dune"})
    book.save()
    assert entries() == []


def test_a_failed_save_records_failed(tmp_path, monkeypatch, history_on):
    path = make_epub(str(tmp_path / "a.epub"), title="Dune")
    book = EpubBook(path)
    book.apply_metadata({"title": "Changed"})

    def locked(*_a, **_k):
        raise PermissionError("the file is locked")

    monkeypatch.setattr(epub_metadata, "replace_with_retry", locked)
    with pytest.raises(PermissionError):
        book.save()
    [entry] = entries()
    assert entry.status == "failed" and "locked" in entry.error and entry.changes["Title"] == ("Dune", "Changed")
    assert book.baseline["Title"] == "Dune" and EpubBook(path).metadata.title == "Dune"


def test_a_cover_change_is_flagged_not_stored(tmp_path, history_on):
    book = EpubBook(make_epub(str(tmp_path / "a.epub")))
    book.remove_cover()
    book.save()
    [entry] = entries()
    assert entry.cover_changed and entry.changes == {}


def test_a_very_long_description_is_truncated_and_not_restorable(tmp_path, history_on):
    path = make_epub(str(tmp_path / "a.epub"), title="Dune")
    book = EpubBook(path)
    book.apply_metadata({"description": "x" * (MAX_VALUE_CHARS + 50)})
    book.save()
    [entry] = entries()
    assert entry.truncated == ["Description"] and not entry.restorable
    book.apply_metadata({"title": "New", "description": "short"})
    book.save()
    entry = entries()[0]
    assert entry.truncated == ["Description"] and entry.restorable
    values, skipped = Journal.restore_values(entry)
    assert values == {"Title": "Dune"} and skipped == ["Description"]
    assert history.apply_restore(path, values) == ""
    back = EpubBook(path).metadata
    assert back.title == "Dune" and back.description == "short"  # the cut field is left alone


def test_save_as_copy_records_only_when_it_overwrites_a_file(tmp_path, history_on):
    book = EpubBook(make_epub(str(tmp_path / "a.epub"), title="Dune"))
    other = make_epub(str(tmp_path / "b.epub"), title="Old Copy")
    book.apply_metadata({"title": "Dune 2"})
    book.save(str(tmp_path / "new.epub"))
    assert entries() == []  # a brand-new file has nothing to undo
    book.save(other)
    [entry] = entries()
    assert entry.path == other and entry.changes == {"Title": ("Old Copy", "Dune 2")}
    assert book.dirty and book.baseline["Title"] == "Dune"  # the book's own file was not written


def test_redact_records_one_redact_entry_per_book(tmp_path, env, history_on):
    path = make_epub(str(tmp_path / "r.epub"), authors=("Ann &amp; Bob",), description="&lt;p&gt;Hi&lt;/p&gt;")
    run([EpubBook(path)], env, only("validate_fix", "strip_description_html"))
    [entry] = entries()
    assert entry.kind == "redact" and entry.status == "ok" and entry.path == path
    assert entry.changes["Description"] == ("<p>Hi</p>", "Hi")
    assert entry.changes["Author(s)"] == ("Ann & Bob", "Ann; Bob")
    assert history.apply_restore(path, Journal.restore_values(entry)[0]) == ""
    assert EpubBook(path).metadata.description == "<p>Hi</p>"


def test_a_broken_journal_never_blocks_a_save(tmp_path, capsys, history_on):
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("x")
    history.set_journal(Journal(str(blocker / "journal.jsonl")))
    path = make_epub(str(tmp_path / "a.epub"), title="Dune")
    for title in ("One", "Two"):
        book = EpubBook(path)
        book.apply_metadata({"title": title})
        book.save()
    assert EpubBook(path).metadata.title == "Two"
    assert "could not be written" in history.take_notice() and history.take_notice() == ""
    assert capsys.readouterr().err.count("history journal") == 1


def test_apply_restore_reports_problems_in_plain_words(tmp_path):
    bad = tmp_path / "bad.epub"
    bad.write_bytes(b"not a zip")
    assert "could not be read" in history.apply_restore(str(bad), {"Title": "x"})
    path = make_epub(str(tmp_path / "a.epub"))
    assert "does not know" in history.apply_restore(path, {"Nonsense": "x"})


def test_the_command_line_set_is_journaled(tmp_path, capsys, history_on):
    from epubcli.main import main

    path = make_epub(str(tmp_path / "a.epub"), title="Dune")
    assert main(["set", path, "-s", "title=Arrakis"]) == 0
    [entry] = entries()
    assert entry.kind == "save" and entry.changes == {"Title": ("Dune", "Arrakis")}


def test_tools_history_reloads_restored_books(tmp_path, monkeypatch, history_on):
    import gui.main_window as mw

    path = make_epub(str(tmp_path / "a.epub"), title="Dune")
    book = EpubBook(path)
    book.apply_metadata({"title": "Changed"})
    book.save()
    window = mw.MainWindow()
    window.books = [book]
    window._rebuild_table()
    assert "history" in get_action_registry(window)

    def fake_dialog(journal, apply_restore, parent, title):
        assert journal is history.get_journal() and parent is window and title == "History"
        entry = journal.entries()[0]
        assert apply_restore(entry.path, Journal.restore_values(entry)[0]) == ""

        class Shown:
            def exec(self):
                return 0
        return Shown()

    monkeypatch.setattr(mw, "HistoryDialog", fake_dialog)
    window.open_history_dialog()
    assert window.books[0] is not book and window.books[0].metadata.title == "Dune"
    assert "reloaded 1" in window.status.currentMessage()
