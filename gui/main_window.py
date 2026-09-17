"""
gui/main_window.py

Top-level window. Layout mirrors mp3tag's classic 3-part feel:

  [ toolbar: add / remove / save / undo / search actions, filter box ]
  [ tag panel (left) | file table (right, most of the space) ]
  [ status bar: credit line (left)  ...  N books loaded (right) ]

Editing model:
  - Editing a cell directly in the table changes just that one book
    (handy for single one-off fixes).
  - Selecting multiple rows and using the Tag Panel's checkboxes +
    "Apply to N selected" stages the same value across all of them.
  - Nothing touches disk until you click Save. Save Changed overwrites
    originals; Save As Copies writes to a folder you choose so your
    originals are never touched.
  - Undo (last 5 changes) covers in-memory edits only -- see
    core/undo.py for why physical file operations (Rename/Export, Save)
    are deliberately excluded.

Row <-> book mapping: the table can be sorted by clicking any column
header (and columns can be dragged to reorder), both of which move rows
independent of self.books' list order. So a book is never looked up by
row index into self.books -- instead, each row's filename item carries a
direct reference to its EpubBook via Qt.ItemDataRole.UserRole (see
_book_for_row / _books_for_rows). That mapping travels with the item
regardless of where sorting/reordering puts the row.
"""

from __future__ import annotations

import copy
import mimetypes
import os
import sys
import traceback
import webbrowser

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QActionGroup, QColor, QGuiApplication, QIcon, QKeySequence
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListView,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from core.epub_metadata import EpubBook, EpubError
from core.fields import FIELDS, NUMERIC_FIELD_KEYS
from core import perf_log
from core.languages import is_blank_or_unknown_language
from core.rename_pattern import rename_book_file, render_filename, unique_path
from core.sigil_tools import DOWNLOAD_URL as SIGIL_DOWNLOAD_URL
from core.sigil_tools import SigilLaunchError, find_sigil
from core.sigil_tools import open_in_sigil as launch_sigil
from core.version import APP_NAME, APP_REPO_URL, APP_VERSION, RELEASE_LABEL
from redactor_common.core.error_summary import summarize_errors
from redactor_common.core.os_utils import reveal_in_file_manager
from redactor_common.core.save_errors import describe_save_error
from redactor_common.core.undo import UndoManager
from redactor_common.gui.action_factory import make_action
from redactor_common.gui.progress import run_with_progress
from redactor_common.gui.async_hash_cache import AsyncHashCache
from redactor_common.gui.async_icon_cache import AsyncIconCache
from redactor_common.gui.quick_series_number import prompt_and_generate_series_numbers
from redactor_common.gui.menu_builder import MenuAction, MenuItems, Separator, Submenu, build_menu_bar
from redactor_common.gui.overwrite_review_dialog import resolve_overwrite_conflicts
from redactor_common.gui.colors import (
    DIRTY_COLOR, ERROR_COLOR, SAVE_FAILED_COLOR, DRM_COLOR, HIGHLIGHT_TEXT_COLOR,
    TABLE_SELECTION_STYLESHEET,
)
from redactor_common.gui.context_menu import show_table_context_menu
from redactor_common.gui.column_menu import show_column_header_context_menu
from redactor_common.gui.collapsible_splitter import SplitterPaneCollapser
from redactor_common.gui import standard_shortcuts as shortcuts
from gui import app_settings
from redactor_common.gui.about_dialog import AboutDialog, ChangelogDialog, CreditsDialog
from redactor_common.core.version import REDACTOR_COMMON_REPO_URL, REDACTOR_COMMON_VERSION
from gui.author_sort_dialog import AuthorSortDialog
from gui.blank_language_default_dialog import BlankLanguageDefaultDialog
from gui.calibre_lookup_dialog import CalibreLookupDialog
from gui.case_conversion_dialog import CaseConversionDialog
from gui.column_settings_dialog import ColumnSettingsDialog
from gui.compress_images_dialog import CompressImagesDialog, format_size
from gui.content_scan_dialog import ContentScanDialog
from gui.cover_generator_dialog import CoverGeneratorDialog
from gui.cover_render import generate_cover_image
from gui.ebook_convert_dialog import EbookConvertDialog
from gui.filename_parse_dialog import FilenameParseDialog
from gui.google_books_dialog import GoogleBooksDialog
from gui.image_compress import recompress_jpeg
from gui.manage_list_dialog import ManageListDialog
from gui.manifest_rebuild_dialog import ManifestRebuildDialog
from gui.missing_space_dialog import MissingSpaceDialog
from gui.nav_repair_dialog import NavRepairDialog
from gui.open_library_dialog import OpenLibraryDialog
from gui.polish_book_dialog import PolishBookDialog
from gui.rename_dialog import RenameDialog
from gui.search_replace_dialog import FILENAME_FIELD_KEY, SearchReplaceDialog
from gui.series_number_dialog import SeriesNumberDialog
from gui.send_to_ereader_dialog import SendToEreaderDialog
from gui.send_to_kobo_dialog import SendToKoboDialog
from gui.strip_description_html_dialog import StripDescriptionHtmlDialog
from gui.tag_panel import TagPanel
from gui.validation_dialog import ValidationDialog

try:
    import send2trash
except ImportError:  # pragma: no cover -- exercised only on a real install
    send2trash = None

PATH_COL = 0
FILENAME_COL = 1
STATUS_COL = 2
FIRST_FIELD_COL = 3
# Junk Cover is appended AFTER every FIELDS column, deliberately, rather
# than being inserted among the other fixed columns -- both column
# widths and hidden-columns are persisted keyed by logical index (see
# app_settings.load_column_widths/load_hidden_columns), so slotting a
# new column in earlier would shift every FIELDS column's saved index
# out from under existing users' settings on upgrade.
JUNK_COVER_COL = FIRST_FIELD_COL + len(FIELDS)
# Colors now live in redactor_common.gui.colors -- this project's own
# scheme became the shared standard (mp3/video had each picked their
# own row-tint/selection colors independently). See that module's
# docstring for the light-background/dark-text rationale. Junk Cover
# is purely a local, app-side flag (never written to the EPUB, no
# equivalent concept in the sibling projects), so its color stays local
# too rather than joining the shared palette.
STATUS_CELL_COLORS = {"OK": None, "ISSUES": DIRTY_COLOR, "DRM": DRM_COLOR, "INVALID": ERROR_COLOR}
JUNK_COVER_COLOR = QColor("#f3d9fa")  # soft magenta -- distinct from the shared status colors
COVER_ICON_SIZE = QSize(24, 32)
UNDO_MAX_ENTRIES = 5
LOAD_PROGRESS_THRESHOLD = 3  # don't bother with a progress dialog for a tiny batch
# Populating each row is much cheaper than loading a whole book from
# disk, so this threshold is deliberately much higher than the one
# above -- a progress dialog for a routine rebuild of a few dozen rows
# would just flicker in and out uselessly. Genuinely large libraries
# (thousands of rows) are where an uninterrupted rebuild loop can run
# long enough to look exactly like a frozen app with no feedback at all.
REBUILD_PROGRESS_THRESHOLD = 500
TABLE_ZOOM_MIN_PT = 6
TABLE_ZOOM_MAX_PT = 20
TAG_PANEL_COLLAPSED_WIDTH = 32  # slim strip, not zero -- keeps the panel's own toggle button reachable

IMAGE_FILE_FILTER = "Images (*.jpg *.jpeg *.png *.gif *.webp)"

# For redactor_common.gui.overwrite_review_dialog.resolve_overwrite_conflicts()'s
# per-field review table -- same name/shape as cbzredactor's own
# _FIELD_LABELS/_field_label, the project this was promoted from.
_FIELD_LABELS = {key: label for key, label, _multiline in FIELDS}


def _field_label(key: str) -> str:
    return _FIELD_LABELS.get(key, key.replace("_", " ").title())


