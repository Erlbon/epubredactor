"""File > Export Settings / Import Settings: the adapter over app_settings'
QSettings ini (conftest points it at a temp file), and the menu wiring."""

import json
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(__file__))

import pytest  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

import gui.main_window as mw  # noqa: E402
from gui import app_settings  # noqa: E402
from gui.settings_adapter import EpubSettingsAdapter  # noqa: E402
from redactor_common.core import settings_bundle as sb  # noqa: E402
from redactor_common.gui.standard_menus import get_action_registry  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)

KEYS = mw.COLUMN_KEYS
PORTABLE = {"redact", "patterns", "field_defaults", "columns", "view", "lists", "covers"}
MACHINE = {"tools", "folders", "ereader"}


@pytest.fixture
def adapter():
    return EpubSettingsAdapter(KEYS)


def _everything(adapter):
    return {s.key for s in adapter.sections()}


def test_sections_split_portable_and_machine_specific(adapter):
    specs = {s.key: s.portable for s in adapter.sections()}
    assert {k for k, p in specs.items() if p} == PORTABLE
    assert {k for k, p in specs.items() if not p} == MACHINE
    assert sb.default_selection(adapter) == PORTABLE


def test_read_section_is_json_typed_and_complete(adapter):
    for key in _everything(adapter):
        items = adapter.read_section(key)
        assert items, key
        json.dumps(items)  # plain JSON types only
    fd = adapter.read_section("field_defaults")
    assert fd == {"blank_language_enabled": True, "blank_language_code": "en", "ascii_filenames": False,
                  "zero_pad_enabled": False, "zero_pad_width": 2}
    assert adapter.read_section("columns") == {"hidden": [], "widths": {}}
    assert adapter.read_section("view") == {"text_overflow_mode": "wrap"}


def test_types_survive_the_ini_round_trip(adapter):
    adapter.write_section("field_defaults", {
        "blank_language_enabled": False, "blank_language_code": "nb", "ascii_filenames": True,
        "zero_pad_enabled": True, "zero_pad_width": 3,
    })
    adapter.write_section("lists", {"custom_languages": [["tl", "Tlingit"]], "custom_genres": ["Saga"]})
    fd = adapter.read_section("field_defaults")
    assert fd["blank_language_enabled"] is False and fd["ascii_filenames"] is True
    assert fd["zero_pad_enabled"] is True and fd["zero_pad_width"] == 3 and isinstance(fd["zero_pad_width"], int)
    lists = adapter.read_section("lists")
    assert lists["custom_languages"] == [["tl", "Tlingit"]] and lists["custom_genres"] == ["Saga"]


def test_export_change_import_restores(adapter, tmp_path):
    app_settings.save_redact_recipe('{"steps": ["a"]}')
    app_settings.save_pattern_used("%author% - %title%")
    app_settings.save_text_overflow_mode("clip")
    app_settings.save_hidden_column_keys({"path", "status"})
    app_settings.save_column_widths_by_key({"filename": 222})
    app_settings.add_custom_genre("Saga")
    app_settings.hide_default_genre("Fantasy")
    app_settings.save_junk_cover_hashes({"abc"})
    app_settings.save_ascii_filenames(True)
    text = sb.dump_bundle(sb.build_bundle(adapter, sb.default_selection(adapter)))
    path = tmp_path / "epubredactor-settings.json"
    path.write_text(text, encoding="utf-8")

    # Change everything, then import.
    app_settings.save_redact_recipe("")
    app_settings.save_pattern_used("%title%")
    app_settings.save_text_overflow_mode("wrap")
    app_settings.save_hidden_column_keys(set())
    app_settings.save_column_widths_by_key({"filename": 10})
    app_settings.remove_custom_genre("Saga")
    app_settings.restore_default_genres()
    app_settings.save_junk_cover_hashes(set())
    app_settings.save_ascii_filenames(False)

    bundle = sb.parse_bundle(path.read_text(encoding="utf-8"), "epubredactor")
    result = sb.apply_bundle(adapter, bundle, PORTABLE)
    assert not result.failed and set(result.applied) == PORTABLE
    assert app_settings.load_redact_recipe() == '{"steps": ["a"]}'
    assert app_settings.load_pattern_history()[0] == "%author% - %title%"
    assert app_settings.load_text_overflow_mode() == "clip"
    assert app_settings.load_hidden_column_keys(KEYS) == {"path", "status"}
    assert app_settings.load_column_widths_by_key(KEYS) == {"filename": 222}
    assert app_settings.load_custom_genres() == ["Saga"]
    assert "Fantasy" in app_settings.load_hidden_default_genres()
    assert app_settings.load_junk_cover_hashes() == {"abc"}
    assert app_settings.load_ascii_filenames() is True
    assert sb.diff_bundle(adapter, bundle) == []


