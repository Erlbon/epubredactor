"""
Rename/Export by Pattern on redactor_common's shared RenamePatternDialog
(2026-09-23; this app's own gui/rename_dialog.py was retired). The
dialog's exec() is patched to accept, so the real handler runs.
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QDialog  # noqa: E402

import gui.main_window as mw  # noqa: E402
from core.epub_metadata import EpubBook  # noqa: E402
from test_core import build_sample_epub  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)


def _window_with(tmp_path, monkeypatch, pattern):
    path = str(tmp_path / "original.epub")
    build_sample_epub(path)
    book = EpubBook(path)
    window = mw.MainWindow()
    window.books = [book]
    window._rebuild_table()

    def fake_exec(dialog):
        dialog.pattern_edit.setText(pattern)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(mw.RenamePatternDialog, "exec", fake_exec)
    return window, book


def test_rename_in_place_saves_unsaved_edits_first(tmp_path, monkeypatch):
    window, book = _window_with(tmp_path, monkeypatch, "%title%")
    book.apply_metadata({"title": "Renamed Title"})
    assert book.dirty
    window.open_rename_dialog()
    assert os.path.basename(book.path) == "Renamed Title.epub"
    assert not os.path.exists(tmp_path / "original.epub")
    assert EpubBook(book.path).metadata.title == "Renamed Title"  # saved before the rename


def test_export_writes_a_copy_and_leaves_the_original(tmp_path, monkeypatch):
    window, book = _window_with(tmp_path, monkeypatch, "%title% [%series% %series_index%]")
    out = tmp_path / "out"
    out.mkdir()
    book.apply_metadata({"title": "Copy", "series": ""})

    real_init = mw.RenamePatternDialog.__init__

    def init_in_export_mode(dialog, *args, **kwargs):
        real_init(dialog, *args, **kwargs)
        dialog.output_folder = str(out)
        dialog.export_radio.setChecked(True)
        dialog._refresh_preview()

    monkeypatch.setattr(mw.RenamePatternDialog, "__init__", init_in_export_mode)
    window.open_rename_dialog()
    assert os.listdir(out) == ["Copy.epub"]  # empty [series] group dropped
    assert book.path == str(tmp_path / "original.epub")
    assert EpubBook(str(out / "Copy.epub")).metadata.title == "Copy"
