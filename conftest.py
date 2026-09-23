"""Shared test setup: isolate Calibre/Sigil lookup from whatever is
actually installed on the machine running the tests. Their well-known
install-folder tier would otherwise find a real install under Program
Files and break tests that simulate it being absent."""

import pytest


@pytest.fixture(autouse=True)
def _no_real_install_dirs(monkeypatch):
    import core.calibre_tools as calibre_tools
    import core.sigil_tools as sigil_tools

    monkeypatch.setattr(calibre_tools, "_default_install_dirs", lambda: [])
    monkeypatch.setattr(sigil_tools, "_default_install_dirs", lambda: [])


@pytest.fixture(autouse=True)
def _non_blocking_message_boxes(monkeypatch):
    """QMessageBox.information/warning/critical are modal and never
    return under the offscreen test platform -- two tests
    (test_main_window_overwrite.py, test_perf_logging_wiring.py) hung
    forever on a plain "Done"/"Enabled" notice. Stub the notice-style
    ones; question() is left alone since its answer drives logic and
    tests patch it explicitly where needed. A test can still patch any
    of these itself to assert on them."""
    from PyQt6.QtWidgets import QMessageBox

    ok = QMessageBox.StandardButton.Ok
    for name in ("information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *args, **kwargs: ok))


@pytest.fixture(autouse=True)
def _isolated_settings_and_perf_flag(monkeypatch, tmp_path):
    """Keep tests off the real dev-mode epubredactor_settings.ini (a
    test toggling perf logging used to persist that into the
    developer's own settings) and reset perf logging's in-process flag,
    which otherwise leaks from one test into the next."""
    import core.perf_log as perf_log
    import gui.app_settings as app_settings

    monkeypatch.setattr(app_settings, "_settings_ini_path", lambda: str(tmp_path / "settings.ini"))
    monkeypatch.setattr(perf_log, "_enabled", False)