def test_machine_specific_is_excluded_by_default(adapter, tmp_path):
    app_settings.save_calibre_install_dir(str(tmp_path))
    app_settings.save_library_root("D:/Books")
    bundle = sb.build_bundle(adapter, sb.default_selection(adapter))
    assert not (set(bundle.sections) & MACHINE)
    text = sb.dump_bundle(bundle)
    assert str(tmp_path) not in text and "D:/Books" not in text


def test_machine_specific_opt_in_and_missing_paths_are_ignored(adapter, tmp_path):
    bundle = sb.build_bundle(adapter, MACHINE)
    bundle.sections["tools"].items.update({"calibre_install_dir": str(tmp_path), "sigil_path": "Z:/nope/sigil.exe"})
    bundle.sections["folders"].items["library_root"] = "D:/Books"
    sb.apply_bundle(adapter, bundle, MACHINE)
    assert app_settings.load_calibre_install_dir() == str(tmp_path)  # exists here
    assert app_settings.load_sigil_path() == ""  # doesn't exist here: skipped
    assert app_settings.load_library_root() == "D:/Books"


def test_invalid_values_are_skipped_and_unknown_keys_ignored(adapter):
    app_settings.save_text_overflow_mode("ellipsis")
    bundle = sb.Bundle(app="epubredactor", sections={
        "view": sb.BundleSection("View", {"text_overflow_mode": "sideways", "mystery": 1}),
        "columns": sb.BundleSection("Columns", {
            "hidden": ["path", "filename", "no_such_column"], "widths": {"path": -5, "status": 80, "zzz": 9},
        }),
        "field_defaults": sb.BundleSection("FD", {"zero_pad_width": "wide", "ascii_filenames": "yes"}),
        "not_a_section": sb.BundleSection("X", {"a": 1}),
    })
    sb.apply_bundle(adapter, bundle, _everything(adapter) | {"not_a_section"})
    assert app_settings.load_text_overflow_mode() == "ellipsis"
    assert app_settings.load_hidden_column_keys(KEYS) == {"path"}  # filename can't be hidden
    assert app_settings.load_column_widths_by_key(KEYS) == {"status": 80}
    assert adapter.read_section("field_defaults")["zero_pad_width"] == 2
    assert adapter.read_section("field_defaults")["ascii_filenames"] is False
    assert "mystery" not in adapter.read_section("view")


def test_writes_stay_inside_their_sections(adapter):
    app_settings.save_redact_recipe("keep-me")
    app_settings.save_library_root("D:/keep")
    adapter.write_section("view", {"text_overflow_mode": "clip"})
    adapter.write_section("lists", {"custom_genres": ["X"]})
    assert app_settings.load_redact_recipe() == "keep-me" and app_settings.load_library_root() == "D:/keep"


def test_secret_looking_keys_never_travel(adapter):
    class Leaky(EpubSettingsAdapter):
        def read_section(self, key):
            items = super().read_section(key)
            if key == "view":
                items["api_key"] = "sk-123"
            return items

    leaky = Leaky(KEYS)
    text = sb.dump_bundle(sb.build_bundle(leaky, {"view"}))
    assert "sk-123" not in text and "api_key" not in text
    bundle = sb.parse_bundle(text.replace('"view": {', '"view": {"api_key": "x",', 1), "epubredactor")
    assert "api_key" not in bundle.sections["view"].items


def test_file_for_another_app_is_rejected(adapter):
    text = json.dumps({"format": "redactor-settings", "version": 1, "app": "mp3redactor", "sections": {}})
    with pytest.raises(sb.SettingsBundleError):
        sb.parse_bundle(text, adapter.app_slug)


def test_menu_actions_present_enabled_and_invoke_the_dialogs(monkeypatch):
    calls = []
    monkeypatch.setattr(mw, "export_settings", lambda parent, adapter: calls.append(("export", adapter)))
    monkeypatch.setattr(
        mw, "import_settings",
        lambda parent, adapter, on_applied=None: calls.append(("import", adapter, on_applied)),
    )
    window = mw.MainWindow()
    registry = get_action_registry(window)
    for key in ("export_settings", "import_settings"):
        assert key in registry and registry[key].isEnabled()
        assert registry.path_of(key).startswith("File")
    registry["export_settings"].trigger()
    registry["import_settings"].trigger()
    assert [c[0] for c in calls] == ["export", "import"]
    assert isinstance(calls[0][1], EpubSettingsAdapter) and calls[1][2] == window._on_settings_imported


def test_import_refreshes_the_live_window():
    window = mw.MainWindow()
    app_settings.save_hidden_column_keys({"path"})
    app_settings.save_column_widths_by_key({"status": 123})
    app_settings.save_text_overflow_mode("clip")
    window._on_settings_imported(sb.ApplyResult(applied=["columns", "view"]))
    assert window.table.isColumnHidden(KEYS.index("path"))
    assert window.table.columnWidth(KEYS.index("status")) == 123
    assert window._text_overflow_mode == "clip"
    assert get_action_registry(window)["text_wrap_mode_clip"].isChecked()
