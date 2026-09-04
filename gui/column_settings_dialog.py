"""
gui/column_settings_dialog.py

Add/Remove Columns: toggle which table columns are visible. Filename
stays always-visible (it's the only reliable way to tell rows apart);
everything else can be hidden to declutter the view.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QVBoxLayout, QWidget


class ColumnSettingsDialog(QDialog):
    def __init__(
        self,
        column_names: list[str],
        hidden_indices: set[int],
        locked_indices: set[int],
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Add/Remove Columns")
        self.resize(300, 420)
        self._checkboxes: dict[int, QCheckBox] = {}

        layout = QVBoxLayout(self)
        container = QWidget()
        inner_layout = QVBoxLayout(container)
        for i, name in enumerate(column_names):
            cb = QCheckBox(name)
            cb.setChecked(i not in hidden_indices)
            if i in locked_indices:
                cb.setEnabled(False)
                cb.setToolTip("Always visible")
            self._checkboxes[i] = cb
            inner_layout.addWidget(cb)
        inner_layout.addStretch(1)
        layout.addWidget(container, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.accept)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def visible_indices(self) -> set[int]:
        return {i for i, cb in self._checkboxes.items() if cb.isChecked()}
