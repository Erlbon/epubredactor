"""The shared conversion policy (Preferences > Conversion) in epubredactor: the never-saved policy equals the old
behaviour (ask, keep the originals), each on_open value, what happens to an original (keep / quarantine with an undo
log / Recycle Bin), the dry run, and the Preferences page. Offscreen, tmp_path only."""

import os
import sys
import zipfile
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

import gui.ebook_convert_dialog as ecd
import gui.main_window as mw
from core import conversion_safety as cs
from gui import preferences
from redactor_common.core import conversion_policy as pm

_app = QApplication.instance() or QApplication(sys.argv)

TODAY = date(2026, 10, 18)


def _policy(**kw):
    base = dict(on_open=pm.ON_OPEN_ASK, originals=pm.ORIGINALS_KEEP, recent_minutes=0, dry_run_first=False)
    base.update(kw)
    return pm.ConversionPolicy(**base)


def _epub(path):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", "<container/>")
    return str(path)


def _pair(tmp_path, name="a"):
    source = tmp_path / f"{name}.mobi"
    source.write_bytes(b"mobi")
    return str(source), _epub(tmp_path / f"{name}.epub")


# -- defaults ---------------------------------------------------------------------------------------------------------


def test_never_saved_policy_is_what_the_app_always_did():
    policy = cs.get_policy()
    assert policy.on_open == pm.ON_OPEN_ASK and policy.originals == pm.ORIGINALS_KEEP
    assert policy.dry_run_first is False and policy.quarantine_folder == ""


def test_saved_policy_is_read_back():
    cs.save_policy(_policy(on_open=pm.ON_OPEN_AUTO, originals=pm.ORIGINALS_RECYCLE, dry_run_first=True))
    policy = cs.get_policy()
    assert (policy.on_open, policy.originals, policy.dry_run_first) == (pm.ON_OPEN_AUTO, pm.ORIGINALS_RECYCLE, True)


# -- what happens to the original --------------------------------------------------------------------------------------


def test_keep_leaves_the_original_alone(tmp_path):
    source, result = _pair(tmp_path)
    outcome = cs.settle_original(source, result, _policy())
    assert outcome.action == "kept" and os.path.exists(source)


def test_quarantine_moves_the_original_beside_the_file_with_an_undo_log(tmp_path):
    source, result = _pair(tmp_path)
    outcome = cs.settle_original(source, result, _policy(originals=pm.ORIGINALS_QUARANTINE), today=TODAY)
    folder = tmp_path / "converted originals 2026-10-18"
    assert outcome.action == "quarantined" and not os.path.exists(source)
    assert (folder / "a.mobi").read_bytes() == b"mobi"
    log = (tmp_path / "converted originals 2026-10-18 undo log.tsv").read_text(encoding="utf-8").splitlines()
    assert log == [f"{folder / 'a.mobi'}\t{source}", f"{result}\tCREATED"]


def test_quarantine_uses_the_set_folders_and_never_overwrites(tmp_path):
    q, logs = tmp_path / "q", tmp_path / "logs"
    policy = _policy(originals=pm.ORIGINALS_QUARANTINE, quarantine_folder=str(q), undo_log_folder=str(logs))
    (q / "converted originals 2026-10-18").mkdir(parents=True)
    (q / "converted originals 2026-10-18" / "a.mobi").write_bytes(b"earlier")
    source, result = _pair(tmp_path)
    outcome = cs.settle_original(source, result, policy, today=TODAY)
    assert os.path.basename(outcome.destination) == "a (2).mobi"
    assert (q / "converted originals 2026-10-18" / "a.mobi").read_bytes() == b"earlier"
    assert (logs / "converted originals 2026-10-18 undo log.tsv").exists()


def test_recycle_sends_the_original_to_the_bin(tmp_path):
    source, result = _pair(tmp_path)
    binned = []
    outcome = cs.settle_original(source, result, _policy(originals=pm.ORIGINALS_RECYCLE), trash=binned.append)
    assert outcome.action == "recycled" and binned == [source]


