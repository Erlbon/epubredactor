"""
gui/tag_panel.py

The bulk-edit panel, the heart of the mp3tag-style workflow:

- Select one or more rows in the file table.
- Each field shows the shared value if every selected book agrees, or
  a "<multiple values>" placeholder if they differ.
- Tick a field's checkbox and type a value to stage it for the whole
  selection. Unticked fields are left completely alone -- this is the
  safety net that stops you from accidentally blanking a field just
  because it happened to be empty on-screen.
- "Apply to N book(s)" writes the checked fields into memory for every
  selected row (does not touch disk -- that's the Save button).
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core.author_sort import author_sort_to_authors, authors_to_author_sort
from core.epub_metadata import EpubBook
from core.fields import FIELDS
from core.genres import add_genre
from gui import app_settings
from redactor_common.gui.image_label import AspectRatioImageLabel
from redactor_common.gui.collapsible_splitter import CollapseToggleButton

MULTIPLE_VALUES_PLACEHOLDER = "<multiple values>"
COVER_PREVIEW_MIN_SIZE = (60, 80)
ADD_CUSTOM_LANGUAGE_LABEL = "Add custom language…"
# A single narrow, consistent-width button style for every field-side
# action (Google Books lookup, Author Sort auto-fill, Genre/Language
# pickers) -- a downward arrow works for all of them even though two are
# direct actions and two are dropdown menus, since visual consistency (and
# saving horizontal space) matters more here than the arrow being a
# literal "this opens a menu" indicator in every single case.
FIELD_BUTTON_GLYPH = "\u25bc"
FIELD_BUTTON_WIDTH = 26


class MultiValueLineEdit(QLineEdit):
    """A QLineEdit that can additionally hold a small set of alternative
    values -- the distinct non-empty values present across a multi-book
    selection -- and cycle through them via mouse wheel. Lets you
    actually see and pick one of several differing values, instead of
    just being told "<multiple values>" with no way to inspect what
    they are. Never includes a blank/empty value among the alternatives
    to cycle through -- an absent value on some books isn't a usable
    "pick this for everyone" option the way an actual value is."""

    valuePicked = pyqtSignal()  # emitted after the wheel cycles to a new value

    def __init__(self, parent=None):
        super().__init__(parent)
        self._alternatives: list[str] = []
        self._alt_index = -1

    def set_alternatives(self, values: list[str]) -> None:
        self._alternatives = values
        self._alt_index = -1

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt override signature
        if not self._alternatives:
            super().wheelEvent(event)
            return
        delta = event.angleDelta().y()
        if delta == 0:
            super().wheelEvent(event)
            return
        if self._alt_index == -1:
            self._alt_index = 0
        else:
            step = -1 if delta > 0 else 1
            self._alt_index = (self._alt_index + step) % len(self._alternatives)
        self.setText(self._alternatives[self._alt_index])
        self.setPlaceholderText("")
        self.valuePicked.emit()
        event.accept()


FIELDS_BY_KEY = {key: (label, multiline) for key, label, multiline in FIELDS}


class TagPanel(QWidget):
    applyRequested = pyqtSignal(dict)  # {field_key: value} for checked fields only
    isbnLookupRequested = pyqtSignal()  # Google Books lookup applies per-book, not via applyRequested
    coverAddReplaceRequested = pyqtSignal()  # cover edits apply per-book too
    coverGenerateRequested = pyqtSignal()
    coverDeleteRequested = pyqtSignal()
    selectionCountChanged = pyqtSignal(int)  # lets MainWindow mirror this in its toolbar Apply action
    collapseToggleRequested = pyqtSignal()  # the panel doesn't control its own width -- MainWindow does

    def __init__(self, parent=None):
        super().__init__(parent)
        self._checkboxes: dict[str, QCheckBox] = {}
        self._editors: dict[str, QWidget] = {}
        self._current_books: list[EpubBook] = []
        self._visible_field_keys: list[str] = [key for key, _l, _m in FIELDS]
        self._build_ui()
        self.set_selection([])

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)

        # Sits at the very top regardless of how narrow the panel gets,
        # so the toggle stays reachable even when minimized -- MainWindow
        # collapses to a slim strip, not to zero width, for exactly this
        # reason (see toggle_tag_panel()).
        toggle_row = QHBoxLayout()
        toggle_row.addStretch(1)
        self.collapse_toggle_btn = CollapseToggleButton(width=FIELD_BUTTON_WIDTH)
        self.collapse_toggle_btn.clicked.connect(self.collapseToggleRequested.emit)
        toggle_row.addWidget(self.collapse_toggle_btn)
        outer.addLayout(toggle_row)

        self._fields_box = QGroupBox("Bulk Edit Tags")
        self._fields_grid = QGridLayout(self._fields_box)
        self._fields_grid.setColumnStretch(2, 1)
        self._build_field_rows(self._visible_field_keys)

        # Scrollable so the fields section can be dragged much shorter
        # than its natural content height without the rows themselves
        # getting crushed/unreadable -- they just scroll instead.
        fields_scroll = QScrollArea()
        fields_scroll.setWidgetResizable(True)
        fields_scroll.setFrameShape(QFrame.Shape.NoFrame)
        fields_scroll.setWidget(self._fields_box)

        cover_box = QGroupBox("Cover Image")
        cover_layout = QVBoxLayout(cover_box)

        self.cover_preview = AspectRatioImageLabel()
        self.cover_preview.setText("No cover")
        self.cover_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_preview.setMinimumSize(*COVER_PREVIEW_MIN_SIZE)
        self.cover_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.cover_preview.setStyleSheet(
            "border: 1px solid palette(mid); border-radius: 4px; color: gray;"
        )
        cover_layout.addWidget(self.cover_preview, 1)

        self.cover_hint = QLabel("")
        self.cover_hint.setStyleSheet("color: gray; font-size: 11px;")
        self.cover_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cover_layout.addWidget(self.cover_hint)

        cover_btn_row = QHBoxLayout()
        self.cover_add_btn = QPushButton("Add/Replace")
        self.cover_add_btn.setToolTip(
            "Choose an image file to set as the cover for every selected book"
        )
        self.cover_add_btn.clicked.connect(self.coverAddReplaceRequested.emit)
        cover_btn_row.addWidget(self.cover_add_btn)

        self.cover_generate_btn = QPushButton("Generate")
        self.cover_generate_btn.setToolTip(
            "Generate a placeholder cover (title, author, series if present, on a plain "
            "background) for every selected book, replacing any existing cover"
        )
        self.cover_generate_btn.clicked.connect(self.coverGenerateRequested.emit)
        cover_btn_row.addWidget(self.cover_generate_btn)

        self.cover_delete_btn = QPushButton("Delete")
        self.cover_delete_btn.setToolTip("Remove the cover image from every selected book")
        self.cover_delete_btn.clicked.connect(self.coverDeleteRequested.emit)
        cover_btn_row.addWidget(self.cover_delete_btn)

        cover_layout.addLayout(cover_btn_row)

        # A real draggable divider between the two sections -- lets you
        # give the cover image much more room by dragging, even if that
        # squeezes Bulk Edit Tags down to something that needs to scroll.
        # Both panes are collapsible (Qt's default), so either one can be
        # dragged all the way down to make room for the other.
        self._vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        self._vertical_splitter.addWidget(fields_scroll)
        self._vertical_splitter.addWidget(cover_box)
        self._vertical_splitter.setStretchFactor(0, 1)
        self._vertical_splitter.setStretchFactor(1, 1)
        self._vertical_splitter.setSizes([600, 300])  # initial bias toward fields; purely a starting hint
        outer.addWidget(self._vertical_splitter, 1)

        btn_row = QVBoxLayout()
        clear_btn = QPushButton("Uncheck All Fields")
        clear_btn.clicked.connect(self._uncheck_all)
        btn_row.addWidget(clear_btn)

        outer.addLayout(btn_row)

        self._selected_count = 0
        # Guard against textChanged firing while we're programmatically
        # repopulating fields on selection change (would wrongly tick boxes).
        self._populating = False

    def _build_field_rows(self, field_keys: list[str]) -> None:
        """Builds one grid row per key in field_keys, in that order.
        Assumes the grid is currently empty -- see set_visible_fields()
        for the teardown-and-rebuild path used after the first call."""
        for row, key in enumerate(field_keys):
            label, multiline = FIELDS_BY_KEY[key]
            cb = QCheckBox()
            cb.setToolTip("Tick to include this field when applying to the selection")
            self._checkboxes[key] = cb

            lbl = QLabel(label)

            if multiline:
                editor = QPlainTextEdit()
                editor.setFixedHeight(70)
            else:
                editor = MultiValueLineEdit()
            # Typing in a field implicitly opts it in -- convenient, and
            # matches how mp3tag behaves (any edit means "change this").
            if isinstance(editor, QLineEdit):
                editor.textEdited.connect(lambda _text, k=key: self._checkboxes[k].setChecked(True))
            else:
                editor.textChanged.connect(lambda k=key: self._on_plaintext_changed(k))
            if isinstance(editor, MultiValueLineEdit):
                # Scrolling to a different alternative counts as picking
                # it, same as typing -- opts the field in automatically.
                editor.valuePicked.connect(lambda k=key: self._checkboxes[k].setChecked(True))

            self._editors[key] = editor

            self._fields_grid.addWidget(cb, row, 0)
            self._fields_grid.addWidget(lbl, row, 1)
            self._fields_grid.addWidget(editor, row, 2)

            if key == "tags_str":
                self._fields_grid.addWidget(self._build_genre_button(key), row, 3)
            elif key == "language":
                self._fields_grid.addWidget(self._build_language_button(key), row, 3)
            elif key == "authors_str":
                autofill_btn = self._build_field_button(
                    "Guess \"First Last\" from the Author Sort field below "
                    "(splits on the first comma in each entry -- the exact "
                    "inverse of that field's own guess button, so it won't "
                    "be right wherever that one wasn't)",
                    glyph="\u25b2",  # points up -- pulls its value from the field below
                )
                autofill_btn.clicked.connect(self._on_autofill_authors_from_sort)
                self._fields_grid.addWidget(autofill_btn, row, 3)
            elif key == "author_sort_str":
                autofill_btn = self._build_field_button(
                    "Guess \"Last, First\" from the Author(s) field above "
                    "(splits on the last space in each name -- check the "
                    "result, it won't be right for every name)"
                )
                autofill_btn.clicked.connect(self._on_autofill_author_sort)
                self._fields_grid.addWidget(autofill_btn, row, 3)
            elif key == "isbn":
                lookup_btn = self._build_field_button(
                    "Import Metadata from Google Books for each selected book, "
                    "using its title/author (brings in more than just ISBN -- "
                    "review what's found before anything's applied)"
                )
                lookup_btn.clicked.connect(self.isbnLookupRequested.emit)
                self._fields_grid.addWidget(lookup_btn, row, 3)

    def set_visible_fields(self, field_keys: list[str]) -> None:
        """Rebuilds the Bulk Edit Tags rows to show exactly these fields,
        in this order -- called by MainWindow whenever the table's
        column visibility or column order changes (Settings ->
        Add/Remove Columns, or dragging a column header), so the two
        stay in sync rather than needing a second, separate
        field-management UI. A no-op if the requested set is already
        what's showing.

        Any pending edit (a field ticked with a value typed in, but not
        yet Applied) is preserved across the rebuild -- without this, a
        column-visibility change while you had unapplied edits sitting
        in the panel would silently discard them, since rebuilding the
        rows recreates the checkboxes/editors from scratch and
        repopulates them from the books' actual saved data, not from
        whatever was mid-edit in the old (about-to-be-deleted) widgets."""
        valid_keys = set(FIELDS_BY_KEY)
        field_keys = [k for k in field_keys if k in valid_keys]
        if not field_keys:
            field_keys = [key for key, _l, _m in FIELDS]  # never show a totally empty panel
        if field_keys == self._visible_field_keys:
            return

        pending = {
            key: self._editor_text(editor)
            for key, editor in self._editors.items()
            if self._checkboxes[key].isChecked()
        }

        while self._fields_grid.count():
            item = self._fields_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self._checkboxes.clear()
        self._editors.clear()
        self._visible_field_keys = field_keys
        self._build_field_rows(field_keys)
        self.set_selection(self._current_books)  # repopulate the rebuilt rows with current data

        for key, text in pending.items():
            if key in self._editors:
                self._set_editor_text(self._editors[key], text)
                self._checkboxes[key].setChecked(True)

    def _on_plaintext_changed(self, key: str) -> None:
        if not self._populating:
            self._checkboxes[key].setChecked(True)

    def _build_field_button(self, tooltip: str, glyph: str = FIELD_BUTTON_GLYPH) -> QPushButton:
        """Shared narrow-button style for every field-side action button
        (see FIELD_BUTTON_GLYPH/WIDTH above) -- callers wire up either a
        direct click handler or a menu afterward. `glyph` lets a caller
        override the default "▼" -- used for the Author(s) guess button,
        which points up rather than down, since it pulls its value from
        Author Sort below it (the field it points down at gets read
        FROM, the arrow always points toward the source). The
        menu-indicator stylesheet rule matters specifically for the two
        menu-driven buttons (Genre, Language): Qt automatically draws
        its own native dropdown-arrow decoration on any button with
        setMenu() called on it, on top of whatever text the button
        already has -- without suppressing that, those two buttons would
        show a doubled-up arrow (ours + Qt's) while the direct-action
        buttons (ISBN, Author Sort) show only ours, which is exactly why
        they looked inconsistent. Harmless no-op on buttons with no menu
        attached."""
        btn = QPushButton(glyph)
        btn.setMaximumWidth(FIELD_BUTTON_WIDTH)
        btn.setToolTip(tooltip)
        btn.setStyleSheet("QPushButton::menu-indicator { image: none; width: 0px; }")
        return btn

    def _build_genre_button(self, field_key: str) -> QPushButton:
        """Click for a menu of common (plus any custom-added) genres. The
        field itself stays free text -- picking a menu item appends it to
        whatever's already typed (semicolon list), it never replaces the
        field's content. Menu is rebuilt fresh each time it opens, so a
        just-added custom genre (via Settings -> Add/Remove Genres) shows
        up immediately without needing a restart."""
        btn = self._build_field_button("Add a genre to the field on the left")
        menu = QMenu(btn)
        menu.aboutToShow.connect(lambda m=menu, k=field_key: self._populate_genre_menu(m, k))
        btn.setMenu(menu)
        return btn

    def _populate_genre_menu(self, menu: QMenu, field_key: str) -> None:
        menu.clear()
        for genre in app_settings.load_genres():
            action = menu.addAction(genre)
            action.triggered.connect(lambda _checked, g=genre, k=field_key: self._on_genre_picked(k, g))

    def _on_genre_picked(self, field_key: str, genre: str) -> None:
        editor = self._editors[field_key]
        current = self._editor_text(editor)
        merged = add_genre(current, genre)
        if merged != current:
            self._set_editor_text(editor, merged)
            self._checkboxes[field_key].setChecked(True)

    def _build_language_button(self, field_key: str) -> QPushButton:
        """Click for a menu of common languages (plus any custom ones
        added previously). Unlike Genre, Language is single-valued, so
        picking one REPLACES the field rather than appending. The menu is
        rebuilt fresh each time it opens, so a just-added custom language
        shows up right away."""
        btn = self._build_field_button("Set the language from a quick list, or add a new one")
        menu = QMenu(btn)
        menu.aboutToShow.connect(lambda m=menu, k=field_key: self._populate_language_menu(m, k))
        btn.setMenu(menu)
        return btn

    def _populate_language_menu(self, menu: QMenu, field_key: str) -> None:
        menu.clear()
        for code, name in app_settings.load_languages():
            action = menu.addAction(f"{name} ({code})")
            action.triggered.connect(lambda _checked, c=code, k=field_key: self._on_language_picked(k, c))
        menu.addSeparator()
        add_action = menu.addAction(ADD_CUSTOM_LANGUAGE_LABEL)
        add_action.triggered.connect(lambda _checked, k=field_key: self._on_add_custom_language(k))

    def _on_language_picked(self, field_key: str, code: str) -> None:
        editor = self._editors[field_key]
        if self._editor_text(editor) != code:
            self._set_editor_text(editor, code)
            self._checkboxes[field_key].setChecked(True)

    def _on_add_custom_language(self, field_key: str) -> None:
        code, ok = QInputDialog.getText(
            self, "Add Custom Language",
            "Language code (ISO 639-1, e.g. \"pt\" for Portuguese):"
        )
        if not ok or not code.strip():
            return
        name, ok = QInputDialog.getText(
            self, "Add Custom Language",
            "Display name (e.g. \"Portuguese\"):"
        )
        if not ok or not name.strip():
            return
        app_settings.add_custom_language(code.strip(), name.strip())
        self._on_language_picked(field_key, code.strip())

    def _on_autofill_author_sort(self) -> None:
        """Naive "Firstname Lastname" -> "Lastname, Firstname" guess, per
        semicolon-separated author. See core/author_sort.py for the
        exact splitting rule and its caveats."""
        authors_text = self._editor_text(self._editors["authors_str"])
        result = authors_to_author_sort(authors_text)
        if not result:
            return
        editor = self._editors["author_sort_str"]
        self._set_editor_text(editor, result)
        self._checkboxes["author_sort_str"].setChecked(True)

    def _on_autofill_authors_from_sort(self) -> None:
        """The exact inverse of _on_autofill_author_sort() above -- same
        caveats apply in reverse. See core/author_sort.py."""
        sort_text = self._editor_text(self._editors["author_sort_str"])
        result = author_sort_to_authors(sort_text)
        if not result:
            return
        editor = self._editors["authors_str"]
        self._set_editor_text(editor, result)
        self._checkboxes["authors_str"].setChecked(True)

    def _uncheck_all(self) -> None:
        for cb in self._checkboxes.values():
            cb.setChecked(False)

    def set_collapsed_indicator(self, collapsed: bool) -> None:
        """Updates the panel's own toggle button to reflect whether it's
        currently minimized. MainWindow owns the actual collapsed/expanded
        state (via the splitter, since resizing is its job, not this
        widget's) and calls this after any change -- the toggle button
        click, or the user dragging the splitter handle by hand."""
        self.collapse_toggle_btn.set_collapsed(collapsed)

    # ------------------------------------------------------------------

    def set_selection(self, books: list[EpubBook]) -> None:
        """books: the currently selected EpubBook objects (non-error only).
        Repopulates every visible field, showing the common value or a
        <multiple values> placeholder, and unchecks everything. Also
        refreshes the cover preview to the first selected book's cover."""
        self._current_books = books
        self._populating = True
        self._selected_count = len(books)
        self.selectionCountChanged.emit(self._selected_count)
        self.cover_add_btn.setEnabled(self._selected_count > 0)
        self.cover_generate_btn.setEnabled(self._selected_count > 0)
        self.cover_delete_btn.setEnabled(self._selected_count > 0)

        metadatas = [b.metadata for b in books]
        for key in self._visible_field_keys:
            editor = self._editors[key]
            self._checkboxes[key].setChecked(False)

            if not metadatas:
                if isinstance(editor, MultiValueLineEdit):
                    editor.set_alternatives([])
                self._set_editor_text(editor, "")
                self._set_editor_placeholder(editor, "")
                continue

            values = {self._value_for(m, key) for m in metadatas}
            if isinstance(editor, MultiValueLineEdit):
                # Alternatives to scroll through -- never includes a
                # blank value (an absent value on some books isn't a
                # usable "apply this to everyone" option), and only
                # meaningful at all when there's a genuine disagreement.
                alternatives = sorted(v for v in values if v) if len(values) > 1 else []
                editor.set_alternatives(alternatives)
                editor.setToolTip(
                    f"Scroll to cycle through {len(alternatives)} different values in the selection"
                    if alternatives else ""
                )
            if len(values) == 1:
                self._set_editor_text(editor, values.pop())
                self._set_editor_placeholder(editor, "")
            else:
                self._set_editor_text(editor, "")
                self._set_editor_placeholder(editor, MULTIPLE_VALUES_PLACEHOLDER)

        self._update_cover_preview(books)
        self._populating = False

    def _update_cover_preview(self, books: list[EpubBook]) -> None:
        if not books:
            self.cover_preview.setText("No selection")
            self.cover_preview.set_original_pixmap(None)
            self.cover_hint.setText("")
            return

        first = books[0]
        extra = f" (showing 1st of {len(books)} selected)" if len(books) > 1 else ""

        if not first.cover_bytes:
            self.cover_preview.setText("No cover")
            self.cover_preview.set_original_pixmap(None)
            self.cover_hint.setText(extra.strip(" ()") or "")
            return

        pixmap = QPixmap()
        if pixmap.loadFromData(first.cover_bytes):
            self.cover_preview.setText("")
            self.cover_preview.set_original_pixmap(pixmap)
        else:
            self.cover_preview.set_original_pixmap(None)
            self.cover_preview.setText("(cover image unreadable)")
        self.cover_hint.setText(extra.strip(" ()") or "")

    @staticmethod
    def _value_for(metadata, key: str) -> str:
        return getattr(metadata, key, "") or ""

    @staticmethod
    def _set_editor_text(editor: QWidget, text: str) -> None:
        if isinstance(editor, QLineEdit):
            editor.setText(text)
        else:
            editor.blockSignals(True)
            editor.setPlainText(text)
            editor.blockSignals(False)

    @staticmethod
    def _set_editor_placeholder(editor: QWidget, text: str) -> None:
        if isinstance(editor, QLineEdit):
            editor.setPlaceholderText(text)
        # QPlainTextEdit has no native placeholder pre-6.x style we rely on;
        # leaving it blank when values differ is clear enough in context.

    def _editor_text(self, editor: QWidget) -> str:
        if isinstance(editor, QLineEdit):
            return editor.text()
        return editor.toPlainText()

    def apply_bulk_edit(self) -> None:
        """Collects every checked field's value and emits applyRequested.
        Public (not a private click handler) since Apply now lives as a
        toolbar action in MainWindow rather than a button inside this
        panel -- see the note in MainWindow._build_menu_bar()."""
        result = {}
        for key in self._visible_field_keys:
            if self._checkboxes[key].isChecked():
                result[key] = self._editor_text(self._editors[key]).strip() if key != "description" else self._editor_text(self._editors[key])
        if result:
            self.applyRequested.emit(result)
        self._uncheck_all()
