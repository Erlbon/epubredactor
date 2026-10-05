"""
gui/isfdb_settings_dialog.py

Tools > ISFDB Database... -- points the app at an offline ISFDB lookup
database and builds it. The ISFDB (Internet Speculative Fiction Database,
isfdb.org) publishes its whole database as a MySQL backup (about 0.3 GB
zipped); the app never downloads it: the user fetches it from isfdb.org
(Downloads), picks it here, and Build Database... converts it
(core/isfdb_import.py) behind a cancellable progress dialog.

What ISFDB adds for this app is the book's SERIES and its number, plus
title/author lookup of science fiction, fantasy and horror.

redactor_common's LocalDatabaseSettingsDialog supplies the database path,
Check File and the Build button; this adds the backup picker and a
status line (what the file was built from).
"""

from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtWidgets import (
    QFileDialog,
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

from core.isfdb_import import build_isfdb_database, describe_database
from gui import app_settings

DOWNLOADS_URL = "https://www.isfdb.org/wiki/index.php/ISFDB_Downloads"
BACKUP_FILTER = "ISFDB backup (*.zip *.sql *.gz *.bz2 *.xz);;All files (*)"

INSTRUCTIONS = (
    "Look up books offline in the <b>ISFDB</b> (Internet Speculative Fiction Database): by ISBN, or by title "
    "and author, with no network and no rate limits. Its strength is the book's <b>series and number</b>, which "
    "Open Library lacks; it covers science fiction, fantasy and horror.<br><br><b>Building it:</b><ol>"
    f"<li>From <a href=\"{DOWNLOADS_URL}\">isfdb.org/wiki/index.php/ISFDB_Downloads</a> download the latest "
    "<b>MySQL backup</b> (<code>backup-MySQL-55-YYYY-MM-DD.zip</code>, a few hundred MB). Keep it zipped.</li>"
    "<li>Choose it below and click <b>Build Database...</b>. It takes a couple of minutes; Cancel is safe.</li></ol>"
    "Expect roughly 150 MB for the database, plus about the same free disk space for a temporary file while it "
    "builds. ISFDB's data is licensed Creative Commons Attribution (credited under Help &gt; Credits)."
)


class IsfdbSettingsDialog(LocalDatabaseSettingsDialog):
    def __init__(self, parent=None):
        super().__init__(
            title="ISFDB Database",
            instructions_html=INSTRUCTIONS,
            path=app_settings.load_isfdb_database(),
            check=describe_database,
            save=self._save_all,
            error_types=(LocalDatabaseError,),
            file_filter="SQLite database (*.db *.sqlite *.sqlite3);;All files (*)",
            build=lambda dialog: self._build_database(),
            build_label="Build Database…",
            parent=parent,
        )
        self.setMinimumWidth(620)
        self.path_edit.setPlaceholderText(app_settings.default_isfdb_database_path())

        box = QGroupBox("Build from the ISFDB backup")
        layout = QVBoxLayout(box)
        row = QHBoxLayout()
        row.addWidget(QLabel("MySQL backup:"))
        self.backup_edit = QLineEdit(app_settings.load_isfdb_backup())
        self.backup_edit.setPlaceholderText("Path to backup-MySQL-55-….zip")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_backup)
        row.addWidget(self.backup_edit, 1)
        row.addWidget(browse)
        layout.addLayout(row)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        # Between the path row and the Check File / Build row.
        self.layout().insertWidget(2, box)
        self.layout().insertWidget(2, self.status_label)
        self.path_edit.textChanged.connect(self._refresh_status)
        self._refresh_status()

    # -- widgets -------------------------------------------------------------------------

    def _browse_backup(self) -> None:
        start = self.backup_edit.text() or app_settings.load_last_directory()
        path, _ = QFileDialog.getOpenFileName(self, "Choose the ISFDB MySQL backup", start, BACKUP_FILTER)
        if path:
            self.backup_edit.setText(path)

    def _browse(self) -> None:
        """The database may not exist yet, so this is a Save dialog that doesn't
        ask to overwrite (picking an existing file just selects it)."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Choose where the database is (or will be) stored",
            self.path_edit.text().strip() or app_settings.default_isfdb_database_path(),
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

    # -- build ---------------------------------------------------------------------------

    def _save_all(self, path: str) -> None:
        app_settings.save_isfdb_database(path)
        app_settings.save_isfdb_backup(self.backup_edit.text().strip())

    def _build_database(self) -> Optional[str]:
        """Converts the chosen backup; returns the new database's path (None
        if abandoned, cancelled or failed)."""
        backup = self.backup_edit.text().strip()
        if not backup:
            QMessageBox.information(self, "Build Database", "Choose the ISFDB MySQL backup first.")
            return None
        dest = self.path_edit.text().strip() or app_settings.default_isfdb_database_path()
        replacing = (
            "\n\nThe existing database is replaced only when the new one is complete." if os.path.exists(dest) else ""
        )
        answer = QMessageBox.question(
            self, "Build Database",
            f"Build {os.path.basename(dest)} from the ISFDB backup?\n\nIt reads the whole backup, which takes a few "
            f"minutes, and needs a few hundred MB of free disk space.{replacing}",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return None
        self._save_all(dest)  # remember the backup even if the build is cancelled
        forget_cached(dest)  # a lookup may still hold the old build open
        try:
            summary = run_dump_import(
                self, "Build ISFDB Database", "Reading the ISFDB backup…",
                lambda progress, cancelled: build_isfdb_database(backup, dest, progress, cancelled),
            )
        except DumpImportError as exc:
            QMessageBox.warning(self, "Build ISFDB Database", str(exc))
            return None
        if summary is None:
            return None
        QMessageBox.information(self, "Build ISFDB Database", summary.describe())
        self.path_edit.setText(dest)
        self._refresh_status()
        return dest
