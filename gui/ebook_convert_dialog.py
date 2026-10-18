"""
gui/ebook_convert_dialog.py

File > Import and Convert (dialog title "Import to EPUB"): converts other ebook/document formats into EPUB via
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
import threading

from PyQt6.QtWidgets import (
    QDialog,
    QCheckBox,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core import conversion_safety
from core.calibre_tools import cancellable_run, find_tool
from core.ebook_convert import EbookConvertError, SUPPORTED_SOURCE_EXTENSIONS, convert_to_epub
from redactor_common.gui.background_call import call_in_background
from redactor_common.gui.progress import run_with_progress
from core.rename_pattern import unique_path
from gui import app_settings


def _file_filter() -> str:
    exts = " ".join(f"*{ext}" for ext in sorted(SUPPORTED_SOURCE_EXTENSIONS))
    return f"Supported formats ({exts})"


class EbookConvertDialog(QDialog):
    def __init__(self, parent=None, initial_paths: list[str] | None = None, policy=None):
        super().__init__(parent)
        # The shared conversion policy (Preferences > Conversion): what happens to each original afterwards.
        self._policy = policy or conversion_safety.get_policy()
        self.outcomes: list[conversion_safety.Outcome] = []
        self.report_text = ""
        self.setWindowTitle("Import to EPUB")
        self.resize(600, 440)
        self._tool_path = ""
        self._source_paths: list[str] = []
        self._converted_paths: list[str] = []

        self._build_ui()
        self._resolve_tool()
        if initial_paths:
            self.add_paths(initial_paths)

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

        self.dry_run_box = QCheckBox("Dry run first: list what would be converted and what would happen to the "
                                     "originals, and change nothing")
        self.dry_run_box.setChecked(self._policy.dry_run_first)
        layout.addWidget(self.dry_run_box)

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
        self.add_paths(paths)

    def add_paths(self, paths: list[str]) -> None:
        """Puts files in the list (once each): from this dialog's Add Files, or handed over by Open Folder."""
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
        """The Convert button: a dry run when the box is ticked (it is then unticked, so the next click converts)."""
        dry_run = self.dry_run_box.isChecked()
        self.convert_all(dry_run=dry_run, show_report=True)
        if dry_run:
            self.dry_run_box.setChecked(False)

    def convert_all(self, dry_run: bool = False, show_report: bool = True) -> bool:
        """Converts the listed files; True when the dialog should now close (something was converted). A dry run
        converts nothing, touches nothing and only reports. Each original is then settled by the policy, after the
        result was verified."""
        if not self._source_paths:
            return False
        succeeded: list[str] = []
        errors: list[str] = []
        taken: set[str] = set()
        outcomes: list[conversion_safety.Outcome] = []
        if dry_run:
            lines = []
            for source in self._source_paths:
                directory = os.path.dirname(source)
                stem = os.path.splitext(os.path.basename(source))[0]
                output_path = unique_path(directory, stem, ".epub", taken)
                taken.add(os.path.normcase(os.path.abspath(output_path)))
                outcome = conversion_safety.settle_original(source, output_path, self._policy, dry_run=True)
                lines.append(f"{os.path.basename(source)} -> {os.path.basename(output_path)}; original "
                             + {"kept": "kept", "quarantined": f"would be moved to {outcome.destination}",
                                "recycled": "would go to the Recycle Bin"}.get(outcome.action, outcome.action)
                             + (f" ({outcome.note})" if outcome.note else ""))
            self.report_text = "Dry run: nothing was converted or changed.\n\n" + "\n".join(lines)
            if show_report:
                QMessageBox.information(self, "Dry run", self.report_text)
            return False
        # Each conversion is one long ebook-convert process: it runs off the
        # GUI thread (the window keeps painting) and Cancel kills it.
        cancel = threading.Event()
        run_fn = cancellable_run(cancel)

        def _step(source: str, _index: int) -> None:
            directory = os.path.dirname(source)
            stem = os.path.splitext(os.path.basename(source))[0]
            try:
                output_path = unique_path(directory, stem, ".epub", taken)
                call_in_background(convert_to_epub, self._tool_path, source, output_path, run_fn=run_fn)
                succeeded.append(output_path)
                taken.add(os.path.normcase(os.path.abspath(output_path)))
            except (EbookConvertError, OSError) as exc:
                if not cancel.is_set():
                    errors.append(f"{os.path.basename(source)}: {exc}")
                return
            outcomes.append(conversion_safety.settle_original(source, output_path, self._policy))

        run_with_progress(
            self, self._source_paths, _step, "Converting to EPUB…", threshold=1,
            label_for=lambda source: f"Converting: {os.path.basename(source)}",
            on_cancel=cancel.set,
        )
        self._converted_paths = succeeded
        self.outcomes = outcomes

        total = len(self._source_paths)
        report = [f"Converted {len(succeeded)} of {total} file(s)."] + [o.line() for o in outcomes]
        if errors:
            report += ["", "Failed:"] + errors[:5] + (["..."] if len(errors) > 5 else [])
        self.report_text = "\n".join(report)

        if errors:
            details = "\n".join(errors[:5]) + ("\n..." if len(errors) > 5 else "")
            QMessageBox.warning(
                self, "Some conversions failed",
                f"{len(succeeded)} of {total} succeeded.\n\nFailed:\n{details}",
            )
        # Today's behaviour (originals kept) stays silent on success; moving or recycling an original is said.
        if show_report and succeeded and self._policy.originals != conversion_safety.policy_mod.ORIGINALS_KEEP:
            QMessageBox.information(self, "Conversion done", self.report_text)

        if succeeded:
            self.accept()
            return True
        # If nothing succeeded, stay open so the user can adjust and retry
        # rather than closing on a fully-failed batch.
        return False

    # ------------------------------------------------------------------
    # Result accessor, read by the caller after exec() returns Accepted

    def converted_epub_paths(self) -> list[str]:
        return self._converted_paths
