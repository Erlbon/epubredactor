"""Open Folder tells about e-books in other formats that Calibre can convert (gui.main_window.find_convertible_books,
over redactor_common's find_by_extension) and hands them to the Import and Convert dialog (titled "Import to EPUB")
through redactor_common's convert offer."""

import os
import sys

from PyQt6.QtWidgets import QApplication

import gui.main_window as mw
from gui.ebook_convert_dialog import EbookConvertDialog
from gui.main_window import find_convertible_books, find_epubs

_app = QApplication.instance() or QApplication(sys.argv)


def _tree(root):
    for name in ("a.epub", "b.mobi", "notes.txt", "page.html", "comic.cbz", "sub/c.AZW3", "sub/deep/d.fb2", "sub/x.docx", "sub/y.jpg"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x")


def _rel(paths, root):
    return [os.path.relpath(p, root).replace(os.sep, "/") for p in paths]


def test_finds_book_formats_in_subfolders_and_skips_notes_pages_and_comics(tmp_path):
    _tree(tmp_path)
    found = _rel(find_convertible_books([str(tmp_path)]), tmp_path)
    assert found == ["b.mobi", "sub/c.AZW3", "sub/deep/d.fb2"]  # not .epub, .txt, .html, .cbz, .docx, .jpg


def test_non_recursive_lists_only_the_folder_itself(tmp_path):
    _tree(tmp_path)
    assert [os.path.basename(p) for p in find_convertible_books([str(tmp_path)], recursive=False)] == ["b.mobi"]
    assert find_convertible_books([str(tmp_path / "missing")]) == []


def test_epub_scans_skip_the_apps_own_leftovers(tmp_path):
    """redactor_common's temp-name registry: a Redact backup or a hidden scratch copy left by a killed run never
    shows up as a book in Open Folder / a drop / Refresh List; a file named directly is taken as meant."""
    _tree(tmp_path)
    for name in ("Dune.redact-orig.epub", ".Dune.redact-0123abcd.epub", ".epubredactor-scratch.epub", "sub/b.redact-orig.mobi",
                 "My.Partial.Cut.epub"):
        (tmp_path / name).write_text("x")
    assert _rel(find_epubs([str(tmp_path)]), tmp_path) == ["a.epub", "My.Partial.Cut.epub"]
    assert "sub/b.redact-orig.mobi" not in _rel(find_convertible_books([str(tmp_path)]), tmp_path)
    named = str(tmp_path / "Dune.redact-orig.epub")
    assert find_epubs([named]) == [named]


def test_open_folder_offer_uses_the_shared_dialog_with_the_old_wording(tmp_path, monkeypatch):
    seen = {}

    def fake_offer(parent, found, loaded_count, kind_label, target_label, remember_key=None, remember=None, **kw):
        seen.update(found=found, loaded=loaded_count, kind=kind_label, target=target_label, key=remember_key,
                    remember=remember, **kw)
        return "no"  # declined: the Import and Convert dialog is not opened

    monkeypatch.setattr(mw, "offer_conversion", fake_offer)
    window = mw.MainWindow()
    window._offer_import_of_other_formats([str(tmp_path / "b.mobi")], [], [str(tmp_path)])
    assert seen["converter"] == "Calibre" and seen["title"] == "Other E-book Formats Found"
    assert seen["question"] == "Open File > Import and Convert with them listed?"
    assert (seen["kind"], seen["target"], seen["yes_text"], seen["no_text"]) == ("EPUB", "EPUB", "Yes", "No")
    assert seen["key"] == str(tmp_path) and seen["remember"] is not None
    window._offer_import_of_other_formats([str(tmp_path / "b.mobi")], [], [str(tmp_path), str(tmp_path / "sub")])
    assert seen["key"] == [str(tmp_path), str(tmp_path / "sub")]  # "Don't ask again for these folders"
    assert seen["remember"] is not None
    window._offer_import_of_other_formats([str(tmp_path / "b.mobi")], [], [])
    assert seen["key"] is None and seen["remember"] is None


def test_several_declined_folders_skip_the_offer_with_the_real_store(tmp_path, monkeypatch):
    """Multi-folder Open Folder through the real shared offer and the app's declined-folders store: once
    every opened folder was declined, the box is not shown again."""
    declined = set()
    store = (lambda key: key in declined, declined.add)
    monkeypatch.setattr(mw, "_declined_convert_folders", lambda: store)
    shown = []
    monkeypatch.setattr(mw.QMessageBox, "exec", lambda self: shown.append(self) or 0, raising=False)
    folders = [str(tmp_path / "a"), str(tmp_path / "b")]
    from redactor_common.gui.convert_offer import folder_key
    for folder in folders:
        declined.add(folder_key(folder))
    window = mw.MainWindow()
    window._offer_import_of_other_formats([str(tmp_path / "a" / "x.mobi")], [], folders)
    assert shown == []


def test_dont_ask_again_folders_are_kept_in_the_settings(tmp_path):
    from redactor_common.gui.convert_offer import offer_text
    from gui import app_settings

    remember = mw._declined_convert_folders()
    assert remember.is_declined(str(tmp_path)) is False
    remember.decline(str(tmp_path))
    assert mw._declined_convert_folders().is_declined(str(tmp_path))
    assert len(app_settings.load_convert_offer_declined_folders()) == 1
    text = offer_text(["a.mobi", "b.fb2"], 0, "EPUB", "EPUB", "file", "Calibre", "Open File > Import and Convert with them listed?")
    assert text == ("No EPUB files found, but 2 file(s) in other formats (FB2, MOBI) that Calibre can convert to EPUB.\n\n"
                    "Open File > Import and Convert with them listed?")


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
