"""
gui/rename_dialog.py

The "Tag -> Filename" dialog, mp3tag's Convert feature. Lets you build a
filename pattern from metadata placeholders, preview the result for every
book being processed, then either:

  - Rename the files in place (in their current folder), or
  - Export copies with the new names into a folder you choose, leaving
    the originals completely untouched.

Renaming always reflects each book's *current* metadata (including
unsaved in-memory edits) -- see the docstring on MainWindow.perform_rename_export
for how that's kept consistent with what actually ends up inside the file.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.epub_metadata import EpubBook
from core.rename_pattern import DEFAULT_PATTERN, PLACEHOLDERS, render_filename
from gui import app_settings

# Same narrow "▼" style used for every other field-side menu button in
# the app (see gui/filename_parse_dialog.py, gui/tag_panel.py) -- kept
# as a local copy rather than importing from either, to avoid a
# cross-dialog dependency for one shared constant.
RECENT_BUTTON_GLYPH = "\u25bc"
RECENT_BUTTON_WIDTH = 26


class RenameDialog(QDialog):
    def __init__(self, books: list[EpubBook], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Rename / Export by Metadata Pattern")
        self.resize(990, 560)
        self.books = books
        self.output_folder: str | None = None

        self._build_ui()
        self._refresh_preview()

    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QHBoxLayout(self)

        layout = QVBoxLayout()
        outer.addLayout(layout, 2)
        layout.addWidget(QLabel(f"Applies to {len(self.books)} book(s)."))

        pattern_row = QHBoxLayout()
        pattern_row.addWidget(QLabel("Pattern:"))
        starting_pattern = app_settings.load_last_pattern(DEFAULT_PATTERN)
        self.pattern_edit = QLineEdit(starting_pattern)
        self.pattern_edit.textChanged.connect(self._refresh_preview)
        pattern_row.addWidget(self.pattern_edit, 1)

        self.recent_btn = QPushButton(RECENT_BUTTON_GLYPH)
        self.recent_btn.setMaximumWidth(RECENT_BUTTON_WIDTH)
        self.recent_btn.setToolTip("Choose from recently used patterns")
        self.recent_btn.clicked.connect(self._show_recent_menu)
        pattern_row.addWidget(self.recent_btn)

        layout.addLayout(pattern_row)

        self.zero_pad_cb = QCheckBox("Zero-pad series number to 2 digits (e.g. 02)")
        self.zero_pad_cb.stateChanged.connect(self._refresh_preview)
        layout.addWidget(self.zero_pad_cb)

        mode_box = QGroupBox("Action")
        mode_layout = QVBoxLayout(mode_box)
        self.rename_radio = QRadioButton("Rename files in place (in their current folder)")
        self.export_radio = QRadioButton("Export renamed copies to a folder (originals untouched)")
        self.rename_radio.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self.rename_radio)
        group.addButton(self.export_radio)
        mode_layout.addWidget(self.rename_radio)

        export_row = QHBoxLayout()
        export_row.addWidget(self.export_radio)
        self.choose_folder_btn = QPushButton("Choose Folder…")
        self.choose_folder_btn.clicked.connect(self._choose_folder)
        self.choose_folder_btn.setEnabled(False)
        export_row.addWidget(self.choose_folder_btn)
        mode_layout.addLayout(export_row)

        self.folder_label = QLabel("(no folder chosen)")
        self.folder_label.setStyleSheet("color: gray; font-size: 11px;")
        mode_layout.addWidget(self.folder_label)

        self.rename_radio.toggled.connect(self._on_mode_toggled)
        self.export_radio.toggled.connect(self._on_mode_toggled)

        layout.addWidget(mode_box)

        self.preview_table = QTableWidget()
        self.preview_table.setColumnCount(2)
        self.preview_table.setHorizontalHeaderLabels(["Current filename", "New filename"])
        self.preview_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.preview_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.preview_table, 1)

        self.warning_label = QLabel("")
        self.warning_label.setStyleSheet("color: #b45309; font-size: 11px;")
        self.warning_label.setWordWrap(True)
        layout.addWidget(self.warning_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Apply")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)

        # Available field codes, always visible in their own panel to the
        # side rather than a single cramped line of text above the
        # pattern field -- double-click one to insert it at the cursor's
        # current position in the pattern field.
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

    # ------------------------------------------------------------------

    def _on_mode_toggled(self) -> None:
        self.choose_folder_btn.setEnabled(self.export_radio.isChecked())

    def _show_recent_menu(self) -> None:
        """Anchored to the pattern FIELD's bottom-left corner, not the
        small arrow button beside it -- so the menu appears right under
        where your eye already is (reading the pattern text), rather
        than off to the side under the button."""
        menu = QMenu(self)
        self._populate_recent_menu(menu)
        pos = self.pattern_edit.mapToGlobal(self.pattern_edit.rect().bottomLeft())
        menu.exec(pos)

    def _populate_recent_menu(self, menu: QMenu) -> None:
        """Full pattern text, never truncated -- a QMenu sizes itself to
        its widest item, unlike a fixed-width combo box."""
        history = app_settings.load_pattern_history()
        if not history:
            action = menu.addAction("(no recent patterns yet)")
            action.setEnabled(False)
            return
        for pattern in history:
            action = menu.addAction(pattern)
            action.triggered.connect(lambda _checked, p=pattern: self._on_recent_picked(p))

    def _on_recent_picked(self, pattern: str) -> None:
        self.pattern_edit.setText(pattern)

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose Output Folder")
        if folder:
            self.output_folder = folder
            self.folder_label.setText(folder)
            self._refresh_preview()

    # ------------------------------------------------------------------

    def _refresh_preview(self) -> None:
        pattern = self.pattern_edit.text()
        zero_pad = self.zero_pad_cb.isChecked()

        self.preview_table.setRowCount(len(self.books))
        new_names: list[str] = []
        for row, book in enumerate(self.books):
            old_name = os.path.basename(book.path)
            stem = render_filename(book.metadata, pattern, zero_pad, fallback=os.path.splitext(old_name)[0])
            new_name = stem + ".epub"
            new_names.append(new_name)

            self.preview_table.setItem(row, 0, QTableWidgetItem(old_name))
            self.preview_table.setItem(row, 1, QTableWidgetItem(new_name))
        self.preview_table.resizeColumnsToContents()

        # Warn (but don't block) about duplicate resulting names -- the
        # actual apply step will auto-number them, but it's worth flagging
        # since it usually means the pattern is too generic for this batch.
        dupes = {n for n in new_names if new_names.count(n) > 1}
        if dupes:
            self.warning_label.setText(
                f"Note: {len(dupes)} filename(s) would collide and will be "
                f"automatically numbered, e.g. \"{next(iter(dupes))}\" -> \"... (2).epub\"."
            )
        else:
            self.warning_label.setText("")

    # ------------------------------------------------------------------

    def _on_accept(self) -> None:
        if self.export_radio.isChecked() and not self.output_folder:
            self.warning_label.setText("Choose an output folder before applying.")
            self.warning_label.setStyleSheet("color: #b91c1c; font-size: 11px;")
            return
        # Only patterns that were actually applied get remembered -- not
        # every keystroke while the user was experimenting.
        app_settings.save_pattern_used(self.pattern_edit.text())
        self.accept()

    # ------------------------------------------------------------------
    # Result accessors, read by the caller after exec() returns Accepted

    def result_pattern(self) -> str:
        return self.pattern_edit.text()

    def result_zero_pad(self) -> bool:
        return self.zero_pad_cb.isChecked()

    def result_mode(self) -> str:
        return "export" if self.export_radio.isChecked() else "rename"

    def result_output_folder(self) -> str | None:
        return self.output_folder
