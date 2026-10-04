"""The menu bar follows redactor_common's standard menu skeleton
(File, Edit, View, Metadata, Repair, Send, Tools, Help): heading order, the
place of every old feature, that every action is connected, the toolbar and
the right-click menu."""

import os
import sys
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(__file__))

from PyQt6.QtGui import QAction  # noqa: E402
from PyQt6.QtWidgets import QApplication, QToolBar  # noqa: E402

import gui.main_window as mw  # noqa: E402
from redactor_common.core import labels  # noqa: E402
from redactor_common.gui.standard_menus import get_action_registry  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)


def _menus(window):
    return {labels.plain_label(a.text()): a.menu() for a in window.menuBar().actions()}


def _plain_items(menu):
    """Plain labels of a menu's entries; a separator is '-'."""
    return ["-" if a.isSeparator() else labels.plain_label(a.text()) for a in menu.actions()]


def _submenu(menu, name):
    return next(a.menu() for a in menu.actions() if not a.isSeparator() and labels.plain_label(a.text()) == name)


def test_headings_in_skeleton_order():
    window = mw.MainWindow()
    assert list(_menus(window)) == ["File", "Edit", "View", "Metadata", "Repair", "Send", "Tools", "Help"]


def test_menu_contents_and_order():
    m = _menus(mw.MainWindow())
    assert _plain_items(m["File"]) == [
        "Open Files", "Open Folder", "Import and Convert", "-",
        "Save As", "Save All", "-",
        "Rename File", "Undo Last Rename", "Rename / Export / Move", "-",
        "Read Book", "-",
        "Export Settings", "Import Settings", "-",
        "Remove from List", "Clear List", "Delete Files", "-",
        "Exit",
    ]
    assert _plain_items(m["Edit"]) == [
        "Undo", "Redo", "-", "Apply to 0 Selected", "-", "Redact", "Edit Redact Recipe", "-",
        "Search and Replace", "Change Case", "Filter List",
    ]
    assert _plain_items(m["View"]) == [
        "Show Metadata Panel", "-", "Zoom In", "Zoom Out", "Reset Zoom", "-",
        "Text Wrapping", "-", "Refresh List", "Command Palette",
    ]
    assert _plain_items(m["Metadata"]) == [
        "Parse Filename", "Scan File Content", "-", "Look Up", "-",
        "Suggest Genres", "Convert Author Sort", "Number Series", "-", "Cover",
    ]
    assert _plain_items(m["Repair"]) == [
        "Validate and Fix", "Rebuild Manifest", "Deduplicate Manifest IDs", "Repair Navigation", "Find Duplicates", "-",
        "Generate Table of Contents", "Detect Missing Spaces", "Strip HTML from Description", "Clean Up Authors", "-",
        "Polish Book", "Compress Images", "-", "Set Blank Language to Default",
    ]
    assert _plain_items(m["Send"]) == ["Send to Kobo (USB)", "Send to eReader (Wireless)", "Open in Sigil"]
    assert _plain_items(m["Tools"]) == [
        "Preferences", "-", "Open Library Database", "-", "Columns", "Genres", "Languages", "-",
        "Enable Performance Logging", "Open Performance Log",
    ]
    assert _plain_items(m["Help"])[:3] == ["Changelog", "Credits", "-"]
    assert _plain_items(m["Help"])[3].startswith("About ")


def test_submenus():
    m = _menus(mw.MainWindow())
    assert _plain_items(_submenu(m["Metadata"], "Look Up")) == ["Google Books", "Open Library", "Open Library (Local Database)", "Calibre"]
    assert _plain_items(_submenu(m["Metadata"], "Cover")) == [
        "Find Better Covers", "Generate Cover from Metadata", "Regenerate Junk Covers", "-",
        "Flag Cover as Junk", "Unflag Cover as Junk",
    ]
    assert [a.isCheckable() for a in _submenu(m["View"], "Text Wrapping").actions()] == [True] * 3


