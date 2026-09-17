"""
gui/blank_language_default_dialog.py

Settings -> Blank Language Default: lets the person enable/disable the
Repair menu's "Set Blank/Unknown Language to Default" action, and choose
which language it fills in. Kept as its own small settings dialog
(rather than a plain checkbox in some existing settings surface) since
it needs both a toggle and a language picker together.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)


class BlankLanguageDefaultDialog(QDialog):
    def __init__(
        self,
        enabled: bool,
        current_code: str,
        languages: list[tuple[str, str]],
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Blank Language Default")
        self.resize(380, 160)

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Controls Repair → Set Blank/Unknown Language to Default, which "
            "sets every book in the working set with no language (or a "
            "placeholder like \"unknown\") to the language chosen below -- "
            "applied immediately, with no per-book review."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.enabled_cb = QCheckBox("Enable this action (Repair menu)")
        self.enabled_cb.setChecked(enabled)
        layout.addWidget(self.enabled_cb)

        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel("Default language:"))
        self.language_combo = QComboBox()
        current_index = 0
        for i, (code, name) in enumerate(languages):
            self.language_combo.addItem(f"{name} ({code})", code)
            if code == current_code:
                current_index = i
        self.language_combo.setCurrentIndex(current_index)
        lang_row.addWidget(self.language_combo, 1)
        layout.addLayout(lang_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def result_enabled(self) -> bool:
        return self.enabled_cb.isChecked()

    def result_code(self) -> str:
        return self.language_combo.currentData() or "en"
