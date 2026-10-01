"""
gui/open_library_settings_dialog.py

Tools > Open Library Database... -- points the app at an offline Open
Library lookup database and builds it. Open Library's bulk dumps are
huge (the editions file alone is several GB compressed), so the app never
downloads them: the user fetches the editions dump (and the authors dump,
for author names) from openlibrary.org/developers/dumps, picks them here,
chooses which languages to keep, and Build Database... converts them
(core/openlibrary_import.py) behind a cancellable progress dialog.

redactor_common's LocalDatabaseSettingsDialog supplies the database path,
Check File and the Build button; this adds the two source pickers, the
language options and a status line (what the file was built from).
"""

from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)
from redactor_common.core.dump_import import DumpImportError
from redactor_common.core.local_db import LocalDatabaseError, forget_cached
from redactor_common.gui.dump_import_runner import run_dump_import
from redactor_common.gui.local_db_settings_dialog import LocalDatabaseSettingsDialog

from core.openlibrary_import import (
    LANGUAGE_CHOICES,
    BuildOptions,
    build_openlibrary_database,
    describe_database,
)
from gui import app_settings

DUMPS_URL = "https://openlibrary.org/developers/dumps"
DUMP_FILTER = "Open Library dump (*.txt *.txt.gz *.gz *.bz2 *.xz *.zip);;All files (*)"

INSTRUCTIONS = (
    "Look up books offline in <b>Open Library</b>: by ISBN, or by title and author, with no network "
    "and no rate limits.<br><br><b>Building it:</b><ol>"
    f"<li>From <a href=\"{DUMPS_URL}\">openlibrary.org/developers/dumps</a> download the "
    "<b>editions</b> dump (<code>ol_dump_editions_*.txt.gz</code>) and the <b>authors</b> dump "
    "(<code>ol_dump_authors_*.txt.gz</code>) -- or the single all-types <code>ol_dump_*.txt.gz</code>, "
    "which you then pick for both. They are several GB; keep them compressed.</li>"
    "<li>Choose them below, tick the languages to keep, and click <b>Build Database...</b>. "
    "Reading the dumps takes a while (tens of minutes); Cancel is safe.</li></ol>"
    "Only editions with a valid ISBN are kept. Expect roughly 2-3 GB for the default languages "
    "(more for all languages), plus about as much free disk space while it builds."
)


