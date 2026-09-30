"""
gui/settings_adapter.py

File > Export Settings... / Import Settings...: the SettingsAdapter that
lets redactor_common's settings_bundle read and write this app's
QSettings ini (gui/app_settings.py). The file format, the diff/apply
logic and the dialogs are shared; this module only says which settings
exist, which are portable, and how to turn each into plain JSON and back.

QSettings hands lists, bools and ints back as strings in an ini file, so
every key is read with an explicit type and written only after validation.
A value that doesn't validate is skipped (the rest of the section still
applies), and nothing outside these sections is ever touched.

SECRETS: this app stores none. The shared guard (looks_secret) would drop
a credential-named key anyway.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from core.version import APP_VERSION
from gui import app_settings
from redactor_common.core import managed_list, pattern_history
from redactor_common.core import settings_bundle as sb

_PORTABLE_SECTIONS = [
    sb.SectionSpec("redact", "Redact recipe"),
    sb.SectionSpec("patterns", "Rename / export / parse pattern history"),
    sb.SectionSpec("field_defaults", "Field defaults (blank-language default, ASCII and zero-pad choices)"),
    sb.SectionSpec("columns", "Column visibility and widths"),
    sb.SectionSpec("view", "View options (text wrapping)"),
    sb.SectionSpec("lists", "Custom and hidden genres and languages"),
    sb.SectionSpec("covers", "Junk cover list"),
]
_MACHINE_SECTIONS = [
    sb.SectionSpec("tools", "External tool paths (Calibre, Sigil) - this computer only", portable=False),
    sb.SectionSpec("folders", "Last-used and library folders - this computer only", portable=False),
    sb.SectionSpec("ereader", "Send to eReader services - this computer only", portable=False),
]


def _text(settings, key: str, default: str = "") -> str:
    return str(settings.value(key, default, type=str) or "")


def _json_list(settings, key: str) -> list:
    """A list stored as JSON text; [] when missing or corrupt."""
    try:
        data = json.loads(_text(settings, key))
    except (ValueError, TypeError):
        return []
    return data if isinstance(data, list) else []


def _str_list(value: Any) -> list[str] | None:
    """A list of non-blank strings (blanks dropped), or None if `value` isn't a list of strings."""
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        return None
    return [v for v in value if v.strip()]


def _pair_list(value: Any) -> list[list[str]] | None:
    """[[code, name], ...] with both parts non-blank strings, or None if malformed."""
    if not isinstance(value, list):
        return None
    pairs = []
    for item in value:
        if not (isinstance(item, (list, tuple)) and len(item) == 2
                and all(isinstance(p, str) and p.strip() for p in item)):
            return None
        pairs.append([item[0], item[1]])
    return pairs