# Every action the old menus had, by its old key, and the key it has now
# (the standard helpers dictate the new names of the shared ones).
OLD_TO_NEW_KEYS = {
    "load_files": "open_files", "load_folder": "open_folder", "save": "save_all", "save_as": "save_as",
    "rename_file": "rename_file", "undo_rename": "undo_last_rename",
    "rename_files": "rename_export_move", "export_settings": "export_settings",
    "import_settings": "import_settings", "remove_files": "remove_from_list",
    "delete_files": "delete_files", "refresh": "refresh_list", "clear": "clear_list", "exit": "exit",
    "import_from_filename": "import_from_filename", "import_google_books": "import_google_books",
    "import_file_content": "import_file_content", "suggest_genres": "suggest_genres",
    "import_open_library": "import_open_library", "import_calibre": "import_calibre",
    "import_to_epub": "import_convert", "apply_bulk_edit": "apply", "redact": "redact",
    "redact_recipe": "redact_recipe", "case_conversion": "change_case",
    "author_sort_convert": "author_sort_convert", "number_series": "number_series",
    "generate_cover": "generate_cover", "find_better_covers": "find_better_covers",
    "regenerate_junk_covers": "regenerate_junk_covers", "search_replace": "search_replace",
    "polish_book": "polish_book", "compress_images_lossy": "compress_images_lossy",
    "undo": "undo", "redo": "redo", "column_settings": "columns", "language_settings": "languages",
    "genre_settings": "genres", "blank_language_default": "preferences",  # folded into Tools > Preferences > Language
    "text_wrap_mode_wrap": "text_wrap_mode_wrap", "text_wrap_mode_ellipsis": "text_wrap_mode_ellipsis",
    "text_wrap_mode_clip": "text_wrap_mode_clip", "perf_logging": "perf_logging",
    "open_perf_log": "open_perf_log", "about": "about", "changelog": "changelog", "credits": "credits",
    "validate": "validate", "rebuild_manifest": "rebuild_manifest",
    "dedupe_manifest_ids": "dedupe_manifest_ids", "repair_navigation": "repair_navigation",
    "find_duplicates": "find_duplicates",  # new: Repair > Find Duplicates
    "generate_toc": "generate_toc", "missing_space": "missing_space",
    "strip_description_html": "strip_description_html", "clean_authors": "clean_authors", "set_default_language": "set_default_language",
    "send_to_kobo_usb": "send_to_kobo_usb", "send_to_ereader": "send_to_ereader",
    "open_sigil": "open_sigil",  # was context-menu only
    "flag_junk_cover": "flag_junk_cover", "unflag_junk_cover": "unflag_junk_cover",  # likewise
}


def test_every_old_action_is_still_reachable():
    registry = get_action_registry(mw.MainWindow())
    for old, new in OLD_TO_NEW_KEYS.items():
        assert new in registry, f"{old} -> {new} missing"
        assert registry.path_of(new), f"{new} is in no menu"


def test_every_action_is_owned_and_shared_with_the_window():
    window = mw.MainWindow()
    registry = get_action_registry(window)
    for entry in registry.entries():
        # Invoking each action would open dialogs, so check ownership only:
        # the registry holds a real QAction parented to the window.
        assert entry.action.parent() is window
    # The attributes the rest of the window uses are the registry's objects.
    assert window.save_act is registry["save_all"]
    assert window.load_files_act is registry["open_files"]
    assert window.rename_files_act is registry["rename_export_move"]


def _keys(action):
    return [s.toString() for s in action.shortcuts()]


def test_save_all_is_save_files_renamed_and_keeps_ctrl_s_as_an_alias():
    window = mw.MainWindow()
    registry = get_action_registry(window)
    assert "save" not in registry  # there is no save-selected to offer
    assert labels.plain_label(window.save_act.text()) == "Save All"
    assert _keys(window.save_act) == ["Ctrl+Shift+A", "Ctrl+S"]


def test_shortcut_fixes_and_their_aliases():
    registry = get_action_registry(mw.MainWindow())
    assert _keys(registry["delete_files"]) == ["Shift+Del", "F8"]
    assert _keys(registry["about"]) == []  # F1 is Help contents, never About
    assert _keys(registry["refresh_list"]) == ["F5", "Ctrl+R"]
    assert _keys(registry["command_palette"]) == ["Ctrl+K"]
    assert _keys(registry["filter_list"]) == ["Ctrl+F"]
    assert _keys(registry["reset_zoom"]) == ["Ctrl+0"]
    assert _keys(registry["preferences"]) == ["Ctrl+,"]


def test_zoom_keys_are_owned_by_the_menu_not_ambiguous_with_the_toolbar():
    window = mw.MainWindow()
    registry = get_action_registry(window)
    assert "Ctrl++" in _keys(registry["zoom_in"]) and "Ctrl+-" in _keys(registry["zoom_out"])
    assert window.zoom.zoom_in_action.shortcuts() == [] and window.zoom.zoom_out_action.shortcuts() == []
    # No key is bound to two actions anywhere on the window.
    from collections import Counter
    bound = Counter(k for a in window.findChildren(QAction) for k in _keys(a))
    assert [k for k, n in bound.items() if n > 1] == []
    # The menu action still zooms.
    before = window.table.font().pointSize()
    registry["zoom_in"].trigger()
    assert window.table.font().pointSize() == before + 1


