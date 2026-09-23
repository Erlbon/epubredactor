"""
Column widths/visibility persisted by field key, not column index
(2026-09-23), with a one-time migration of the old index-based values.
The conftest fixture points settings at a per-test temp ini.
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

import gui.app_settings as app_settings  # noqa: E402
import gui.main_window as mw  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)


def test_old_index_based_values_migrate_once():
    keys = mw.COLUMN_KEYS
    app_settings.save_hidden_columns({0, keys.index("publisher")})
    app_settings.save_column_widths({keys.index("title"): 321})

    assert app_settings.load_hidden_column_keys(keys) == {"path", "publisher"}
    assert app_settings.load_column_widths_by_key(keys) == {"title": 321}

    # Migrated values are now stored by key: a different column order no
    # longer changes which columns they refer to.
    reordered = ["junk_cover", *keys[:-1]]
    assert app_settings.load_hidden_column_keys(reordered) == {"path", "publisher"}
    assert app_settings.load_column_widths_by_key(reordered) == {"title": 321}


def test_window_round_trips_hidden_columns_by_key():
    window = mw.MainWindow()
    col = mw.COLUMN_KEYS.index("ddc")
    window.table.setColumnHidden(col, True)
    window._on_columns_changed()
    assert "ddc" in app_settings.load_hidden_column_keys(mw.COLUMN_KEYS)

    fresh = mw.MainWindow()
    assert fresh.table.isColumnHidden(col)
    assert not fresh.table.isColumnHidden(mw.COLUMN_KEYS.index("filename"))