def test_an_unverified_result_never_touches_the_original(tmp_path):
    source = tmp_path / "a.mobi"
    source.write_bytes(b"mobi")
    empty = tmp_path / "a.epub"
    empty.write_bytes(b"")
    garbage = tmp_path / "b.epub"
    garbage.write_bytes(b"not a zip")
    binned = []
    for result in (str(empty), str(garbage), str(tmp_path / "missing.epub")):
        for mode in (pm.ORIGINALS_QUARANTINE, pm.ORIGINALS_RECYCLE):
            outcome = cs.settle_original(str(source), result, _policy(originals=mode), trash=binned.append)
            assert outcome.action == "failed" and source.exists()
    assert binned == [] and not (tmp_path / "converted originals 2026-10-18").exists()


def test_a_recently_modified_original_is_left_alone(tmp_path):
    source, result = _pair(tmp_path)
    outcome = cs.settle_original(source, result, _policy(originals=pm.ORIGINALS_QUARANTINE, recent_minutes=10))
    assert outcome.action == "kept" and os.path.exists(source)


def test_dry_run_changes_nothing(tmp_path):
    source, result = _pair(tmp_path)
    binned = []
    q = cs.settle_original(source, result, _policy(originals=pm.ORIGINALS_QUARANTINE), dry_run=True, today=TODAY)
    r = cs.settle_original(source, result, _policy(originals=pm.ORIGINALS_RECYCLE), dry_run=True, trash=binned.append)
    assert (q.action, r.action) == ("quarantined", "recycled") and binned == []
    assert os.path.exists(source) and sorted(os.listdir(tmp_path)) == ["a.epub", "a.mobi"]


# -- the Import dialog ------------------------------------------------------------------------------------------------


def _fake_convert(tool, src, dst, run_fn=None):
    _epub(dst)


def _dialog(tmp_path, monkeypatch, policy, names=("a",)):
    monkeypatch.setattr(ecd, "convert_to_epub", _fake_convert)
    sources = []
    for name in names:
        path = tmp_path / f"{name}.mobi"
        path.write_bytes(b"mobi")
        sources.append(str(path))
    dialog = ecd.EbookConvertDialog(None, initial_paths=sources, policy=policy)
    dialog._tool_path = "ebook-convert"
    return dialog, sources


def test_dialog_default_keeps_the_original_and_has_no_dry_run(tmp_path, monkeypatch):
    dialog, (source,) = _dialog(tmp_path, monkeypatch, None)
    assert dialog.dry_run_box.isChecked() is False
    dialog._run_conversion()
    assert os.path.exists(source) and dialog.converted_epub_paths() == [str(tmp_path / "a.epub")]


def test_dialog_quarantines_after_a_verified_conversion(tmp_path, monkeypatch):
    dialog, (source,) = _dialog(tmp_path, monkeypatch, _policy(originals=pm.ORIGINALS_QUARANTINE))
    dialog._run_conversion()
    assert not os.path.exists(source) and (tmp_path / "a.epub").exists()
    assert "original moved to" in dialog.report_text


def test_dry_run_in_the_dialog_converts_and_moves_nothing_then_unticks(tmp_path, monkeypatch):
    calls = []
    dialog, (source,) = _dialog(tmp_path, monkeypatch, _policy(originals=pm.ORIGINALS_QUARANTINE, dry_run_first=True))
    monkeypatch.setattr(ecd, "convert_to_epub", lambda *a, **k: calls.append(a))
    assert dialog.dry_run_box.isChecked() is True
    dialog._run_conversion()
    assert calls == [] and os.path.exists(source) and not (tmp_path / "a.epub").exists()
    assert "Dry run" in dialog.report_text and "would be moved" in dialog.report_text
    assert dialog.dry_run_box.isChecked() is False  # the next Convert is the real one


# -- on_open ----------------------------------------------------------------------------------------------------------


def _store(monkeypatch, policy):
    cs.save_policy(policy)


