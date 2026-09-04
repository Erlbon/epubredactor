"""Tests for core/sigil_tools.py."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from core.sigil_tools import SigilLaunchError, find_sigil, open_in_sigil  # noqa: E402

TEST_DIR = "/tmp/sigil_tools_test"
os.makedirs(TEST_DIR, exist_ok=True)


def _make_fake_exe(name: str) -> str:
    path = os.path.join(TEST_DIR, name)
    with open(path, "w") as f:
        f.write("fake exe")
    return path


def test_find_sigil_from_configured_path():
    path = _make_fake_exe("configured_sigil.exe")
    result = find_sigil(configured_path=path, which_fn=lambda n: None)
    assert result == path
    print("PASS: finds Sigil at a previously configured/remembered path")


def test_find_sigil_stale_configured_path_falls_through():
    result = find_sigil(
        configured_path="/nonexistent/sigil.exe",
        which_fn=lambda n: "/usr/bin/sigil" if n == "sigil" else None,
    )
    assert result == "/usr/bin/sigil"
    print("PASS: a stale configured path is skipped, falls through to PATH lookup")


def test_find_sigil_falls_back_to_which():
    result = find_sigil(which_fn=lambda n: "/usr/local/bin/sigil" if n == "sigil" else None)
    assert result == "/usr/local/bin/sigil"
    print("PASS: falls back to PATH lookup when nothing configured")


def test_find_sigil_returns_none_when_nothing_found():
    result = find_sigil(which_fn=lambda n: None)
    assert result is None
    print("PASS: returns None (not an error) when Sigil can't be found anywhere")


def test_open_in_sigil_launches_with_correct_args():
    sigil_path = _make_fake_exe("sigil.exe")
    epub_path = os.path.join(TEST_DIR, "book.epub")
    with open(epub_path, "w") as f:
        f.write("fake epub")

    captured = {}

    def fake_popen(args):
        captured["args"] = args

    open_in_sigil(sigil_path, epub_path, popen_fn=fake_popen)
    assert captured["args"] == [sigil_path, epub_path]
    print("PASS: launches Sigil with the correct [sigil_path, epub_path] arguments")


def test_open_in_sigil_missing_sigil_raises():
    epub_path = os.path.join(TEST_DIR, "book2.epub")
    with open(epub_path, "w") as f:
        f.write("fake epub")
    try:
        open_in_sigil("/nonexistent/sigil.exe", epub_path, popen_fn=lambda args: None)
        assert False, "should have raised"
    except SigilLaunchError as exc:
        assert "not found" in str(exc).lower()
    print("PASS: a missing Sigil executable raises a clear SigilLaunchError")


def test_open_in_sigil_missing_book_raises():
    sigil_path = _make_fake_exe("sigil2.exe")
    try:
        open_in_sigil(sigil_path, "/nonexistent/book.epub", popen_fn=lambda args: None)
        assert False, "should have raised"
    except SigilLaunchError as exc:
        assert "not found" in str(exc).lower()
    print("PASS: a missing book file raises a clear SigilLaunchError")


def test_open_in_sigil_launch_failure_wrapped():
    sigil_path = _make_fake_exe("sigil3.exe")
    epub_path = os.path.join(TEST_DIR, "book3.epub")
    with open(epub_path, "w") as f:
        f.write("fake epub")

    def failing_popen(args):
        raise OSError("permission denied")

    try:
        open_in_sigil(sigil_path, epub_path, popen_fn=failing_popen)
        assert False, "should have raised"
    except SigilLaunchError as exc:
        assert "permission denied" in str(exc)
    print("PASS: a launch failure (e.g. permission denied) is wrapped in a clear SigilLaunchError")


if __name__ == "__main__":
    test_find_sigil_from_configured_path()
    test_find_sigil_stale_configured_path_falls_through()
    test_find_sigil_falls_back_to_which()
    test_find_sigil_returns_none_when_nothing_found()
    test_open_in_sigil_launches_with_correct_args()
    test_open_in_sigil_missing_sigil_raises()
    test_open_in_sigil_missing_book_raises()
    test_open_in_sigil_launch_failure_wrapped()
    print("\nALL SIGIL TOOLS TESTS PASSED")
