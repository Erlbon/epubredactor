"""
gui/about_dialog.py

Two small read-only info dialogs: About (logo + version info + the
content of ABOUT.md) and the Changelog viewer (shows CHANGELOG.md).
Both render real Markdown -- via Qt's own built-in Markdown support
(QTextDocument.setMarkdown(), which QTextBrowser exposes directly),
rather than showing the raw ## headers and [link](url) syntax as flat
text. No editing, no external fetches, nothing more complex than
reading a bundled file and letting Qt render it.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTextBrowser,
    QVBoxLayout,
)

from core.version import APP_NAME, APP_VERSION, RELEASE_LABEL


def _read_text_file(path: str) -> str:
    if not path or not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _markdown_browser(markdown_text: str) -> QTextBrowser:
    browser = QTextBrowser()
    browser.setOpenExternalLinks(True)  # links open in the system browser, not in-app
    browser.setMarkdown(markdown_text or "*(nothing to show)*")
    return browser


class AboutDialog(QDialog):
    def __init__(self, icon_path: str, about_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"About {APP_NAME}")
        self.resize(520, 560)

        layout = QVBoxLayout(self)

        if icon_path and os.path.exists(icon_path):
            logo_label = QLabel()
            pixmap = QPixmap(icon_path).scaled(
                96, 96, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            logo_label.setPixmap(pixmap)
            logo_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            layout.addWidget(logo_label)

        header = QLabel(f"<h2>{APP_NAME}</h2><p>{RELEASE_LABEL}, ver {APP_VERSION}</p>")
        header.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        header.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(header)

        about_text = _read_text_file(about_path)
        layout.addWidget(_markdown_browser(about_text), 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.accept)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


class ChangelogDialog(QDialog):
    def __init__(self, changelog_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Changelog")
        self.resize(560, 560)

        layout = QVBoxLayout(self)
        text = _read_text_file(changelog_path)
        layout.addWidget(_markdown_browser(text), 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.accept)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
