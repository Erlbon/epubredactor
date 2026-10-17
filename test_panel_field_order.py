"""Drag-to-reorder of the side-panel fields (redactor_common's field_order), in the real MainWindow offscreen:
a real mouse drag on a grip moves the field (its tick box, label, editor and buttons together), the order is saved
by field key, a second window restores it, Export/Import carries it, Reset goes back to following the table's column
order, and editing after a reorder still writes the right values to the right fields."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PyQt6.QtGui import QMouseEvent  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402
from redactor_common.core import settings_bundle as sb  # noqa: E402

import gui.app_settings as app_settings  # noqa: E402
from core.epub_metadata import EpubBook  # noqa: E402
from gui.main_window import COLUMN_KEYS, MainWindow  # noqa: E402
from test_epub_duplicates import make_epub  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok))


def _window(tmp_path=None, names=()):
    win = MainWindow()
    win.resize(1500, 900)
    win.show()
    if names:
        win._load_paths([make_epub(tmp_path, n, title=f"Old {n}") for n in names])
    _app.processEvents()
    return win


def _shown(window):
    _app.processEvents()
    return window.tag_panel._field_order.visible_keys()


def _grid_order(window):
    """The field keys in the order of the grid's rows (column 2 = the editors)."""
    panel = window.tag_panel
    grid = panel._fields_grid
    by_widget = {id(w[2]): k for k, w in panel._row_widgets.items()}
    rows = {}
    for key, widgets in panel._row_widgets.items():
        r, _c, _rs, _cs = grid.getItemPosition(grid.indexOf(widgets[2]))
        rows[r] = key
    assert set(by_widget.values()) == set(rows.values())
    return [rows[r] for r in sorted(rows)]


def _drag(window, key, to_key, below=False):
    panel = window.tag_panel
    grip = panel._field_order.grip(key)
    assert grip is not None and grip.isVisible()
    target = panel._row_widgets[to_key][2]
    target_global = target.mapToGlobal(QPoint(5, target.height() - 1 if below else 1))
    start = QPoint(grip.width() // 2, grip.height() // 2)
    QTest.mousePress(grip, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    for point in (grip.mapToGlobal(start) + QPoint(0, 12), target_global):
        QApplication.sendEvent(grip, QMouseEvent(
            QEvent.Type.MouseMove, QPointF(grip.mapFromGlobal(point)), QPointF(point),
            Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    QTest.mouseRelease(grip, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, grip.mapFromGlobal(target_global))
    _app.processEvents()


def test_without_a_saved_order_the_panel_follows_the_tables_column_order():
    window = _window()
    assert app_settings.load_panel_field_order() == []
    assert _grid_order(window) == window.tag_panel._visible_field_keys == _shown(window)


def test_drag_moves_the_whole_row_and_saves_by_key():
    window = _window()
    before = _shown(window)
    first, last = before[0], before[-1]
    _drag(window, last, first)
    after = _shown(window)
    assert after == [last] + before[:-1]
    assert _grid_order(window) == after
    assert app_settings.load_panel_field_order()[:2] == [last, first]
    window.close()


def test_the_extra_buttons_move_with_their_field():
    window = _window()
    panel = window.tag_panel
    assert len(panel._row_widgets["authors_str"]) >= 4  # tick, label, editor, guess button
    _drag(window, "authors_str", _shown(window)[0])
    grid = panel._fields_grid
    rows = {grid.getItemPosition(grid.indexOf(w))[0] for w in panel._row_widgets["authors_str"]}
    assert len(rows) == 1  # all in the same grid row
    window.close()


def test_a_second_window_restores_the_order_and_reset_goes_back_to_the_default():
    window = _window()
    default = _shown(window)
    _drag(window, default[-1], default[0])
    moved = _shown(window)
    window.close()
    second = _window()
    assert _shown(second) == moved
    second.tag_panel.reset_field_order()
    assert _shown(second) == default and app_settings.load_panel_field_order() == []
    second.close()


def test_hiding_a_column_keeps_the_users_order_of_the_rest():
    window = _window()
    default = _shown(window)
    _drag(window, default[-1], default[0])
    moved = _shown(window)
    hidden = moved[3]
    window.table.setColumnHidden(COLUMN_KEYS.index(hidden), True)
    window._on_columns_changed()
    assert _shown(window) == [k for k in moved if k != hidden]
    window.close()


def test_order_travels_through_export_import():
    window = _window()
    default = _shown(window)
    _drag(window, default[-1], default[0])
    wanted = _shown(window)
    adapter = window._settings_adapter
    chosen = sb.default_selection(adapter)
    bundle = sb.parse_bundle(sb.dump_bundle(sb.build_bundle(adapter, chosen)), "epubredactor")
    window.tag_panel.reset_field_order()
    assert _shown(window) == default
    result = sb.apply_bundle(adapter, bundle, chosen)
    window._on_settings_imported(result)
    assert _shown(window) == wanted
    window.close()


def test_edit_two_books_after_a_reorder_writes_the_right_values_to_the_right_fields(tmp_path):
    window = _window(tmp_path, ("a.epub", "b.epub"))
    default = _shown(window)
    _drag(window, "title", default[-1], below=True)
    _drag(window, "publisher", default[0])
    window.table.selectAll()
    _app.processEvents()
    panel = window.tag_panel
    panel._editors["title"].setText("One Title")
    panel._editors["title"].textEdited.emit("One Title")
    panel._editors["publisher"].setText("One Publisher")
    panel._editors["publisher"].textEdited.emit("One Publisher")
    assert panel._checkboxes["title"].isChecked() and panel._checkboxes["publisher"].isChecked()
    assert not panel._checkboxes["language"].isChecked()
    window.save_changed()
    for book in window.books:
        md = EpubBook(book.path).metadata
        assert md.title == "One Title" and md.publisher == "One Publisher"
        book.dirty = False
    window.close()
