"""Tools > Columns... reorders the table's columns (redactor_common's ColumnSettingsDialog + apply_column_order),
in the real MainWindow. EPUB used to persist NO column order (only hidden columns and widths, by key): the order is
now saved by field key (table/column_order_by_key) on every header drag and every Columns... change, restored at
start, and carried by Export/Import Settings. The conftest fixture points settings at a per-test temp ini."""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
from redactor_common.core import settings_bundle as sb  # noqa: E402
from redactor_common.gui.column_settings_dialog import ColumnSettingsDialog  # noqa: E402

import gui.app_settings as app_settings  # noqa: E402
import gui.main_window as mw  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)

KEYS = mw.COLUMN_KEYS


def _visual(window):
    header = window.table.horizontalHeader()
    return [KEYS[header.logicalIndex(v)] for v in range(header.count())]


def _run_dialog(monkeypatch, window, edit):
    seen = {}

    def fake_exec(self):
        seen["order"] = self.column_order()
        edit(self)
        return 1

    monkeypatch.setattr(ColumnSettingsDialog, "exec", fake_exec)
    window.open_column_settings_dialog()
    return seen


def _select(dialog, key):
    dialog.list_widget.setCurrentRow(dialog.column_order().index(key))


def test_nothing_saved_means_default_order_and_path_after_filename():
    window = mw.MainWindow()
    assert _visual(window) == KEYS
    assert app_settings.load_column_order() == []
    assert KEYS.index("path") == KEYS.index("filename") + 1


def test_dialog_lists_visual_order_including_a_header_drag(monkeypatch):
    window = mw.MainWindow()
    header = window.table.horizontalHeader()
    header.moveSection(header.visualIndex(KEYS.index("title")), 7)  # the user drags a header
    expected = _visual(window)
    seen = _run_dialog(monkeypatch, window, lambda d: None)
    assert seen["order"] == expected != KEYS


def test_header_drag_is_persisted_and_restored_in_a_second_window():
    window = mw.MainWindow()
    header = window.table.horizontalHeader()
    header.moveSection(header.visualIndex(KEYS.index("title")), 7)
    expected = _visual(window)
    assert app_settings.load_column_order() == expected
    assert _visual(mw.MainWindow()) == expected


def test_move_in_dialog_reorders_table_and_persists(monkeypatch):
    window = mw.MainWindow()
    window.table.setColumnHidden(KEYS.index("publisher"), True)
    window.table.setColumnWidth(KEYS.index("title"), 222)
    before = _visual(window)

    def edit(dialog):
        _select(dialog, "title")
        for _ in range(2):
            dialog.up_button.click()

    _run_dialog(monkeypatch, window, edit)
    expected = list(before)
    expected.remove("title")
    expected.insert(before.index("title") - 2, "title")
    assert _visual(window) == expected
    assert app_settings.load_column_order() == expected
    assert window.table.isColumnHidden(KEYS.index("publisher"))  # hidden state kept
    assert window.table.columnWidth(KEYS.index("title")) == 222  # width kept
    second = mw.MainWindow()
    assert _visual(second) == expected
    assert second.table.isColumnHidden(KEYS.index("publisher"))


def test_unchecking_in_dialog_keeps_order(monkeypatch):
    window = mw.MainWindow()
    header = window.table.horizontalHeader()
    header.moveSection(header.visualIndex(KEYS.index("title")), 1)
    order = _visual(window)

    def edit(dialog):
        for i in range(dialog.list_widget.count()):
            if dialog.list_widget.item(i).data(Qt.ItemDataRole.UserRole) == "publisher":
                dialog.list_widget.item(i).setCheckState(Qt.CheckState.Unchecked)

    _run_dialog(monkeypatch, window, edit)
    assert _visual(window) == order
    assert window.table.isColumnHidden(KEYS.index("publisher"))


def test_a_column_unknown_to_the_saved_order_goes_to_its_default_place():
    saved = [k for k in reversed(KEYS) if k != "cover_size"]  # saved by an older version without cover_size
    app_settings.save_column_order(saved)
    window = mw.MainWindow()
    assert _visual(window) == saved + ["cover_size"]


def test_panel_follows_the_new_order(monkeypatch):
    window = mw.MainWindow()

    def edit(dialog):
        _select(dialog, "title")
        for _ in range(3):
            dialog.up_button.click()

    _run_dialog(monkeypatch, window, edit)
    field_keys = {key for key, _label, _ml in mw.FIELDS}
    wanted = [k for k in _visual(window) if k in field_keys and not window.table.isColumnHidden(KEYS.index(k))]
    assert window._visible_ordered_field_keys() == wanted


def test_order_travels_through_export_import():
    window = mw.MainWindow()
    header = window.table.horizontalHeader()
    header.moveSection(header.visualIndex(KEYS.index("title")), 1)
    wanted = _visual(window)
    adapter = window._settings_adapter
    chosen = sb.default_selection(adapter)
    bundle = sb.parse_bundle(sb.dump_bundle(sb.build_bundle(adapter, chosen)), "epubredactor")
    header.moveSection(header.visualIndex(KEYS.index("title")), 6)
    assert _visual(window) != wanted
    result = sb.apply_bundle(adapter, bundle, chosen)
    window._on_settings_imported(result)
    assert _visual(window) == wanted
    assert app_settings.load_column_order() == wanted
