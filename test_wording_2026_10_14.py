"""Owner decisions 2026-10-14: the Ctrl+S / F8 aliases are gone (E1, see also
test_menu_skeleton), the actions that open books into the list say "Open Files" /
"Open Folder" / "Import and Convert" everywhere (E2), and Delete Files says
where the files go: "Delete Files (Recycle Bin)" (E3)."""

import os
import re
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(__file__))

from PyQt6.QtGui import QAction  # noqa: E402
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

import gui.main_window as mw  # noqa: E402
from core.epub_metadata import EpubBook  # noqa: E402
from redactor_common.core import labels  # noqa: E402
from redactor_common.gui.standard_menus import get_action_registry  # noqa: E402
from test_review_fixes import build  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)
HERE = os.path.dirname(os.path.abspath(__file__))


def _read(rel):
    with open(os.path.join(HERE, rel), encoding="utf-8") as fh:
        return fh.read()


# --- E1 ----------------------------------------------------------------------------------


def test_no_compatibility_aliases_left():
    window = mw.MainWindow()
    bound = {s.toString() for a in window.findChildren(QAction) for s in a.shortcuts()}
    assert "Ctrl+S" not in bound and "F8" not in bound
    readme = _read("README.md")
    assert "still works for one more release" not in readme


# --- E2 ----------------------------------------------------------------------------------

_OLD_OPEN_WORDS = re.compile(r"\b(Add|Load) (EPUB )?(Files|Folders?)\b|\bAdd Folders of EPUBs\b|\bLoad (some|at least)\b")


def test_open_files_picker_is_titled_like_the_menu(monkeypatch):
    titles = []
    monkeypatch.setattr(
        QFileDialog, "getOpenFileNames", staticmethod(lambda parent, title, *a, **k: titles.append(title) or ([], "")),
    )
    mw.MainWindow().add_files_dialog()
    assert titles == ["Open Files"]


def test_no_add_or_load_wording_for_the_open_actions():
    for rel in ("gui/main_window.py", "gui/app_settings.py", "core/ebook_convert.py", "README.md", "ABOUT.md"):
        text = _read(rel)
        # The converter dialog's own "Add Files…" button (it adds to that dialog's queue) is not an open action.
        text = text.replace("Import and Convert > Add Files", "")
        assert not _OLD_OPEN_WORDS.search(text), (rel, _OLD_OPEN_WORDS.search(text).group(0))
    source = _read("gui/main_window.py")
    assert '"Open Folder (Ctrl/Shift-click to select more than one)"' in source
    assert "Import and Convert with them listed" in source


def test_converter_is_called_import_and_convert_outside_its_dialog_title():
    for rel in ("README.md", "gui/main_window.py", "core/kobo_usb.py"):
        text = _read(rel).replace('titled "Import to EPUB"', "").replace('the "Import to EPUB" dialog', "")
        assert "Import to EPUB" not in text, rel
    assert 'setWindowTitle("Import to EPUB")' in _read("gui/ebook_convert_dialog.py")  # allowed to stay


# --- E3 ----------------------------------------------------------------------------------


def test_delete_files_says_recycle_bin_in_menu_tooltip_and_dialog(tmp_path, monkeypatch):
    window = mw.MainWindow()
    act = get_action_registry(window)["delete_files"]
    assert labels.plain_label(act.text()) == "Delete Files (Recycle Bin)"
    assert act.shortcut().toString() == "Shift+Del"
    assert "Recycle Bin" in act.toolTip()
    window.books = [EpubBook(build(tmp_path / "a.epub"))]
    window._rebuild_table()
    window.table.selectAll()
    titles = []
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda parent, title, *a, **k: titles.append(title) or QMessageBox.StandardButton.No),
    )
    window.delete_files()
    assert titles == ["Delete Files (Recycle Bin)?"]
    readme = _read("README.md")
    assert "| File > Delete Files (Recycle Bin) | Shift+Delete |" in readme
