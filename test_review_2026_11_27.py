"""Tests for the fixes from the 2026-11-27 code review (cards numbered as on the review page)."""

from __future__ import annotations

import subprocess
import sys

import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


# Card 21: the "Download Calibre..." button in Import and Convert crashed with a NameError.
def test_card21_import_dialog_download_button_opens_the_page(monkeypatch, qapp):
    import webbrowser

    from core.calibre_tools import DOWNLOAD_URL
    from gui.ebook_convert_dialog import EbookConvertDialog

    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda url, *a, **k: opened.append(url))
    dialog = EbookConvertDialog(initial_paths=[])
    dialog.download_btn.click()
    assert opened == [DOWNLOAD_URL]


# Card 50: external tools get stdin=DEVNULL (family rule).
def test_card50_sigil_is_started_with_stdin_devnull(tmp_path):
    from core.sigil_tools import open_in_sigil

    sigil = tmp_path / "sigil.exe"
    sigil.write_bytes(b"x")
    book = tmp_path / "book.epub"
    book.write_bytes(b"x")
    seen = {}
    open_in_sigil(str(sigil), str(book), popen_fn=lambda args, **kw: seen.update(kw))
    assert seen["stdin"] is subprocess.DEVNULL


def test_card50_fetch_ebook_metadata_is_started_with_stdin_devnull():
    from core.calibre_lookup import CalibreLookupError, fetch_metadata

    seen = {}

    def fake_run(args, **kw):
        seen.update(kw)
        return subprocess.CompletedProcess(args, 1, b"", b"")

    with pytest.raises(CalibreLookupError):
        fetch_metadata("fetch-ebook-metadata", title="X", run_fn=fake_run)
    assert seen["stdin"] is subprocess.DEVNULL
