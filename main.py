"""
The EPUB Redactor - entry point.

Run with:  python main.py
Build a standalone .exe with:  build_exe.bat  (see README.md)
"""
import os
import sys
import traceback

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from redactor_common.gui.theme import apply_theme

from core import crash_log
from core.version import APP_NAME
from gui.main_window import MainWindow, resource_path


def _set_windows_app_user_model_id() -> None:
    """Windows-only fix for a common icon problem: running via python.exe
    directly (not a compiled exe) makes the taskbar show python.exe's own
    icon instead of ours, because Windows groups taskbar buttons by the
    underlying executable's AppUserModelID rather than by setWindowIcon()
    alone. Giving the process its own explicit ID fixes this. No-op (and
    harmless) on any other OS, or if this Windows-only API isn't available."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "Pubocyno.EpubRedactor.GUI.1"
        )
    except (AttributeError, OSError):
        pass


def _show_crash_dialog(exc_type, exc_value, exc_tb) -> None:
    """Best-effort friendly notice for an otherwise-unhandled exception --
    shown in addition to (never instead of) logging it, and never allowed
    to itself prevent the app from at least trying to continue running.
    A QApplication must already exist by the time this can run; if
    somehow it doesn't yet (a crash during the earliest startup, before
    QApplication() is even constructed), this quietly does nothing and
    the crash is still captured in the log file either way."""
    if QApplication.instance() is None:
        return
    QMessageBox.critical(
        None,
        "Unexpected Error",
        "Something went wrong that this app didn't expect.\n\n"
        f"{''.join(traceback.format_exception_only(exc_type, exc_value)).strip()}\n\n"
        f"Details have been saved to {crash_log.log_path()} -- "
        "that file may help track down what happened.",
    )


def main() -> int:
    crash_log.install(also_call=_show_crash_dialog)
    _set_windows_app_user_model_id()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    apply_theme(app)  # Fusion + a WCAG-contrast-verified light/dark palette -- see redactor_common/gui/theme.py
    # QMessageBox sizes itself to fit its text, but a long line with no
    # natural break point (a file path, or raw stderr from an external
    # tool like Calibre) can make it grow arbitrarily wide instead of
    # wrapping -- sometimes wider than the whole screen. Capping the
    # internal label's width here, once, at the application level fixes
    # this for every message box in the app (every call site already
    # parents its dialogs to a window inside this app, so there's no
    # need to repeat this per call site).
    app.setStyleSheet("QMessageBox QLabel { max-width: 480px; }")
    icon_path = resource_path("assets", "icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
