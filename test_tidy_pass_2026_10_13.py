"""Tidy-up pass 2026-10-13: progress for slow work (P1), Open in Sigil limits (T3),
Delete Files without a success pop-up (T2), no silent no-ops (T4), and the
right-click Number Series using the menu's dialog (T5)."""

import os
import subprocess
import sys
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(__file__))

import pytest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import gui.main_window as mw  # noqa: E402
from core.calibre_tools import ToolCancelled, cancellable_run  # noqa: E402
from core.epub_metadata import EpubBook  # noqa: E402
from redactor_common.gui.menu_builder import MenuAction, Submenu  # noqa: E402
from test_review_fixes import build  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)
YES = QMessageBox.StandardButton.Yes
NO = QMessageBox.StandardButton.No


def _window_with(tmp_path, count: int):
    window = mw.MainWindow()
    paths = [build(tmp_path / f"b{i}.epub") for i in range(count)]
    window.books = [EpubBook(p) for p in paths]
    window._rebuild_table()
    return window


def _select_all(window):
    window.table.selectAll()


def _record_progress(monkeypatch, module=mw):
    """Wraps module.run_with_progress, recording each call's label and kwargs."""
    calls = []
    real = module.run_with_progress

    def spy(parent, items, step, label, **kwargs):
        calls.append((label, kwargs))
        return real(parent, items, step, label, **kwargs)

    monkeypatch.setattr(module, "run_with_progress", spy)
    return calls


# --- T3 Open in Sigil ---------------------------------------------------------------------


def _sigil_spies(monkeypatch):
    launched, asked, told = [], [], []
    monkeypatch.setattr(mw, "find_sigil", lambda configured_path=None: "sigil.exe")
    monkeypatch.setattr(mw, "launch_sigil", lambda exe, path: launched.append(path))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: asked.append(a[2]) or NO))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: told.append(a[2])))
    return launched, asked, told


def test_sigil_opens_a_handful_without_asking(tmp_path, monkeypatch):
    window = _window_with(tmp_path, mw.SIGIL_CONFIRM_ABOVE)
    _select_all(window)
    launched, asked, _told = _sigil_spies(monkeypatch)
    window.open_in_sigil()
    assert len(launched) == mw.SIGIL_CONFIRM_ABOVE and not asked


def test_sigil_asks_with_the_count_above_five(tmp_path, monkeypatch):
    window = _window_with(tmp_path, 6)
    _select_all(window)
    launched, asked, _told = _sigil_spies(monkeypatch)
    window.open_in_sigil()  # answered No
    assert len(asked) == 1 and "6" in asked[0]
    assert launched == []


def test_sigil_refuses_above_the_cap(tmp_path, monkeypatch):
    window = _window_with(tmp_path, mw.SIGIL_MAX_BOOKS + 1)
    _select_all(window)
    launched, asked, told = _sigil_spies(monkeypatch)
    window.open_in_sigil()
    assert launched == [] and asked == []
    assert len(told) == 1 and str(mw.SIGIL_MAX_BOOKS + 1) in told[0] and str(mw.SIGIL_MAX_BOOKS) in told[0]


# --- T2 Delete Files ----------------------------------------------------------------------


def test_delete_files_success_is_a_status_message_not_a_popup(tmp_path, monkeypatch):
    window = _window_with(tmp_path, 2)
    _select_all(window)
    trashed, popups = [], []
    monkeypatch.setattr(mw, "move_to_trash", lambda path: trashed.append(path))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: YES))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: popups.append(a)))
    window.delete_files()
    assert len(trashed) == 2 and window.books == []
    assert popups == []
    assert "Recycle Bin" in window.status.currentMessage()


# --- T4 no silent no-ops --------------------------------------------------------------------


def test_f2_with_nothing_or_several_selected_says_why(tmp_path):
    window = _window_with(tmp_path, 2)
    window.table.clearSelection()
    window.rename_selected_file()
    assert "select one book" in window.status.currentMessage()
    _select_all(window)
    window.rename_selected_file()
    message = window.status.currentMessage()
    assert "one book at a time" in message and "2" in message and "Rename / Export / Move" in message


