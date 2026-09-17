"""Tests for the Settings -> Enable Performance Logging wiring in
MainWindow: the toggle persists via app_settings and actually flips
core/perf_log.py's module-level flag, and a fresh MainWindow picks up
whatever was persisted from a previous session."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from PyQt6.QtWidgets import QApplication  # noqa: E402

import core.perf_log as perf_log  # noqa: E402
from gui import app_settings  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)


def _reset():
    app_settings.save_perf_logging_enabled(False)
    perf_log.set_enabled(False)


def test_disabled_by_default_on_a_fresh_window():
    _reset()
    window = MainWindow()
    assert not perf_log.is_enabled()
    assert not window.perf_logging_act.isChecked()
    print("PASS: a fresh MainWindow has performance logging disabled by default")


def test_toggling_enables_and_persists():
    _reset()
    window = MainWindow()
    window.perf_logging_act.setChecked(True)
    window.toggle_perf_logging()
    try:
        assert perf_log.is_enabled()
        assert app_settings.load_perf_logging_enabled()
    finally:
        _reset()
    print("PASS: checking the menu action enables logging and persists the setting")


def test_toggling_off_disables_and_persists():
    _reset()
    app_settings.save_perf_logging_enabled(True)
    window = MainWindow()
    assert window.perf_logging_act.isChecked()  # picked up the persisted "on" state
    assert perf_log.is_enabled()

    window.perf_logging_act.setChecked(False)
    window.toggle_perf_logging()
    try:
        assert not perf_log.is_enabled()
        assert not app_settings.load_perf_logging_enabled()
    finally:
        _reset()
    print("PASS: unchecking the menu action disables logging and persists that too")


def test_new_window_picks_up_a_previously_enabled_setting():
    _reset()
    app_settings.save_perf_logging_enabled(True)
    try:
        window = MainWindow()
        assert perf_log.is_enabled()
        assert window.perf_logging_act.isChecked()
    finally:
        _reset()
    print("PASS: a new MainWindow applies a previously-persisted enabled setting immediately, "
          "before any table rebuild happens")


if __name__ == "__main__":
    test_disabled_by_default_on_a_fresh_window()
    test_toggling_enables_and_persists()
    test_toggling_off_disables_and_persists()
    test_new_window_picks_up_a_previously_enabled_setting()
    print("\nALL PERF LOGGING WIRING TESTS PASSED")
