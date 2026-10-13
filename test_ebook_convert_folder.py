"""Add Folder tells about e-books in other formats that Calibre can convert (core.ebook_convert.find_convertible_in_folder)
and hands them to the Import to EPUB dialog."""

import os
import sys

from PyQt6.QtWidgets import QApplication

from core.ebook_convert import find_convertible_in_folder
from gui.ebook_convert_dialog import EbookConvertDialog

_app = QApplication.instance() or QApplication(sys.argv)


def _tree(root):
    for name in ("a.epub", "b.mobi", "notes.txt", "page.html", "comic.cbz", "sub/c.AZW3", "sub/deep/d.fb2", "sub/x.docx", "sub/y.jpg"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x")


def test_finds_book_formats_in_subfolders_and_skips_notes_pages_and_comics(tmp_path):
    _tree(tmp_path)
    found = [os.path.relpath(p, tmp_path).replace(os.sep, "/") for p in find_convertible_in_folder(str(tmp_path))]
    assert found == ["b.mobi", "sub/c.AZW3", "sub/deep/d.fb2"]  # not .epub, .txt, .html, .cbz, .docx, .jpg


def test_non_recursive_lists_only_the_folder_itself(tmp_path):
    _tree(tmp_path)
    assert [os.path.basename(p) for p in find_convertible_in_folder(str(tmp_path), recursive=False)] == ["b.mobi"]
    assert find_convertible_in_folder(str(tmp_path / "missing")) == []


def test_import_dialog_takes_the_listed_files_once(tmp_path):
    files = [str(tmp_path / "b.mobi"), str(tmp_path / "c.azw3")]
    dialog = EbookConvertDialog(initial_paths=files)
    dialog.add_paths(files + [str(tmp_path / "d.fb2")])
    assert [dialog.file_list.item(i).text() for i in range(dialog.file_list.count())] == ["b.mobi", "c.azw3", "d.fb2"]


def test_include_subfolders_setting_defaults_on_and_is_remembered(monkeypatch, tmp_path):
    from PyQt6.QtCore import QSettings
    from gui import app_settings

    store = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr(app_settings, "_settings", lambda: store)
    assert app_settings.load_include_subfolders() is True
    app_settings.save_include_subfolders(False)
    assert app_settings.load_include_subfolders() is False
    app_settings.save_include_subfolders(True)
    assert app_settings.load_include_subfolders() is True


def test_redact_steps_may_draw_covers_on_a_worker_thread():
    """redactor_common's run_redact now runs each book on a worker thread: the cover renderer and the image
    sizer the Redact env hands the steps (Qt painting onto a QImage) must work off the GUI thread."""
    import threading

    from gui import cover_quality
    from gui.cover_render import generate_cover_image

    out = {}

    def work():
        try:
            data = generate_cover_image("A Long Title For A Test Book", "Some Author", "The Series", "3")
            out["size"] = cover_quality.image_size(data)
        except BaseException as exc:  # noqa: BLE001
            out["error"] = repr(exc)

    worker = threading.Thread(target=work)
    worker.start()
    worker.join(30)
    assert "error" not in out and out["size"] == (1200, 1800)


def test_the_gui_redact_env_has_no_gui_thread_net_hook():
    import inspect

    from gui.main_window import MainWindow

    assert "net=" not in inspect.getsource(MainWindow._redact_env)  # the steps run on a worker thread: direct calls
