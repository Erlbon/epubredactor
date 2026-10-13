"""Tools > Preferences: the shared dialog with this app's pages, mapped onto the
existing ini keys (so loaders and Export/Import Settings keep working), and the
live window following what it writes."""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(__file__))

from PyQt6.QtWidgets import QApplication, QComboBox  # noqa: E402

import gui.main_window as mw  # noqa: E402
from gui import app_settings, preferences  # noqa: E402
from redactor_common.core.preferences import (  # noqa: E402
    KEY_ASCII_FILENAMES,
    KEY_AUTO_NUMBER_PADDING,
    KEY_BLANK_LANGUAGE_ENABLED,
    KEY_DEFAULT_LANGUAGE,
    KEY_ZERO_PAD_NUMBERS,
    KEY_ZERO_PAD_WIDTH,
    defaults,
)
from redactor_common.gui.preferences_dialog import PreferencesDialog  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)


def _dialog():
    return preferences.make_dialog()


def test_pages_and_no_auto_number_setting():
    dialog = _dialog()
    assert dialog.page_titles() == ["Filenames", "Language", "Tools and Paths"]
    keys = set(defaults(preferences.build_sections()))
    # this app has no Auto-Numbering (no such key or feature anywhere), so no padding setting for it
    assert KEY_AUTO_NUMBER_PADDING not in keys
    assert {KEY_ASCII_FILENAMES, KEY_ZERO_PAD_NUMBERS, KEY_ZERO_PAD_WIDTH, KEY_BLANK_LANGUAGE_ENABLED,
            KEY_DEFAULT_LANGUAGE} <= keys
    assert keys == set(preferences.INI_KEYS)


def test_wrap_and_perf_logging_are_menu_items_only_not_duplicated_in_preferences():
    """They live in View > Text Wrapping and Tools > Enable Performance Logging
    (the menu skeleton's places); Preferences used to repeat both."""
    ini_keys = set(preferences.INI_KEYS.values())
    assert "table/text_overflow_mode" not in ini_keys
    assert "debug/perf_logging_enabled" not in ini_keys
    window = mw.MainWindow()
    registry = mw.get_action_registry(window)
    assert "text_wrap_mode_wrap" in registry and "perf_logging" in registry


def test_existing_ini_keys_are_the_ones_used():
    assert preferences.INI_KEYS[KEY_ASCII_FILENAMES] == "rename/ascii_only"
    assert preferences.INI_KEYS[KEY_ZERO_PAD_NUMBERS] == "rename/zero_pad_enabled"
    assert preferences.INI_KEYS[KEY_ZERO_PAD_WIDTH] == "rename/zero_pad_width"
    assert preferences.INI_KEYS[KEY_BLANK_LANGUAGE_ENABLED] == "language/blank_default_enabled"
    assert preferences.INI_KEYS[KEY_DEFAULT_LANGUAGE] == "language/blank_default_code"
    assert preferences.INI_KEYS[preferences.KEY_ISFDB_DB] == "isfdb/database"
    assert preferences.INI_KEYS[preferences.KEY_ISFDB_BACKUP] == "isfdb/backup"


def test_dialog_shows_what_the_app_has_stored(tmp_path):
    app_settings.save_ascii_filenames(True)
    app_settings.save_rename_zero_pad(True, 4)
    app_settings.save_blank_language_default_enabled(False)
    app_settings.save_blank_language_default_code("de")
    app_settings.save_isfdb_database(str(tmp_path / "isfdb.db"))
    dialog = _dialog()
    assert dialog.value(KEY_ASCII_FILENAMES) is True
    assert dialog.value(KEY_ZERO_PAD_NUMBERS) is True and dialog.value(KEY_ZERO_PAD_WIDTH) == 4
    assert dialog.value(KEY_BLANK_LANGUAGE_ENABLED) is False
    assert dialog.value(KEY_DEFAULT_LANGUAGE) == "de"
    assert dialog.value(preferences.KEY_ISFDB_DB) == str(tmp_path / "isfdb.db")
    assert not dialog.is_row_enabled(KEY_DEFAULT_LANGUAGE)  # greyed while the switch is off


def test_defaults_match_the_apps_own_defaults():
    dialog = _dialog()
    assert dialog.value(KEY_ASCII_FILENAMES) is app_settings.load_ascii_filenames() is False
    assert (dialog.value(KEY_ZERO_PAD_NUMBERS), dialog.value(KEY_ZERO_PAD_WIDTH)) == app_settings.load_rename_zero_pad()
    assert dialog.value(KEY_BLANK_LANGUAGE_ENABLED) is True
    assert dialog.value(KEY_DEFAULT_LANGUAGE) == app_settings.DEFAULT_BLANK_LANGUAGE_CODE == "en"


