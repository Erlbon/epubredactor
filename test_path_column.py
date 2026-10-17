"""The shared Path column (redactor_common.core.path_column) in the real MainWindow: directly after Filename (it
used to be the FIRST column), visible by default, shows the folder, full path in the tooltip and for Ctrl+C, sorts as
text, is un-hidden once for old saved hidden sets, and follows a rename and a move into folders."""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(__file__))

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402
from redactor_common.core.path_column import lint_path_column  # noqa: E402
from redactor_common.gui.path_column import selected_column_text  # noqa: E402

import gui.main_window as mw  # noqa: E402
from core.epub_metadata import EpubBook  # noqa: E402
from gui import app_settings  # noqa: E402
from test_redact_steps import make_epub  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)
PATH = mw.PATH_COL


def _window(tmp_path, *names):
    window = mw.MainWindow()
    paths = []
    for name in names:
        full = tmp_path / name
        full.parent.mkdir(parents=True, exist_ok=True)
        paths.append(make_epub(str(full)))
    window.books = [EpubBook(p) for p in paths]
    window._rebuild_table()
    return window, paths


def test_path_is_directly_after_filename_and_visible_by_default(tmp_path):
    assert lint_path_column(mw.COLUMN_KEYS) == []
    assert (mw.FILENAME_COL, mw.PATH_COL) == (0, 1) and mw.COLUMN_KEYS[mw.PATH_COL] == "path"
    window, _paths = _window(tmp_path, "a.epub")
    assert window.table.horizontalHeaderItem(mw.PATH_COL).text() == "Path"
    assert window.table.horizontalHeaderItem(mw.FILENAME_COL).text() == "Filename"
    assert not window.table.isColumnHidden(PATH)
    window.close()


def test_cell_shows_the_folder_and_the_tooltip_the_full_path(tmp_path):
    window, (path,) = _window(tmp_path, "Sub/a.epub")
    item = window.table.item(0, PATH)
    assert item.text() == str(tmp_path / "Sub") and item.toolTip() == path
    assert window.table.item(0, mw.FILENAME_COL).text() == "a.epub"
    window.close()


def test_ctrl_c_text_is_the_full_path(tmp_path):
    # The key handling itself (real Ctrl+C, real clipboard) is tested in redactor_common.
    window, (path,) = _window(tmp_path, "Sub/a.epub")
    assert getattr(window.table, "_cell_copy_filter", None) is not None
    window.table.selectRow(0)
    window.table.setCurrentCell(0, PATH)
    assert selected_column_text(window.table) == path
    window.close()


def test_sorting_the_path_column_is_text_order(tmp_path):
    window, _paths = _window(tmp_path, "Vol 10/a.epub", "vol 2/b.epub", "Vol 1/c.epub")
    window.table.sortItems(PATH, Qt.SortOrder.AscendingOrder)
    shown = [os.path.basename(window.table.item(r, PATH).text()) for r in range(window.table.rowCount())]
    assert shown == ["Vol 1", "vol 2", "Vol 10"]
    window.close()


def test_a_hidden_path_column_from_old_settings_is_unhidden_once(tmp_path):
    other = mw.COLUMN_KEYS[mw.FIRST_FIELD_COL]
    app_settings.save_hidden_column_keys({"path", other})
    assert not app_settings.path_column_seeded()
    first = mw.MainWindow()
    try:
        assert not first.table.isColumnHidden(PATH)  # un-hidden once, so it is seen
        assert first.table.isColumnHidden(mw.FIRST_FIELD_COL)  # the other choices stay
        assert app_settings.path_column_seeded()
        first._set_column_visible(PATH, False)  # the user hides it again
    finally:
        first.close()
    second = mw.MainWindow()
    try:
        assert second.table.isColumnHidden(PATH)  # now the user's choice wins
    finally:
        second.close()


def test_a_path_cell_follows_a_rename(tmp_path, monkeypatch):
    window, (path,) = _window(tmp_path, "a.epub")
    book = window.books[0]
    new_dir = tmp_path / "renamed"
    new_dir.mkdir()
    new_path = str(new_dir / "z.epub")

    def fake_prompt(parent, old, setter, log=None):
        setter(new_path)
        return True

    monkeypatch.setattr(mw, "prompt_rename_single_file", fake_prompt)
    window.rename_single_file(book)
    item = window.table.item(0, PATH)
    assert item.text() == str(new_dir) and item.toolTip() == new_path
    window.close()


def test_a_path_cell_follows_a_move_into_folders(tmp_path, monkeypatch):
    root = tmp_path / "library"
    root.mkdir()
    window, (a,) = _window(tmp_path, "a.epub")
    app_settings.save_library_root(str(root))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *args, **kw: QMessageBox.StandardButton.No))

    def fake_exec(dialog):
        dialog.pattern_edit.setText("%authors%/%title%")
        dialog.move_radio.setChecked(True)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(mw.RenamePatternDialog, "exec", fake_exec)
    window.open_rename_dialog()
    item = window.table.item(0, PATH)
    assert item.text() == str(root / "Jane Doe") and item.toolTip() == str(root / "Jane Doe" / "Test Book.epub")
    window.close()