def test_on_open_ask_shows_todays_offer(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(mw, "offer_conversion", lambda *a, **k: seen.append((a, k)) or "no")
    mw.MainWindow()._offer_import_of_other_formats([str(tmp_path / "b.mobi")], [], [str(tmp_path)])
    assert len(seen) == 1 and seen[0][1]["remember"] is not None  # "Don't ask again" belongs to ask


def test_on_open_never_offers_nothing(tmp_path, monkeypatch):
    _store(monkeypatch, _policy(on_open=pm.ON_OPEN_NEVER))
    seen = []
    monkeypatch.setattr(mw, "offer_conversion", lambda *a, **k: seen.append(1) or "yes")
    monkeypatch.setattr(mw, "EbookConvertDialog", lambda *a, **k: seen.append("dialog"))
    mw.MainWindow()._offer_import_of_other_formats([str(tmp_path / "b.mobi")], [], [str(tmp_path)])
    assert seen == []


def test_on_open_auto_converts_without_asking_and_reports(tmp_path, monkeypatch):
    _store(monkeypatch, _policy(on_open=pm.ON_OPEN_AUTO, originals=pm.ORIGINALS_QUARANTINE))
    monkeypatch.setattr(ecd, "convert_to_epub", _fake_convert)
    monkeypatch.setattr(ecd.EbookConvertDialog, "_resolve_tool", lambda self: setattr(self, "_tool_path", "ebook-convert"))
    asked, shown, loaded = [], [], []
    monkeypatch.setattr(mw, "offer_conversion", lambda *a, **k: asked.append(1) or "yes")
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda parent, title, text: shown.append((title, text))))
    window = mw.MainWindow()
    monkeypatch.setattr(window, "_load_paths", loaded.extend)
    source = tmp_path / "b.mobi"
    source.write_bytes(b"x")
    window._offer_import_of_other_formats([str(source)], [], [str(tmp_path)])
    assert asked == [] and loaded == [str(tmp_path / "b.epub")]
    assert not source.exists() and shown and "original moved to" in shown[0][1]


def test_on_open_auto_without_calibre_says_so(tmp_path, monkeypatch):
    _store(monkeypatch, _policy(on_open=pm.ON_OPEN_AUTO))
    monkeypatch.setattr(ecd.EbookConvertDialog, "_resolve_tool", lambda self: None)
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda parent, title, text: warned.append(text)))
    mw.MainWindow()._offer_import_of_other_formats([str(tmp_path / "b.mobi")], [], [str(tmp_path)])
    assert len(warned) == 1 and "Calibre" in warned[0]


# -- the Preferences page ---------------------------------------------------------------------------------------------


def test_conversion_page_is_last_and_shows_the_defaults():
    dialog = preferences.make_dialog()
    assert dialog.page_titles()[-1] == "Conversion"
    policy = dialog.conversion_page.policy_widget.policy()
    assert (policy.on_open, policy.originals, policy.dry_run_first) == (pm.ON_OPEN_ASK, pm.ORIGINALS_KEEP, False)


def test_ok_without_touching_the_page_saves_no_policy():
    dialog = preferences.make_dialog()
    dialog.accept()
    assert preferences.app_settings.raw_setting("conversion_policy/saved") is None


def test_page_saves_the_policy_on_ok_and_cancel_drops_it(tmp_path):
    dialog = preferences.make_dialog()
    page = dialog.conversion_page
    page.policy_widget._on_open[pm.ON_OPEN_AUTO].setChecked(True)
    page.policy_widget._recycle.setChecked(True)
    page.policy_widget._dry_run.setChecked(True)
    dialog.reject()
    assert cs.get_policy().on_open == pm.ON_OPEN_ASK  # Cancel: nothing saved

    dialog = preferences.make_dialog()
    page = dialog.conversion_page
    page.policy_widget._on_open[pm.ON_OPEN_NEVER].setChecked(True)
    page.policy_widget._quarantine.setChecked(True)
    page.policy_widget._quarantine_edit.setText(str(tmp_path / "q"))
    dialog.accept()
    policy = cs.get_policy()
    assert (policy.on_open, policy.originals, policy.quarantine_folder) == (
        pm.ON_OPEN_NEVER, pm.ORIGINALS_QUARANTINE, str(tmp_path / "q"))
