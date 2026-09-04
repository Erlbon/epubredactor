"""
gui/send_to_kobo_dialog.py

Send to Kobo (USB): detects a Kobo connected via USB (by its .kobo
marker folder -- see core/kobo_usb.py) and copies selected books
straight onto it. No network, no third-party server -- the same
mechanism Calibre itself uses for on-device sync.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QVBoxLayout,
)

from core.epub_metadata import EpubBook
from core.kobo_usb import KoboSendError, find_connected_kobos, send_to_kobo


class SendToKoboDialog(QDialog):
    def __init__(self, books: list[EpubBook], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Send to Kobo (USB)")
        self.resize(480, 420)
        self.books = books
        self._sent_count = 0

        self._build_ui()
        self._refresh_kobos()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        info = QLabel(
            f"Copies {len(self.books)} book(s) directly onto a Kobo connected via USB "
            "(detected by its .kobo folder) -- the same mechanism Calibre itself uses. "
            "No network involved."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        device_row = QVBoxLayout()
        device_row.addWidget(QLabel("Connected Kobo:"))
        self.device_combo = QComboBox()
        device_row.addWidget(self.device_combo)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._refresh_kobos)
        device_row.addWidget(self.refresh_btn)
        layout.addLayout(device_row)

        self.book_list = QListWidget()
        for book in self.books:
            self.book_list.addItem(os.path.basename(book.path))
        layout.addWidget(self.book_list, 1)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self.status_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.send_btn = buttons.addButton("Send", QDialogButtonBox.ButtonRole.AcceptRole)
        self.send_btn.clicked.connect(self._run_send)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _refresh_kobos(self) -> None:
        self.device_combo.clear()
        kobos = find_connected_kobos()
        if not kobos:
            self.status_label.setText(
                "No Kobo detected. Connect it via USB (and make sure it's in USB/file "
                "transfer mode, not just charging), then click Refresh."
            )
            self.send_btn.setEnabled(False)
            return
        self.device_combo.addItems(kobos)
        self.status_label.setText(f"Found {len(kobos)} connected Kobo(s).")
        self.send_btn.setEnabled(bool(self.books))

    def _run_send(self) -> None:
        kobo_root = self.device_combo.currentText()
        if not kobo_root:
            return

        progress = QProgressDialog("Sending to Kobo…", "Cancel", 0, len(self.books), self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)

        sent = 0
        errors: list[str] = []
        for i, book in enumerate(self.books):
            if progress.wasCanceled():
                break
            progress.setValue(i)
            progress.setLabelText(f"Sending: {os.path.basename(book.path)}")
            QApplication.processEvents()
            try:
                send_to_kobo(kobo_root, book.path)
                sent += 1
            except KoboSendError as exc:
                errors.append(f"{os.path.basename(book.path)}: {exc}")

        progress.setValue(len(self.books))
        self._sent_count = sent

        if errors:
            details = "\n".join(errors[:5]) + ("\n..." if len(errors) > 5 else "")
            QMessageBox.warning(
                self, "Some books failed to send",
                f"Sent {sent} of {len(self.books)}.\n\nFailed:\n{details}",
            )

        if sent:
            self.accept()

    def sent_count(self) -> int:
        return self._sent_count
