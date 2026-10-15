"""House rule (owner, 2026-10-15): every table's column headers can be resized by dragging.

The lint is the machine check; the dialog tests build real dialogs offscreen and prove each column is Interactive
and that resizeSection really changes its width."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication, QHeaderView  # noqa: E402

from redactor_common.gui.table_columns import lint_resizable_headers  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)


def test_no_undraggable_header_modes_in_gui():
    assert lint_resizable_headers(ROOT / "gui") == []


def _assert_draggable(table):
    header = table.horizontalHeader()
    for section in range(header.count()):
        assert header.sectionResizeMode(section) == QHeaderView.ResizeMode.Interactive, section
    for section in range(header.count() - 1):  # the last section also fills the remaining width
        before = header.sectionSize(section)
        header.resizeSection(section, before + 37)
        assert header.sectionSize(section) == before + 37, section


def _books(tmp_path):
    from test_content_scan_multilingual import build_epub

    body = "<p>Copyright 2019 by Jane A. Smith</p><p>(The Expanse #2)</p><p>Translated by Kari Nordmann</p>"
    return [build_epub(tmp_path / f"b{i}.epub", [("a", body)]) for i in range(3)]


def test_validation_dialog_columns_draggable(tmp_path):
    from gui.validation_dialog import ValidationDialog

    dialog = ValidationDialog(_books(tmp_path))
    _assert_draggable(dialog.table)


def test_content_scan_dialog_columns_draggable(tmp_path):
    from gui.content_scan_dialog import ContentScanDialog

    dialog = ContentScanDialog(_books(tmp_path))
    _assert_draggable(dialog.table)


def test_series_number_dialog_columns_draggable(tmp_path):
    from gui.series_number_dialog import SeriesNumberDialog

    dialog = SeriesNumberDialog(_books(tmp_path))
    _assert_draggable(dialog.table)
    width = dialog.table.columnWidth(0)
    dialog.table.horizontalHeader().resizeSection(0, width + 50)
    dialog.start_edit.setText("5")  # a refreshed preview keeps the dragged width
    assert dialog.table.columnWidth(0) == width + 50


def test_author_clean_and_missing_space_dialogs_columns_draggable():
    from gui.author_clean_dialog import AuthorCleanDialog
    from gui.missing_space_dialog import MissingSpaceDialog
    from test_strip_description_html_wiring import _fake_book

    books = [_fake_book("/x/a.epub", title="TheHobbit", authors=["J.R.R.Tolkien"], author_sort=[]),
             _fake_book("/x/b.epub", title="Dune", authors=["Frank Herbert"], author_sort=["Herbert, Frank"])]
    clean = AuthorCleanDialog(books)
    _assert_draggable(clean.table)
    spacing = MissingSpaceDialog(books)
    _assert_draggable(spacing.table)
