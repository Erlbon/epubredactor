"""
gui/send_to_ereader_dialog.py

Send to eReader (Wireless): manages a list of send2ereader-style server
URLs (https://github.com/daniel-j/send2ereader -- self-hostable; the
public instance at send.djazz.se ships as a starting suggestion) and
streamlines the manual handoff to one of them.

This deliberately does NOT attempt to silently automate the actual
upload. send2ereader has no documented API -- even people trying to
self-host it report there's no README or spec for the wire protocol
(see the project's own issue tracker) -- so guessing at endpoint names
and shipping that as if it were verified would risk silent, confusing
failures. Instead: pick a server, this opens it in your browser and
opens the selected book's containing folder in Explorer, so the only
manual step left is dragging the file in and typing the key your
e-reader's browser shows -- same as using the site directly, just
without hunting for the file first.
"""

from __future__ import annotations

import os
import webbrowser

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core.epub_metadata import EpubBook
from gui import app_settings
from redactor_common.core.os_utils import reveal_in_file_manager


class SendToEreaderDialog(QDialog):
    def __init__(self, books: list[EpubBook], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Send to eReader (Wireless)")
        self.resize(480, 420)
        self.books = books

        self._build_ui()
        self._refresh_servers()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        info = QLabel(
            "Uses a send2ereader-style service (self-hostable: "
            "github.com/daniel-j/send2ereader) to send books to your e-reader over "
            "wireless. send2ereader has no documented upload API, so this app can't "
            "safely automate the transfer -- pick a server below, and this opens it "
            "in your browser plus the book's folder, ready to drag in."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        server_row = QHBoxLayout()
        server_row.addWidget(QLabel("Server:"))
        self.server_combo = QComboBox()
        server_row.addWidget(self.server_combo, 1)
        self.add_server_btn = QPushButton("Add…")
        self.add_server_btn.clicked.connect(self._on_add_server)
        server_row.addWidget(self.add_server_btn)
        self.remove_server_btn = QPushButton("Remove")
        self.remove_server_btn.clicked.connect(self._on_remove_server)
        server_row.addWidget(self.remove_server_btn)
        layout.addLayout(server_row)

        self.book_list = QListWidget()
        for book in self.books:
            self.book_list.addItem(os.path.basename(book.path))
        if self.books:
            self.book_list.setCurrentRow(0)
        layout.addWidget(self.book_list, 1)

        steps = QLabel(
            "1. On your e-reader's own browser, open the same server and note the "
            "key it shows.\n"
            "2. Click \"Open Server + Folder\" below.\n"
            "3. On the server page (opened in your browser), enter the key, then "
            "drag in the file from the folder window that also opened."
        )
        steps.setWordWrap(True)
        steps.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(steps)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.open_btn = buttons.addButton("Open Server + Folder", QDialogButtonBox.ButtonRole.ActionRole)
        self.open_btn.clicked.connect(self._on_open)
        buttons.rejected.connect(self.accept)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def _refresh_servers(self) -> None:
        current = self.server_combo.currentText()
        self.server_combo.clear()
        servers = app_settings.load_ereader_servers()
        self.server_combo.addItems(servers)
        if current in servers:
            self.server_combo.setCurrentText(current)

    def _on_add_server(self) -> None:
        url, ok = QInputDialog.getText(
            self, "Add Server",
            "Server URL (e.g. your own self-hosted send2ereader instance):",
            text="https://",
        )
        if ok and url.strip():
            app_settings.add_ereader_server(url.strip())
            self._refresh_servers()
            self.server_combo.setCurrentIndex(self.server_combo.count() - 1)

    def _on_remove_server(self) -> None:
        url = self.server_combo.currentText()
        if not url:
            return
        reply = QMessageBox.question(
            self, "Remove Server", f"Remove \"{url}\" from your server list?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            app_settings.remove_ereader_server(url)
            self._refresh_servers()

    def _on_open(self) -> None:
        server = self.server_combo.currentText()
        if not server:
            QMessageBox.information(self, "No server", "Add or select a server first.")
            return
        row = self.book_list.currentRow()
        if row < 0 or row >= len(self.books):
            QMessageBox.information(self, "No book selected", "Select a book to send first.")
            return

        webbrowser.open(server)
        reveal_in_file_manager(self.books[row].path)
