"""Tests for core/crash_log.py."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import core.crash_log as crash_log  # noqa: E402
from core.crash_log import (  # noqa: E402
    format_crash_entry,
    install,
    write_crash_entry,
)

TEST_DIR = "/tmp/crash_log_test"
os.makedirs(TEST_DIR, exist_ok=True)


def _make_exc_info():
    try:
        raise ValueError("something went wrong")
    except ValueError:
        return sys.exc_info()


def test_format_crash_entry_includes_timestamp_and_traceback():
    exc_type, exc_value, exc_tb = _make_exc_info()
    entry = format_crash_entry(exc_type, exc_value, exc_tb)
    assert "ValueError" in entry
    assert "something went wrong" in entry
    # A timestamp of the form YYYY-MM-DD HH:MM:SS should be present somewhere.
    import re
    assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", entry)
    print("PASS: a crash entry includes both a timestamp and the actual traceback")


def test_write_crash_entry_appends_to_file():
    path = os.path.join(TEST_DIR, "append_test.log")
    if os.path.exists(path):
        os.remove(path)
    exc_type, exc_value, exc_tb = _make_exc_info()
    write_crash_entry(exc_type, exc_value, exc_tb, path=path)
    write_crash_entry(exc_type, exc_value, exc_tb, path=path)
    with open(path) as f:
        content = f.read()
    # Count entry separators rather than "ValueError" itself: the actual
    # traceback text includes the raising source line when it can be
    # read from a real file ("raise ValueError(...)"), which contains
    # the word a second time on top of the summary line -- making a
    # plain substring count an unreliable way to count entries. The "="
    # separator is this module's own, deterministic per-entry marker.
    assert content.count("=" * 70) == 2, "two separate crashes should both be present, not overwritten"
    print("PASS: successive crashes are appended, not overwritten")


def test_write_crash_entry_never_raises_on_bad_path():
    exc_type, exc_value, exc_tb = _make_exc_info()
    # A path in a directory that doesn't exist -- open() will raise
    # OSError/FileNotFoundError internally, which must be swallowed.
    write_crash_entry(exc_type, exc_value, exc_tb, path="/this/does/not/exist/crash.log")
    print("PASS: an unwritable path is handled silently, doesn't raise")


def test_trim_keeps_file_bounded():
    path = os.path.join(TEST_DIR, "trim_test.log")
    original_max = crash_log.MAX_LOG_BYTES
    crash_log.MAX_LOG_BYTES = 500  # small, to trigger trimming without a huge test file
    try:
        if os.path.exists(path):
            os.remove(path)
        exc_type, exc_value, exc_tb = _make_exc_info()
        for _ in range(30):
            write_crash_entry(exc_type, exc_value, exc_tb, path=path)
        size = os.path.getsize(path)
        assert size < 3000, f"log grew unbounded: {size} bytes"
        with open(path) as f:
            content = f.read()
        assert "ValueError" in content, "trimming must not remove everything, only the oldest entries"
    finally:
        crash_log.MAX_LOG_BYTES = original_max
    print("PASS: repeated crashes don't grow the log file without bound")


def test_install_chains_to_previous_hook():
    original_hook = sys.excepthook
    original_write = crash_log.write_crash_entry
    calls = {"written": False, "chained": False}

    def fake_write(exc_type, exc_value, exc_tb, path=None):
        calls["written"] = True

    def fake_previous_hook(exc_type, exc_value, exc_tb):
        calls["chained"] = True

    try:
        crash_log.write_crash_entry = fake_write
        sys.excepthook = fake_previous_hook
        install(faulthandler_path=os.path.join(TEST_DIR, "faulthandler1.log"))
        exc_type, exc_value, exc_tb = _make_exc_info()
        sys.excepthook(exc_type, exc_value, exc_tb)
        assert calls["written"], "install() must log the crash"
        assert calls["chained"], "install() must still call whatever hook was there before"
    finally:
        crash_log.write_crash_entry = original_write
        sys.excepthook = original_hook
    print("PASS: install() logs the crash and still chains to the previous exception hook")


def test_install_also_call_failure_does_not_prevent_chaining():
    """The crash handler itself must never crash -- if the optional
    also_call callback (e.g. a dialog) itself raises, the previous hook
    must still run."""
    original_hook = sys.excepthook
    original_write = crash_log.write_crash_entry
    calls = {"chained": False}

    def fake_write(exc_type, exc_value, exc_tb, path=None):
        pass

    def failing_also_call(exc_type, exc_value, exc_tb):
        raise RuntimeError("the dialog itself is broken")

    def fake_previous_hook(exc_type, exc_value, exc_tb):
        calls["chained"] = True

    try:
        crash_log.write_crash_entry = fake_write
        sys.excepthook = fake_previous_hook
        install(also_call=failing_also_call, faulthandler_path=os.path.join(TEST_DIR, "faulthandler2.log"))
        exc_type, exc_value, exc_tb = _make_exc_info()
        sys.excepthook(exc_type, exc_value, exc_tb)  # must not itself raise
        assert calls["chained"]
    finally:
        crash_log.write_crash_entry = original_write
        sys.excepthook = original_hook
    print("PASS: a failing also_call doesn't prevent the previous hook from still running")


def test_install_enables_faulthandler():
    import faulthandler
    original_hook = sys.excepthook
    was_enabled_before = faulthandler.is_enabled()
    try:
        install(faulthandler_path=os.path.join(TEST_DIR, "faulthandler3.log"))
        assert faulthandler.is_enabled()
    finally:
        sys.excepthook = original_hook
        if not was_enabled_before:
            faulthandler.disable()
    print("PASS: install() enables faulthandler, for catching native-level crashes too")


if __name__ == "__main__":
    test_format_crash_entry_includes_timestamp_and_traceback()
    test_write_crash_entry_appends_to_file()
    test_write_crash_entry_never_raises_on_bad_path()
    test_trim_keeps_file_bounded()
    test_install_chains_to_previous_hook()
    test_install_also_call_failure_does_not_prevent_chaining()
    test_install_enables_faulthandler()
    print("\nALL CRASH LOG TESTS PASSED")