def test_empty_list_actions_say_why(tmp_path):
    window = mw.MainWindow()
    window.clear_list()
    assert "already empty" in window.status.currentMessage()
    window.refresh_list()
    assert "nothing is loaded" in window.status.currentMessage()
    window.remove_selected()
    assert "select the books" in window.status.currentMessage()


def test_loading_only_already_loaded_files_says_so(tmp_path):
    window = _window_with(tmp_path, 1)
    window._load_paths([window.books[0].path])
    assert "Already in the list" in window.status.currentMessage()


def test_unflag_without_any_cover_says_why(tmp_path, monkeypatch):
    window = _window_with(tmp_path, 1)
    _select_all(window)
    monkeypatch.setattr(EpubBook, "cover_hash", property(lambda self: None))
    window.unflag_selected_covers_as_junk()
    assert "has a cover" in window.status.currentMessage()


# --- T5 right-click Number Series ----------------------------------------------------------


def test_context_menu_number_series_is_the_menu_dialog(tmp_path):
    window = _window_with(tmp_path, 2)
    items = window._context_menu_items(window.books)
    organize = next(i for i in items if isinstance(i, Submenu) and i.text == "Organize")
    number = next(i for i in organize.items if isinstance(i, MenuAction) and i.key == "number_series")
    assert number.slot == window.open_series_number_dialog
    assert not hasattr(window, "quick_number_series")


# --- P1 progress for slow work -------------------------------------------------------------


def test_big_batch_refreshes_and_applies_show_progress(tmp_path, monkeypatch):
    window = _window_with(tmp_path, 3)
    monkeypatch.setattr(mw, "REBUILD_PROGRESS_THRESHOLD", 1)
    calls = _record_progress(monkeypatch)
    _select_all(window)
    window._refresh_rows_full(window.books)
    window._apply_bulk_edit({"publisher": "P"})
    window._refresh_affected_rows(window.books)
    window._refresh_all_junk_cover_cells()
    labels = [label for label, _kw in calls]
    assert labels.count("Updating list…") >= 2  # rows refresh + junk-cover cells
    assert "Applying changes…" in labels and "Updating covers…" in labels
    assert all(b.metadata.publisher == "P" for b in window.books)


def test_manifest_repairs_run_under_progress(tmp_path, monkeypatch):
    window = _window_with(tmp_path, 3)
    calls = _record_progress(monkeypatch)

    class _Dialog:
        class DialogCode:
            Accepted = 1

        def __init__(self, books, parent=None):
            self.books = books

        def exec(self):
            return 1

        def accepted_book_indices(self):
            return list(range(len(self.books)))

    monkeypatch.setattr(mw, "ManifestRebuildDialog", _Dialog)
    monkeypatch.setattr(mw, "ManifestDedupeDialog", _Dialog)
    window.open_manifest_rebuild_dialog()
    window.open_manifest_dedupe_dialog()
    labels = [label for label, _kw in calls]
    assert "Rebuilding manifests…" in labels and "Deduplicating manifest IDs…" in labels


def test_polished_books_are_reloaded_under_progress(tmp_path, monkeypatch):
    window = _window_with(tmp_path, 3)
    calls = _record_progress(monkeypatch)
    old = list(window.books)

    class _Dialog:
        class DialogCode:
            Accepted = 1

        def __init__(self, books, parent=None):
            pass

        def exec(self):
            return 1

        def result_polished_in_place(self):
            return old

        def result_exported_paths(self):
            return []

    monkeypatch.setattr(mw, "PolishBookDialog", _Dialog)
    window.open_polish_book_dialog()
    assert "Reloading…" in [label for label, _kw in calls]
    assert len(window.books) == 3 and not any(b in old for b in window.books)  # fresh objects, same order
    assert [b.path for b in window.books] == [b.path for b in old]


