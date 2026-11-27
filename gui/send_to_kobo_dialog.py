"""
gui/send_to_kobo_dialog.py

Send to Kobo (USB): detects a Kobo connected via USB (by its .kobo
marker folder -- see core/kobo_usb.py) and copies selected books
straight onto it. No network, no third-party server -- the same
mechanism Calibre itself uses for on-device sync.

Each copy runs off the GUI thread under a progress dialog whose Cancel
stops it (the half-copied file is removed). A book of the same name on
the Kobo is replaced (or, with the box unticked, left alone and the book
skipped). Books with unsaved changes are named first, with "Save and
Send" or "Send Anyway": the Kobo gets the file as it is on disk.
"""

from __future__ import annotations

import os
import threading
from typing import Callable

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core.epub_metadata import EpubBook
from core.kobo_usb import KoboSendCancelled, KoboSendError, find_connected_kobos, send_to_kobo
from redactor_common.gui.background_call import call_in_background
from redactor_common.gui.progress import run_with_progress
from redactor_common.gui.owned_dialog import OwnedDialog

UNSAVED_SAVE, UNSAVED_SEND_ANYWAY, UNSAVED_CANCEL = "save", "anyway", "cancel"

# save_books(books) -> [(path, error)] for the ones that could not be saved (main_window._save_books in place).
SaveBooks = Callable[[list[EpubBook]], list[tuple[str, str]]]


class SendToKoboDialog(OwnedDialog):
    def __init__(self, books: list[EpubBook], parent=None, save_books: SaveBooks | None = None):
        super().__init__(parent)
        self.setWindowTitle("Send to Kobo (USB)")
        self.resize(480, 420)
        self.books = books
        self._save_books = save_books
        self._sent_count = 0
        self.saved_any = False  # the caller refreshes the table when Save and Send saved something

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

        self.replace_cb = QCheckBox("Replace a book with the same file name already on the Kobo")
        self.replace_cb.setToolTip(
            "Ticked: the copy on the Kobo is replaced by this one (sending an edited book again).\n"
            "Unticked: such a book is skipped and the Kobo's copy is left alone."
        )
        self.replace_cb.setChecked(True)
        layout.addWidget(self.replace_cb)

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

    def _ask_about_unsaved(self, unsaved: list[EpubBook]) -> str:
        """Names the books with unsaved changes; returns UNSAVED_SAVE, UNSAVED_SEND_ANYWAY or UNSAVED_CANCEL."""
        names = ", ".join(os.path.basename(b.path) for b in unsaved[:5])
        more = f", and {len(unsaved) - 5} more" if len(unsaved) > 5 else ""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Unsaved changes")
        box.setText(
            f"{len(unsaved)} book(s) have unsaved changes ({names}{more}). The Kobo gets the file as it is on "
            "disk, so without saving it gets the old metadata and cover."
        )
        save_btn = box.addButton("Save and Send", QMessageBox.ButtonRole.AcceptRole) if self._save_books else None
        anyway_btn = box.addButton("Send Anyway", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(save_btn or anyway_btn)
        box.exec()
        clicked = box.clickedButton()
        if save_btn is not None and clicked is save_btn:
            return UNSAVED_SAVE
        if clicked is anyway_btn:
            return UNSAVED_SEND_ANYWAY
        return UNSAVED_CANCEL

    def _run_send(self) -> None:
        kobo_root = self.device_combo.currentText()
        if not kobo_root:
            return

        books = list(self.books)
        errors: list[str] = []
        unsaved = [b for b in books if b.dirty and not b.load_error]
        if unsaved:
            answer = self._ask_about_unsaved(unsaved)
            if answer == UNSAVED_CANCEL:
                return
            if answer == UNSAVED_SAVE and self._save_books is not None:
                self.saved_any = True
                failed = {os.path.normcase(os.path.abspath(p)): err for p, err in self._save_books(unsaved)}
                if failed:
                    # A book that could not be saved is not sent: the Kobo would get the old file.
                    errors += [f"{os.path.basename(p)}: not sent, the save failed ({err})" for p, err in failed.items()]
                    books = [b for b in books if os.path.normcase(os.path.abspath(b.path)) not in failed]

        sent = 0
        skipped: list[str] = []
        replace = self.replace_cb.isChecked()
        # Each copy runs off the GUI thread (a big book on a slow USB stick froze the window); Cancel stops it.
        cancel = threading.Event()

        def _step(book: EpubBook, _index: int) -> None:
            nonlocal sent
            try:
                written = call_in_background(
                    send_to_kobo, kobo_root, book.path, replace_existing=replace, cancel=cancel,
                )
            except KoboSendCancelled:
                return
            except KoboSendError as exc:
                errors.append(f"{os.path.basename(book.path)}: {exc}")
                return
            if written:
                sent += 1
            else:
                skipped.append(os.path.basename(book.path))

        run_with_progress(
            self, books, _step, "Sending to Kobo…", threshold=1,
            label_for=lambda book: f"Sending: {os.path.basename(book.path)}",
            on_cancel=cancel.set,
        )
        self._sent_count = sent

        notes = []
        if skipped:
            names = ", ".join(skipped[:5]) + (f", and {len(skipped) - 5} more" if len(skipped) > 5 else "")
            notes.append(f"Skipped {len(skipped)} already on the Kobo ({names}).")
        if errors:
            details = "\n".join(errors[:5]) + ("\n..." if len(errors) > 5 else "")
            notes.append(f"Failed:\n{details}")
        if notes:
            QMessageBox.warning(
                self, "Some books were not sent",
                f"Sent {sent} of {len(self.books)}.\n\n" + "\n\n".join(notes),
            )

        if sent:
            self.accept()

    def sent_count(self) -> int:
        return self._sent_count
