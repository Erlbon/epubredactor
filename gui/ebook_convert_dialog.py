"""
gui/ebook_convert_dialog.py

Import to EPUB: converts other ebook/document formats into EPUB via
Calibre's ebook-convert tool (see core/ebook_convert.py). Converted
files are returned to the caller (gui/main_window.py), which adds them
straight into the working list for metadata editing, the same as any
other loaded file.

Locating Calibre reuses the same install-folder setting as the metadata
lookup dialog (gui/calibre_lookup_dialog.py) -- point this app at your
Calibre install once, and both features use it.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QVBoxLayout,
)

from core.calibre_tools import find_tool
from core.ebook_convert import EbookConvertError, SUPPORTED_SOURCE_EXTENSIONS, convert_to_epub
from core.rename_pattern import unique_path
from gui import app_settings


def _file_filter() -> str:
    exts = " ".join(f"*{ext}" for ext in sorted(SUPPORTED_SOURCE_EXTENSIONS))
    return f"Supported formats ({exts})"


class EbookConvertDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import to EPUB")
        self.resize(600, 440)
        self._tool_path = ""
        self._source_paths: list[str] = []
        self._converted_paths: list[str] = []

        self._build_ui()
        self._resolve_tool()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        info = QLabel(
            "Converts other ebook/document formats to EPUB via your Calibre "
            "installation, then adds the results to your working list.\n"
            "PDF isn't offered here by default -- PDF-to-EPUB conversion "
            "quality is inconsistent, since PDFs have no real text-flow "
            "structure to extract."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(self.file_list.SelectionMode.ExtendedSelection)
        layout.addWidget(self.file_list, 1)

        btn_row = QHBoxLayout()
        self.add_files_btn = QPushButton("Add Files…")
        self.add_files_btn.clicked.connect(self._add_files)
        btn_row.addWidget(self.add_files_btn)
        self.remove_btn = QPushButton("Remove Selected")
        self.remove_btn.clicked.connect(self._remove_selected)
        btn_row.addWidget(self.remove_btn)
        btn_row.addStretch(1)
        self.change_tool_btn = QPushButton("Change Calibre Location…")
        self.change_tool_btn.clicked.connect(self._browse_for_tool)
        btn_row.addWidget(self.change_tool_btn)
        self.download_btn = QPushButton("Download Calibre…")
        self.download_btn.clicked.connect(lambda: webbrowser.open(DOWNLOAD_URL))
        self.download_btn.setVisible(False)  # only shown once Calibre genuinely can't be found
        btn_row.addWidget(self.download_btn)
        layout.addLayout(btn_row)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self.status_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.convert_btn = buttons.addButton("Convert", QDialogButtonBox.ButtonRole.AcceptRole)
        self.convert_btn.clicked.connect(self._run_conversion)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    # Locating Calibre's tool

    def _resolve_tool(self) -> None:
        configured_dir = app_settings.load_calibre_install_dir()
        found = find_tool("ebook-convert", configured_install_dir=configured_dir)
        if found is None:
            self.status_label.setText(
                "Couldn't find Calibre automatically. If you have it installed, click "
                "\"Change Calibre Location…\" and pick your install folder (shared with "
                "the metadata lookup feature, only needs doing once). If you don't have "
                "it, it's free -- click \"Download Calibre…\"."
            )
            self.download_btn.setVisible(True)
            self.convert_btn.setEnabled(False)
        else:
            self.download_btn.setVisible(False)
            self._tool_path = found
            self._update_convert_enabled()

    def _browse_for_tool(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Locate Your Calibre Install Folder")
        if not folder:
            return
        app_settings.save_calibre_install_dir(folder)
        self._resolve_tool()

    # ------------------------------------------------------------------
    # File list management

    def _add_files(self) -> None:
        paths, _filter = QFileDialog.getOpenFileNames(
            self, "Choose Files to Convert", "", _file_filter()
        )
        for path in paths:
            if path not in self._source_paths:
                self._source_paths.append(path)
                self.file_list.addItem(os.path.basename(path))
        self._update_convert_enabled()

    def _remove_selected(self) -> None:
        for item in sorted(self.file_list.selectedItems(), key=lambda i: -self.file_list.row(i)):
            row = self.file_list.row(item)
            self.file_list.takeItem(row)
            del self._source_paths[row]
        self._update_convert_enabled()

    def _update_convert_enabled(self) -> None:
        self.convert_btn.setEnabled(bool(self._source_paths) and bool(self._tool_path))

    # ------------------------------------------------------------------
    # Conversion

    def _run_conversion(self) -> None:
        if not self._source_paths:
            return
        progress = QProgressDialog("Converting to EPUB…", "Cancel", 0, len(self._source_paths), self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)

        succeeded: list[str] = []
        errors: list[str] = []
        taken: set[str] = set()

        for i, source in enumerate(self._source_paths):
            if progress.wasCanceled():
                break
            progress.setValue(i)
            progress.setLabelText(f"Converting: {os.path.basename(source)}")
            QApplication.processEvents()

            directory = os.path.dirname(source)
            stem = os.path.splitext(os.path.basename(source))[0]
            output_path = unique_path(directory, stem, ".epub", taken)
            try:
                convert_to_epub(self._tool_path, source, output_path)
                succeeded.append(output_path)
                taken.add(os.path.normcase(os.path.abspath(output_path)))
            except EbookConvertError as exc:
                errors.append(f"{os.path.basename(source)}: {exc}")

        progress.setValue(len(self._source_paths))
        self._converted_paths = succeeded

        if errors:
            details = "\n".join(errors[:5]) + ("\n..." if len(errors) > 5 else "")
            QMessageBox.warning(
                self, "Some conversions failed",
                f"{len(succeeded)} of {len(self._source_paths)} succeeded.\n\nFailed:\n{details}",
            )

        if succeeded:
            self.accept()
        # If nothing succeeded, stay open so the user can adjust and retry
        # rather than closing on a fully-failed batch.

    # ------------------------------------------------------------------
    # Result accessor, read by the caller after exec() returns Accepted

    def converted_epub_paths(self) -> list[str]:
        return self._converted_paths
