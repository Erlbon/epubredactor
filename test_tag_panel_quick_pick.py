"""
Genre/Language "+" pickers on redactor_common's QuickPickDialog
(2026-09-23) -- searchable and fixed-size, replacing flat QMenus that
overflowed the screen once enough custom genres piled up. Genre appends
(semicolon list), Language replaces.
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QDialog  # noqa: E402

import gui.tag_panel as tp  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)


def _accept_with(monkeypatch, keys):
    monkeypatch.setattr(tp.QuickPickDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(tp.QuickPickDialog, "selected_keys", lambda self: list(keys))


def test_genres_are_appended_and_the_field_ticked(monkeypatch):
    panel = tp.TagPanel()
    panel._set_editor_text(panel._editors["tags_str"], "Fantasy")
    _accept_with(monkeypatch, ["Horror", "Fantasy"])
    panel._pick_genres("tags_str")
    assert panel._editor_text(panel._editors["tags_str"]) == "Fantasy; Horror"
    assert panel._checkboxes["tags_str"].isChecked()


def test_language_replaces_the_field(monkeypatch):
    panel = tp.TagPanel()
    panel._set_editor_text(panel._editors["language"], "en")
    _accept_with(monkeypatch, ["nb"])
    panel._pick_language("language")
    assert panel._editor_text(panel._editors["language"]) == "nb"
