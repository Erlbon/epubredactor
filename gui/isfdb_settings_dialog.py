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
from redactor_common.core.local_db import LocalDatabaseError
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
            # The shared build tail: the default path is the placeholder, Browse's start and the build's
            # destination; Browse is a Save dialog (the file may not exist yet); a status line under the path.
            default_path=app_settings.default_isfdb_database_path,
            browse_for_destination=True,
            show_status=True,
        )
        self.setMinimumWidth(620)

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
        self.add_section(box)  # under the status line, above the Check File / Build row

    # -- widgets -------------------------------------------------------------------------

    def _browse_backup(self) -> None:
        start = self.backup_edit.text() or app_settings.load_last_directory()
        path, _ = QFileDialog.getOpenFileName(self, "Choose the ISFDB MySQL backup", start, BACKUP_FILTER)
        if path:
            self.backup_edit.setText(path)

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
        # redactor_common's build tail: asks (adding "replaced only when the new one is complete" when the file
        # exists), saves the backup path first so it is remembered even if the build is cancelled, releases a
        # cached open handle, builds on a worker thread behind a cancellable progress dialog, reports the result.
        return self.run_build(
            "Build ISFDB Database", "Reading the ISFDB backup…",
            lambda dest, progress, cancelled: build_isfdb_database(backup, dest, progress, cancelled),
            confirm="Build {name} from the ISFDB backup?\n\nIt reads the whole backup, which takes a few minutes, "
                    "and needs a few hundred MB of free disk space.",
        )