def _flag(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


class EpubSettingsAdapter(sb.SettingsAdapter):
    """`column_keys` is the table's logical column keys (MainWindow.COLUMN_KEYS);
    `redetect` is the optional callback behind "Re-detect tools" after an import."""

    app_slug = "epubredactor"
    app_version = APP_VERSION

    def __init__(self, column_keys: list[str], redetect: Callable[[], None] | None = None):
        self._column_keys = list(column_keys)
        if redetect is not None:
            self.redetect_tools = redetect

    def sections(self) -> list[sb.SectionSpec]:
        return _PORTABLE_SECTIONS + _MACHINE_SECTIONS

    # ------------------------------------------------------------------
    # Reading: every supported key, current value or default, as JSON types
    # ------------------------------------------------------------------

    def read_section(self, key: str) -> dict[str, Any]:
        s = app_settings._settings()
        if key == "redact":
            return {"recipe": _text(s, "redact/recipe")}
        if key == "patterns":
            return {"history": pattern_history.decode_history(_text(s, "rename/pattern_history"))}
        if key == "field_defaults":
            return {
                "blank_language_enabled": bool(s.value("language/blank_default_enabled", True, type=bool)),
                "blank_language_code": app_settings.load_blank_language_default_code(),
                "ascii_filenames": bool(s.value("rename/ascii_only", False, type=bool)),
                "zero_pad_enabled": bool(s.value("rename/zero_pad_enabled", False, type=bool)),
                "zero_pad_width": int(s.value("rename/zero_pad_width", 2, type=int)),
            }
        if key == "columns":
            return {
                "hidden": sorted(k for k in managed_list.decode_names(_text(s, "table/hidden_column_keys"))
                                 if k in self._column_keys),
                "widths": {k: w for k, w in app_settings._parse_column_widths_by_key(
                    _text(s, "table/column_widths_by_key")).items() if k in self._column_keys},
            }
        if key == "view":
            return {"text_overflow_mode": app_settings.load_text_overflow_mode()}
        if key == "lists":
            return {
                "custom_genres": managed_list.decode_names(_text(s, "genres/custom")),
                "hidden_default_genres": managed_list.decode_names(_text(s, "genres/hidden_defaults")),
                "custom_languages": [list(p) for p in
                                     managed_list.decode_pairs(_text(s, "languages/custom"))],
                "hidden_default_languages": managed_list.decode_names(_text(s, "languages/hidden_defaults")),
            }
        if key == "covers":
            return {"junk_hashes": sorted(app_settings._parse_junk_cover_hashes(_text(s, "covers/junk_hashes")))}
        if key == "tools":
            return {"calibre_install_dir": _text(s, "calibre/install_dir"), "sigil_path": _text(s, "sigil/exe_path")}
        if key == "folders":
            return {"last_directory": _text(s, "files/last_directory"), "library_root": _text(s, "move/library_root")}
        if key == "ereader":
            return {"servers": app_settings.load_ereader_servers()}
        raise KeyError(key)

    # ------------------------------------------------------------------
    # Writing: only known keys with valid values; anything else is skipped
    # ------------------------------------------------------------------

    def write_section(self, key: str, values: dict[str, Any]) -> None:
        s = app_settings._settings()
        if key == "redact":
            if isinstance(values.get("recipe"), str):
                app_settings.save_redact_recipe(values["recipe"])
        elif key == "patterns":
            history = _str_list(values.get("history"))
            if history is not None:
                s.setValue("rename/pattern_history",
                           pattern_history.encode_history(history[:app_settings._MAX_HISTORY]))
        elif key == "field_defaults":
            self._write_field_defaults(s, values)
        elif key == "columns":
            self._write_columns(s, values)
        elif key == "view":
            app_settings.save_text_overflow_mode(values.get("text_overflow_mode"))  # ignores unknown modes
        elif key == "lists":
            self._write_lists(s, values)
        elif key == "covers":
            hashes = _str_list(values.get("junk_hashes"))
            if hashes is not None:
                app_settings.save_junk_cover_hashes(set(hashes))
        elif key == "tools":
            # Both savers ignore a path that doesn't exist on this computer.
            if isinstance(values.get("calibre_install_dir"), str):
                app_settings.save_calibre_install_dir(values["calibre_install_dir"])
            if isinstance(values.get("sigil_path"), str):
                app_settings.save_sigil_path(values["sigil_path"])
        elif key == "folders":
            folder = values.get("last_directory")
            if isinstance(folder, str) and folder:
                app_settings.save_last_directory(folder)  # ignores a missing folder
            if isinstance(values.get("library_root"), str):
                app_settings.save_library_root(values["library_root"])
        elif key == "ereader":
            servers = _str_list(values.get("servers"))
            if servers:
                s.setValue("ereader/servers", json.dumps([u.strip().rstrip("/") for u in servers]))
        else:
            raise KeyError(key)

    @staticmethod
    def _write_field_defaults(s, values: dict[str, Any]) -> None:
        if _flag(values.get("blank_language_enabled")) is not None:
            app_settings.save_blank_language_default_enabled(values["blank_language_enabled"])
        if isinstance(values.get("blank_language_code"), str):
            app_settings.save_blank_language_default_code(values["blank_language_code"])
        if _flag(values.get("ascii_filenames")) is not None:
            app_settings.save_ascii_filenames(values["ascii_filenames"])
        if _flag(values.get("zero_pad_enabled")) is not None:
            s.setValue("rename/zero_pad_enabled", values["zero_pad_enabled"])
        width = values.get("zero_pad_width")
        if isinstance(width, int) and not isinstance(width, bool) and 1 <= width <= 10:
            s.setValue("rename/zero_pad_width", width)

    def _write_columns(self, s, values: dict[str, Any]) -> None:
        hidden = _str_list(values.get("hidden"))
        if hidden is not None:
            # The filename column can never be hidden (see open_column_settings_dialog).
            app_settings.save_hidden_column_keys({k for k in hidden if k in self._column_keys and k != "filename"})
        widths = values.get("widths")
        if isinstance(widths, dict):
            clean = {k: w for k, w in widths.items()
                     if k in self._column_keys and isinstance(w, int) and not isinstance(w, bool) and w > 0}
            app_settings.save_column_widths_by_key(clean)

    @staticmethod
    def _write_lists(s, values: dict[str, Any]) -> None:
        for field, setting in (("custom_genres", "genres/custom"),
                               ("hidden_default_genres", "genres/hidden_defaults"),
                               ("hidden_default_languages", "languages/hidden_defaults")):
            names = _str_list(values.get(field))
            if names is not None:
                s.setValue(setting, managed_list.encode_names(names))
        pairs = _pair_list(values.get("custom_languages"))
        if pairs is not None:
            s.setValue("languages/custom", managed_list.encode_pairs([(c, n) for c, n in pairs]))

