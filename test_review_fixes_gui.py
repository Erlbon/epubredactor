"""Regression tests for the verified code-review findings (2026-09-30),
MainWindow side: batch loops with progress and per-book error isolation,
Save As Copy collisions, DRM cover warnings, honest load-failure text."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from PyQt6.QtWidgets import QApplication  # noqa: E402

from core.epub_metadata import EpubBook  # noqa: E402
from test_review_fixes import ENC_TEMPLATE, build  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)


# --- MainWindow loops ---------------------------------------------------------

def _window():
    from gui.main_window import MainWindow
    return MainWindow()


def test_load_paths_dedupes_by_normcase_abspath(tmp_path):
    path = build(tmp_path / "a.epub")
    window = _window()
    window._load_paths([path])
    window._load_paths([path.upper() if os.name == "nt" else path, path])
    assert len(window.books) == 1


def test_save_as_copy_same_basename_does_not_overwrite(tmp_path):
    (tmp_path / "s1").mkdir()
    (tmp_path / "s2").mkdir()
    out = tmp_path / "out"
    out.mkdir()
    b1 = EpubBook(build(tmp_path / "s1" / "same.epub"))
    b2 = EpubBook(build(tmp_path / "s2" / "same.epub"))
    window = _window()
    errors = window._save_books([b1, b2], output_folder=str(out))
    assert errors == []
    assert sorted(os.listdir(out)) == ["same (2).epub", "same.epub"]


def test_rename_export_one_bad_book_does_not_abort_batch(tmp_path):
    good = EpubBook(build(tmp_path / "g.epub"))
    bad = EpubBook(build(tmp_path / "b.epub"))

    def boom(*a, **k):
        raise KeyError("unexpected")

    bad.save = boom
    window = _window()
    window.perform_rename_export(
        [(bad, bad.path, str(tmp_path / "x1.epub")), (good, good.path, str(tmp_path / "x2.epub"))],
        export=True)
    assert (tmp_path / "x2.epub").exists()


def test_rename_export_and_delete_loops_use_progress(tmp_path, monkeypatch):
    import gui.main_window as mw
    seen = []
    real = mw.run_with_progress

    def spy(parent, items, step, label, **kw):
        seen.append(label)
        return real(parent, items, step, label, **kw)

    monkeypatch.setattr(mw, "run_with_progress", spy)
    window = _window()
    b = EpubBook(build(tmp_path / "a.epub"))
    window.perform_rename_export([(b, b.path, str(tmp_path / "r.epub"))], export=False)
    window._apply_filename_search_replace([b], {0: "zz.epub"})
    window.books = [b]
    window._rebuild_table()
    assert "Renaming books…" in seen and "Renaming files…" in seen


def test_delete_files_uses_progress_and_id_filter(tmp_path, monkeypatch):
    import gui.main_window as mw
    from PyQt6.QtWidgets import QMessageBox
    labels = []
    real = mw.run_with_progress
    monkeypatch.setattr(mw, "run_with_progress",
                        lambda parent, items, step, label, **kw: (labels.append(label), real(parent, items, step, label, **kw))[1])
    monkeypatch.setattr(mw, "move_to_trash", lambda p: os.remove(p))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    books = [EpubBook(build(tmp_path / f"{n}.epub")) for n in "abc"]
    window = _window()
    window.books = list(books)
    window._rebuild_table()
    window.table.selectRow(0)
    window.delete_files()
    assert "Deleting files…" in labels
    assert window.books == books[1:] and not os.path.exists(books[0].path)


def test_cover_generate_uses_progress_and_warns_on_drm(tmp_path, monkeypatch):
    import gui.main_window as mw
    enc = ENC_TEMPLATE.format(alg="http://www.w3.org/2001/04/xmlenc#aes128-cbc",
                              uri="OEBPS/im%20ages/cover%20art.jpg")
    drm = EpubBook(build(tmp_path / "d.epub", extra={"META-INF/encryption.xml": enc}))
    plain = EpubBook(build(tmp_path / "p.epub"))
    labels = []
    real = mw.run_with_progress
    monkeypatch.setattr(mw, "run_with_progress",
                        lambda parent, items, step, label, **kw: (labels.append(label), real(parent, items, step, label, **kw))[1])
    warned = []
    monkeypatch.setattr(mw.MainWindow, "_warn_drm_covers_skipped", lambda self, books: warned.extend(books))
    window = _window()
    window.books = [drm, plain]
    window._rebuild_table()
    window.table.selectAll()
    window.on_cover_generate()
    assert "Generating covers…" in labels and warned == [drm]
    assert plain.cover_changed and not drm.cover_changed


def test_refresh_list_survives_a_constructor_exception(tmp_path, monkeypatch):
    import gui.main_window as mw
    good = build(tmp_path / "g.epub")
    bad = build(tmp_path / "b.epub")
    window = _window()
    window._load_paths([good, bad])
    real = mw.EpubBook

    def flaky(path):
        if path.endswith("b.epub"):
            raise RuntimeError("boom")
        return real(path)

    monkeypatch.setattr(mw, "EpubBook", flaky)
    window.refresh_list()
    assert len(window.books) == 2


def test_dropped_file_message_is_truthful(tmp_path, monkeypatch):
    import gui.main_window as mw
    shown = []
    monkeypatch.setattr(mw.QMessageBox, "warning", lambda *a, **k: shown.append(a[2]))

    def boom(path):
        raise RuntimeError("boom")

    monkeypatch.setattr(mw, "EpubBook", boom)
    window = _window()
    window._load_paths([build(tmp_path / "x.epub")])
    assert window.books == []
    assert "highlighted in red" not in shown[0] and "not added" in shown[0]


def test_send_to_ereader_only_opens_http(monkeypatch):
    import gui.send_to_ereader_dialog as d
    src = open(d.__file__, encoding="utf-8").read()
    assert 'urlparse(server).scheme.lower() in ("http", "https")' in src
