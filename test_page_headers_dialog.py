"""gui/page_headers_dialog.py: lists only the books whose page headers prove themselves, with examples."""

import sys

from PyQt6.QtWidgets import QApplication

from core.epub_metadata import EpubBook
from gui.page_headers_dialog import PageHeadersDialog
from test_page_headers import scanned_book
from test_redact_steps import make_epub

_app = QApplication.instance() or QApplication(sys.argv)


def test_only_the_scanned_book_is_listed_and_it_shows_examples(tmp_path):
    scanned = EpubBook(scanned_book(tmp_path))
    plain = EpubBook(make_epub(str(tmp_path / "plain.epub")))
    dialog = PageHeadersDialog([plain, scanned])
    assert dialog.table.rowCount() == 1 and dialog.table.item(0, 0).text() == "scanned.epub"
    assert dialog.table.item(0, 1).text() == "12" and dialog.table.item(0, 3).text() == "12"
    assert "header with page number" in dialog.examples.toPlainText()
    assert list(dialog.accepted_plans()) == [1]  # the index in the list given, ticked by default
    dialog._checkboxes[1].setChecked(False)
    assert dialog.accepted_plans() == {}


def test_turning_the_join_off_changes_the_preview(tmp_path):
    dialog = PageHeadersDialog([EpubBook(scanned_book(tmp_path))])
    dialog.join_check.setChecked(False)
    assert dialog.table.item(0, 3).text() == "0"


def test_nothing_to_clean_disables_apply(tmp_path):
    dialog = PageHeadersDialog([EpubBook(make_epub(str(tmp_path / "plain.epub")))])
    assert dialog.table.rowCount() == 0 and not dialog._ok_button.isEnabled()
