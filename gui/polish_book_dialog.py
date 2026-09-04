"""
gui/polish_book_dialog.py

Polish Book: applies lightweight Calibre ebook-polish cleanups (smarten
punctuation, font subsetting/embedding, image compression, unused CSS
removal, soft hyphens, book jacket, EPUB2->3 upgrade) to selected books.

Books with unsaved changes are skipped: polishing acts on the file as it
exists on disk right now, so any pending in-memory edits would otherwise
be silently ignored -- and then lost outright once the book gets
reloaded afterward. Save those first, then polish them separately.

"Polish in place" writes to a temp file next to the original and
atomically replaces it (so a crash mid-polish can't corrupt the
original), then the caller (gui/main_window.py) reloads the book fresh
from disk -- same reasoning as Refresh List, since polishing is a real
file rewrite, not a staged edit. "Export polished copies" leaves
originals untouched and adds the copies to the working list instead.
"""

from __future__ import annotations

import os
import webbrowser

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from core.calibre_tools import DOWNLOAD_URL, find_tool
from core.ebook_polish import EbookPolishError, PolishOptions, polish_book
from core.epub_metadata import EpubBook
from core.rename_pattern import unique_path
from gui import app_settings

HYPHENS_DONT_CHANGE, HYPHENS_ADD, HYPHENS_REMOVE = "Don't change", "Add", "Remove"
JACKET_DONT_CHANGE, JACKET_INSERT, JACKET_REMOVE = "Don't change", "Insert", "Remove"