def test_no_dead_planned_entries():
    registry = get_action_registry(mw.MainWindow())
    for key in ("auto_number",):
        assert key not in registry
    # Only state-dependent actions may start greyed out.
    greyed = {e.key for e in registry.entries() if not e.action.isEnabled()}
    assert greyed <= {"undo", "redo", "apply", "set_default_language"}


def test_filter_list_focuses_the_toolbar_box():
    window = mw.MainWindow()
    window.show()
    window.activateWindow()
    _app.processEvents()
    get_action_registry(window)["filter_list"].trigger()
    assert window.filter_edit.hasFocus() or window.focusWidget() is window.filter_edit
    window.close()


def test_show_metadata_panel_tracks_the_panel():
    window = mw.MainWindow()
    window.show()  # the splitter only has real sizes once shown
    _app.processEvents()
    act = get_action_registry(window)["show_metadata_panel"]
    assert act.isChecked()
    act.trigger()
    assert window._panel_collapser.is_collapsed() and not act.isChecked()
    window.toggle_tag_panel()  # the toolbar button
    assert act.isChecked()


def test_apply_text_follows_the_selection_count():
    window = mw.MainWindow()
    window._on_tag_panel_selection_count_changed(3)
    assert window.apply_bulk_edit_act.text() == "&Apply to 3 Selected"
    assert window.apply_bulk_edit_act.isEnabled()
    window._on_tag_panel_selection_count_changed(0)
    assert not window.apply_bulk_edit_act.isEnabled()


def test_toolbar():
    window = mw.MainWindow()
    bar = window.findChildren(QToolBar)[0]
    texts = [labels.plain_label(a.text()) for a in bar.actions() if not a.isSeparator() and a.text()]
    assert texts[:7] == [
        "Open Files", "Open Folder", "Save All", "Apply to 0 Selected", "Redact", "Undo", "Redo",
    ]
    assert window.redact_act in bar.actions()


def _names(entries):
    out = []
    for i in entries:
        if isinstance(i, mw.Separator):
            out.append("-")
        elif isinstance(i, mw.Submenu):
            out.append(labels.plain_label(i.text) + ">")
        else:
            out.append(labels.plain_label(i.text if isinstance(i, mw.MenuAction) else i.text()))
    return out


def test_context_menu():
    window = mw.MainWindow()
    book = SimpleNamespace(load_error=None, cover_hash=None)  # all the menu looks at
    items = window._context_menu_items([book])

    assert _names(items) == [
        "-", "Rename File", "-", "Look Up>", "Read Book", "Organize>", "Cover>", "-",
        "Redact", "Validate and Fix", "Open in Sigil", "Send to>", "-",
        "Remove from List", "Delete Files",
    ]

    def sub(name):
        return next(i for i in items if isinstance(i, mw.Submenu) and labels.plain_label(i.text) == name)

    assert _names(sub("Organize").items) == ["Rename / Export / Move", "Number Series"]
    assert _names(sub("Send to").items) == ["Kobo (USB)", "eReader (Wireless)"]
    assert _names(sub("Cover").items) == ["Find Better Covers"]  # no cover on this book: nothing to flag
    # Several books: no single-file rename.
    assert "Rename File" not in _names(window._context_menu_items([book, book]))


# --- lint + command palette -------------------------------------------------

# Violations lint_menu_bar() is allowed to report on the real window, each
# with the reason it is still there. Empty = fully conforming.
DOCUMENTED_LINT_EXCEPTIONS: list[str] = []


def test_lint_menu_bar_is_clean():
    from redactor_common.gui.menu_lint import lint_menu_bar

    assert lint_menu_bar(mw.MainWindow()) == DOCUMENTED_LINT_EXCEPTIONS


def test_command_palette_lists_every_action_and_runs_one():
    window = mw.MainWindow()
    registry = get_action_registry(window)
    palette = window.command_palette
    palette.show_palette()
    titles = {c.title for c in palette.visible_commands()}
    assert {"Open Files", "Redact", "Validate and Fix", "Open in Sigil", "Scan File Content"} <= titles
    palette.filter_edit.setText("refresh")
    assert [c.title for c in palette.visible_commands()][0] == "Refresh List"
    assert registry["command_palette"].shortcut().toString() == "Ctrl+K"
    palette.close()