def test_restoring_the_last_session_checks_files_off_the_gui_thread(tmp_path, monkeypatch):
    window = mw.MainWindow()
    path = build(tmp_path / "a.epub")
    mw.app_settings.save_last_session_files([path, str(tmp_path / "gone.epub")])
    busy = []
    real = mw.run_busy
    monkeypatch.setattr(mw, "run_busy", lambda parent, label, fn, *a, **k: busy.append(label) or real(parent, label, fn, *a, **k))
    window._restore_last_session()
    assert busy and [b.path for b in window.books] == [os.path.normpath(path)]


def test_better_cover_previews_show_progress(tmp_path, monkeypatch):
    import gui.better_cover_dialog as bcd

    calls = _record_progress(monkeypatch, bcd)
    monkeypatch.setattr(bcd, "THUMBNAIL_PROGRESS_THRESHOLD", 1)
    book = EpubBook(build(tmp_path / "a.epub"))
    dialog = bcd.BetterCoverDialog([(book, b"")], parent=None)
    assert dialog.table.rowCount() == 1
    assert [label for label, _kw in calls] == ["Preparing cover previews…"]


# --- P1 Calibre convert / polish: off the GUI thread, Cancel kills the process --------------


def test_cancellable_run_kills_the_process_on_cancel():
    cancel = threading.Event()
    run = cancellable_run(cancel, poll_seconds=0.05)
    threading.Timer(0.3, cancel.set).start()
    started = time.monotonic()
    with pytest.raises(ToolCancelled):
        run([sys.executable, "-c", "import time; time.sleep(30)"], capture_output=True, timeout=60)
    assert time.monotonic() - started < 10


def test_cancellable_run_behaves_like_subprocess_run():
    run = cancellable_run(threading.Event())
    proc = run([sys.executable, "-c", "import sys; sys.stderr.write('oops'); sys.exit(3)"], capture_output=True, timeout=60)
    assert proc.returncode == 3 and b"oops" in proc.stderr
    with pytest.raises(subprocess.TimeoutExpired):
        run([sys.executable, "-c", "import time; time.sleep(30)"], capture_output=True, timeout=0.3)


def test_convert_runs_in_the_background_with_a_working_cancel(tmp_path, monkeypatch):
    import gui.ebook_convert_dialog as ecd

    source = tmp_path / "a.mobi"
    source.write_bytes(b"x")
    seen = {}

    def fake_convert(tool, src, dst, run_fn=None):
        seen["run_fn"] = run_fn
        seen["thread"] = threading.current_thread()
        open(dst, "wb").close()

    calls = _record_progress(monkeypatch, ecd)
    monkeypatch.setattr(ecd, "convert_to_epub", fake_convert)
    dialog = ecd.EbookConvertDialog(None, initial_paths=[str(source)])
    dialog._tool_path = "ebook-convert"
    dialog._run_conversion()
    assert seen["run_fn"] is not None and seen["thread"] is not threading.main_thread()
    assert calls and calls[0][1].get("on_cancel") is not None
    assert dialog.converted_epub_paths() == [str(tmp_path / "a.epub")]


def test_polish_runs_in_the_background_with_a_working_cancel(tmp_path, monkeypatch):
    import gui.polish_book_dialog as pbd

    book = EpubBook(build(tmp_path / "a.epub"))
    seen = {}

    def fake_polish(tool, src, dst, options, run_fn=None):
        seen["run_fn"] = run_fn
        seen["thread"] = threading.current_thread()
        with open(src, "rb") as f_in, open(dst, "wb") as f_out:
            f_out.write(f_in.read())

    calls = _record_progress(monkeypatch, pbd)
    monkeypatch.setattr(pbd, "polish_book", fake_polish)
    dialog = pbd.PolishBookDialog([book])
    dialog._tool_path = "ebook-polish"
    monkeypatch.setattr(dialog, "_collect_options", lambda: type("O", (), {"any_selected": lambda self: True})())
    dialog._run_polish()
    assert seen["run_fn"] is not None and seen["thread"] is not threading.main_thread()
    assert calls and calls[0][1].get("on_cancel") is not None
    assert dialog.result_polished_in_place() == [book]