class PolishBookDialog(QDialog):
    def __init__(self, books: list[EpubBook], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Polish Book")
        self.resize(520, 600)
        self.all_books = books
        self.eligible_books = [b for b in books if not b.dirty and not b.load_error]
        self.skipped_dirty = [b for b in books if b.dirty and not b.load_error]
        self._tool_path = ""
        self.output_folder = ""
        self._polished_in_place: list[EpubBook] = []
        self._exported_paths: list[str] = []

        self._build_ui()
        self._resolve_tool()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        info = QLabel(
            f"Applies to {len(self.eligible_books)} of {len(self.all_books)} selected book(s) "
            "via your Calibre installation's ebook-polish tool. This works directly on the "
            "file on disk -- a real file change, not staged like other edits in this app."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        if self.skipped_dirty:
            names = ", ".join(os.path.basename(b.path) for b in self.skipped_dirty[:5])
            more = f", and {len(self.skipped_dirty) - 5} more" if len(self.skipped_dirty) > 5 else ""
            warn = QLabel(
                f"Skipping {len(self.skipped_dirty)} book(s) with unsaved changes ({names}{more}) "
                "-- save those first, then polish them separately."
            )
            warn.setWordWrap(True)
            warn.setStyleSheet("color: #b45309; font-size: 11px;")
            layout.addWidget(warn)

        actions_box = QGroupBox("Actions")
        actions_layout = QVBoxLayout(actions_box)

        self.smarten_cb = QCheckBox("Smarten punctuation (straight quotes/dashes \u2192 typographic)")
        actions_layout.addWidget(self.smarten_cb)
        self.subset_fonts_cb = QCheckBox("Subset embedded fonts (reduce file size)")
        actions_layout.addWidget(self.subset_fonts_cb)
        self.embed_fonts_cb = QCheckBox("Embed referenced fonts that aren't embedded yet")
        actions_layout.addWidget(self.embed_fonts_cb)
        self.compress_images_cb = QCheckBox("Losslessly compress images")
        actions_layout.addWidget(self.compress_images_cb)
        self.remove_css_cb = QCheckBox("Remove unused CSS rules")
        actions_layout.addWidget(self.remove_css_cb)
        self.upgrade_cb = QCheckBox("Upgrade EPUB2 books to EPUB3, where possible")
        actions_layout.addWidget(self.upgrade_cb)

        hyphens_row = QHBoxLayout()
        hyphens_row.addWidget(QLabel("Soft hyphens:"))
        self.hyphens_combo = QComboBox()
        self.hyphens_combo.addItems([HYPHENS_DONT_CHANGE, HYPHENS_ADD, HYPHENS_REMOVE])
        hyphens_row.addWidget(self.hyphens_combo, 1)
        actions_layout.addLayout(hyphens_row)

        jacket_row = QHBoxLayout()
        jacket_row.addWidget(QLabel("Book jacket page:"))
        self.jacket_combo = QComboBox()
        self.jacket_combo.addItems([JACKET_DONT_CHANGE, JACKET_INSERT, JACKET_REMOVE])
        jacket_row.addWidget(self.jacket_combo, 1)
        actions_layout.addLayout(jacket_row)

        layout.addWidget(actions_box)

        mode_box = QGroupBox("Action")
        mode_layout = QVBoxLayout(mode_box)
        self.in_place_radio = QRadioButton("Polish files in place")
        self.export_radio = QRadioButton("Export polished copies to a folder (originals untouched)")
        self.in_place_radio.setChecked(True)
        mode_layout.addWidget(self.in_place_radio)

        export_row = QHBoxLayout()
        export_row.addWidget(self.export_radio)
        self.choose_folder_btn = QPushButton("Choose Folder\u2026")
        self.choose_folder_btn.clicked.connect(self._choose_folder)
        self.choose_folder_btn.setEnabled(False)
        export_row.addWidget(self.choose_folder_btn)
        mode_layout.addLayout(export_row)
        self.in_place_radio.toggled.connect(lambda checked: self.choose_folder_btn.setEnabled(not checked))

        self.folder_label = QLabel("(no folder chosen)")
        self.folder_label.setStyleSheet("color: gray; font-size: 11px;")
        mode_layout.addWidget(self.folder_label)

        layout.addWidget(mode_box)

        tool_row = QHBoxLayout()
        self.change_tool_btn = QPushButton("Change Calibre Location\u2026")
        self.change_tool_btn.clicked.connect(self._browse_for_tool)
        tool_row.addWidget(self.change_tool_btn)
        self.download_btn = QPushButton("Download Calibre\u2026")
        self.download_btn.clicked.connect(lambda: webbrowser.open(DOWNLOAD_URL))
        self.download_btn.setVisible(False)  # only shown once Calibre genuinely can't be found
        tool_row.addWidget(self.download_btn)
        tool_row.addStretch(1)
        layout.addLayout(tool_row)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self.status_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.polish_btn = buttons.addButton("Polish", QDialogButtonBox.ButtonRole.AcceptRole)
        self.polish_btn.clicked.connect(self._run_polish)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    # Locating Calibre's tool

    def _resolve_tool(self) -> None:
        configured_dir = app_settings.load_calibre_install_dir()
        found = find_tool("ebook-polish", configured_install_dir=configured_dir)
        if found is None:
            self.status_label.setText(
                "Couldn't find Calibre automatically. If you have it installed, click "
                "\"Change Calibre Location\u2026\" and pick your install folder (shared "
                "with the other Calibre features, only needs doing once). If you don't "
                "have it, it's free -- click \"Download Calibre\u2026\"."
            )
            self.download_btn.setVisible(True)
            self.polish_btn.setEnabled(False)
        else:
            self.download_btn.setVisible(False)
            self._tool_path = found
            self.polish_btn.setEnabled(bool(self.eligible_books))

    def _browse_for_tool(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Locate Your Calibre Install Folder")
        if not folder:
            return
        app_settings.save_calibre_install_dir(folder)
        self._resolve_tool()

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose Output Folder")
        if folder:
            self.output_folder = folder
            self.folder_label.setText(folder)

    # ------------------------------------------------------------------
    # Running

    def _collect_options(self) -> PolishOptions:
        return PolishOptions(
            smarten_punctuation=self.smarten_cb.isChecked(),
            subset_fonts=self.subset_fonts_cb.isChecked(),
            embed_fonts=self.embed_fonts_cb.isChecked(),
            compress_images=self.compress_images_cb.isChecked(),
            remove_unused_css=self.remove_css_cb.isChecked(),
            add_soft_hyphens=self.hyphens_combo.currentText() == HYPHENS_ADD,
            remove_soft_hyphens=self.hyphens_combo.currentText() == HYPHENS_REMOVE,
            insert_jacket=self.jacket_combo.currentText() == JACKET_INSERT,
            remove_jacket=self.jacket_combo.currentText() == JACKET_REMOVE,
            upgrade_book=self.upgrade_cb.isChecked(),
        )

    def _run_polish(self) -> None:
        options = self._collect_options()
        if not options.any_selected():
            QMessageBox.information(self, "Nothing selected", "Choose at least one polish action.")
            return
        if not self.eligible_books:
            QMessageBox.information(self, "Nothing to polish", "No eligible books to polish.")
            return
        if self.export_radio.isChecked() and not self.output_folder:
            QMessageBox.information(self, "Choose a folder", "Choose an output folder first.")
            return

        progress = QProgressDialog("Polishing\u2026", "Cancel", 0, len(self.eligible_books), self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)

        succeeded_in_place: list[EpubBook] = []
        succeeded_export_paths: list[str] = []
        errors: list[str] = []
        taken: set[str] = set()

        for i, book in enumerate(self.eligible_books):
            if progress.wasCanceled():
                break
            progress.setValue(i)
            progress.setLabelText(f"Polishing: {os.path.basename(book.path)}")
            QApplication.processEvents()

            tmp_path = None
            try:
                if self.export_radio.isChecked():
                    stem = os.path.splitext(os.path.basename(book.path))[0]
                    ext = os.path.splitext(book.path)[1] or ".epub"
                    output_path = unique_path(self.output_folder, stem, ext, taken)
                    polish_book(self._tool_path, book.path, output_path, options)
                    succeeded_export_paths.append(output_path)
                    taken.add(os.path.normcase(os.path.abspath(output_path)))
                else:
                    root, ext = os.path.splitext(book.path)
                    tmp_path = f"{root}.polish_tmp{ext}"
                    polish_book(self._tool_path, book.path, tmp_path, options)
                    os.replace(tmp_path, book.path)
                    tmp_path = None  # renamed away, nothing left to clean up
                    succeeded_in_place.append(book)
            except (EbookPolishError, OSError) as exc:
                errors.append(f"{os.path.basename(book.path)}: {exc}")
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass

        progress.setValue(len(self.eligible_books))
        self._polished_in_place = succeeded_in_place
        self._exported_paths = succeeded_export_paths

        if errors:
            details = "\n".join(errors[:5]) + ("\n..." if len(errors) > 5 else "")
            QMessageBox.warning(
                self, "Some books failed to polish",
                f"{len(succeeded_in_place) + len(succeeded_export_paths)} of "
                f"{len(self.eligible_books)} succeeded.\n\nFailed:\n{details}",
            )

        if succeeded_in_place or succeeded_export_paths:
            self.accept()

    # ------------------------------------------------------------------
    # Result accessors, read by the caller after exec() returns Accepted

    def result_polished_in_place(self) -> list[EpubBook]:
        return self._polished_in_place

    def result_exported_paths(self) -> list[str]:
        return self._exported_paths
