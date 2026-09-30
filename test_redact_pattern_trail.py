"""Redact pattern trail: a saved recipe keeps the pattern saved in it, an empty
one follows the app's current pattern, and the first save pins today's
patterns. Also the editor's caption / suggestions (offscreen)."""

import json
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(__file__))

from PyQt6.QtWidgets import QApplication, QComboBox, QDialog, QFormLayout  # noqa: E402

import gui.main_window as mw  # noqa: E402
from core.redact_steps import (  # noqa: E402
    DEFAULT_PATH_PATTERN,
    RenameStep,
    build_catalogue,
    pin_pattern_options,
    recipe_from_setting,
    recipe_to_setting,
)
from gui import app_settings  # noqa: E402
from redactor_common.core.pipeline import Recipe, run_recipe  # noqa: E402
from redactor_common.gui.redact_dialog import RecipeEditorDialog  # noqa: E402
from core.redact_steps import EpubCtx, recipe_for_run, run_catalogue, save_finalize  # noqa: E402
from test_redact_steps import env, load, make_epub, only, trash  # noqa: E402,F401  (env/trash are fixtures)

_app = QApplication.instance() or QApplication(sys.argv)


def _run(books, env, recipe, rename_pattern="", path_pattern=""):
    env.begin()
    report = run_recipe(
        books, recipe_for_run(recipe), run_catalogue(rename_pattern, path_pattern),
        lambda b: EpubCtx(b, env), describe=lambda b: os.path.basename(b.path),
        finalize=save_finalize, finalize_label="Save",
    )
    env.flush_log()
    return report


def test_every_pattern_option_has_a_trail_and_an_empty_default():
    cat = build_catalogue("%title%", "%authors%/%title%", history=lambda: ["%title%"])
    for key in ("rename", "move_into_folders", "path_tags"):
        spec = next(s for s in cat if s.key == key).options[0]
        assert spec.default == "" and spec.suggestions() == ["%title%"]
        assert spec.fallback_label and spec.fallback() and spec.preview(spec.fallback())
    assert next(s for s in cat if s.key == "rename").options[0].fallback() == "%title%"
    assert next(s for s in cat if s.key == "path_tags").options[0].fallback() == "%authors%/%title%"
    bare = build_catalogue()  # no history: folder steps use the built-in pattern, rename has none
    assert next(s for s in bare if s.key == "move_into_folders").options[0].fallback() == DEFAULT_PATH_PATTERN
    assert next(s for s in bare if s.key == "rename").options[0].fallback() == ""


def test_preview_uses_the_sample_and_never_raises():
    def boom():
        raise RuntimeError("no sample")

    spec = next(s for s in build_catalogue(sample=boom) if s.key == "rename").options[0]
    assert spec.preview("%authors% - %title%") == "Jane Author - The Long Way Home.epub"
    spec = next(s for s in build_catalogue(sample=lambda: {"title": "T", "authors": "A"}) if s.key == "move_into_folders").options[0]
    assert spec.preview("%authors%/%title%") == "A/T.epub"


def test_stored_pattern_wins_and_empty_follows_the_fallback(tmp_path, env):
    a = make_epub(str(tmp_path / "a.epub"))
    recipe = only("rename", options={"rename": {"pattern": "%title%"}})
    _run([load(a)], env, recipe, rename_pattern="%authors% - %title%")
    assert os.path.exists(tmp_path / "Test Book.epub")  # stored %title% beat the app's pattern

    b = make_epub(str(tmp_path / "b.epub"))
    _run([load(b)], env, only("rename", options={"rename": {"pattern": ""}}), rename_pattern="%authors% - %title%")
    assert os.path.exists(tmp_path / "Jane Doe - Test Book.epub")  # empty followed the fallback


