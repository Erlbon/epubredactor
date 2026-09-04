"""
gui/filename_parse_dialog.py

The reverse of the Rename/Export dialog: instead of building a filename
from metadata, this extracts metadata FROM a filename using the same
%field% pattern syntax (see core/filename_parser.py). Shares its pattern
history with Rename/Export via gui/app_settings -- if you've already
described your naming convention there, it's the natural pattern to
parse back with too.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.epub_metadata import EpubBook
from core.filename_parser import (
    best_matching_pattern,
    count_matching_filenames,
    parse_filename,
    parsed_to_metadata_kwargs,
)
from core.rename_pattern import DEFAULT_PATTERN, PLACEHOLDERS
from gui import app_settings

# Same narrow "▼" style used for every other field-side menu button in
# the app (Google Books lookup, Genre, Language, Author Sort/Author
# guesses in gui/tag_panel.py) -- kept as a local copy rather than
# importing from there, to avoid a cross-dialog dependency for one
# shared constant.
RECENT_BUTTON_GLYPH = "\u25bc"
RECENT_BUTTON_WIDTH = 26
BOOK_COL, EXTRACTED_COL, APPLY_COL = range(3)


class FilenameParseDialog(QDialog):
    def __init__(self, books: list[EpubBook], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Parse Filename \u2192 Metadata")
        self.resize(1060, 560)
        self.books = books
        self._checkboxes: dict[int, QCheckBox] = {}
        self._parsed: dict[int, dict[str, str]] = {}
        self._filename_stems = [os.path.splitext(os.path.basename(b.path))[0] for b in self.books]

        self._build_ui()
        self._refresh_preview()

    def _build_ui(self) -> None:
        outer = QHBoxLayout(self)

        layout = QVBoxLayout()
        outer.addLayout(layout, 2)
        layout.addWidget(QLabel(
            f"Applies to {len(self.books)} book(s). Only fields present in the pattern "
            "are extracted and offered; everything else is left untouched."
        ))

        pattern_row = QHBoxLayout()
        pattern_row.addWidget(QLabel("Pattern:"))
        # Rather than just reusing whatever pattern was used last (which
        # could easily be from a completely different batch of books),
        # check every pattern in history against THESE filenames and
        # start with whichever one actually fits best -- falling back to
        # the last-used pattern only if nothing in history matches
        # anything here. See _refresh_preview() for the "auto-detected"
        # status message this produces on first load.
        detected = best_matching_pattern(self._filename_stems, app_settings.load_pattern_history())
        if detected:
            starting_pattern = detected[0]
            self._auto_detected_pattern = detected[0]
        else:
            starting_pattern = app_settings.load_last_pattern(DEFAULT_PATTERN)
            self._auto_detected_pattern = None
        self.pattern_edit = QLineEdit(starting_pattern)
        self.pattern_edit.textChanged.connect(self._refresh_preview)
        pattern_row.addWidget(self.pattern_edit, 1)

        self.recent_btn = QPushButton(RECENT_BUTTON_GLYPH)
        self.recent_btn.setMaximumWidth(RECENT_BUTTON_WIDTH)
        self.recent_btn.setToolTip("Choose from recently used patterns")
        self.recent_btn.clicked.connect(self._show_recent_menu)
        pattern_row.addWidget(self.recent_btn)
        layout.addLayout(pattern_row)

        # Recent patterns are also shown as a small always-visible,
        # directly-clickable list right below the field -- not just
        # tucked behind the "▼" button above, which not everyone thinks
        # to click. Clicking a row here does exactly what picking it
        # from that button's menu does; both are kept since they cost
        # little and suit different habits.
        self.recent_list = QListWidget()
        self.recent_list.setMaximumHeight(90)
        self.recent_list.itemClicked.connect(self._on_recent_list_clicked)
        self._populate_recent_list()
        layout.addWidget(self.recent_list)

        self.preview_table = QTableWidget()
        self.preview_table.setColumnCount(3)
        self.preview_table.setHorizontalHeaderLabels(["Book", "Extracted fields", "Apply"])
        self.preview_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.preview_table.horizontalHeader().setSectionResizeMode(EXTRACTED_COL, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.preview_table, 1)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self.status_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Apply")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Available field codes, always visible in their own panel to the
        # side rather than a single cramped line of text above the
        # pattern field -- double-click one to insert it at the cursor's
        # current position in the pattern field, same idea as picking a
        # recent pattern above but for building a brand new one field by
        # field instead of reusing a whole one at once.
        codes_panel = QVBoxLayout()
        outer.addLayout(codes_panel, 1)
        codes_panel.addWidget(QLabel("Available fields (double-click to insert):"))
        self.codes_list = QListWidget()
        for key, label in PLACEHOLDERS:
            item = QListWidgetItem(f"%{key}%   \u2014   {label}")
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.codes_list.addItem(item)
        self.codes_list.itemDoubleClicked.connect(self._insert_placeholder)
        codes_panel.addWidget(self.codes_list, 1)

    def _insert_placeholder(self, item: QListWidgetItem) -> None:
        key = item.data(Qt.ItemDataRole.UserRole)
        if key:
            self.pattern_edit.insert(f"%{key}%")
            self.pattern_edit.setFocus()

    def _show_recent_menu(self) -> None:
        """Anchored to the pattern FIELD's bottom-left corner, not the
        small arrow button beside it -- so the menu appears right under
        where your eye already is (reading the pattern text), rather
        than off to the side under the button, which meant a bigger jump
        for your eye to follow every time."""
        menu = QMenu(self)
        for pattern, label in self._pattern_history_labels():
            action = menu.addAction(label)
            if pattern is None:
                action.setEnabled(False)
            else:
                action.triggered.connect(lambda _checked, p=pattern: self._on_recent_picked(p))
        pos = self.pattern_edit.mapToGlobal(self.pattern_edit.rect().bottomLeft())
        menu.exec(pos)

    def _populate_recent_list(self) -> None:
        """Same content and ordering as the "▼" button's menu, just
        always visible instead of needing that button clicked first."""
        self.recent_list.clear()
        for pattern, label in self._pattern_history_labels():
            item = QListWidgetItem(label)
            if pattern is None:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable & ~Qt.ItemFlag.ItemIsEnabled)
            else:
                item.setData(Qt.ItemDataRole.UserRole, pattern)
            self.recent_list.addItem(item)

    def _pattern_history_labels(self) -> list[tuple[str | None, str]]:
        """(pattern, display label) pairs for every pattern in history,
        each labeled with how many of the currently loaded filenames it
        actually matches -- shared by the menu and the always-visible
        list below the field, so both stay in sync automatically. A
        pattern of None marks a disabled placeholder entry (shown when
        there's no history yet), not a real, pickable pattern."""
        history = app_settings.load_pattern_history()
        if not history:
            return [(None, "(no recent patterns yet)")]
        labels = []
        for pattern in history:
            count = count_matching_filenames(self._filename_stems, pattern)
            labels.append((pattern, f"{pattern}   \u2014   {count}/{len(self.books)} match"))
        return labels

    def _on_recent_list_clicked(self, item: QListWidgetItem) -> None:
        pattern = item.data(Qt.ItemDataRole.UserRole)
        if pattern:
            self._on_recent_picked(pattern)

    def _on_recent_picked(self, pattern: str) -> None:
        self.pattern_edit.setText(pattern)

    def _refresh_preview(self) -> None:
        pattern = self.pattern_edit.text()
        self._checkboxes = {}
        self._parsed = {}

        self.preview_table.setRowCount(len(self.books))
        matched_count = 0
        for row, book in enumerate(self.books):
            stem = self._filename_stems[row]
            self.preview_table.setItem(row, BOOK_COL, self._readonly_item(os.path.basename(book.path)))

            parsed = parse_filename(stem, pattern) if pattern.strip() else None
            non_empty = {k: v for k, v in (parsed or {}).items() if v}
            non_empty = parsed_to_metadata_kwargs(non_empty)

            cb = QCheckBox()
            if non_empty:
                summary = "; ".join(f"{k}: {v}" for k, v in non_empty.items())
                self.preview_table.setItem(row, EXTRACTED_COL, self._readonly_item(summary))
                cb.setChecked(True)
                self._parsed[row] = non_empty
                matched_count += 1
            else:
                self.preview_table.setItem(row, EXTRACTED_COL, self._readonly_item("(no match)"))
                cb.setEnabled(False)
            self._checkboxes[row] = cb
            self.preview_table.setCellWidget(row, APPLY_COL, cb)

        self.preview_table.resizeColumnsToContents()
        if self._auto_detected_pattern and pattern == self._auto_detected_pattern:
            self.status_label.setText(
                f"Auto-detected from your pattern history: {matched_count} of {len(self.books)} "
                "filename(s) match this pattern."
            )
        else:
            self.status_label.setText(f"{matched_count} of {len(self.books)} filename(s) match this pattern.")

    @staticmethod
    def _readonly_item(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    def _on_accept(self) -> None:
        if self._parsed:
            app_settings.save_pattern_used(self.pattern_edit.text())
        self.accept()

    # ------------------------------------------------------------------
    # Result accessor, read by the caller after exec() returns Accepted

    def accepted_changes(self) -> dict[int, dict[str, str]]:
        """book index -> {field_key: value}, for every row whose checkbox
        is checked and which actually matched the pattern."""
        return {
            row: self._parsed[row]
            for row, cb in self._checkboxes.items()
            if cb.isChecked() and cb.isEnabled() and row in self._parsed
        }
