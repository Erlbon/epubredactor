"""2026-10-13 review (A list): the EPUB save rides out a transient lock on the target (A15c) and the page-headers
dialog no longer promises a Recycle Bin copy that Save never makes (A12)."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import redactor_common.core.os_utils as ou  # noqa: E402

from core.epub_metadata import EpubBook  # noqa: E402
from test_dates_ddc_cover import build_epub  # noqa: E402


def test_a15c_save_retries_a_transient_lock_on_the_target(tmp_path, monkeypatch):
    path = str(tmp_path / "book.epub")
    build_epub(path, date_value="2001")
    book = EpubBook(path)
    assert not book.load_error
    book.metadata.title = "Locked for a moment"
    real_replace = os.replace
    failures = {"n": 2}

    def flaky(src, dst):
        if failures["n"] > 0:
            failures["n"] -= 1
            raise PermissionError(13, "held by a scanner")
        real_replace(src, dst)

    monkeypatch.setattr(ou.os, "replace", flaky)
    monkeypatch.setattr(ou.time, "sleep", lambda s: None)
    book.save()
    assert failures["n"] == 0
    assert EpubBook(path).metadata.title == "Locked for a moment"
    assert os.listdir(tmp_path) == ["book.epub"]  # no .tmp_write left behind


def test_a12_page_headers_dialog_does_not_promise_the_recycle_bin():
    import inspect

    from gui import page_headers_dialog

    source = inspect.getsource(page_headers_dialog)
    assert "goes to the Recycle Bin" not in source and "goes to the\n" not in source
    assert "rewrites the book in" in source