def resource_path(*parts: str) -> str:
    """Resolve a bundled asset path, working both when run from source
    and when packaged by PyInstaller (which unpacks assets into a temp
    dir referenced by sys._MEIPASS at runtime)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, *parts)


class NumericTableWidgetItem(QTableWidgetItem):
    """Sorts numerically when both sides parse as numbers (so "9" sorts
    before "10"), falling back to normal text sorting otherwise (so a
    blank or non-numeric cell doesn't crash the comparison)."""

    def __lt__(self, other):
        try:
            return float(self.text()) < float(other.text())
        except (ValueError, TypeError):
            return super().__lt__(other)


class BookTableWidget(QTableWidget):
    """QTableWidget with spreadsheet-style keyboard navigation:
    Tab/Shift+Tab move horizontally (wrapping to the next/previous row at
    the ends), Enter/Return moves down one row in the same column. Left
    to Qt's own defaults: plain arrow keys (already move the current
    cell), and editing behavior (double-click or F2 to start, which
    still auto-commits via the standard delegate when the current cell
    changes)."""

    def keyPressEvent(self, event) -> None:
        key = event.key()
        row, col = self.currentRow(), self.currentColumn()

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if row < self.rowCount() - 1:
                self.setCurrentCell(row + 1, col)
            event.accept()
            return

        if key == Qt.Key.Key_Tab:
            if col < self.columnCount() - 1:
                self.setCurrentCell(row, col + 1)
            elif row < self.rowCount() - 1:
                self.setCurrentCell(row + 1, 0)
            event.accept()
            return

        if key == Qt.Key.Key_Backtab:  # Shift+Tab
            if col > 0:
                self.setCurrentCell(row, col - 1)
            elif row > 0:
                self.setCurrentCell(row - 1, self.columnCount() - 1)
            event.accept()
            return

        super().keyPressEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # Applied first, before anything else below runs, so a session
        # that had this left on from before captures the very first
        # table rebuild too -- see core/perf_log.py and Settings ->
        # Enable Performance Logging.
        perf_log.set_enabled(app_settings.load_perf_logging_enabled())
        self.setWindowTitle(f"{APP_NAME} ({APP_VERSION})")
        self.resize(1280, 760)
        self._center_on_screen()
        icon_path = resource_path("assets", "icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.books: list[EpubBook] = []
        self._updating_table = False
        self.undo_manager = UndoManager(max_entries=UNDO_MAX_ENTRIES)
        self._cover_icon_cache = AsyncIconCache(COVER_ICON_SIZE, parent=self)
        self._cover_icon_cache.icon_ready.connect(self._on_cover_icon_ready)
        # book -> its current FILENAME_COL QTableWidgetItem, rebuilt fresh
        # in _rebuild_table() and kept in sync by _populate_row() -- lets
        # _on_cover_icon_ready() apply an async decode result in O(1)
        # instead of _find_row_for_book()'s O(row count) scan. That scan
        # is fine for an occasional single-book lookup (still used by
        # _refresh_row_full()), but _on_cover_icon_ready() fires once PER
        # BOOK as each background decode completes -- for a large library
        # that's thousands of independent O(row count) scans in a burst
        # right after loading, an O(n^2) cost that dominated "Updating
        # list" time for anything but a small library.
        self._filename_item_by_book: dict[EpubBook, QTableWidgetItem] = {}
        self._perf_accum = perf_log.Accumulator()  # real one created fresh per rebuild; this is just a safe default
        self._cover_hash_cache = AsyncHashCache(parent=self)
        self._cover_hash_cache.hash_ready.connect(self._on_cover_hash_ready)
        # book -> its current JUNK_COVER_COL QTableWidgetItem -- same
        # reasoning and same lifecycle as _filename_item_by_book above,
        # for the same reason: computing a book's cover_hash (needed for
        # the Junk Cover check) is real SHA-256 work over the full cover
        # image, once per book, every table rebuild -- for a large
        # library with real cover art that was several real seconds of
        # synchronous hashing, found profiling a reported "Updating list
        # is still slow" regression after the O(n^2) row-lookup fix
        # above had already landed. AsyncHashCache moves the hash itself
        # off the main thread the same way AsyncIconCache already does
        # for cover decoding.
        self._junk_cover_item_by_book: dict[EpubBook, QTableWidgetItem] = {}
        # Cached in memory rather than re-reading app_settings on every
        # row paint (_populate_row runs once per book, potentially
        # thousands of times per rebuild) -- reloaded from disk only when
        # actually needed, at startup. Kept current afterward by
        # flag_selected_covers_as_junk/unflag_selected_covers_as_junk,
        # the only things that ever change it.
        self._junk_cover_hashes: set[str] = app_settings.load_junk_cover_hashes()

        self._build_ui()
        self.setAcceptDrops(True)
        self._refresh_status()
        QTimer.singleShot(0, self._restore_last_session)
        # _show_beta_warning is intentionally not scheduled for now: it
        # could steal focus from an "include subfolders?" prompt shown by
        # a startup action running around the same time, since both are
        # modal popups competing to grab attention right as the window
        # first appears. The method is left in place below in case this
        # notice comes back later, just not shown automatically.

    def _restore_last_session(self) -> None:
        """Reopens whatever was loaded when the app was last closed --
        deferred via QTimer.singleShot(0, ...) so it runs after the
        window is already visible, rather than delaying the window's own
        first paint while a potentially large session loads. Silently
        skips any remembered path that no longer exists (moved or
        deleted since last time) rather than showing it as a load-error
        row -- that's a different, more mundane situation than a file
        that exists but is actually corrupted."""
        remembered = app_settings.load_last_session_files()
        existing = [p for p in remembered if os.path.isfile(p)]
        if existing:
            self._load_paths(existing)
        missing_count = len(remembered) - len(existing)
        if missing_count:
            self.status.showMessage(
                f"{missing_count} book(s) from your last session could no longer be found "
                "and were skipped.",
                8000,
            )

    def _show_beta_warning(self) -> None:
        """Shown once per session, right after the window first appears
        (QTimer.singleShot(0, ...) defers it until the event loop is
        already running, so it pops up over an already-visible,
        already-positioned window rather than racing the window's own
        first paint)."""
        QMessageBox.warning(
            self, "Early Development Notice",
            "This program is in the early stages of development. Please take a "
            "copy of the files you are working with before you edit them. "
            "No guarantees.",
        )

    def _center_on_screen(self) -> None:
        """resize() alone only sets the window's size, not its position --
        without this, Windows' default placement can land the window
        noticeably off-center (often toward a corner) on startup, which
        is invisible once maximized since the window then just fills the
        screen regardless of where it started. Centering explicitly
        avoids depending on OS/window-manager placement behavior."""
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return
        frame = self.frameGeometry()
        frame.moveCenter(screen.availableGeometry().center())
        self.move(frame.topLeft())

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(self.splitter)

        self.tag_panel = TagPanel()
        # Deliberately low minimum -- lets the panel be dragged down to
        # a sliver, or fully collapsed (see toggle_tag_panel()) rather
        # than being locked to a wide fixed range.
        self.tag_panel.setMinimumWidth(24)
        self.tag_panel.setMaximumWidth(440)
        self.tag_panel.applyRequested.connect(self._apply_bulk_edit)
        self.tag_panel.isbnLookupRequested.connect(self.open_google_books_dialog)
        self.tag_panel.coverAddReplaceRequested.connect(self.on_cover_add_replace)
        self.tag_panel.coverGenerateRequested.connect(self.on_cover_generate)
        self.tag_panel.coverDeleteRequested.connect(self.on_cover_delete)
        self.tag_panel.coverToggleJunkRequested.connect(self.on_cover_toggle_junk)
        self.tag_panel.selectionCountChanged.connect(self._on_tag_panel_selection_count_changed)
        self.tag_panel.collapseToggleRequested.connect(self.toggle_tag_panel)
        self.splitter.addWidget(self.tag_panel)

        self.table = BookTableWidget()
        self._default_table_font_pt = self.table.font().pointSize()
        # Debounces row-height reflow while a column is being dragged --
        # sectionResized fires continuously during a drag, and
        # resizeRowsToContents() over the whole table on every single one
        # of those events would be wasteful (and janky) for a large
        # library. Restarted on every resize event; only actually fires
        # once resizing has paused for a moment. See _on_column_resized
        # and _reflow_table_rows below.
        self._row_reflow_timer = QTimer(self)
        self._row_reflow_timer.setSingleShot(True)
        self._row_reflow_timer.timeout.connect(self._reflow_table_rows)
        self._text_overflow_mode = app_settings.load_text_overflow_mode()
        headers = ["Path", "Filename", "Status"] + [label for _key, label, _m in FIELDS] + ["Junk Cover"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionsMovable(True)  # drag headers to reorder columns
        self.table.horizontalHeader().sectionMoved.connect(self._on_columns_changed)

        # Restore any column widths saved from a previous session, keyed
        # by logical column index (stable across sessions regardless of
        # visual reordering or hiding). If there's nothing saved yet
        # (first ever run), _rebuild_table() auto-fits once on the first
        # real population instead -- see self._columns_sized below.
        saved_widths = app_settings.load_column_widths()
        for col, width in saved_widths.items():
            if 0 <= col < self.table.columnCount():
                self.table.setColumnWidth(col, width)
        self._columns_sized = bool(saved_widths)
        self.table.horizontalHeader().sectionResized.connect(self._on_column_resized)

        # Restore hidden columns from a previous session too -- FILENAME_COL
        # is excluded defensively (it's the one column the UI never lets you
        # hide, see open_column_settings_dialog's `locked` set) even though
        # it should never end up in a saved hidden set in the first place.
        saved_hidden = app_settings.load_hidden_columns()
        for col in saved_hidden:
            if 0 <= col < self.table.columnCount() and col != FILENAME_COL:
                self.table.setColumnHidden(col, True)

        self.table.verticalHeader().setVisible(True)  # row numbers, always positionally accurate
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setIconSize(COVER_ICON_SIZE)
        self.table.setSortingEnabled(True)  # click a header to sort by that column
        self._apply_text_overflow_mode(self._text_overflow_mode)
        # Strong, theme-independent selection/current-cell indicators --
        # otherwise the default look can blend into our own custom row
        # colors (dirty/status highlighting) and make it hard to tell
        # where you clicked. Selection color takes priority over a row's
        # dirty/status color while selected; the current cell (relevant
        # for typing and Tab/Enter navigation) gets its own bright
        # outline so it's visible even within a selected row.
        self.table.setStyleSheet(TABLE_SELECTION_STYLESHEET)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_table_context_menu)
        self.table.horizontalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.horizontalHeader().customContextMenuRequested.connect(self._show_header_context_menu)
        self.splitter.addWidget(self.table)
        self.splitter.setCollapsible(0, True)  # dragging the handle by hand can still reach 0 width
        self.splitter.setCollapsible(1, False)  # the table itself should never fully vanish
        self.splitter.splitterMoved.connect(self._on_splitter_moved)

        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)

        self._panel_collapser = SplitterPaneCollapser(
            self.splitter, pane_index=0, collapsed_width=TAG_PANEL_COLLAPSED_WIDTH, default_width=340,
        )

        # Menu bar and toolbar are built after the widgets above, since
        # some of their actions (Apply) are wired directly to tag_panel.
        self._build_menu_bar()
        self._build_toolbar()
        self._on_columns_changed()  # initial sync; a no-op given the default column order

        self.status = QStatusBar()
        self.setStatusBar(self.status)

        self.status_label = QLabel()
        self.status.addPermanentWidget(self.status_label)

    def _build_menu_bar(self) -> None:
        # Built via the shared redactor_common menu framework so the
        # top-level shape (File / Import / Operations / Settings / Help,
        # in that order, with those exact mnemonics) matches every other
        # Redactor project. "Kobo" is this project's one bit of
        # project-specific menu, inserted via extra_menus rather than
        # folded into the standard five -- see menu_builder.py.
        #
        # "About" is folded into "Help" here (it used to be its own
        # top-level menu) to match the shared spec; nothing about the
        # actions themselves changes.
        specs = {
            "File": [
                MenuAction("load_files", "&Load Files…", self.add_files_dialog, shortcut=shortcuts.LOAD_FILES),
                MenuAction(
                    "load_folder", "Load &Folder…", self.add_folder_dialog, shortcut=shortcuts.LOAD_FOLDER
                ),
                Separator(),
                MenuAction("save", "&Save Files", self.save_changed, shortcut=shortcuts.SAVE),
                MenuAction("save_as", "Save As Cop&y…", self.save_as_copies, shortcut=shortcuts.SAVE_AS),
                Separator(),
                # Quick, direct rename of the one selected file -- matches
                # Explorer's F2 exactly. Distinct from "rename_files"
                # below (the pattern-based batch tool, moved off F2 to
                # make room for this): see rename_selected_file().
                MenuAction(
                    "rename_file", "&Rename File…", self.rename_selected_file,
                    shortcut=shortcuts.RENAME_SINGLE_FILE,
                ),
                MenuAction(
                    "rename_files", "Rename Files (&Pattern)…", self.open_rename_dialog,
                    shortcut=shortcuts.RENAME_EXPORT_BY_PATTERN,
                ),
                Separator(),
                MenuAction("remove_files", "Remo&ve Files", self.remove_selected, shortcut=shortcuts.REMOVE_FROM_LIST),
                MenuAction("delete_files", "&Delete Files…", self.delete_files, shortcut="F8"),
                Separator(),
                MenuAction("refresh", "Re&fresh List", self.refresh_list, shortcuts=shortcuts.REFRESH_LIST),
                MenuAction("clear", "&Clear List", self.clear_list),
                Separator(),
                # No explicit shortcut -- Alt+F4 already closes this (or
                # any) plain QMainWindow at the OS level, verified
                # directly (launch, send Alt+F4, confirm the process
                # exits), independent of anything bound here.
                MenuAction("exit", "E&xit Program", self.close),
            ],
            "Import": [
                MenuAction(
                    "import_from_filename", "Import Metadata from &Filename…",
                    self.open_filename_parse_dialog, shortcut=shortcuts.PARSE_FILENAME_TO_METADATA,
                ),
                MenuAction(
                    "import_google_books", "Import Metadata from &Google Books…",
                    self.open_google_books_dialog,
                ),
                MenuAction(
                    "import_file_content", "Import Metadata from File &Content…",
                    self.open_content_scan_dialog,
                ),
                MenuAction(
                    "import_open_library", "Import Metadata from &Open Library…",
                    self.open_open_library_dialog,
                ),
                MenuAction(
                    "import_calibre", "Import Metadata from &Calibre…",
                    self.open_calibre_lookup_dialog,
                ),
                Separator(),
                MenuAction("import_to_epub", "Import &to EPUB…", self.open_ebook_convert_dialog),
            ],
            "Operations": [
                # Apply lives in the toolbar too (see _build_toolbar) --
                # sharing this QAction instance means its dynamic
                # "Apply to N selected book(s)" text and enabled state
                # never drift out of sync between the two.
                MenuAction("apply_bulk_edit", "&Apply to 0 selected book(s)", self.tag_panel.apply_bulk_edit),
                MenuAction("case_conversion", "&Case Conversion…", self.open_case_conversion_dialog),
                MenuAction(
                    "author_sort_convert", "Author Sor&t Conversion…",
                    self.open_author_sort_dialog,
                ),
                MenuAction("number_series", "&Number Series…", self.open_series_number_dialog),
                MenuAction(
                    "generate_cover", "&Generate Cover from Metadata…",
                    self.open_cover_generator_dialog,
                ),
                MenuAction(
                    "regenerate_junk_covers", "Regenerate &Junk Covers…",
                    self.open_regenerate_junk_covers_dialog,
                ),
                MenuAction(
                    "search_replace", "&Search/Replace…", self.open_search_replace_dialog,
                    shortcut=shortcuts.SEARCH_REPLACE,
                ),
                MenuAction("polish_book", "&Polish Book…", self.open_polish_book_dialog),
                MenuAction(
                    "compress_images_lossy", "&Compress Images (Lossy)…",
                    self.open_compress_images_dialog,
                ),
                Separator(),
                MenuAction("undo", "&Undo", self.on_undo, shortcut=shortcuts.UNDO,
                           tooltip="Undo the last change (in-memory edits only, up to 5 steps back)"),
                MenuAction("redo", "&Redo", self.on_redo, shortcut=shortcuts.REDO,
                           tooltip="Redo the last undone change"),
            ],
            "Settings": [
                MenuAction("column_settings", "Add/Remove &Columns…", self.open_column_settings_dialog),
                MenuAction("language_settings", "Add/Remove &Languages…", self.open_language_settings_dialog),
                MenuAction("genre_settings", "Add/Remove &Genres…", self.open_genre_settings_dialog),
                MenuAction(
                    "blank_language_default", "&Blank Language Default…",
                    self.open_blank_language_default_settings,
                ),
                Submenu("&Text Wrapping", [
                    MenuAction(
                        "text_wrap_mode_wrap", "&Wrap Text (grow row height)",
                        lambda: self.set_text_overflow_mode("wrap"), checkable=True,
                    ),
                    MenuAction(
                        "text_wrap_mode_ellipsis", "&Truncate with … (fixed row height)",
                        lambda: self.set_text_overflow_mode("ellipsis"), checkable=True,
                    ),
                    MenuAction(
                        "text_wrap_mode_clip", "&Clip, No … (fixed row height)",
                        lambda: self.set_text_overflow_mode("clip"), checkable=True,
                    ),
                ]),
                Separator(),
                MenuAction(
                    "perf_logging", "&Enable Performance Logging",
                    self.toggle_perf_logging, checkable=True,
                    tooltip="Logs a timing breakdown of slow operations (table rebuilds, saves) "
                            "to a file next to the crash log, for diagnosing a slowdown that "
                            "doesn't reproduce on a smaller library.",
                ),
                MenuAction("open_perf_log", "Open Performance &Log File…", self.open_perf_log_file),
            ],
            "Help": [
                MenuAction("about", f"&About {APP_NAME}…", self.open_about_dialog, shortcut=shortcuts.HELP),
                MenuAction("changelog", "View &Changelog…", self.open_changelog_dialog),
                MenuAction("credits", "&Credits…", self.open_credits_dialog),
            ],
        }
        # Repair: batch operations specifically for books that arrive with
        # structural or metadata damage (most often from older files that
        # have been through several lossy format conversions) -- kept
        # separate from Operations, which is everyday field editing, since
        # this category kept growing (Validate/Fix Issues, Rebuild
        # Manifest, Missing Space detection, and now Nav/Manifest Repair
        # and the blank-language default) and deserved its own place
        # rather than continuing to pile into one menu.
        repair_items = [
            MenuAction("validate", "&Validate / Fix Issues…", self.open_validation_dialog),
            MenuAction("rebuild_manifest", "Re&build Manifest…", self.open_manifest_rebuild_dialog),
            MenuAction(
                "repair_navigation", "Repair &Navigation…",
                self.open_nav_repair_dialog,
            ),
            MenuAction("missing_space", "Detect &Missing Spaces…", self.open_missing_space_dialog),
            MenuAction(
                "strip_description_html", "&Strip HTML from Description…",
                self.open_strip_description_html_dialog,
            ),
            Separator(),
            MenuAction(
                "set_default_language", "Set &Blank/Unknown Language to Default…",
                self.set_blank_languages_to_default,
            ),
        ]
        kobo_items = [
            MenuAction("send_to_kobo_usb", "Send to &Kobo (USB)…", self.open_send_to_kobo_dialog),
            MenuAction(
                "send_to_ereader", "Send to e&Reader (Wireless)…",
                self.open_send_to_ereader_dialog,
            ),
        ]
        actions = build_menu_bar(
            self, specs, extra_menus=[("Repair", 3, repair_items), ("Kobo", 4, kobo_items)]
        )

        # Back-compat: the rest of this file (toolbar, context menus)
        # references these as self.<x>_act attributes directly.
        self.load_files_act = actions["load_files"]
        self.load_folder_act = actions["load_folder"]
        self.save_act = actions["save"]
        self.save_as_act = actions["save_as"]
        self.rename_file_act = actions["rename_file"]
        self.rename_files_act = actions["rename_files"]
        self.remove_files_act = actions["remove_files"]
        self.delete_files_act = actions["delete_files"]
        self.apply_bulk_edit_act = actions["apply_bulk_edit"]
        self.apply_bulk_edit_act.setEnabled(False)
        self.undo_act = actions["undo"]
        self.undo_act.setEnabled(False)
        self.redo_act = actions["redo"]
        self.redo_act.setEnabled(False)
        self.set_default_language_act = actions["set_default_language"]
        self._update_blank_language_default_action_state()

        # Mutually exclusive radio-style trio for the Text Wrapping
        # submenu, checked to match whatever mode _build_ui already
        # applied to the table from saved settings.
        text_wrap_group = QActionGroup(self)
        text_wrap_group.setExclusive(True)
        for mode, key in (
            ("wrap", "text_wrap_mode_wrap"),
            ("ellipsis", "text_wrap_mode_ellipsis"),
            ("clip", "text_wrap_mode_clip"),
        ):
            act = actions[key]
            text_wrap_group.addAction(act)
            act.setChecked(mode == self._text_overflow_mode)

        self.perf_logging_act = actions["perf_logging"]
        self.perf_logging_act.setChecked(perf_log.is_enabled())

    def _build_toolbar(self) -> None:
        """Slim toolbar: just the handful of most-frequent actions,
        sharing QAction instances with the menu bar above so nothing
        drifts out of sync between the two. Everything else lives in the
        menu bar only."""
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        toolbar.addAction(self.load_files_act)
        toolbar.addAction(self.load_folder_act)
        toolbar.addSeparator()
        toolbar.addAction(self.save_act)
        toolbar.addSeparator()
        toolbar.addAction(self.apply_bulk_edit_act)
        toolbar.addSeparator()
        toolbar.addAction(self.undo_act)
        toolbar.addAction(self.redo_act)
        toolbar.addSeparator()

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter by filename or title…")
        self.filter_edit.setMaximumWidth(300)
        self.filter_edit.textChanged.connect(self._apply_filter)
        toolbar.addWidget(self.filter_edit)

        # Everything added after an Expanding-policy spacer widget gets
        # pushed to the far right of the toolbar.
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        toggle_panel_act = make_action(self, "Panel", self.toggle_tag_panel)
        toggle_panel_act.setToolTip("Minimize or restore the bulk-edit panel")
        toolbar.addAction(toggle_panel_act)
        toolbar.addSeparator()

        zoom_out_act = make_action(
            self, "\u2212", self.zoom_out, shortcut=QKeySequence.StandardKey.ZoomOut
        )
        zoom_out_act.setToolTip("Decrease table font size")
        toolbar.addAction(zoom_out_act)

        self.zoom_label = QLabel("100%")
        self.zoom_label.setMinimumWidth(44)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zoom_label.setToolTip("Table font size, relative to the default (100%). Click to reset.")
        self.zoom_label.mousePressEvent = lambda _event: self.zoom_reset()
        toolbar.addWidget(self.zoom_label)

        zoom_in_act = make_action(
            self, "+", self.zoom_in, shortcut=QKeySequence.StandardKey.ZoomIn
        )
        zoom_in_act.setToolTip("Increase table font size")
        toolbar.addAction(zoom_in_act)

    def zoom_in(self) -> None:
        self._adjust_table_zoom(1)

    def zoom_out(self) -> None:
        self._adjust_table_zoom(-1)

    def zoom_reset(self) -> None:
        self._set_table_font_size(self._default_table_font_pt)

    def _adjust_table_zoom(self, delta: int) -> None:
        new_size = max(TABLE_ZOOM_MIN_PT, min(TABLE_ZOOM_MAX_PT, self.table.font().pointSize() + delta))
        self._set_table_font_size(new_size)

    def _set_table_font_size(self, point_size: int) -> None:
        """Adjusts the table's (and its headers') font size, then re-fits
        row heights to the new text size and updates the toolbar's
        percentage indicator (relative to the size captured at startup,
        i.e. the default is always 100%). Not persisted across sessions
        -- purely a this-window display preference for fitting more (or
        more readable) content."""
        font = self.table.font()
        if point_size == font.pointSize():
            return
        font.setPointSize(point_size)
        self.table.setFont(font)
        self.table.horizontalHeader().setFont(font)
        self.table.verticalHeader().setFont(font)
        self.table.resizeRowsToContents()
        percent = round(point_size / self._default_table_font_pt * 100)
        self.zoom_label.setText(f"{percent}%")

    # ------------------------------------------------------------------
    # Bulk-edit panel: toolbar Apply, collapse/restore, field sync
    # ------------------------------------------------------------------

    def _on_tag_panel_selection_count_changed(self, count: int) -> None:
        self.apply_bulk_edit_act.setText(f"Apply to {count} selected book(s)")
        self.apply_bulk_edit_act.setEnabled(count > 0)

    def toggle_tag_panel(self) -> None:
        """Collapses the bulk-edit panel to a slim strip (not all the way
        to zero -- its own toggle button lives inside the panel, see
        TagPanel._build_ui(), so collapsing to nothing would take the
        only way to bring it back with it), or restores it to its last
        width. Also reachable via the toolbar's "Panel" button, and via
        dragging the splitter handle by hand. Resize logic itself lives
        in redactor_common's SplitterPaneCollapser -- shared with video.
        """
        self._panel_collapser.toggle()
        self._sync_tag_panel_collapsed_indicator()

    def _on_splitter_moved(self, _pos, _index) -> None:
        """Keeps the panel's own toggle-button glyph in sync when the
        user drags the splitter handle by hand, not just when they use
        the button/toolbar action."""
        self._sync_tag_panel_collapsed_indicator()

    def _sync_tag_panel_collapsed_indicator(self) -> None:
        self.tag_panel.set_collapsed_indicator(self._panel_collapser.is_collapsed())

    def _visible_ordered_field_keys(self) -> list[str]:
        """The bulk-edit field keys, filtered to visible table columns
        and ordered to match the table's current (possibly
        drag-reordered) left-to-right column order."""
        header = self.table.horizontalHeader()
        result = []
        for visual_index in range(self.table.columnCount()):
            logical_index = header.logicalIndex(visual_index)
            if logical_index < FIRST_FIELD_COL or self.table.isColumnHidden(logical_index):
                continue
            field_index = logical_index - FIRST_FIELD_COL
            if 0 <= field_index < len(FIELDS):
                result.append(FIELDS[field_index][0])
        return result

    def _on_columns_changed(self, *_args) -> None:
        """Keeps the bulk-edit panel's fields in sync with the table's
        column visibility and order -- called after Add/Remove Columns
        is applied, and whenever a column header is dragged to a new
        position. *_args absorbs QHeaderView.sectionMoved's (logical,
        old_visual, new_visual) arguments, which aren't needed here.
        Also persists the current hidden-columns set, so a column you've
        hidden stays hidden next time you open the app -- previously
        only column widths were remembered, not visibility, so every
        restart quietly showed every column again regardless of what
        you'd hidden last time."""
        self.tag_panel.set_visible_fields(self._visible_ordered_field_keys())
        hidden = {i for i in range(self.table.columnCount()) if self.table.isColumnHidden(i)}
        app_settings.save_hidden_columns(hidden)

    # ------------------------------------------------------------------
    # Right-click context menus
    # ------------------------------------------------------------------

    def _show_table_context_menu(self, pos) -> None:
        # Selection-fix, and the generic Open Containing Folder/Copy Path
        # actions, are handled by the shared helper -- see its docstring.
        def extra(books: list[EpubBook]) -> MenuItems:
            items: MenuItems = []
            if len(books) == 1 and not books[0].load_error:
                # Reuses the actual File-menu QAction (F2) rather than
                # building a fresh one -- same object, so this shows the
                # real shortcut hint and can never drift out of sync
                # with it. Only offered for a single book -- renaming
                # several to the same name doesn't make sense. Distinct
                # from "Rename Files…" just below (the pattern-based
                # batch tool) -- this is the quick, direct fix for one
                # typo at a time.
                items.append(self.rename_file_act)
            items.append(Separator())
            items.append(self.rename_files_act)
            items.append(self.save_act)
            items.append(Separator())
            items.append(self.remove_files_act)
            items.append(self.delete_files_act)
            items.append(Separator())
            items.append(MenuAction("validate", "Validate / Fix Issues…", self.open_validation_dialog))
            items.append(MenuAction("calibre_lookup", "Look Up via Calibre…", self.open_calibre_lookup_dialog))
            items.append(MenuAction("polish_book", "Polish Book…", self.open_polish_book_dialog))
            items.append(MenuAction("number_series", "Number Series…", self.quick_number_series))
            books_with_covers = [b for b in books if b.cover_hash is not None]
            if any(not self._book_is_junk_cover(b) for b in books_with_covers):
                items.append(MenuAction(
                    "flag_junk_cover", "Flag Cover as Junk",
                    self.flag_selected_covers_as_junk,
                ))
            if any(self._book_is_junk_cover(b) for b in books_with_covers):
                items.append(MenuAction(
                    "unflag_junk_cover", "Unflag Cover as Junk",
                    self.unflag_selected_covers_as_junk,
                ))
            items.append(Separator())
            items.append(MenuAction("open_sigil", "Open with Sigil…", self.open_in_sigil))
            items.append(Separator())
            items.append(MenuAction("send_kobo", "Send to Kobo (USB)…", self.open_send_to_kobo_dialog))
            items.append(MenuAction(
                "send_ereader", "Send to eReader (Wireless)…", self.open_send_to_ereader_dialog
            ))
            return items

        show_table_context_menu(
            self, self.table, pos,
            get_selected_items=self._currently_selected_books,
            get_path=lambda book: book.path,
            extra_items=extra,
        )

    # ------------------------------------------------------------------
    # Open with Sigil
    # ------------------------------------------------------------------

    def open_in_sigil(self) -> None:
        books = self._currently_selected_books()
        if not books:
            QMessageBox.information(
                self, "No books selected", "Select the book(s) to open in Sigil first."
            )
            return

        dirty_books = [b for b in books if b.dirty]
        if dirty_books:
            reply = QMessageBox.question(
                self, "Unsaved changes",
                f"{len(dirty_books)} of the selected book(s) have unsaved changes in this app. "
                "Sigil edits the file on disk directly -- if you save there and then Save here "
                "too, whichever you save last overwrites the other's changes.\n\n"
                "Save here first (recommended), or continue anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        sigil_path = find_sigil(configured_path=app_settings.load_sigil_path())
        if sigil_path is None:
            self._prompt_for_sigil(books)
            return

        self._launch_sigil_for(sigil_path, books)

    def _launch_sigil_for(self, sigil_path: str, books: list[EpubBook]) -> None:
        errors = []
        for book in books:
            try:
                launch_sigil(sigil_path, book.path)
            except SigilLaunchError as exc:
                errors.append(f"{os.path.basename(book.path)}: {exc}")
        if errors:
            QMessageBox.warning(self, "Could not open in Sigil", summarize_errors(errors))

    def _prompt_for_sigil(self, books: list[EpubBook]) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("Sigil Not Found")
        box.setText(
            "Couldn't find Sigil (a free, open-source EPUB editor) on this system -- it can "
            "fix some structural issues this app can't.\n\n"
            "If you already have it installed, click \"Locate Sigil…\" and point to sigil.exe "
            "(this only needs doing once). If you don't have it, it's free -- click "
            "\"Download Sigil…\"."
        )
        locate_btn = box.addButton("Locate Sigil…", QMessageBox.ButtonRole.ActionRole)
        download_btn = box.addButton("Download Sigil…", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()

        clicked = box.clickedButton()
        if clicked == locate_btn:
            self._browse_for_sigil(books)
        elif clicked == download_btn:
            webbrowser.open(SIGIL_DOWNLOAD_URL)

    def _browse_for_sigil(self, books: list[EpubBook]) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Locate Sigil", "", "Sigil (sigil.exe)")
        if not path:
            return
        app_settings.save_sigil_path(path)
        sigil_path = find_sigil(configured_path=app_settings.load_sigil_path())
        if sigil_path:
            self._launch_sigil_for(sigil_path, books)

    # ------------------------------------------------------------------

    def _show_header_context_menu(self, pos) -> None:
        # Still index-keyed (this project's column-hiding predates
        # core/table_settings.py's field-name scheme, and hasn't been
        # migrated onto it) -- show_column_header_context_menu's keys are
        # untyped for exactly this case, see its module docstring.
        column_order = [i for i in range(self.table.columnCount()) if i != FILENAME_COL]
        label_lookup = {
            i: self.table.horizontalHeaderItem(i).text() for i in column_order
        }
        hidden = {i for i in range(self.table.columnCount()) if self.table.isColumnHidden(i)}

        show_column_header_context_menu(
            self, self.table, pos,
            column_order=column_order,
            label_lookup=label_lookup,
            protected_columns=frozenset({FILENAME_COL}),
            hidden_fields=hidden,
            is_visible=lambda i, hidden_set: i not in hidden_set,
            on_toggle=lambda i, checked: self._set_column_visible(i, checked),
            open_column_settings_dialog=self.open_column_settings_dialog,
        )

    def _set_column_visible(self, logical_index: int, visible: bool) -> None:
        self.table.setColumnHidden(logical_index, not visible)
        self._on_columns_changed()

    # ------------------------------------------------------------------
    # Row <-> book mapping (sort-safe: see module docstring)
    # ------------------------------------------------------------------

    def _book_for_row(self, row: int) -> EpubBook | None:
        item = self.table.item(row, FILENAME_COL)
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _selected_rows(self) -> list[int]:
        return sorted({idx.row() for idx in self.table.selectedIndexes()})

    def _books_for_rows(self, rows: list[int], exclude_errors: bool = True) -> list[EpubBook]:
        result = []
        for r in rows:
            book = self._book_for_row(r)
            if book is None:
                continue
            if exclude_errors and book.load_error:
                continue
            result.append(book)
        return result

    def _currently_selected_books(self) -> list[EpubBook]:
        return self._books_for_rows(self._selected_rows(), exclude_errors=True)

    def _selection_or_all_books(self) -> list[EpubBook]:
        """Currently selected rows' books, or every loaded (non-error) book
        if nothing is selected. Shared by actions that operate on 'the
        current working set': rename/export, Google Books lookup, search/replace."""
        selected = self._currently_selected_books()
        return selected if selected else [b for b in self.books if not b.load_error]

    def _find_row_for_book(self, book: EpubBook) -> int | None:
        for row in range(self.table.rowCount()):
            if self._book_for_row(row) is book:
                return row
        return None

    def _rows_by_book(self) -> dict[EpubBook, int]:
        """A book -> row-index map covering every row currently in the
        table, built once in O(row count). Prefer this over repeated
        _find_row_for_book() calls when looking up MANY books at once
        (restoring a multi-book selection, refreshing several rows
        after a bulk edit) -- each _find_row_for_book() call scans the
        whole table on its own, so looking up N books that way costs
        O(N * row count) instead of the O(row count) this takes to
        build, plus O(1) per lookup after that. Difference is
        negligible for a handful of books, but genuinely matters once a
        large library is fully selected before an operation like Save
        -- that was quietly making saving feel much slower than it
        needed to be for exactly that case. For a single book,
        _find_row_for_book() alone is simpler and just as fast."""
        result: dict[EpubBook, int] = {}
        for row in range(self.table.rowCount()):
            book = self._book_for_row(row)
            if book is not None and book not in result:
                # First occurrence wins, matching _find_row_for_book()'s
                # own behavior exactly -- shouldn't matter in practice
                # (each book should only ever occupy one row), but keeps
                # this a drop-in equivalent rather than a subtly
                # different one for that edge case.
                result[book] = row
        return result

    def _refresh_row_full(self, book: EpubBook) -> None:
        """Re-sync every displayed cell (path, filename, fields, status,
        cover icon, dirty style) for one book's current row from its
        actual current state. Used after operations that change several
        things at once (or come from Undo) rather than one -- avoids a
        full table rebuild, which would lose the current selection and
        sort order.

        For refreshing MANY books at once, use _refresh_rows_full()
        instead -- this re-derives its row via _find_row_for_book()'s
        O(row count) scan on every call, which is fine for the
        occasional single-book refresh this is designed for, but
        becomes an O(n^2) cost called once per book in a loop over a
        large batch (the exact shape of bug _on_cover_icon_ready() had
        before it was fixed to use a cached book->item lookup instead --
        found here the same way, profiling a reported freeze)."""
        row = self._find_row_for_book(book)
        if row is None:
            return
        was_updating = self._updating_table
        self._updating_table = True
        was_sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        self._refresh_row_cells(row, book)
        self.table.setSortingEnabled(was_sorting)
        self._updating_table = was_updating

    def _refresh_rows_full(self, books: list[EpubBook]) -> None:
        """Bulk version of _refresh_row_full(): refreshes every book in
        `books`' row in O(len(books) + row count) total, by building the
        book->row map ONCE via _rows_by_book() rather than paying
        _find_row_for_book()'s O(row count) scan again for every single
        book. Prefer this over a loop of _refresh_row_full() calls
        whenever `books` could be a large batch (not just one or two) --
        see its own docstring."""
        if not books:
            return
        was_updating = self._updating_table
        self._updating_table = True
        was_sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        rows_by_book = self._rows_by_book()
        for book in books:
            row = rows_by_book.get(book)
            if row is not None:
                self._refresh_row_cells(row, book)
        self.table.setSortingEnabled(was_sorting)
        self._updating_table = was_updating

    def _refresh_row_cells(self, row: int, book: EpubBook) -> None:
        """The actual per-row refresh logic shared by _refresh_row_full()
        and _refresh_rows_full() -- assumes the caller already knows
        `row` and has set up the _updating_table guard (without it, each
        item.setText() below would itself fire _on_item_changed, which
        unconditionally pushes to the undo stack -- turning one refresh
        into a cascade of bogus undo entries for every field column)."""
        path_item = self.table.item(row, PATH_COL)
        if path_item is not None:
            path_item.setText(os.path.dirname(book.path))
            path_item.setToolTip(book.path)
        name_item = self.table.item(row, FILENAME_COL)
        if name_item is not None:
            name_item.setText(os.path.basename(book.path))
            name_item.setToolTip(book.path)
            self._apply_cover_icon(name_item, book)
        for i, (key, _label, multiline) in enumerate(FIELDS):
            col = FIRST_FIELD_COL + i
            item = self.table.item(row, col)
            if item is not None:
                item.setText(self._field_display_text(getattr(book.metadata, key, ""), multiline))
        self._update_status_cell(row, book)
        self._update_junk_cover_cell(row, book)
        self._set_row_dirty_style(row, book.dirty)

    # ------------------------------------------------------------------
    # Undo
    # ------------------------------------------------------------------

    @staticmethod
    def _snapshot_book(book: EpubBook) -> dict:
        return {
            "metadata": copy.deepcopy(book.metadata),
            "dirty": book.dirty,
            "cover_bytes": book.cover_bytes,
            "cover_mime": book.cover_mime,
            "cover_changed": book.cover_changed,
            "cover_removed": book.cover_removed,
            "image_replacements": dict(book._image_replacements),
        }

    @staticmethod
    def _restore_book(book: EpubBook, snapshot: dict) -> None:
        book.metadata = snapshot["metadata"]
        book.dirty = snapshot["dirty"]
        book.cover_bytes = snapshot["cover_bytes"]
        book.cover_mime = snapshot["cover_mime"]
        book.cover_changed = snapshot["cover_changed"]
        book.cover_removed = snapshot["cover_removed"]
        book._image_replacements = snapshot["image_replacements"]

    def _push_undo(self, label: str, books: list[EpubBook]) -> None:
        """Call BEFORE mutating `books`."""
        if books:
            self.undo_manager.push(label, books, self._snapshot_book)
            self.undo_act.setEnabled(True)
            self.redo_act.setEnabled(False)  # push() clears any pending redo

    def on_undo(self) -> None:
        # snapshot_fn passed too (not just restore_fn) so the state
        # being overwritten is captured onto the redo stack first --
        # see redactor_common.core.undo's own docstring.
        affected = self.undo_manager.undo(self._restore_book, self._snapshot_book)
        if not affected:
            return
        self._refresh_rows_full(affected)
        self._refresh_status()
        self._on_selection_changed()  # cover preview / bulk-edit fields may need refreshing
        self.undo_act.setEnabled(self.undo_manager.can_undo())
        self.redo_act.setEnabled(self.undo_manager.can_redo())

    def on_redo(self) -> None:
        affected = self.undo_manager.redo(self._restore_book, self._snapshot_book)
        if not affected:
            return
        self._refresh_rows_full(affected)
        self._refresh_status()
        self._on_selection_changed()
        self.undo_act.setEnabled(self.undo_manager.can_undo())
        self.redo_act.setEnabled(self.undo_manager.can_redo())

    # ------------------------------------------------------------------
    # Drag and drop
    # ------------------------------------------------------------------

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = [url.toLocalFile() for url in event.mimeData().urls()]
        epub_paths: list[str] = []
        for p in paths:
            if os.path.isdir(p):
                epub_paths.extend(self._find_epubs_in_folder(p, recursive=True))
            elif p.lower().endswith(".epub"):
                epub_paths.append(p)
        self._load_paths(epub_paths)

    # ------------------------------------------------------------------
    # Loading files
    # ------------------------------------------------------------------

    def add_files_dialog(self) -> None:
        start_dir = app_settings.load_last_directory()
        paths, _filter = QFileDialog.getOpenFileNames(
            self, "Add EPUB Files", start_dir, "EPUB files (*.epub)"
        )
        if paths:
            app_settings.save_last_directory(paths[0])
            self._load_paths(paths)

    def add_folder_dialog(self) -> None:
        # Qt's native folder picker can't multi-select directories at all
        # -- that's an OS limitation (Explorer's browse-folder dialog
        # only ever returns one), not something Qt chooses to omit. To
        # get real Ctrl/Shift-click multi-select, this uses Qt's own
        # (non-native) file dialog instead, with extended selection
        # turned on for its internal list/tree views -- the standard
        # workaround for this. Trade-off: the dialog looks like Qt's
        # file browser rather than the OS's native folder picker.
        start_dir = app_settings.load_last_directory()
        dialog = QFileDialog(
            self, "Add Folders of EPUBs (Ctrl/Shift-click to select more than one)", start_dir
        )
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        for view in dialog.findChildren(QListView) + dialog.findChildren(QTreeView):
            view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        if not dialog.exec():
            return
        folders = [f for f in dialog.selectedFiles() if os.path.isdir(f)]
        if not folders:
            return
        # Opening a folder replaces the current list rather than adding
        # to it -- choosing a whole new folder to work in usually means
        # starting fresh, not building up a mixed set from several
        # places (Load Files, or drag-and-drop, still add to whatever's
        # already loaded, since those are more often used specifically
        # to top up an existing working set with a few more files).
        # Same unsaved-changes confirmation as the existing Clear List
        # action, since this is functionally that action immediately
        # followed by loading the new folder(s).
        if self.books:
            if self._count_dirty() and not self._confirm_discard(
                "clear the current list and open a new folder"
            ):
                return
            self.books = []
            self._rebuild_table()
            self._refresh_status()
        app_settings.save_last_directory(folders[-1])
        reply = QMessageBox.question(
            self,
            "Include Subfolders?",
            "Include EPUB files in subfolders too?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        recursive = reply == QMessageBox.StandardButton.Yes
        epub_paths: list[str] = []
        for folder in folders:
            epub_paths.extend(self._find_epubs_in_folder(folder, recursive=recursive))
        self._load_paths(epub_paths)

    @staticmethod
    def _find_epubs_in_folder(folder: str, recursive: bool = True) -> list[str]:
        found = []
        if recursive:
            for root, _dirs, files in os.walk(folder):
                for f in files:
                    if f.lower().endswith(".epub"):
                        found.append(os.path.join(root, f))
        else:
            try:
                for f in os.listdir(folder):
                    full = os.path.join(folder, f)
                    if os.path.isfile(full) and f.lower().endswith(".epub"):
                        found.append(full)
            except OSError:
                pass
        return found

    def _load_paths(self, paths: list[str]) -> None:
        # Normalize to the OS's native separator right at this single
        # choke point -- Qt's file dialogs and drag-and-drop both commonly
        # hand back forward-slash paths even on Windows (Qt's own internal
        # path convention), which os.path there tolerates as valid but
        # doesn't normalize, so the Path column would otherwise show a
        # mix of slash styles instead of native backslashes.
        paths = [os.path.normpath(p) for p in paths]
        already_loaded = {b.path for b in self.books}
        new_paths = [p for p in paths if p not in already_loaded]
        if not new_paths:
            return

        added = 0
        failed = []

        def _step(path: str, _index: int) -> None:
            nonlocal added
            try:
                book = EpubBook(path)
            except Exception:  # noqa: BLE001 - a single unusually-broken file must never take down the whole batch
                # EpubBook._load() already catches every known kind of
                # corruption internally and sets load_error gracefully
                # instead of raising -- this is a second, broader safety
                # net for whatever kind that internal handling doesn't
                # yet anticipate, so one file can't crash loading for
                # every other file in the same batch.
                failed.append((path, traceback.format_exc(limit=2)))
                return
            self.books.append(book)
            if book.load_error:
                failed.append((path, book.load_error))
            added += 1

        run_with_progress(
            self, new_paths, _step, "Loading books…",
            threshold=LOAD_PROGRESS_THRESHOLD,
            label_for=lambda path: f"Loading: {os.path.basename(path)}",
        )

        if added:
            self._rebuild_table()
        if failed:
            details = "\n".join(f"- {os.path.basename(p)}: {err}" for p, err in failed)
            QMessageBox.warning(
                self,
                "Some files failed to load",
                f"{len(failed)} file(s) could not be read as valid EPUBs and are "
                f"shown highlighted in red. They will be skipped on save.\n\n{details}",
            )
        self._refresh_status()

    # ------------------------------------------------------------------
    # Table population
    # ------------------------------------------------------------------

    def _select_books(self, books: list[EpubBook]) -> None:
        """Selects exactly the rows currently showing these books (any
        book no longer present -- e.g. removed -- is simply skipped).
        Used to restore a selection by book identity after an operation
        that repopulates the table wholesale, like _rebuild_table()."""
        self.table.clearSelection()
        rows_by_book = self._rows_by_book()
        first_row = None
        for book in books:
            row = rows_by_book.get(book)
            if row is not None:
                self.table.selectRow(row)
                if first_row is None:
                    first_row = row
        if first_row is not None:
            self.table.scrollToItem(self.table.item(first_row, FILENAME_COL))

    def _rebuild_table(self) -> None:
        with perf_log.timed(f"_rebuild_table total ({len(self.books)} books)"):
            self._rebuild_table_impl()

    def _rebuild_table_impl(self) -> None:
        # Capture the current selection by BOOK IDENTITY (not row index)
        # before repopulating, and restore it after -- row indices alone
        # aren't reliable here, since sorting or a rename can shift which
        # book ends up at a given row. Without this, Qt's own selection
        # model has no way to know that when every row's items are being
        # replaced wholesale, and the selection ends up pointing at
        # whatever book now happens to occupy that row index -- looking
        # like the selection is "jumping" to a different book than the
        # one actually selected before.
        previously_selected = self._books_for_rows(self._selected_rows(), exclude_errors=False)

        self._updating_table = True
        was_sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)  # avoid reorder-mid-populate
        self.table.setRowCount(len(self.books))
        self._filename_item_by_book = {}  # repopulated fresh below, in _populate_row()
        self._junk_cover_item_by_book = {}  # ditto

        # Per-section timing across the whole populate loop below (see
        # core/perf_log.py) -- a no-op unless Settings -> Enable
        # Performance Logging is on. Stashed on self so _populate_row()
        # (called once per book via the lambda below) can record into
        # the SAME accumulator across the whole rebuild, rather than
        # each row producing its own separate summary.
        self._perf_accum = perf_log.Accumulator()

        # A plain, uninterrupted loop here blocks the whole UI thread
        # until every row is built -- fine for a handful of books, but
        # for a genuinely large library (thousands of rows) this can run
        # long enough to look exactly like a frozen, unresponsive app,
        # with no way to tell it's actually still working. No cancel
        # button, deliberately: unlike loading, this is just re-drawing
        # a decision that's already been made (files already loaded,
        # already saved, already deleted, ...), not an operation there's
        # any reason to interrupt partway through.
        run_with_progress(
            self, self.books, lambda book, row: self._populate_row(row, book), "Updating list…",
            threshold=REBUILD_PROGRESS_THRESHOLD, cancellable=False, update_every=50,
        )
        self._perf_accum.dump(f"_populate_row breakdown ({len(self.books)} books)")

        if not self._columns_sized and self.books:
            # Only ever auto-fits once, the very first time real content
            # lands in the table (and only when nothing was restored from
            # a previous session) -- otherwise this ran on every single
            # rebuild (after Save, Refresh, Undo, Delete, ...), silently
            # overwriting any manual column resizing every time.
            self.table.resizeColumnsToContents()
            self._columns_sized = True
        self.table.setSortingEnabled(was_sorting)
        self._updating_table = False
        self._apply_filter(self.filter_edit.text())

        if previously_selected:
            self._select_books(previously_selected)

    def _on_column_resized(self, _logical_index, _old_size, _new_size) -> None:
        if self._updating_table:
            # The one-time auto-fit (resizeColumnsToContents(), right
            # after populating the table) also fires this signal, once
            # per column -- not a real user resize, and importantly not
            # one that needs a row-height reflow either: auto-fit only
            # ever WIDENS columns to fit their content, which can't make
            # a cell wrap onto MORE lines than it already needed, only
            # fewer. Scheduling a full-table resizeRowsToContents() here
            # anyway was a real perf regression on a large library (every
            # auto-fit column triggers this once, debounced into exactly
            # one full-table re-measure pass either way, but on a huge
            # table even one pass is a real, previously non-existent cost
            # right after loading) -- skip it, matching the same guard
            # that already skips saving column widths here.
            return
        # Narrowing a column can change how much (if any) of a cell's text
        # wraps or gets clipped, which changes how tall its row needs to
        # be -- reflow row heights to match, debounced so a click-drag
        # resize doesn't re-measure the whole table on every pixel of
        # mouse movement. Restarted (not just started) on every event, so
        # it fires once when dragging actually stops.
        self._row_reflow_timer.start(120)
        widths = {i: self.table.columnWidth(i) for i in range(self.table.columnCount())}
        app_settings.save_column_widths(widths)

    def _reflow_table_rows(self) -> None:
        """Re-measures every row's height against its current content and
        column widths -- the fix for rows whose text wraps onto more (or
        fewer) lines than the row is currently tall enough to show
        cleanly, e.g. after a column was resized. Cheap to call whenever
        row heights might be stale; Qt only actually redraws what's
        visible."""
        self.table.resizeRowsToContents()

    def _apply_text_overflow_mode(self, mode: str) -> None:
        """Switches how an over-long cell value is shown when its column
        is too narrow -- "wrap" (grow the row), "ellipsis" (single-line,
        trailing "…"), or "clip" (single-line, hard cut, no "…"). See
        app_settings.load_text_overflow_mode() for the full rationale."""
        self._text_overflow_mode = mode
        self.table.setWordWrap(mode == "wrap")
        self.table.setTextElideMode(
            Qt.TextElideMode.ElideNone if mode == "clip" else Qt.TextElideMode.ElideRight
        )
        self._refresh_multiline_field_cells()
        self._reflow_table_rows()

    def set_text_overflow_mode(self, mode: str) -> None:
        """Settings -> Text Wrapping menu handler: applies `mode` and
        remembers it for next launch."""
        self._apply_text_overflow_mode(mode)
        app_settings.save_text_overflow_mode(mode)

    def _refresh_multiline_field_cells(self) -> None:
        """Re-derives every multiline field's (currently just
        Description) displayed cell text for the CURRENT text-overflow
        mode -- whether embedded newlines are collapsed for display
        depends on the mode (see _field_display_text), unlike every
        other field's display text, which doesn't. Always re-read fresh
        from book.metadata rather than transformed from whatever's
        currently shown, so switching Wrap -> Truncate -> Wrap again
        round-trips cleanly instead of needing to "undo" a previous
        collapse. Cheap even for a large library: touches one column,
        not a full rebuild.

        Guarded by _updating_table, same reasoning as _refresh_row_full:
        without it, each item.setText() below fires _on_item_changed,
        which unconditionally writes item.text() back into
        book.metadata AND pushes an undo entry -- silently overwriting
        every book's real Description with the collapsed display text
        the moment the mode changed, not just changing what's shown.
        Real bug, caught by round-tripping Wrap -> Clip -> Wrap in
        test_main_window_table.py and finding the metadata itself had
        changed, not just the cell."""
        col = None
        for i, (key, _label, multiline) in enumerate(FIELDS):
            if key == "description":
                col = FIRST_FIELD_COL + i
                break
        if col is None:
            return
        was_updating = self._updating_table
        self._updating_table = True
        for row in range(self.table.rowCount()):
            book = self._book_for_row(row)
            if book is None:
                continue
            item = self.table.item(row, col)
            if item is not None:
                item.setText(self._field_display_text(book.metadata.description, multiline=True))
        self._updating_table = was_updating

    def _field_display_text(self, value: str, multiline: bool) -> str:
        """Table-cell text for a field value. For a multiline field
        (currently just Description), collapses embedded newlines (and
        any other whitespace runs) to single spaces UNLESS the current
        mode is "wrap" -- Wrap Text's whole point is showing the full
        value, and preserving real paragraph breaks there reads better
        (the same way a spreadsheet's own "wrap text" still respects an
        Alt+Enter line break inside a wrapped cell). In the two
        fixed-row-height modes (Truncate/Clip) collapsing is required,
        not just nicer: Qt renders a literal newline in cell text as a
        real line break regardless of the table's word-wrap setting
        (word wrap only controls whether ONE long line breaks to fit
        the column width, it doesn't suppress newlines already in the
        string) -- without this, a description containing raw HTML with
        embedded newlines between tags could blow a row's height up
        even in a "fixed row height" mode. Only affects what's shown in
        the table; the underlying metadata value (used for editing and
        saving) is untouched."""
        if multiline and self._text_overflow_mode != "wrap":
            return " ".join(value.split())
        return value

    def _populate_row(self, row: int, book: EpubBook) -> None:
        accum = self._perf_accum
        with accum.section("path+filename cells"):
            path_item = QTableWidgetItem(os.path.dirname(book.path))
            path_item.setFlags(path_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            path_item.setToolTip(book.path)
            self.table.setItem(row, PATH_COL, path_item)

            name_item = QTableWidgetItem(os.path.basename(book.path))
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            name_item.setToolTip(book.path)
            name_item.setData(Qt.ItemDataRole.UserRole, book)
            self._filename_item_by_book[book] = name_item
            self.table.setItem(row, FILENAME_COL, name_item)

        with accum.section("cover icon (_apply_cover_icon)"):
            self._apply_cover_icon(name_item, book)

        with accum.section("status cell"):
            status_item = QTableWidgetItem(book.validation_status)
            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, STATUS_COL, status_item)
            self._update_status_cell(row, book)

        if book.load_error:
            with accum.section("load-error row styling"):
                for col in range(self.table.columnCount()):
                    item = self.table.item(row, col) or QTableWidgetItem()
                    item.setBackground(ERROR_COLOR)
                    item.setForeground(HIGHLIGHT_TEXT_COLOR)
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.table.setItem(row, col, item)
                name_item.setToolTip(f"{book.path}\nError: {book.load_error}")
            return

        with accum.section("field cells"):
            for i, (key, _label, multiline) in enumerate(FIELDS):
                col = FIRST_FIELD_COL + i
                value = self._field_display_text(getattr(book.metadata, key, ""), multiline)
                item = NumericTableWidgetItem(value) if key in NUMERIC_FIELD_KEYS else QTableWidgetItem(value)
                self.table.setItem(row, col, item)

        with accum.section("junk cover cell (_update_junk_cover_cell)"):
            junk_item = QTableWidgetItem("")
            junk_item.setFlags(junk_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, JUNK_COVER_COL, junk_item)
            self._junk_cover_item_by_book[book] = junk_item
            self._update_junk_cover_cell(row, book)

        with accum.section("dirty row styling"):
            self._set_row_dirty_style(row, book.dirty)

    def _update_status_cell(self, row: int, book: EpubBook) -> None:
        item = self.table.item(row, STATUS_COL)
        if item is None:
            return
        if book.save_error:
            # Takes priority over the normal validation status -- failing
            # to persist your edits is the more urgent thing to know
            # about, and this flag is exactly what keeps that visible
            # between Save attempts (see _save_books()) rather than only
            # surfacing once, in a dialog, at the moment the save failed.
            item.setText("SAVE FAILED")
            item.setToolTip(f"Could not save this file: {book.save_error}\n\nDouble-click to retry.")
            item.setBackground(SAVE_FAILED_COLOR)
            item.setForeground(HIGHLIGHT_TEXT_COLOR)
            return
        item.setText(book.validation_status)
        item.setToolTip(
            "; ".join(i.message for i in book.validation_issues)
            or "No issues found. Double-click for details."
        )
        color = STATUS_CELL_COLORS.get(book.validation_status)
        if color is not None:
            item.setBackground(color)
            item.setForeground(HIGHLIGHT_TEXT_COLOR)
        else:
            item.setData(Qt.ItemDataRole.BackgroundRole, None)
            item.setData(Qt.ItemDataRole.ForegroundRole, None)

    def _book_is_junk_cover(self, book: EpubBook) -> bool:
        """A book's cover counts as "junk" purely by matching an
        already-flagged cover image byte-for-byte (see EpubBook.cover_hash)
        -- there's no per-book flag to drift out of sync, so flagging (or
        unflagging) one book's cover always correctly covers every other
        loaded book sharing that exact same cover image too."""
        cover_hash = book.cover_hash
        return cover_hash is not None and cover_hash in self._junk_cover_hashes

    def _update_junk_cover_cell(self, row: int, book: EpubBook) -> None:
        """Sets the Junk Cover cell from a cached hash if book's cover
        hasn't changed since it was last hashed, or a neutral (not
        flagged) state plus a background hash request otherwise -- see
        redactor_common.gui.async_hash_cache's module docstring. The
        real result for a genuine miss arrives later, via
        _on_cover_hash_ready(), updating this cell alone. Mirrors
        _apply_cover_icon()'s exact shape for the exact same reason:
        SHA-256-hashing every book's full cover image synchronously,
        once per book, on every table rebuild, is real, avoidable cost
        for a large library."""
        item = self.table.item(row, JUNK_COVER_COL)
        if item is None:
            return
        if not book.cover_bytes:
            self._apply_junk_cover_style(item, False)
            return
        cached = self._cover_hash_cache.get_cached_hash(book, book.cover_bytes)
        if cached is not None:
            book.set_cached_cover_hash(book.cover_bytes, cached)  # keep EpubBook's own sync cache warm too
            self._apply_junk_cover_style(item, cached in self._junk_cover_hashes)
            return
        self._apply_junk_cover_style(item, False)  # neutral until the background hash finishes
        self._cover_hash_cache.request(book, book.cover_bytes, book.cover_bytes)

    def _on_cover_hash_ready(self, book: EpubBook, digest: str) -> None:
        """A background cover hash (queued by _update_junk_cover_cell's
        cache-miss path) has finished. Sets ONLY this book's Junk Cover
        cell, applied directly to the item captured in
        _junk_cover_item_by_book at population time -- same reasoning
        as _on_cover_icon_ready() for not re-deriving the row."""
        if digest:
            book.set_cached_cover_hash(book.cover_bytes, digest)
        item = self._junk_cover_item_by_book.get(book)
        if item is not None:
            self._apply_junk_cover_style(item, bool(digest) and digest in self._junk_cover_hashes)

    @staticmethod
    def _apply_junk_cover_style(item: QTableWidgetItem, is_junk: bool) -> None:
        item.setText("Junk" if is_junk else "")
        if is_junk:
            item.setToolTip(
                "Flagged as a junk cover -- shares its cover image with every other book "
                "flagged this way. See Operations > Regenerate Junk Covers…"
            )
            item.setBackground(JUNK_COVER_COLOR)
            item.setForeground(HIGHLIGHT_TEXT_COLOR)
        else:
            item.setToolTip("")
            item.setData(Qt.ItemDataRole.BackgroundRole, None)
            item.setData(Qt.ItemDataRole.ForegroundRole, None)

    def _on_cell_double_clicked(self, row: int, col: int) -> None:
        if col == FILENAME_COL:
            book = self._book_for_row(row)
            if book is not None and not book.load_error:
                self.rename_single_file(book)
            return
        if col != STATUS_COL:
            return
        book = self._book_for_row(row)
        if book is None:
            return
        if book.save_error:
            reply = QMessageBox.question(
                self, "Retry Save?",
                f"This book failed to save:\n\n{book.save_error}\n\n"
                "Retry saving it now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.retry_save(book)
            return
        self._show_validation_dialog([book])

    def rename_single_file(self, book: EpubBook) -> None:
        """Quick, direct rename of a single book's file on disk -- for
        fixing a typo or small mistake in the filename without going
        through the pattern-based Rename/Export tool. Acts on disk
        immediately (not staged until Save), same as Rename/Export's own
        "rename in place" mode -- and, like that, isn't tracked by Undo,
        which only ever covers in-memory metadata edits, never file
        operations. Triggered by double-clicking a Filename cell, or via
        the table's right-click menu."""
        current_stem = os.path.splitext(os.path.basename(book.path))[0]
        new_stem, ok = QInputDialog.getText(
            self, "Rename File",
            f'New filename for "{os.path.basename(book.path)}" '
            "(the file extension is kept automatically):",
            text=current_stem,
        )
        if not ok:
            return
        new_stem = new_stem.strip()
        if new_stem == current_stem:
            return
        try:
            rename_book_file(book, new_stem)
        except (ValueError, FileExistsError, OSError) as exc:
            QMessageBox.warning(self, "Could not rename", str(exc))
            return
        self._refresh_row_full(book)
        self._refresh_status()

    def rename_selected_file(self) -> None:
        """F2 entry point (Explorer convention: select one item, press
        F2, rename it directly) -- same guard the right-click "Rename
        File…" item uses (exactly one book selected, no load error,
        via _currently_selected_books()), since F2 and that menu item
        are the same action reached two ways."""
        selected = self._currently_selected_books()
        if len(selected) == 1:
            self.rename_single_file(selected[0])

    def _apply_cover_icon(self, item: QTableWidgetItem, book: EpubBook) -> None:
        """Sets item's icon from book.cover_bytes -- from cache if
        book's cover hasn't changed since it was last computed
        (checked by identity, not content: cover_bytes is reassigned,
        never mutated in place, whenever a cover actually changes, so
        `is` is enough and never re-hashes potentially large image
        bytes on every rebuild), or a blank placeholder immediately
        plus a background decode request otherwise -- see
        redactor_common.gui.async_icon_cache's module docstring. The
        real icon for a genuine miss arrives later, via
        _on_cover_icon_ready(), updating this cell alone."""
        if not book.cover_bytes:
            item.setIcon(QIcon())
            return
        cached = self._cover_icon_cache.get_cached_icon(book, book.cover_bytes)
        if cached is not None:
            item.setIcon(cached)
            return
        item.setIcon(QIcon())
        self._cover_icon_cache.request(book, book.cover_bytes, book.cover_bytes)

    def _on_cover_icon_ready(self, book: EpubBook, icon: QIcon) -> None:
        """A background cover decode (queued by _apply_cover_icon's
        cache-miss path) has finished. Sets ONLY this book's icon, never
        a rebuild, never any other cell. Applied directly to the item
        object captured in _filename_item_by_book at population time,
        not re-looked-up by row -- Qt's own column-sort reorders items
        between rows without any callback into this project's code, but
        the ITEM object itself is the same object throughout a sort (Qt
        moves item pointers between row slots, it doesn't recreate
        them), so setIcon() on the captured reference always lands on
        whichever row this book currently occupies, correctly, without
        needing to re-derive that row at all."""
        item = self._filename_item_by_book.get(book)
        if item is not None:
            item.setIcon(icon)

    def _set_row_dirty_style(self, row: int, dirty: bool) -> None:
        for col in range(self.table.columnCount()):
            if col == STATUS_COL:
                continue  # keeps its own OK/ISSUES/INVALID color, set by _update_status_cell
            item = self.table.item(row, col)
            if item is None:
                continue
            if dirty:
                item.setBackground(DIRTY_COLOR)
                item.setForeground(HIGHLIGHT_TEXT_COLOR)
            else:
                # Clear any override entirely (pass None, not an empty
                # QBrush -- QBrush()'s default color is black, which
                # would silently force black text regardless of theme).
                # With no override at all, the item falls back to
                # whatever the current theme's normal colors are.
                item.setData(Qt.ItemDataRole.BackgroundRole, None)
                item.setData(Qt.ItemDataRole.ForegroundRole, None)

    # ------------------------------------------------------------------
    # Editing
    # ------------------------------------------------------------------

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating_table:
            return
        row = item.row()
        col = item.column()
        if col in (PATH_COL, FILENAME_COL, STATUS_COL, JUNK_COVER_COL):
            return
        book = self._book_for_row(row)
        if book is None or book.load_error:
            return
        key, label, _multiline = FIELDS[col - FIRST_FIELD_COL]
        self._push_undo(f"Edit {label}", [book])
        book.apply_metadata({key: item.text()})
        self._set_row_dirty_style(row, book.dirty)
        self._refresh_status()

    def _on_selection_changed(self) -> None:
        books = self._currently_selected_books()
        self.tag_panel.set_selection(books)
        # Reflects/acts on the FIRST selected book, same "first of N"
        # convention the cover preview itself uses for a mixed selection.
        self.tag_panel.set_cover_junk_flagged(bool(books) and self._book_is_junk_cover(books[0]))

    def _apply_bulk_edit(self, values: dict) -> None:
        books = self._currently_selected_books()
        if not books:
            # Can normally only happen now via save_changed()/save_as_copies()
            # calling tag_panel.apply_bulk_edit() proactively -- the toolbar
            # Apply action itself is disabled whenever nothing's selected,
            # so this guards against a spurious no-op undo entry in that case.
            return
        self._push_undo("Bulk edit", books)
        self._updating_table = True
        was_sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)  # keep row positions stable mid-loop
        rows_by_book = self._rows_by_book()
        for book in books:
            book.apply_metadata(values)
            row = rows_by_book.get(book)
            if row is None:
                continue
            for i, (key, _label, multiline) in enumerate(FIELDS):
                if key in values:
                    col = FIRST_FIELD_COL + i
                    item = self.table.item(row, col)
                    if item is not None:
                        item.setText(self._field_display_text(getattr(book.metadata, key, ""), multiline))
            self._set_row_dirty_style(row, book.dirty)
        self.table.setSortingEnabled(was_sorting)
        self._updating_table = False
        self._refresh_status()

    # ------------------------------------------------------------------
    # Search & Replace
    # ------------------------------------------------------------------

    def open_search_replace_dialog(self) -> None:
        target_books = self._selection_or_all_books()
        if not target_books:
            QMessageBox.information(
                self, "No books", "Load some books first (or select the ones to search)."
            )
            return

        dialog = SearchReplaceDialog(target_books, self)
        if dialog.exec() != SearchReplaceDialog.DialogCode.Accepted:
            return

        field_key = dialog.result_field_key()
        changes = dialog.accepted_changes()  # index in target_books -> new value
        if not changes:
            return

        if field_key == FILENAME_FIELD_KEY:
            self._apply_filename_search_replace(target_books, changes)
        else:
            affected_books = [target_books[i] for i in changes]
            self._push_undo("Search & Replace", affected_books)
            for i, new_value in changes.items():
                target_books[i].apply_metadata({field_key: new_value})
            self._refresh_rows_full(affected_books)
            self._refresh_status()
            self._on_selection_changed()  # bulk-edit panel may be showing a field this just changed

    def _apply_filename_search_replace(self, books: list[EpubBook], changes: dict[int, str]) -> None:
        """Filename changes are physical renames, same mechanics as
        Rename/Export -- and, like that feature, deliberately NOT covered
        by Undo (see core/undo.py)."""
        taken: set[str] = set()
        errors: list[tuple[str, str]] = []
        succeeded = 0
        for i, new_filename in changes.items():
            book = books[i]
            try:
                stem, ext = os.path.splitext(new_filename)
                directory = os.path.dirname(book.path)
                new_path = unique_path(directory, stem, ext or ".epub", taken)
                os.rename(book.path, new_path)
                book.path = new_path
                taken.add(os.path.normcase(os.path.abspath(new_path)))
                succeeded += 1
            except OSError as exc:
                errors.append((book.path, str(exc)))

        self._rebuild_table()
        self._refresh_status()
        total = len(changes)
        if not errors:
            QMessageBox.information(self, "Done", f"Renamed {succeeded} of {total} file(s).")
        else:
            details = "\n".join(f"- {os.path.basename(p)}: {err}" for p, err in errors)
            QMessageBox.warning(
                self, "Some files failed",
                f"{succeeded} of {total} succeeded.\n\nFailed:\n{details}",
            )

    # ------------------------------------------------------------------
    # Cover image
    # ------------------------------------------------------------------

    def on_cover_add_replace(self) -> None:
        books = self._currently_selected_books()
        if not books:
            QMessageBox.information(
                self, "No books selected", "Select at least one book first."
            )
            return
        start_dir = app_settings.load_last_directory()
        path, _filter = QFileDialog.getOpenFileName(self, "Choose Cover Image", start_dir, IMAGE_FILE_FILTER)
        if not path:
            return
        app_settings.save_last_directory(path)
        try:
            with open(path, "rb") as f:
                image_bytes = f.read()
        except OSError as exc:
            QMessageBox.warning(self, "Couldn't read image", str(exc))
            return
        mime = mimetypes.guess_type(path)[0] or "image/jpeg"

        self._push_undo("Change cover", books)
        for book in books:
            book.set_cover(image_bytes, mime)
        self._refresh_affected_rows(books)

    def on_cover_generate(self) -> None:
        """The panel's own "Generate" button -- applies directly to the
        current table selection, same immediacy as Add/Replace and
        Delete right next to it (you're already looking at the live
        cover preview, so there's nothing a separate preview step would
        add here). For generating across many books at once with a
        review table first, see Operations -> Generate Cover from
        Metadata instead (gui/cover_generator_dialog.py)."""
        books = self._currently_selected_books()
        if not books:
            QMessageBox.information(
                self, "No books selected", "Select at least one book first."
            )
            return
        self._push_undo("Generate cover from metadata", books)
        for book in books:
            m = book.metadata
            image_bytes = generate_cover_image(m.title, m.authors_str, m.series, m.series_index)
            book.set_cover(image_bytes, "image/png")
        self._refresh_affected_rows(books)

    def on_cover_delete(self) -> None:
        books = self._currently_selected_books()
        if not books:
            QMessageBox.information(
                self, "No books selected", "Select at least one book first."
            )
            return
        self._push_undo("Delete cover", books)
        for book in books:
            book.remove_cover()
        self._refresh_affected_rows(books)

    def on_cover_toggle_junk(self) -> None:
        """The cover preview panel's Junk button -- which direction to go
        is decided from the FIRST selected book's current flagged state
        (same "first of N" convention the preview itself uses), then
        applied via the same flag/unflag methods the table right-click
        uses, which already act on the whole current selection."""
        books = self._currently_selected_books()
        if not books:
            QMessageBox.information(
                self, "No books selected", "Select at least one book first."
            )
            return
        if self._book_is_junk_cover(books[0]):
            self.unflag_selected_covers_as_junk()
        else:
            self.flag_selected_covers_as_junk()

    def _refresh_affected_rows(self, books: list[EpubBook]) -> None:
        # Guards the Junk Cover cell's item.setText() below the same way
        # _refresh_row_full() does -- without it, _on_item_changed would
        # treat it as a user edit and push a bogus undo entry.
        was_updating = self._updating_table
        self._updating_table = True
        was_sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        rows_by_book = self._rows_by_book()
        for book in books:
            row = rows_by_book.get(book)
            if row is None:
                continue
            item = self.table.item(row, FILENAME_COL)
            if item is not None:
                self._apply_cover_icon(item, book)
            self._set_row_dirty_style(row, book.dirty)
            self._update_junk_cover_cell(row, book)  # cover just changed -- its hash may have too
        self.table.setSortingEnabled(was_sorting)
        self._updating_table = was_updating
        self._refresh_status()
        self._on_selection_changed()  # refresh the cover preview panel too

    # ------------------------------------------------------------------
    # Junk Cover flag (table right-click) / Regenerate Junk Covers (Operations)
    # ------------------------------------------------------------------

    def flag_selected_covers_as_junk(self) -> None:
        """Flags every SELECTED book's cover image as junk -- and, because
        the flag lives on the cover's hash rather than any one book, that
        immediately flags every OTHER loaded book sharing that exact same
        cover image too, whether or not it's currently selected. Not
        pushed to Undo: this isn't an edit to a book's own content, just
        a standing note about a cover image (persisted the same way as a
        column width or a custom genre, see app_settings.py), so it
        doesn't dirty the book or need saving."""
        books = self._currently_selected_books()
        new_hashes = {b.cover_hash for b in books if b.cover_hash is not None}
        if not new_hashes:
            QMessageBox.information(
                self, "No cover to flag", "None of the selected book(s) have a cover to flag."
            )
            return
        self._junk_cover_hashes |= new_hashes
        app_settings.save_junk_cover_hashes(self._junk_cover_hashes)
        self._refresh_all_junk_cover_cells()
        self._on_selection_changed()  # cover preview panel's Junk button may need to flip to "Unflag"

    def unflag_selected_covers_as_junk(self) -> None:
        """The exact inverse of flag_selected_covers_as_junk() above --
        same reasoning applies in reverse: unflagging any one book whose
        cover is currently flagged un-flags every other book sharing that
        exact cover image too."""
        books = self._currently_selected_books()
        hashes_to_clear = {b.cover_hash for b in books if b.cover_hash is not None}
        if not hashes_to_clear:
            return
        self._junk_cover_hashes -= hashes_to_clear
        app_settings.save_junk_cover_hashes(self._junk_cover_hashes)
        self._refresh_all_junk_cover_cells()
        self._on_selection_changed()  # cover preview panel's Junk button may need to flip to "Flag"

    def _refresh_all_junk_cover_cells(self) -> None:
        """Re-checks every loaded book's Junk Cover cell against the
        current flagged-hash set. Unlike _refresh_affected_rows(), this
        has to cover every loaded book, not just the ones just acted on --
        flagging (or unflagging) one book's cover can affect every OTHER
        book that happens to share the exact same cover image."""
        was_updating = self._updating_table
        self._updating_table = True
        was_sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        rows_by_book = self._rows_by_book()
        for book in self.books:
            row = rows_by_book.get(book)
            if row is not None:
                self._update_junk_cover_cell(row, book)
        self.table.setSortingEnabled(was_sorting)
        self._updating_table = was_updating

    def open_regenerate_junk_covers_dialog(self) -> None:
        """Operations menu batch version of the table right-click's Flag
        Cover as Junk -- runs the exact same Generate Cover from Metadata
        preview/apply flow as Operations > Generate Cover from Metadata
        (gui/cover_generator_dialog.py), just pre-filtered to books
        currently flagged, rather than the current selection."""
        target_books: list[EpubBook] = []

        def _step(book: EpubBook, _index: int) -> None:
            if not book.load_error and self._book_is_junk_cover(book):
                target_books.append(book)

        run_with_progress(
            self, self.books, _step, "Checking flagged covers…",
            cancellable=False, update_every=25,
        )
        if not target_books:
            QMessageBox.information(
                self, "No junk covers flagged",
                "No loaded books are currently flagged as junk covers. Right-click a book "
                "with a junk cover and choose \"Flag Cover as Junk\" first.",
            )
            return

        dialog = CoverGeneratorDialog(target_books, self)
        if dialog.exec() != CoverGeneratorDialog.DialogCode.Accepted:
            return

        covers = dialog.accepted_covers()  # book index -> (image_bytes, mime)
        if not covers:
            return

        affected_books = [dialog.books[i] for i in covers]
        self._push_undo("Regenerate junk covers", affected_books)
        for i, (image_bytes, mime) in covers.items():
            dialog.books[i].set_cover(image_bytes, mime)
        self._refresh_affected_rows(affected_books)

    # ------------------------------------------------------------------
    # Remove / clear / delete / refresh
    # ------------------------------------------------------------------

    def remove_selected(self) -> None:
        to_remove = self._books_for_rows(self._selected_rows(), exclude_errors=False)
        if not to_remove:
            return
        self.books = [b for b in self.books if b not in to_remove]
        self._rebuild_table()
        self._refresh_status()

    def clear_list(self) -> None:
        if not self.books:
            return
        if self._count_dirty() and not self._confirm_discard("clear the list"):
            return
        self.books = []
        self._rebuild_table()
        self._refresh_status()

    def delete_files(self) -> None:
        """Sends the selected books' files to the Recycle Bin (recoverable,
        not a permanent delete) and removes them from the list. Requires
        the send2trash package (in requirements.txt)."""
        to_delete = self._books_for_rows(self._selected_rows(), exclude_errors=False)
        if not to_delete:
            QMessageBox.information(self, "No books selected", "Select at least one book to delete.")
            return
        if send2trash is None:
            QMessageBox.warning(
                self, "Can't delete files",
                "The send2trash package isn't installed. Run:\n\n"
                "    pip install -r requirements.txt\n\n"
                "and restart the app.",
            )
            return

        preview = "\n".join(f"- {os.path.basename(b.path)}" for b in to_delete[:10])
        if len(to_delete) > 10:
            preview += f"\n...and {len(to_delete) - 10} more"
        reply = QMessageBox.question(
            self,
            "Delete Files?",
            f"Send {len(to_delete)} file(s) to the Recycle Bin?\n\n{preview}\n\n"
            "This removes them from disk (recoverable from the Recycle Bin) "
            "and from this list.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        deleted: list[EpubBook] = []
        errors: list[tuple[str, str]] = []
        for book in to_delete:
            try:
                send2trash.send2trash(book.path)
                deleted.append(book)
            except Exception as exc:  # noqa: BLE001 - surface any OS/trash error, don't crash
                errors.append((book.path, str(exc)))

        self.books = [b for b in self.books if b not in deleted]
        self._rebuild_table()
        self._refresh_status()

        if errors:
            details = "\n".join(f"- {os.path.basename(p)}: {err}" for p, err in errors)
            QMessageBox.warning(
                self, "Some files failed to delete",
                f"{len(deleted)} of {len(to_delete)} sent to the Recycle Bin.\n\nFailed:\n{details}",
            )
        else:
            QMessageBox.information(self, "Deleted", f"Sent {len(deleted)} file(s) to the Recycle Bin.")

    def refresh_list(self) -> None:
        """Re-scans the folders your currently-loaded books live in
        (picking up new files added there since you loaded), then
        re-reads metadata for everything still present. The previous
        version only re-read the exact same files already in the list --
        if nothing about those specific files had changed on disk, the
        table redrew identically and could look like the button did
        nothing, even when it had genuinely just found no changes.

        Doesn't discover a brand-new subfolder you haven't loaded
        anything from yet (only folders already represented in your
        current list get scanned, non-recursively) -- use Load Folder
        for that. A file that's disappeared from disk isn't silently
        dropped from the list either; it shows up as a load error on its
        row, same as any other unreadable file, rather than vanishing
        without a trace.

        Discards unsaved in-memory edits (with confirmation first) and
        clears the undo stack, since its entries would reference book
        objects this replaces."""
        if not self.books:
            return
        if self._count_dirty() and not self._confirm_discard(
            "refresh the list (discarding unsaved changes)"
        ):
            return

        existing_paths = [os.path.normpath(b.path) for b in self.books]
        seen = set(existing_paths)
        folders = {os.path.dirname(p) for p in existing_paths}
        new_paths = []
        for folder in folders:
            for path in self._find_epubs_in_folder(folder, recursive=False):
                normalized = os.path.normpath(path)
                if normalized not in seen:
                    new_paths.append(normalized)
                    seen.add(normalized)
        new_paths.sort()

        self.books = [EpubBook(p) for p in existing_paths + new_paths]
        self.undo_manager = UndoManager(max_entries=UNDO_MAX_ENTRIES)
        self.undo_act.setEnabled(False)
        self._rebuild_table()
        self._refresh_status()
        self._on_selection_changed()  # old selection referenced now-replaced book objects

        if new_paths:
            QMessageBox.information(
                self, "Refreshed", f"Found {len(new_paths)} new file(s) and reloaded everything else."
            )
        else:
            QMessageBox.information(self, "Refreshed", "No new files found. Reloaded everything from disk.")

    # ------------------------------------------------------------------
    # Saving
    # ------------------------------------------------------------------

    def save_changed(self) -> None:
        # Apply whatever's currently ticked/typed in the bulk-edit panel
        # first -- otherwise a pending panel edit that was never explicitly
        # Applied would be silently invisible to Save, since typing into a
        # field only stages it in the panel, it doesn't touch the book's
        # actual in-memory metadata until Apply runs. Safe to call
        # unconditionally: it's a no-op if nothing's checked, or if nothing
        # is currently selected in the table (see _apply_bulk_edit's guard).
        self.tag_panel.apply_bulk_edit()

        all_dirty = [b for b in self.books if b.dirty and not b.load_error]
        # Books that already failed to save last time are excluded from
        # this automatic sweep -- some causes (a path that's simply too
        # long for Windows, for instance) are permanent properties of
        # the file, not transient problems, so blindly re-attempting
        # them on every single Save click just repeats the same failure
        # forever with no way to make progress. They're still flagged
        # "SAVE FAILED" in the Status column the whole time (see
        # _update_status_cell), and double-clicking that cell retries
        # just that one book explicitly once you believe the underlying
        # problem is actually fixed.
        dirty_books = [b for b in all_dirty if not b.save_error]
        previously_failed = len(all_dirty) - len(dirty_books)

        if not dirty_books:
            if previously_failed:
                QMessageBox.information(
                    self, "Nothing to save",
                    f"{previously_failed} book(s) still have unsaved changes, but already "
                    "failed to save and are being skipped to avoid repeating the same "
                    "error. Double-click a book's \"SAVE FAILED\" status to retry it "
                    "once you believe the problem is fixed.",
                )
            else:
                QMessageBox.information(self, "Nothing to save", "No unsaved changes.")
            return

        reply = QMessageBox.question(
            self,
            "Overwrite original files?",
            f"This will overwrite {len(dirty_books)} original EPUB file(s) in place.\n"
            "This cannot be undone. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        errors = self._save_books(dirty_books, output_folder=None)
        self._rebuild_table()
        self._refresh_status()
        self._on_selection_changed()  # panel could be showing stale data from before this save
        self._report_save_result(len(dirty_books), errors, in_place=True)

    def retry_save(self, book: EpubBook) -> None:
        """Explicitly retries saving one book that previously failed --
        the one case where re-attempting a save_error book IS wanted,
        bypassing save_changed()'s automatic skip. Triggered by
        double-clicking a "SAVE FAILED" status cell (see
        _on_cell_double_clicked)."""
        errors = self._save_books([book], output_folder=None)
        self._refresh_row_full(book)
        self._refresh_status()
        self._on_selection_changed()
        self._report_save_result(1, errors, in_place=True)

    def save_as_copies(self) -> None:
        # Same reasoning as save_changed() -- apply pending panel edits
        # first, so "Save As Copy" can't silently export without them either.
        self.tag_panel.apply_bulk_edit()

        changed_books = [b for b in self.books if not b.load_error]
        if not changed_books:
            QMessageBox.information(self, "Nothing to save", "No books loaded.")
            return
        folder = QFileDialog.getExistingDirectory(self, "Choose Output Folder")
        if not folder:
            return
        errors = self._save_books(changed_books, output_folder=folder)
        self._rebuild_table()
        self._refresh_status()
        self._on_selection_changed()  # panel could be showing stale data from before this save
        self._report_save_result(len(changed_books), errors, in_place=False)

    def _save_books(self, books: list[EpubBook], output_folder: str | None) -> list[tuple[str, str]]:
        errors: list[tuple[str, str]] = []

        def _step(book: EpubBook, _index: int) -> None:
            try:
                if output_folder:
                    out_path = os.path.join(output_folder, os.path.basename(book.path))
                    book.save(out_path)
                    # Save As Copy doesn't touch this book's own file, so
                    # a past save_error here (from an earlier in-place
                    # save attempt) says nothing about whether THIS book
                    # is still a problem -- leave it as-is either way.
                else:
                    book.save()
                    # Re-check against what's actually on disk now -- confirms
                    # any fixes (or the always-promised mimetype correction)
                    # really took effect, rather than trusting the pre-save
                    # snapshot. Only meaningful for the in-place overwrite:
                    # a "Save As Copy" doesn't change this book's own file,
                    # so its validation status is unaffected either way.
                    book.revalidate()
                    book.save_error = ""
            except (EpubError, OSError) as exc:
                message = describe_save_error(exc)
                errors.append((book.path, message))
                if not output_folder:
                    book.save_error = message
            except Exception:  # noqa: BLE001 - surface unexpected errors, don't crash
                message = traceback.format_exc(limit=2)
                errors.append((book.path, message))
                if not output_folder:
                    book.save_error = message

        label = "Saving copies…" if output_folder else "Saving books…"
        run_with_progress(
            self, books, _step, label,
            threshold=LOAD_PROGRESS_THRESHOLD,
            label_for=lambda book: f"Saving: {os.path.basename(book.path)}",
        )
        return errors

    def _report_save_result(self, attempted: int, errors: list[tuple[str, str]], in_place: bool) -> None:
        if not errors:
            QMessageBox.information(self, "Saved", f"Successfully saved {attempted} file(s).")
            return
        details = "\n".join(f"- {os.path.basename(p)}: {err}" for p, err in errors)
        flag_note = (
            "\n\nFailed file(s) are now flagged \"SAVE FAILED\" in the Status column "
            "(hover for the error) so you don't need to re-save everything just to "
            "see this again."
            if in_place else ""
        )
        QMessageBox.warning(
            self,
            "Some files failed to save",
            f"{attempted - len(errors)} of {attempted} saved successfully.\n\n"
            f"Failed:\n{details}{flag_note}",
        )

    # ------------------------------------------------------------------
    # Rename / export by metadata pattern
    # ------------------------------------------------------------------

    def open_rename_dialog(self) -> None:
        target_books = self._selection_or_all_books()
        if not target_books:
            QMessageBox.information(
                self, "No books", "Load some books first (or select the ones to rename)."
            )
            return

        dialog = RenameDialog(target_books, self)
        if dialog.exec() != RenameDialog.DialogCode.Accepted:
            return

        self.perform_rename_export(
            books=target_books,
            pattern=dialog.result_pattern(),
            zero_pad=dialog.result_zero_pad(),
            mode=dialog.result_mode(),
            output_folder=dialog.result_output_folder(),
        )

    def perform_rename_export(
        self,
        books: list[EpubBook],
        pattern: str,
        zero_pad: bool,
        mode: str,
        output_folder: str | None,
    ) -> None:
        """Rename in place, or export renamed copies.

        For "rename in place": a book with unsaved metadata edits is saved
        first, so the new filename always matches what's actually inside
        the file, not a stale on-disk value.

        For "export": EpubBook.save(new_path) already writes the book's
        *current* in-memory metadata into the new file regardless of the
        dirty flag, and (per the fix above) does not disturb the original
        book's own path/dirty state -- so exporting never touches originals.

        Note: physical rename/export is deliberately NOT covered by Undo
        -- see core/undo.py.
        """
        taken: set[str] = set()
        errors: list[tuple[str, str]] = []
        succeeded = 0

        for book in books:
            try:
                old_name = os.path.basename(book.path)
                stem = render_filename(
                    book.metadata, pattern, zero_pad,
                    fallback=os.path.splitext(old_name)[0],
                )

                if mode == "export":
                    new_path = unique_path(output_folder, stem, ".epub", taken)
                    book.save(new_path)
                else:
                    if book.dirty:
                        book.save()  # embed current metadata before renaming
                    directory = os.path.dirname(book.path)
                    new_path = unique_path(directory, stem, ".epub", taken)
                    os.rename(book.path, new_path)
                    book.path = new_path

                taken.add(os.path.normcase(os.path.abspath(new_path)))
                succeeded += 1
            except (EpubError, OSError) as exc:
                errors.append((book.path, str(exc)))

        self._rebuild_table()
        self._refresh_status()

        total = len(books)
        if not errors:
            verb = "Exported" if mode == "export" else "Renamed"
            QMessageBox.information(self, "Done", f"{verb} {succeeded} of {total} file(s).")
        else:
            details = "\n".join(f"- {os.path.basename(p)}: {err}" for p, err in errors)
            QMessageBox.warning(
                self,
                "Some files failed",
                f"{succeeded} of {total} succeeded.\n\nFailed:\n{details}",
            )

    # ------------------------------------------------------------------
    # Google Books lookup
    # ------------------------------------------------------------------

    def open_google_books_dialog(self) -> None:
        target_books = self._selection_or_all_books()
        if not target_books:
            QMessageBox.information(
                self, "No books", "Load some books first (or select the ones to look up)."
            )
            return

        dialog = GoogleBooksDialog(target_books, self)
        if dialog.exec() != GoogleBooksDialog.DialogCode.Accepted:
            return

        metadata_changes = dialog.accepted_metadata()  # row index -> {field_key: value}
        cover_changes = dialog.accepted_covers()  # row index -> (image_bytes, mime)
        if not metadata_changes and not cover_changes:
            return

        # Per-field review before anything is actually applied -- covers
        # are a separate, visual thing (not reviewed field-by-field
        # here), only the text metadata goes through this. Skips itself
        # entirely if nothing found would overwrite an existing,
        # different value; see resolve_overwrite_conflicts()'s own
        # docstring. None means the user cancelled the review outright,
        # which aborts applying the cover changes too, not just metadata.
        if metadata_changes:
            metadata_changes = resolve_overwrite_conflicts(self, target_books, metadata_changes, _field_label)
            if metadata_changes is None:
                return
        if not metadata_changes and not cover_changes:
            return

        affected_rows = set(metadata_changes) | set(cover_changes)
        affected_books = [target_books[row] for row in affected_rows]
        self._push_undo("Import metadata from Google Books", affected_books)
        for row, fields in metadata_changes.items():
            target_books[row].apply_metadata(fields)
        for row, (image_bytes, mime) in cover_changes.items():
            target_books[row].set_cover(image_bytes, mime)
        self._refresh_rows_full(affected_books)

        self._refresh_status()
        self._on_selection_changed()  # bulk-edit panel may be showing a field this just changed
        QMessageBox.information(
            self, "Applied",
            f"Applied Google Books data to {len(affected_books)} book(s). Remember to save.",
        )

    # ------------------------------------------------------------------
    # Validation / fixes
    # ------------------------------------------------------------------

    def open_validation_dialog(self) -> None:
        target_books = self._selection_or_all_books()
        if not target_books:
            QMessageBox.information(
                self, "No books", "Load some books first (or select the ones to validate)."
            )
            return
        self._show_validation_dialog(target_books)

    def _show_validation_dialog(self, books: list[EpubBook]) -> None:
        """Shared by the toolbar action (selection/all) and double-clicking
        a single book's Status cell. apply_fixes() is deliberately NOT
        pushed to Undo -- see EpubBook.apply_fixes for why."""
        dialog = ValidationDialog(books, self)
        dialog.exec()  # fixes (if any) are applied live inside the dialog
        self._refresh_rows_full(books)
        self._refresh_status()
        self._on_selection_changed()  # a language/id fix can affect a bulk-edit panel field

    # ------------------------------------------------------------------
    # Parse filename -> metadata
    # ------------------------------------------------------------------

    def open_filename_parse_dialog(self) -> None:
        target_books = self._selection_or_all_books()
        if not target_books:
            QMessageBox.information(
                self, "No books", "Load some books first (or select the ones to parse)."
            )
            return

        dialog = FilenameParseDialog(target_books, self)
        if dialog.exec() != FilenameParseDialog.DialogCode.Accepted:
            return

        changes = dialog.accepted_changes()  # book index -> {field_key: value}
        if not changes:
            return

        affected_books = [target_books[i] for i in changes]
        self._push_undo("Parse filename to metadata", affected_books)
        for i, field_values in changes.items():
            target_books[i].apply_metadata(field_values)
        self._refresh_rows_full(affected_books)
        self._refresh_status()
        self._on_selection_changed()  # bulk-edit panel was showing stale data for these fields

    # ------------------------------------------------------------------
    # Scan content for metadata
    # ------------------------------------------------------------------

    def open_content_scan_dialog(self) -> None:
        target_books = self._selection_or_all_books()
        if not target_books:
            QMessageBox.information(
                self, "No books", "Load some books first (or select the ones to scan)."
            )
            return

        dialog = ContentScanDialog(target_books, self)
        if dialog.exec() != ContentScanDialog.DialogCode.Accepted:
            return

        changes = dialog.accepted_changes()  # book index -> {field_key: value}
        if not changes:
            return

        affected_books = [target_books[i] for i in changes]
        self._push_undo("Scan content for metadata", affected_books)
        for i, field_values in changes.items():
            target_books[i].apply_metadata(field_values)
        self._refresh_rows_full(affected_books)
        self._refresh_status()
        self._on_selection_changed()  # bulk-edit panel was showing stale data for these fields
        QMessageBox.information(
            self, "Applied", f"Applied scanned metadata to {len(changes)} book(s). Remember to save."
        )

    # ------------------------------------------------------------------
    # Look up via Calibre
    # ------------------------------------------------------------------

    def open_calibre_lookup_dialog(self) -> None:
        target_books = self._selection_or_all_books()
        if not target_books:
            QMessageBox.information(
                self, "No books", "Load some books first (or select the ones to look up)."
            )
            return

        dialog = CalibreLookupDialog(target_books, self)
        if dialog.exec() != CalibreLookupDialog.DialogCode.Accepted:
            return

        changes = dialog.accepted_changes()  # book index -> {field_key: value}
        if not changes:
            return

        # Per-field review before anything is actually applied -- skips
        # itself entirely if nothing found would overwrite an existing,
        # different value; see resolve_overwrite_conflicts()'s own
        # docstring. Returns None if the user cancelled outright.
        changes = resolve_overwrite_conflicts(self, target_books, changes, _field_label)
        if changes is None:
            return
        if not changes:
            return

        affected_books = [target_books[i] for i in changes]
        self._push_undo("Look up via Calibre", affected_books)
        for i, field_values in changes.items():
            target_books[i].apply_metadata(field_values)
        self._refresh_rows_full(affected_books)
        self._refresh_status()
        self._on_selection_changed()  # bulk-edit panel was showing stale data for these fields
        QMessageBox.information(
            self, "Applied", f"Applied Calibre metadata to {len(changes)} book(s). Remember to save."
        )

    # ------------------------------------------------------------------
    # Case Conversion
    # ------------------------------------------------------------------

    def open_case_conversion_dialog(self) -> None:
        target_books = self._selection_or_all_books()
        if not target_books:
            QMessageBox.information(
                self, "No books", "Load some books first (or select the ones to convert)."
            )
            return

        dialog = CaseConversionDialog(target_books, self)
        if dialog.exec() != CaseConversionDialog.DialogCode.Accepted:
            return

        changes = dialog.accepted_changes()  # book index -> new value
        if not changes:
            return

        field_key = dialog.result_field_key()
        affected_books = [target_books[i] for i in changes]
        self._push_undo("Case conversion", affected_books)
        for i, new_value in changes.items():
            target_books[i].apply_metadata({field_key: new_value})
        self._refresh_rows_full(affected_books)
        self._refresh_status()
        self._on_selection_changed()  # bulk-edit panel may be showing the field this just changed

    # ------------------------------------------------------------------
    # Strip HTML from Description
    # ------------------------------------------------------------------

    def open_strip_description_html_dialog(self) -> None:
        target_books = self._selection_or_all_books()
        if not target_books:
            QMessageBox.information(
                self, "No books", "Load some books first (or select the ones to check)."
            )
            return

        dialog = StripDescriptionHtmlDialog(target_books, self)
        if dialog.exec() != StripDescriptionHtmlDialog.DialogCode.Accepted:
            return

        changes = dialog.accepted_changes()  # book index -> new (stripped) description
        if not changes:
            return

        affected_books = [target_books[i] for i in changes]
        self._push_undo("Strip HTML from Description", affected_books)
        for i, new_value in changes.items():
            target_books[i].apply_metadata({"description": new_value})
        self._refresh_rows_full(affected_books)
        self._refresh_status()
        self._on_selection_changed()

    # ------------------------------------------------------------------
    # Author Sort Conversion
    # ------------------------------------------------------------------

    def open_author_sort_dialog(self) -> None:
        target_books = self._selection_or_all_books()
        if not target_books:
            QMessageBox.information(
                self, "No books", "Load some books first (or select the ones to convert)."
            )
            return

        dialog = AuthorSortDialog(target_books, self)
        if dialog.exec() != AuthorSortDialog.DialogCode.Accepted:
            return

        changes = dialog.accepted_changes()  # book index -> new value
        if not changes:
            return

        field_key = dialog.result_field_key()
        affected_books = [target_books[i] for i in changes]
        self._push_undo("Author Sort conversion", affected_books)
        for i, new_value in changes.items():
            target_books[i].apply_metadata({field_key: new_value})
        self._refresh_rows_full(affected_books)
        self._refresh_status()
        self._on_selection_changed()  # bulk-edit panel may be showing the field this just changed

    # ------------------------------------------------------------------
    # Rebuild Manifest
    # ------------------------------------------------------------------

    def open_manifest_rebuild_dialog(self) -> None:
        target_books = self._selection_or_all_books()
        if not target_books:
            QMessageBox.information(
                self, "No books", "Load some books first (or select the ones to check)."
            )
            return

        dialog = ManifestRebuildDialog(target_books, self)
        if dialog.exec() != ManifestRebuildDialog.DialogCode.Accepted:
            return

        indices = dialog.accepted_book_indices()
        if not indices:
            return

        # rebuild_manifest() acts directly on the book, similar to
        # apply_fixes() -- not pushed to Undo, same convention and same
        # reasoning: a structural repair, not user-authored content. The
        # dialog's own upfront confirmation (listing exactly what will
        # be removed) is the safeguard here instead.
        affected_books = [dialog.books[i] for i in indices]
        total_removed = 0
        for book in affected_books:
            total_removed += len(book.rebuild_manifest())
        self._refresh_rows_full(affected_books)
        self._refresh_status()
        self._on_selection_changed()
        QMessageBox.information(
            self, "Manifest Rebuilt",
            f"Removed {total_removed} broken manifest reference(s) across "
            f"{len(affected_books)} book(s). Remember to save.",
        )

    # ------------------------------------------------------------------
    # Compress Images (Lossy)
    # ------------------------------------------------------------------

    def open_compress_images_dialog(self) -> None:
        target_books = self._selection_or_all_books()
        if not target_books:
            QMessageBox.information(
                self, "No books", "Load some books first (or select the ones to compress)."
            )
            return

        dialog = CompressImagesDialog(target_books, self)
        if dialog.exec() != CompressImagesDialog.DialogCode.Accepted:
            return

        indices = dialog.accepted_book_indices()
        if not indices:
            return

        quality = dialog.quality()
        affected_books = [dialog.books[i] for i in indices]
        self._push_undo("Compress images (lossy)", affected_books)

        totals = {"compressed": 0, "skipped": 0, "original_bytes": 0, "new_bytes": 0}

        def _step(book: EpubBook, _index: int) -> None:
            for archive_path, _size in book.find_compressible_images():
                data = book.read_archive_file(archive_path)
                if data is None:
                    totals["skipped"] += 1
                    continue
                new_data = recompress_jpeg(data, quality)
                # Only keep it if it's actually smaller -- a JPEG that's
                # already efficient at this quality (or a fully-opaque
                # decode/re-encode round trip that happened to grow) is
                # left untouched rather than "compressed" into something
                # bigger.
                if new_data is None or len(new_data) >= len(data):
                    totals["skipped"] += 1
                    continue
                book.stage_image_replacement(archive_path, new_data)
                totals["original_bytes"] += len(data)
                totals["new_bytes"] += len(new_data)
                totals["compressed"] += 1

        run_with_progress(
            self, affected_books, _step, "Compressing images…",
            threshold=1, label_for=lambda book: f"Compressing: {os.path.basename(book.path)}",
        )
        self._refresh_rows_full(affected_books)
        self._refresh_status()
        self._on_selection_changed()

        if totals["compressed"] == 0:
            QMessageBox.information(
                self, "Nothing Compressed",
                "No image ended up smaller at this quality -- nothing was changed.",
            )
            return
        saved = totals["original_bytes"] - totals["new_bytes"]
        skip_note = f" ({totals['skipped']} image(s) left unchanged)" if totals["skipped"] else ""
        QMessageBox.information(
            self, "Images Compressed",
            f"Compressed {totals['compressed']} image(s) across {len(affected_books)} book(s), "
            f"saving {format_size(saved)}{skip_note}. Remember to save.",
        )

    # ------------------------------------------------------------------
    # Repair Navigation
    # ------------------------------------------------------------------

    def open_nav_repair_dialog(self) -> None:
        target_books = self._selection_or_all_books()
        if not target_books:
            QMessageBox.information(
                self, "No books", "Load some books first (or select the ones to check)."
            )
            return

        dialog = NavRepairDialog(target_books, self)
        if dialog.exec() != NavRepairDialog.DialogCode.Accepted:
            return

        indices = dialog.accepted_book_indices()
        if not indices:
            return

        # Structural repair, not user-authored content -- not pushed to
        # Undo, same convention as Rebuild Manifest. The dialog's own
        # upfront listing is the safeguard instead.
        affected_books = [dialog.books[i] for i in indices]
        totals = {"guide_refs": 0, "orphans": 0}

        def _step(book: EpubBook, _index: int) -> None:
            totals["guide_refs"] += len(book.repair_guide_references())
            totals["orphans"] += len(book.remove_orphaned_files())

        run_with_progress(
            self, affected_books, _step, "Repairing navigation…",
            cancellable=False, update_every=25,
        )
        total_guide_refs = totals["guide_refs"]
        total_orphans = totals["orphans"]
        self._refresh_rows_full(affected_books)
        self._refresh_status()
        self._on_selection_changed()
        QMessageBox.information(
            self, "Navigation Repaired",
            f"Removed {total_guide_refs} broken guide reference(s) and staged "
            f"{total_orphans} orphaned file(s) for removal across {len(affected_books)} "
            f"book(s). Remember to save.",
        )

    # ------------------------------------------------------------------
    # Detect Missing Spaces
    # ------------------------------------------------------------------

    def open_missing_space_dialog(self) -> None:
        target_books = self._selection_or_all_books()
        if not target_books:
            QMessageBox.information(
                self, "No books", "Load some books first (or select the ones to scan)."
            )
            return

        dialog = MissingSpaceDialog(target_books, self)
        if dialog.exec() != MissingSpaceDialog.DialogCode.Accepted:
            return

        changes = dialog.accepted_changes()  # [(book, field_key, new_value), ...]
        if not changes:
            return

        affected_books = list({id(book): book for book, _k, _v in changes}.values())
        self._push_undo("Detect Missing Spaces", affected_books)
        for book, field_key, new_value in changes:
            book.apply_metadata({field_key: new_value})
        self._refresh_rows_full(affected_books)
        self._refresh_status()
        self._on_selection_changed()

    # ------------------------------------------------------------------
    # Blank/Unknown Language Default
    # ------------------------------------------------------------------

    def open_blank_language_default_settings(self) -> None:
        dialog = BlankLanguageDefaultDialog(
            app_settings.load_blank_language_default_enabled(),
            app_settings.load_blank_language_default_code(),
            app_settings.load_languages(),
            self,
        )
        if dialog.exec() != BlankLanguageDefaultDialog.DialogCode.Accepted:
            return
        app_settings.save_blank_language_default_enabled(dialog.result_enabled())
        app_settings.save_blank_language_default_code(dialog.result_code())
        self._update_blank_language_default_action_state()

    def _update_blank_language_default_action_state(self) -> None:
        enabled = app_settings.load_blank_language_default_enabled()
        self.set_default_language_act.setEnabled(enabled)
        self.set_default_language_act.setToolTip(
            "" if enabled else "Disabled in Settings → Blank Language Default"
        )

    def set_blank_languages_to_default(self) -> None:
        # No per-book review step, unlike every other batch operation in
        # this app -- a deliberate exception (see app_settings' own note
        # on the setting this reads), which is exactly why the Settings
        # -> Blank Language Default toggle exists: disabling it there
        # disables this QAction outright, so it can't be clicked by
        # accident by anyone who doesn't want that risk at all.
        target_books = self._selection_or_all_books()
        if not target_books:
            QMessageBox.information(
                self, "No books", "Load some books first (or select the ones to set)."
            )
            return

        code = app_settings.load_blank_language_default_code()
        affected_books: list[EpubBook] = []

        def _scan_step(book: EpubBook, _index: int) -> None:
            if is_blank_or_unknown_language(book.metadata.language):
                affected_books.append(book)

        run_with_progress(
            self, target_books, _scan_step, "Checking languages…",
            cancellable=False, update_every=25,
        )
        if not affected_books:
            QMessageBox.information(
                self, "Nothing to Do",
                "None of the selected book(s) have a blank or unrecognized language.",
            )
            return

        self._push_undo("Set default language", affected_books)
        for book in affected_books:
            book.apply_metadata({"language": code})
        self._refresh_rows_full(affected_books)
        self._refresh_status()
        self._on_selection_changed()
        QMessageBox.information(
            self, "Language Set",
            f'Set {len(affected_books)} book(s) with a blank or unrecognized language to "{code}".',
        )

    # ------------------------------------------------------------------
    # Number Series
    # ------------------------------------------------------------------

    def open_series_number_dialog(self) -> None:
        # Deliberately requires an explicit selection rather than falling
        # back to "all books" (unlike most other bulk actions) -- this one
        # assigns DIFFERENT values based on table order, so silently
        # numbering everything in whatever the full table's current order
        # happens to be is much more likely to be a mistake than a
        # deliberate choice.
        target_books = self._currently_selected_books()
        if not target_books:
            QMessageBox.information(
                self, "No books selected",
                "Select the books to number, in the order you want them numbered "
                "(sort or arrange the table first), then try again.",
            )
            return

        dialog = SeriesNumberDialog(target_books, self)
        if dialog.exec() != SeriesNumberDialog.DialogCode.Accepted:
            return

        values = dialog.result_values()  # book index -> new series_index value
        if not values:
            return

        self._push_undo("Number series", target_books)
        for i, new_value in values.items():
            target_books[i].apply_metadata({"series_index": new_value})
        self._refresh_rows_full(target_books)
        self._refresh_status()
        self._on_selection_changed()  # bulk-edit panel may be showing the Series # field

    def quick_number_series(self) -> None:
        """The table right-click's quick version of Number Series: just
        prompts for a starting value (no step, no preview) and numbers
        the selected books +1 per row from there, in their current table
        order. For anything beyond the plain "start here, count up by
        one" case -- a different step, or a look at what's changing
        before it does -- use Operations -> Number Series instead."""
        target_books = self._currently_selected_books()
        if not target_books:
            return  # this menu item only ever shows with a selection already in place

        values = prompt_and_generate_series_numbers(
            self, len(target_books), field_label="Starting Series #"
        )
        if values is None:
            return

        self._push_undo("Number series", target_books)
        for book, new_value in zip(target_books, values):
            book.apply_metadata({"series_index": new_value})
        self._refresh_rows_full(target_books)
        self._refresh_status()
        self._on_selection_changed()  # bulk-edit panel may be showing the Series # field

    # ------------------------------------------------------------------
    # Polish Book
    # ------------------------------------------------------------------

    def open_polish_book_dialog(self) -> None:
        target_books = self._selection_or_all_books()
        if not target_books:
            QMessageBox.information(
                self, "No books", "Load some books first (or select the ones to polish)."
            )
            return

        dialog = PolishBookDialog(target_books, self)
        if dialog.exec() != PolishBookDialog.DialogCode.Accepted:
            return

        polished_in_place = dialog.result_polished_in_place()
        exported_paths = dialog.result_exported_paths()

        if polished_in_place:
            # Polishing rewrote these files directly on disk -- reload
            # each one fresh, in place in the list, same as Refresh List
            # and for the same reason: this isn't a staged edit, it's a
            # real file change. Undo entries may reference the
            # now-superseded book objects, so the stack is cleared too.
            for old_book in polished_in_place:
                idx = self.books.index(old_book)
                self.books[idx] = EpubBook(old_book.path)
            self.undo_manager = UndoManager(max_entries=UNDO_MAX_ENTRIES)
            self.undo_act.setEnabled(False)
            self._rebuild_table()
            self._refresh_status()
            self._on_selection_changed()  # old selection referenced now-replaced book objects

        if exported_paths:
            self._load_paths(exported_paths)

        if polished_in_place or exported_paths:
            msg = f"Polished {len(polished_in_place)} book(s) in place"
            if exported_paths:
                msg += f", exported {len(exported_paths)} polished copy/copies"
            QMessageBox.information(self, "Polished", msg + ".")

    # ------------------------------------------------------------------
    # Send to Kobo (USB) / Send to eReader (Wireless)
    # ------------------------------------------------------------------

    def open_send_to_kobo_dialog(self) -> None:
        target_books = self._selection_or_all_books()
        if not target_books:
            QMessageBox.information(
                self, "No books", "Load some books first (or select the ones to send)."
            )
            return
        dialog = SendToKoboDialog(target_books, self)
        dialog.exec()

    def open_send_to_ereader_dialog(self) -> None:
        target_books = self._selection_or_all_books()
        if not target_books:
            QMessageBox.information(
                self, "No books", "Load some books first (or select the ones to send)."
            )
            return
        dialog = SendToEreaderDialog(target_books, self)
        dialog.exec()

    # ------------------------------------------------------------------
    # Open Library lookup
    # ------------------------------------------------------------------

    def open_open_library_dialog(self) -> None:
        target_books = self._selection_or_all_books()
        if not target_books:
            QMessageBox.information(
                self, "No books", "Load some books first (or select the ones to look up)."
            )
            return

        dialog = OpenLibraryDialog(target_books, self)
        if dialog.exec() != OpenLibraryDialog.DialogCode.Accepted:
            return

        metadata_changes = dialog.accepted_metadata()  # row index -> {field_key: value}
        cover_changes = dialog.accepted_covers()  # row index -> (image_bytes, mime)
        if not metadata_changes and not cover_changes:
            return

        # Per-field review before anything is actually applied -- covers
        # are a separate, visual thing (not reviewed field-by-field
        # here), only the text metadata goes through this. Skips itself
        # entirely if nothing found would overwrite an existing,
        # different value; see resolve_overwrite_conflicts()'s own
        # docstring. None means the user cancelled the review outright,
        # which aborts applying the cover changes too, not just metadata.
        if metadata_changes:
            metadata_changes = resolve_overwrite_conflicts(self, target_books, metadata_changes, _field_label)
            if metadata_changes is None:
                return
        if not metadata_changes and not cover_changes:
            return

        affected_rows = set(metadata_changes) | set(cover_changes)
        affected_books = [target_books[row] for row in affected_rows]
        self._push_undo("Import metadata from Open Library", affected_books)
        for row, fields in metadata_changes.items():
            target_books[row].apply_metadata(fields)
        for row, (image_bytes, mime) in cover_changes.items():
            target_books[row].set_cover(image_bytes, mime)
        self._refresh_rows_full(affected_books)

        self._refresh_status()
        self._on_selection_changed()  # bulk-edit panel may be showing a field this just changed
        QMessageBox.information(
            self, "Applied",
            f"Applied Open Library data to {len(affected_books)} book(s). Remember to save.",
        )

    # ------------------------------------------------------------------
    # Generate Cover from Metadata
    # ------------------------------------------------------------------

    def open_cover_generator_dialog(self) -> None:
        target_books = self._selection_or_all_books()
        if not target_books:
            QMessageBox.information(
                self, "No books",
                "Load some books first (or select the ones to generate covers for).",
            )
            return

        dialog = CoverGeneratorDialog(target_books, self)
        if dialog.exec() != CoverGeneratorDialog.DialogCode.Accepted:
            return

        covers = dialog.accepted_covers()  # book index -> (image_bytes, mime)
        if not covers:
            return

        affected_books = [dialog.books[i] for i in covers]
        self._push_undo("Generate cover from metadata", affected_books)
        for i, (image_bytes, mime) in covers.items():
            dialog.books[i].set_cover(image_bytes, mime)
        self._refresh_affected_rows(affected_books)

    # ------------------------------------------------------------------
    # Import to EPUB
    # ------------------------------------------------------------------

    def open_ebook_convert_dialog(self) -> None:
        dialog = EbookConvertDialog(self)
        if dialog.exec() != EbookConvertDialog.DialogCode.Accepted:
            return
        paths = dialog.converted_epub_paths()
        if paths:
            self._load_paths(paths)

    # ------------------------------------------------------------------
    # Settings: columns / genres / languages
    # ------------------------------------------------------------------

    def open_column_settings_dialog(self) -> None:
        column_names = [
            self.table.horizontalHeaderItem(i).text() for i in range(self.table.columnCount())
        ]
        hidden = {i for i in range(self.table.columnCount()) if self.table.isColumnHidden(i)}
        locked = {FILENAME_COL}  # the one column you always need to tell rows apart
        dialog = ColumnSettingsDialog(column_names, hidden, locked, self)
        dialog.exec()
        visible = dialog.visible_indices()
        for i in range(self.table.columnCount()):
            self.table.setColumnHidden(i, i not in visible and i not in locked)
        self._on_columns_changed()

    def open_genre_settings_dialog(self) -> None:
        def load_defaults_fn() -> list[tuple[str, str]]:
            return [(g, g) for g in app_settings.load_visible_default_genres()]

        def add_dialog_fn(parent_widget) -> None:
            text, ok = QInputDialog.getText(parent_widget, "Add Genre", "New genre name:")
            if ok and text.strip():
                app_settings.add_custom_genre(text.strip())

        def load_custom_fn() -> list[tuple[str, str]]:
            return [(g, g) for g in app_settings.load_custom_genres()]

        dialog = ManageListDialog(
            "Add/Remove Genres", load_defaults_fn, load_custom_fn,
            add_dialog_fn, app_settings.remove_custom_genre,
            app_settings.hide_default_genre, app_settings.restore_default_genres, self,
        )
        dialog.exec()

    def open_language_settings_dialog(self) -> None:
        def load_defaults_fn() -> list[tuple[str, str]]:
            return [(code, f"{name} ({code})") for code, name in app_settings.load_visible_default_languages()]

        def add_dialog_fn(parent_widget) -> None:
            code, ok = QInputDialog.getText(
                parent_widget, "Add Custom Language",
                "Language code (ISO 639-1, e.g. \"pt\" for Portuguese):",
            )
            if not ok or not code.strip():
                return
            name, ok = QInputDialog.getText(
                parent_widget, "Add Custom Language", "Display name (e.g. \"Portuguese\"):"
            )
            if not ok or not name.strip():
                return
            app_settings.add_custom_language(code.strip(), name.strip())

        def load_custom_fn() -> list[tuple[str, str]]:
            return [(code, f"{name} ({code})") for code, name in app_settings.load_custom_languages()]

        dialog = ManageListDialog(
            "Add/Remove Languages", load_defaults_fn, load_custom_fn,
            add_dialog_fn, app_settings.remove_custom_language,
            app_settings.hide_default_language, app_settings.restore_default_languages, self,
        )
        dialog.exec()

    # ------------------------------------------------------------------
    # About / Changelog
    # ------------------------------------------------------------------

    def open_about_dialog(self) -> None:
        icon_path = resource_path("assets", "icon.png")
        about_path = resource_path("ABOUT.md")
        AboutDialog(
            app_name=APP_NAME,
            app_version=APP_VERSION,
            release_label=RELEASE_LABEL,
            icon_path=icon_path,
            about_path=about_path,
            component_versions={"redactor_common": REDACTOR_COMMON_VERSION},
            repo_url=APP_REPO_URL,
            component_repo_urls={"redactor_common": REDACTOR_COMMON_REPO_URL},
            parent=self,
        ).exec()

    def open_changelog_dialog(self) -> None:
        changelog_path = resource_path("CHANGELOG.md")
        ChangelogDialog(changelog_path, self).exec()

    def open_credits_dialog(self) -> None:
        credits_path = resource_path("CREDITS.md")
        CreditsDialog(credits_path, self).exec()

    # ------------------------------------------------------------------
    # Performance logging (see core/perf_log.py)
    # ------------------------------------------------------------------

    def toggle_perf_logging(self) -> None:
        enabled = self.perf_logging_act.isChecked()
        perf_log.set_enabled(enabled)
        app_settings.save_perf_logging_enabled(enabled)
        if enabled:
            QMessageBox.information(
                self, "Performance Logging Enabled",
                "Timing details for table rebuilds and saves will be appended to:\n\n"
                f"{perf_log.log_path()}\n\n"
                "Reproduce the slow operation now, then use Settings → Open "
                "Performance Log File… to find it.",
            )

    def open_perf_log_file(self) -> None:
        path = perf_log.log_path()
        if not os.path.isfile(path):
            QMessageBox.information(
                self, "No Log Yet",
                "No performance log exists yet. Enable Settings → Enable Performance "
                "Logging first, then reproduce the slow operation.",
            )
            return
        reveal_in_file_manager(path)

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    def _apply_filter(self, text: str) -> None:
        text = text.strip().lower()
        for row in range(self.table.rowCount()):
            book = self._book_for_row(row)
            if book is None:
                continue
            if not text:
                self.table.setRowHidden(row, False)
                continue
            haystack = f"{os.path.basename(book.path)} {book.metadata.title}".lower()
            self.table.setRowHidden(row, text not in haystack)

    def _count_dirty(self) -> int:
        return sum(1 for b in self.books if b.dirty)

    def _refresh_status(self) -> None:
        dirty = self._count_dirty()
        errors = sum(1 for b in self.books if b.load_error)
        msg = f"{len(self.books)} book(s) loaded"
        if dirty:
            msg += f"  \u2022  {dirty} unsaved change(s)"
        if errors:
            msg += f"  \u2022  {errors} failed to load"
        self.status_label.setText(msg)

    def _confirm_discard(self, action_desc: str) -> bool:
        reply = QMessageBox.question(
            self,
            "Unsaved changes",
            f"You have unsaved changes. Are you sure you want to {action_desc}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def closeEvent(self, event) -> None:
        if self._count_dirty() and not self._confirm_discard("quit without saving"):
            event.ignore()
            return
        # Remember exactly what's loaded right now (including an empty
        # list, if nothing is) so the next launch can pick back up where
        # this session left off -- see _restore_last_session().
        app_settings.save_last_session_files([b.path for b in self.books])
        event.accept()