class OpenLibrarySettingsDialog(LocalDatabaseSettingsDialog):
    def __init__(self, parent=None):
        super().__init__(
            title="Open Library Database",
            instructions_html=INSTRUCTIONS,
            path=app_settings.load_open_library_database(),
            check=describe_database,
            save=self._save_all,
            error_types=(LocalDatabaseError,),
            file_filter="SQLite database (*.db *.sqlite *.sqlite3);;All files (*)",
            build=lambda dialog: self._build_database(),
            build_label="Build Database…",
            parent=parent,
        )
        self.setMinimumWidth(620)
        self.path_edit.setPlaceholderText(app_settings.default_open_library_database_path())
        options = app_settings.load_open_library_build_options()
        editions, authors = app_settings.load_open_library_sources()

        box = QGroupBox("Build from Open Library dumps")
        layout = QVBoxLayout(box)
        self.editions_edit = self._picker(layout, "Editions dump:", editions)
        self.authors_edit = self._picker(layout, "Authors dump:", authors, optional=True)

        layout.addWidget(QLabel("Keep editions in these languages:"))
        grid = QGridLayout()
        self.language_boxes: dict[str, QCheckBox] = {}
        for index, (lang_id, label, _codes) in enumerate(LANGUAGE_CHOICES):
            language_box = QCheckBox(label)
            language_box.setChecked(lang_id in options.languages)
            self.language_boxes[lang_id] = language_box
            grid.addWidget(language_box, index // 3, index % 3)
        layout.addLayout(grid)
        self.all_languages = QCheckBox("All languages (a much larger database)")
        self.all_languages.setChecked(options.all_languages)
        self.all_languages.toggled.connect(self._sync_language_boxes)
        layout.addWidget(self.all_languages)
        self.unknown_language = QCheckBox("Also keep editions with no language recorded")
        self.unknown_language.setChecked(options.include_unknown_language)
        layout.addWidget(self.unknown_language)
        self._sync_language_boxes()

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        # Between the path row and the Check File / Build row.
        self.layout().insertWidget(2, box)
        self.layout().insertWidget(2, self.status_label)
        self.path_edit.textChanged.connect(self._refresh_status)
        self._refresh_status()

    # -- widgets -------------------------------------------------------------------------

    def _picker(self, layout, label: str, value: str, optional: bool = False) -> QLineEdit:
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        edit = QLineEdit(value)
        edit.setPlaceholderText(
            "Optional -- without it books have no author names" if optional else "Path to the dump file"
        )
        browse = QPushButton("Browse…")
        browse.clicked.connect(lambda: self._browse_dump(edit, label))
        row.addWidget(edit, 1)
        row.addWidget(browse)
        layout.addLayout(row)
        return edit

    def _browse_dump(self, edit: QLineEdit, label: str) -> None:
        start = edit.text() or os.path.dirname(self.editions_edit.text() or "") or app_settings.load_last_directory()
        path, _ = QFileDialog.getOpenFileName(self, f"Choose the {label.rstrip(':').lower()}", start, DUMP_FILTER)
        if path:
            edit.setText(path)

    def _sync_language_boxes(self) -> None:
        everything = self.all_languages.isChecked()
        for language_box in self.language_boxes.values():
            language_box.setEnabled(not everything)
        self.unknown_language.setEnabled(not everything)

    def _browse(self) -> None:
        """The database may not exist yet, so this is a Save dialog that doesn't
        ask to overwrite (picking an existing file just selects it)."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Choose where the database is (or will be) stored",
            self.path_edit.text().strip() or app_settings.default_open_library_database_path(),
            self._file_filter, options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if path:
            self.path_edit.setText(path)

    def _refresh_status(self) -> None:
        path = self.path_edit.text().strip()
        if not path:
            self.status_label.setText("No database yet.")
        elif not os.path.isfile(path):
            self.status_label.setText("Not built yet -- the file doesn't exist.")
        else:
            ok, message = self.check_result()
            self.status_label.setText(message if ok else f"Problem: {message}")

    # -- options / build -----------------------------------------------------------------

    def build_options(self) -> BuildOptions:
        return BuildOptions(
            languages=tuple(lang_id for lang_id, box in self.language_boxes.items() if box.isChecked()),
            all_languages=self.all_languages.isChecked(),
            include_unknown_language=self.unknown_language.isChecked(),
        )

    def _save_all(self, path: str) -> None:
        app_settings.save_open_library_database(path)
        app_settings.save_open_library_sources(self.editions_edit.text().strip(), self.authors_edit.text().strip())
        app_settings.save_open_library_build_options(self.build_options())

    def _build_database(self) -> Optional[str]:
        """Converts the chosen dumps; returns the new database's path (None
        if abandoned, cancelled or failed)."""
        editions = self.editions_edit.text().strip()
        authors = self.authors_edit.text().strip()
        if not editions:
            QMessageBox.information(self, "Build Database", "Choose the editions dump first.")
            return None
        options = self.build_options()
        if not options.all_languages and not options.languages and not options.include_unknown_language:
            QMessageBox.information(self, "Build Database", "Tick at least one language, or All languages.")
            return None
        dest = self.path_edit.text().strip() or app_settings.default_open_library_database_path()
        replacing = (
            "\n\nThe existing database is replaced only when the new one is complete." if os.path.exists(dest) else ""
        )
        answer = QMessageBox.question(
            self, "Build Database",
            f"Build {os.path.basename(dest)} from the dump(s)?\n\nIt reads the whole dump, which can take tens of "
            f"minutes, and needs a few GB of free disk space. Keeping: {options.describe()}.{replacing}",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return None
        self._save_all(dest)  # remember the sources even if the build is cancelled
        forget_cached(dest)  # a lookup may still hold the old build open
        try:
            summary = run_dump_import(
                self, "Build Open Library Database", "Reading the Open Library dumps…",
                lambda progress, cancelled: build_openlibrary_database(
                    editions, dest, authors, options, progress, cancelled
                ),
            )
        except DumpImportError as exc:
            QMessageBox.warning(self, "Build Open Library Database", str(exc))
            return None
        if summary is None:
            return None
        QMessageBox.information(self, "Build Open Library Database", summary.describe())
        self.path_edit.setText(dest)
        self._refresh_status()
        return dest