def test_first_save_pins_so_later_pattern_changes_do_not_steer(tmp_path, env):
    cat = build_catalogue("%title%", "%authors%/%title%")
    pinned = pin_pattern_options(Recipe.default_for(cat), cat)
    assert pinned.options["rename"]["pattern"] == "%title%"
    assert pinned.options["path_tags"]["pattern"] == "%authors%/%title%"
    assert pinned.options["move_into_folders"]["pattern"] == "%authors%/%title%"
    saved = recipe_from_setting(recipe_to_setting(pinned), cat)
    saved.enabled["rename"] = True
    path = make_epub(str(tmp_path / "orig.epub"))
    # the app's Rename pattern changed afterwards: the stored recipe still renames by %title%
    _run([load(path)], env, only("rename", options=saved.options), rename_pattern="%authors% - %title%")
    assert os.path.exists(tmp_path / "Test Book.epub")
    assert not os.path.exists(tmp_path / "Jane Doe - Test Book.epub")


def test_pinning_leaves_stored_values_and_skips_empty_fallbacks():
    cat = build_catalogue("", "")
    recipe = Recipe.default_for(cat)
    recipe.options["move_into_folders"]["pattern"] = "%title%"
    pinned = pin_pattern_options(recipe, cat)
    assert pinned.options["move_into_folders"]["pattern"] == "%title%"
    assert pinned.options["rename"]["pattern"] == ""  # nothing to pin: no rename pattern exists yet
    assert recipe.options["path_tags"]["pattern"] == ""  # the input is not modified


def test_old_recipe_json_loads_unchanged():
    text = json.dumps({"order": ["rename"], "enabled": {"rename": True},
                       "options": {"rename": {"pattern": "%title%"}, "path_tags": {"pattern": ""}}})
    cat = build_catalogue("%authors%", "%authors%/%title%")
    recipe = recipe_from_setting(text, cat)
    resolved = {s.key: o for s, o in recipe.resolve(cat)}
    assert resolved["rename"]["pattern"] == "%title%"
    assert resolved["path_tags"]["pattern"] == ""  # still follows
    assert recipe_to_setting(recipe) == json.dumps(recipe.to_dict(), separators=(",", ":"))


def _row(dlg):
    return dlg.options_form.itemAt(0, QFormLayout.ItemRole.FieldRole).widget()


def test_editor_shows_caption_suggestions_and_preview():
    step = RenameStep("%title%", history=lambda: ["%authors%/%title%", "%authors% - %title%", "%title%"])
    dlg = RecipeEditorDialog([step], Recipe.default_for([step]))
    combo = dlg.options_host.findChild(QComboBox)
    assert [combo.itemText(i) for i in range(combo.count())] == ["%authors% - %title%", "%title%", "%authors%/%title%"]
    row = _row(dlg)
    assert row.caption.text() == "In effect: %title% — follows: the last Rename/Export pattern"
    assert row.preview.text() == "Preview: The Long Way Home.epub"
    combo.setCurrentText("%authors% - %title%")
    assert row.caption.text() == "In effect: %authors% - %title% — set in this recipe"
    row.use_fallback.click()
    assert combo.currentText() == "" and "follows:" in row.caption.text()


def test_edit_recipe_first_save_pins_then_keeps_the_typed_value(monkeypatch):
    app_settings.save_redact_recipe("")
    app_settings.save_pattern_used("%authors% - %title%")
    window = mw.MainWindow()
    seen = []

    def fake_exec(self):
        seen.append(self.recipe())
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(mw.RecipeEditorDialog, "exec", fake_exec)
    window.edit_redact_recipe()
    assert seen[0].options["rename"]["pattern"] == "%authors% - %title%"  # pre-filled, OK pinned it
    assert recipe_from_setting(app_settings.load_redact_recipe(), window._redact_catalogue()).options["rename"]["pattern"] == "%authors% - %title%"

    app_settings.save_pattern_used("%title%")  # the app's pattern moves on
    window.edit_redact_recipe()  # already saved: no re-pinning, stored value kept
    assert seen[1].options["rename"]["pattern"] == "%authors% - %title%"
