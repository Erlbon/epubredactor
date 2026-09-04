"""Tests for core/app_paths.py."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from core.app_paths import base_dir  # noqa: E402


def test_base_dir_dev_mode_is_project_root():
    """In dev mode (not a frozen PyInstaller build), base_dir() should
    land on the project root -- verified by checking a file known to
    live there (this repo's own main.py)."""
    result = base_dir()
    assert os.path.isfile(os.path.join(result, "main.py")), result
    print("PASS: in dev mode, base_dir() resolves to the project root")


def test_base_dir_frozen_mode_uses_executable_dir():
    """When frozen (a real PyInstaller build), base_dir() should be the
    directory containing the actual .exe, via sys.executable -- not the
    dev-mode project-root fallback."""
    original_frozen = getattr(sys, "frozen", None)
    original_executable = sys.executable
    try:
        sys.frozen = True
        sys.executable = "/fake/install/location/epubredactor.exe"
        result = base_dir()
        assert result == "/fake/install/location", result
    finally:
        if original_frozen is None:
            del sys.frozen
        else:
            sys.frozen = original_frozen
        sys.executable = original_executable
    print("PASS: when frozen, base_dir() uses the real executable's own directory")


if __name__ == "__main__":
    test_base_dir_dev_mode_is_project_root()
    test_base_dir_frozen_mode_uses_executable_dir()
    print("\nALL APP PATHS TESTS PASSED")
