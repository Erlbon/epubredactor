"""The Include Subfolders checkbox on the main toolbar (right after Open Folder) mirrors File > Include
Subfolders both ways, and there is still exactly one saved setting."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from PyQt6.QtWidgets import QApplication, QToolBar  # noqa: E402

import gui.app_settings as app_settings  # noqa: E402
import gui.main_window as mw  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)


def _window(monkeypatch, start: bool):
    store = {"on": start}
    monkeypatch.setattr(app_settings, "load_include_subfolders", lambda: store["on"])
    monkeypatch.setattr(app_settings, "save_include_subfolders", lambda on: store.__setitem__("on", bool(on)))
    return mw.MainWindow(), store


def test_checkbox_sits_right_after_open_folder(monkeypatch):
    w, _store = _window(monkeypatch, True)
    tb = w.findChildren(QToolBar)[0]
    acts = tb.actions()
    nxt = acts[acts.index(w.load_folder_act) + 1]
    assert tb.widgetForAction(nxt) is w.include_subfolders_box


def test_checkbox_mirrors_saved_setting_at_start(monkeypatch):
    for start in (True, False):
        w, _store = _window(monkeypatch, start)
        assert w.include_subfolders_box.isChecked() is start
        assert w.include_subfolders_act.isChecked() is start


def test_checkbox_and_menu_action_stay_in_step(monkeypatch):
    w, store = _window(monkeypatch, True)
    w.include_subfolders_box.setChecked(False)
    assert not w.include_subfolders_act.isChecked() and store["on"] is False
    w.include_subfolders_act.setChecked(True)
    assert w.include_subfolders_box.isChecked() and store["on"] is True
