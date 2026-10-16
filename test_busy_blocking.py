"""2026-10-16 independent review, 'shared progress dialogs and threading', as it shows in epubredactor: a drop of
folders runs a slow scan under run_busy. Before, the window stayed clickable for ~4 s until the progress dialog showed
(a second drop started a nested scan); now the window is disabled for the whole call and enabled again afterwards."""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QTimer, QUrl  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

import gui.main_window as mw  # noqa: E402

_app = QApplication.instance() or QApplication([])


class _Mime:
    def __init__(self, paths):
        self._urls = [QUrl.fromLocalFile(p) for p in paths]

    def hasUrls(self):
        return True

    def urls(self):
        return self._urls


class _Drop:
    def __init__(self, paths):
        self._mime = _Mime(paths)

    def mimeData(self):
        return self._mime


def test_a_second_drop_during_the_scan_is_blocked_and_the_window_comes_back(tmp_path, monkeypatch):
    window = mw.MainWindow()
    scans = []
    during = []

    def slow_find(paths, recursive):
        scans.append(1)
        time.sleep(0.6)
        return []

    monkeypatch.setattr(mw, "find_epubs", slow_find)
    event = _Drop([str(tmp_path)])
    # a second drop at 100 ms: it is delivered by the event loop the first call runs, so it must find the window disabled
    QTimer.singleShot(100, lambda: (during.append(window.isEnabled()), window.isEnabled() and window.dropEvent(event)))
    window.dropEvent(event)
    assert scans == [1], f"{len(scans)} scans were started"
    assert during == [False]
    assert window.isEnabled()
    window.close()