def test_ok_writes_only_changed_keys_to_the_existing_ini_entries(tmp_path):
    calibre = tmp_path / "Calibre"
    calibre.mkdir()
    dialog = _dialog()
    dialog.set_value(KEY_ASCII_FILENAMES, True)
    dialog.set_value(KEY_ZERO_PAD_NUMBERS, True)
    dialog.set_value(KEY_ZERO_PAD_WIDTH, 3)
    dialog.set_value(KEY_DEFAULT_LANGUAGE, "fr")
    dialog.set_value(preferences.KEY_CALIBRE_DIR, str(calibre))
    dialog.set_value(preferences.KEY_OPENLIBRARY_DB, str(tmp_path / "ol.db"))
    assert KEY_BLANK_LANGUAGE_ENABLED not in dialog.changed_values()
    dialog.accept()
    assert app_settings.load_ascii_filenames() is True
    assert app_settings.load_rename_zero_pad() == (True, 3)
    assert app_settings.load_blank_language_default_code() == "fr"
    assert app_settings.load_blank_language_default_enabled() is True  # untouched
    assert app_settings.load_calibre_install_dir() == str(calibre)
    assert app_settings.load_open_library_database() == str(tmp_path / "ol.db")


def test_cancel_writes_nothing():
    dialog = _dialog()
    dialog.set_value(KEY_ASCII_FILENAMES, True)
    dialog.reject()
    assert app_settings.load_ascii_filenames() is False


def test_tool_and_dump_paths_round_trip(tmp_path):
    sigil = tmp_path / "sigil.exe"
    sigil.write_text("x")
    editions, authors, works = (str(tmp_path / n) for n in ("editions.txt.gz", "authors.txt.gz", "works.txt.gz"))
    dialog = _dialog()
    dialog.set_value(preferences.KEY_SIGIL_PATH, str(sigil))
    dialog.set_value(preferences.KEY_OPENLIBRARY_EDITIONS, editions)
    dialog.set_value(preferences.KEY_OPENLIBRARY_AUTHORS, authors)
    dialog.set_value(preferences.KEY_OPENLIBRARY_WORKS, works)
    dialog.accept()
    assert app_settings.load_sigil_path() == str(sigil)
    assert app_settings.load_open_library_sources() == (editions, authors)
    assert app_settings.load_open_library_works_dump() == works


def test_isfdb_database_and_backup_paths_round_trip(tmp_path):
    """The ISFDB database is configured like the Open Library one: Tools > ISFDB
    Database builds it, and Preferences > Tools and Paths shows and edits the path."""
    db, backup = str(tmp_path / "isfdb.db"), str(tmp_path / "backup.zip")
    dialog = _dialog()
    dialog.set_value(preferences.KEY_ISFDB_DB, db)
    dialog.set_value(preferences.KEY_ISFDB_BACKUP, backup)
    dialog.accept()
    assert app_settings.load_isfdb_database() == db
    assert app_settings.load_isfdb_backup() == backup


def test_the_language_list_is_the_apps_own_including_custom_ones():
    app_settings.add_custom_language("tlh", "Klingon")
    combo = _dialog().control(KEY_DEFAULT_LANGUAGE)
    assert isinstance(combo, QComboBox)
    assert "tlh" in [combo.itemData(i) for i in range(combo.count())]


def test_a_hand_edited_bad_value_falls_back_to_the_default():
    app_settings.write_settings({"rename/zero_pad_width": "banana"})
    dialog = _dialog()
    assert dialog.value(KEY_ZERO_PAD_WIDTH) == 2


# --- the window follows the dialog ----------------------------------------------------------


def test_applied_keys_update_the_live_window():
    window = mw.MainWindow()
    app_settings.save_blank_language_default_enabled(False)
    window._on_preferences_applied({KEY_BLANK_LANGUAGE_ENABLED: False})
    assert not window.set_default_language_act.isEnabled()


def test_open_preferences_connects_the_applied_signal(monkeypatch):
    window = mw.MainWindow()

    class _Fake(PreferencesDialog):
        def exec(self):
            self.set_value(KEY_BLANK_LANGUAGE_ENABLED, False)
            self.apply()
            return 1

    monkeypatch.setattr(preferences, "make_dialog", lambda parent=None: _Fake(
        preferences.build_sections(), preferences.make_backend(), parent))
    window.open_preferences()
    assert app_settings.load_blank_language_default_enabled() is False
    assert not window.set_default_language_act.isEnabled()  # the live handler ran on Apply
