"""
gui/filename_parse_dialog.py

The reverse of the Rename/Export dialog: instead of building a filename
from metadata, this extracts metadata FROM a filename using the same
%field% pattern syntax (see core/filename_parser.py). Shares its pattern
history with Rename/Export via gui/app_settings -- if you've already
described your naming convention there, it's the natural pattern to
parse back with too.

Every candidate pattern -- your own history AND a handful of common
built-in naming templates (core.rename_pattern.SUGGESTED_PATTERNS) -- is
checked against the actual loaded filenames and offered ranked by how
many it matches, best first. This replaced an earlier "detect the
pattern from one already-correctly-tagged book" feature: in practice
there's rarely a conveniently well-tagged book sitting in the very
batch that needs fixing, so it added a manual step that usually had
nothing to work with. Matching a batch of filenames against known-good
templates needs nothing pre-existing to work from at all.
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
    count_matching_filenames,
    field_value_counts,
    folder_metadata_field_counts,
    normalize_field_value,
    parse_filename,
    parsed_to_metadata_kwargs,
    sibling_epub_stems,
)
from core.rename_pattern import DEFAULT_PATTERN, PLACEHOLDERS, SUGGESTED_PATTERNS
from gui import app_settings

# Fields worth cross-checking for repetition across other books -- ones
# a real library commonly has SEVERAL entries sharing the exact same
# value for. %title% is deliberately excluded: it's supposed to be
# different in nearly every file, so repetition there wouldn't confirm
# anything.
_CONFIRMABLE_FIELDS = ("authors", "series")

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
        # Directory -> sibling .epub stems, populated lazily and kept for
        # the dialog's whole lifetime -- the listing itself never changes
        # while this dialog is open, even though _refresh_preview() reruns
        # on every keystroke as the pattern is edited.
        self._sibling_stems_cache: dict[str, list[str]] = {}
        # (directory, field) -> value counts from OTHER files' own saved
        # metadata (see folder_metadata_field_counts()) -- unlike the
        # sibling-filename check above, this doesn't depend on the
        # pattern text at all (it's real metadata, not re-parsed from a
        # filename), so it's cached for the dialog's whole lifetime too,
        # never invalidated by editing the pattern field.
        self._folder_metadata_cache: dict[tuple[str, str], dict[str, int]] = {}

        self._build_ui()
        self._refresh_preview()

    def _build_ui(self) -> None:
        outer = QHBoxLayout(self)

        layout = QVBoxLayout()
        outer.addLayout(layout, 2)
        intro_label = QLabel(
            f"Applies to {len(self.books)} book(s). Only fields present in the pattern "
            "are extracted and offered; everything else is left untouched. Patterns below "
            "are ranked by how many of these filenames they actually match, best first -- "
            "including a few common naming templates tried automatically alongside your own "
            "pattern history. An extracted author or series is marked “confirmed” when the "
            "same value shows up for another loaded book, another filename in the same folder, "
            "or another file's existing metadata in that folder."
        )
        # Without setWordWrap(), a QLabel's size hint wants the ENTIRE
        # text on one line -- for a sentence this long, that forces the
        # whole dialog (and the window itself) to stretch far wider than
        # the screen to fit it. Every other label in this dialog already
        # wraps; this one was just missed.
        intro_label.setWordWrap(True)
        layout.addWidget(intro_label)

        pattern_row = QHBoxLayout()
        pattern_row.addWidget(QLabel("Pattern:"))
        # Rather than just reusing whatever pattern was used last (which
        # could easily be from a completely different batch of books),
        # check every candidate -- pattern history AND the built-in
        # suggested templates -- against THESE filenames and start with
        # whichever one actually fits best, falling back to the
        # last-used pattern only if nothing matches anything here. See
        # _refresh_preview() for the "auto-detected" status message this
        # produces on first load.
        scored_candidates = self._scored_candidates()
        best = scored_candidates[0] if scored_candidates else None
        if best and best[1] > 0:
            starting_pattern = best[0]
            self._auto_detected_pattern = best[0]
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
        for pattern, label in self._candidate_pattern_labels():
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
        for pattern, label in self._candidate_pattern_labels():
            item = QListWidgetItem(label)
            if pattern is None:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable & ~Qt.ItemFlag.ItemIsEnabled)
            else:
                item.setData(Qt.ItemDataRole.UserRole, pattern)
            self.recent_list.addItem(item)

    def _scored_candidates(self) -> list[tuple[str, int, bool]]:
        """(pattern, match_count, is_from_history) for every pattern
        worth offering -- the user's own pattern history plus a handful
        of common built-in naming templates (SUGGESTED_PATTERNS) not
        already in that history -- each checked against the CURRENTLY
        LOADED filenames and sorted by match count, best first. Ties
        keep their original relative order (Python's sort is stable),
        which is history before built-ins, and within each, the order
        they were already in (most-recent-first for history) -- so a
        built-in template only actually outranks something from history
        when it genuinely fits these files better, not merely because
        it's listed first."""
        history = app_settings.load_pattern_history()
        combined = [(p, True) for p in history] + [(p, False) for p in SUGGESTED_PATTERNS if p not in history]
        scored = [
            (pattern, count_matching_filenames(self._filename_stems, pattern), is_history)
            for pattern, is_history in combined
        ]
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored

    def _candidate_pattern_labels(self) -> list[tuple[str | None, str]]:
        """(pattern, display label) pairs, ranked best-match-first -- see
        _scored_candidates(). A pattern of None marks a disabled
        placeholder entry (shown only when there's nothing to offer at
        all), not a real, pickable pattern."""
        scored = self._scored_candidates()
        if not scored:
            return [(None, "(no recent patterns yet)")]
        labels = []
        for pattern, count, is_history in scored:
            suffix = "" if is_history else "  (built-in template)"
            labels.append((pattern, f"{pattern}   \u2014   {count}/{len(self.books)} match{suffix}"))
        return labels

    def _on_recent_list_clicked(self, item: QListWidgetItem) -> None:
        pattern = item.data(Qt.ItemDataRole.UserRole)
        if pattern:
            self._on_recent_picked(pattern)

    def _on_recent_picked(self, pattern: str) -> None:
        self.pattern_edit.setText(pattern)

    def _sibling_stems_for(self, book_path: str) -> list[str]:
        directory = os.path.dirname(book_path)
        cached = self._sibling_stems_cache.get(directory)
        if cached is None:
            cached = sibling_epub_stems(book_path)
            self._sibling_stems_cache[directory] = cached
        return cached

    def _folder_metadata_counts_for(self, book_path: str, field: str) -> dict[str, int]:
        directory = os.path.dirname(book_path)
        key = (directory, field)
        cached = self._folder_metadata_cache.get(key)
        if cached is None:
            cached = folder_metadata_field_counts(directory, field, exclude_path=book_path)
            self._folder_metadata_cache[key] = cached
        return cached

    def _confirmation_note(
        self, field: str, value: str, book_path: str, pattern: str,
        batch_counts: dict[str, dict[str, int]], folder_counts_cache: dict[tuple[str, str], dict[str, int]],
    ) -> str | None:
        """Whether `value` (this row's %authors% or %series%) is
        corroborated by any OTHER book, checked in ascending order of
        cost, stopping at the first tier that confirms it:

        1. Other books already loaded into this dialog -- free, already
           parsed for the batch as a whole.
        2. Other filenames in this book's own folder on disk, parsed
           with the SAME pattern -- a plain directory listing plus
           regex, no files opened.
        3. Other files' OWN saved metadata in that folder -- the most
           expensive tier (actually opens each candidate epub), so it's
           tried last and capped (see MAX_SIBLINGS_OPENED_FOR_METADATA_
           CHECK) -- but also the most authoritative: the book actually
           being fixed here essentially never has good metadata of its
           own to check against (if it did, it wouldn't need this tool),
           but nothing says every OTHER file in the same folder is in
           that same boat -- a handful of newly added, badly-named
           books dropped into an otherwise well-tagged genre folder is
           exactly this situation.

        Comparison is case/whitespace-insensitive (normalize_field_value)
        throughout, so "Terry Pratchett" and "TERRY PRATCHETT" agree. A
        repeating value is real evidence the pattern assigned this
        field's role correctly; a one-off isn't necessarily wrong, just
        unconfirmed by this signal, so it gets no note rather than a
        warning."""
        normalized = normalize_field_value(value)

        batch_count = batch_counts.get(field, {}).get(normalized, 0)
        if batch_count >= 2:
            return f"{field}: confirmed, shared with {batch_count - 1} other loaded book(s)"

        directory = os.path.dirname(book_path)
        cache_key = (directory, field)
        if cache_key not in folder_counts_cache:
            folder_counts_cache[cache_key] = field_value_counts(
                self._sibling_stems_for(book_path), pattern, field
            )
        folder_count = folder_counts_cache[cache_key].get(normalized, 0)
        if folder_count >= 1:
            return f"{field}: confirmed, also found in {folder_count} other filename(s) in this folder"

        metadata_count = self._folder_metadata_counts_for(book_path, field).get(normalized, 0)
        if metadata_count >= 1:
            return f"{field}: confirmed via existing metadata in {metadata_count} other book(s) in this folder"

        return None

    def _refresh_preview(self) -> None:
        pattern = self.pattern_edit.text()
        self._checkboxes = {}
        self._parsed = {}

        batch_counts = {
            field: field_value_counts(self._filename_stems, pattern, field) for field in _CONFIRMABLE_FIELDS
        } if pattern.strip() else {}
        folder_counts_cache: dict[tuple[str, str], dict[str, int]] = {}

        self.preview_table.setRowCount(len(self.books))
        matched_count = 0
        for row, book in enumerate(self.books):
            stem = self._filename_stems[row]
            self.preview_table.setItem(row, BOOK_COL, self._readonly_item(os.path.basename(book.path)))

            parsed = parse_filename(stem, pattern) if pattern.strip() else None
            non_empty = {k: v for k, v in (parsed or {}).items() if v}

            notes = []
            for field in _CONFIRMABLE_FIELDS:
                value = non_empty.get(field)
                if value:
                    note = self._confirmation_note(field, value, book.path, pattern, batch_counts, folder_counts_cache)
                    if note:
                        notes.append(note)

            non_empty = parsed_to_metadata_kwargs(non_empty)

            cb = QCheckBox()
            if non_empty:
                summary = "; ".join(f"{k}: {v}" for k, v in non_empty.items())
                if notes:
                    summary += "  [" + "; ".join(notes) + "]"
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
                f"Best-matching pattern selected automatically: {matched_count} of {len(self.books)} "
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
