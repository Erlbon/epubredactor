"""Tests for redactor_common.core.save_errors (this project's own local
core/save_errors.py -- byte-identical apart from a docstring path --
was the module this was generalized from, and was retired 2026-09-07
in favor of the shared one)."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from redactor_common.core.save_errors import (  # noqa: E402
    PATH_TOO_LONG_MESSAGE,
    describe_save_error,
    is_path_too_long_error,
)


class _FakeWinError(OSError):
    """A minimal stand-in for a real Windows OSError with a winerror
    attribute -- lets the winerror-code path be tested even though this
    suite runs on a non-Windows sandbox where a genuine one can't be
    raised."""

    def __init__(self, winerror, message="Some error"):
        super().__init__(message)
        self.winerror = winerror


def test_is_path_too_long_error_by_winerror_code():
    exc = _FakeWinError(206, "The filename or extension is too long")
    assert is_path_too_long_error(exc)
    print("PASS: detects path-too-long via the Windows winerror 206 code")


def test_is_path_too_long_error_other_winerror_not_matched():
    exc = _FakeWinError(5, "Access is denied")  # a different real Windows error code
    assert not is_path_too_long_error(exc)
    print("PASS: a different winerror code (e.g. access denied) is not mistaken for path-too-long")


def test_is_path_too_long_error_message_fallback_path():
    exc = OSError("The specified path is too long")
    assert is_path_too_long_error(exc)
    print("PASS: falls back to a message-based check when there's no winerror attribute")


def test_is_path_too_long_error_message_fallback_filename():
    exc = OSError("filename too long for this filesystem")
    assert is_path_too_long_error(exc)
    print("PASS: message-based fallback also matches 'filename too long' phrasing")


def test_is_path_too_long_error_unrelated_message_not_matched():
    exc = OSError("Permission denied")
    assert not is_path_too_long_error(exc)
    print("PASS: an unrelated error message is correctly not flagged as path-too-long")


def test_is_path_too_long_error_too_long_alone_not_matched():
    # "too long" alone, with neither "path" nor "filename" nearby,
    # shouldn't be treated as this specific error -- avoids false
    # positives on some other, unrelated "X is too long" message.
    exc = OSError("The requested operation took too long and timed out")
    assert not is_path_too_long_error(exc)
    print("PASS: 'too long' without 'path'/'filename' nearby is not treated as path-too-long")


def test_describe_save_error_path_too_long_uses_clear_message():
    exc = _FakeWinError(206)
    result = describe_save_error(exc)
    assert result == PATH_TOO_LONG_MESSAGE
    assert "again won't help" in result.lower()
    print("PASS: describe_save_error gives the clear, actionable message for path-too-long")


def test_describe_save_error_other_errors_pass_through():
    exc = OSError("Permission denied")
    result = describe_save_error(exc)
    assert result == "Permission denied"
    assert result != PATH_TOO_LONG_MESSAGE
    print("PASS: any other error's own message passes through unchanged")


if __name__ == "__main__":
    test_is_path_too_long_error_by_winerror_code()
    test_is_path_too_long_error_other_winerror_not_matched()
    test_is_path_too_long_error_message_fallback_path()
    test_is_path_too_long_error_message_fallback_filename()
    test_is_path_too_long_error_unrelated_message_not_matched()
    test_is_path_too_long_error_too_long_alone_not_matched()
    test_describe_save_error_path_too_long_uses_clear_message()
    test_describe_save_error_other_errors_pass_through()
    print("\nALL SAVE ERRORS TESTS PASSED")
