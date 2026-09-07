"""Tests for redactor_common.core.error_summary (this project's own
local core/error_summary.py -- byte-identical apart from a docstring
path -- was the module this was generalized from, and was retired
2026-09-07 in favor of the shared one)."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from redactor_common.core.error_summary import summarize_errors  # noqa: E402


def test_summarize_errors_empty():
    assert summarize_errors([]) == ""
    print("PASS: an empty list summarizes to an empty string")


def test_summarize_errors_few_short_messages_unchanged():
    errors = ["book1.epub: not found", "book2.epub: timed out"]
    result = summarize_errors(errors)
    assert result == "book1.epub: not found; book2.epub: timed out"
    print("PASS: a few short messages pass through unchanged, joined with '; '")


def test_summarize_errors_caps_count_shown():
    errors = [f"book{i}.epub: failed" for i in range(10)]
    result = summarize_errors(errors)
    assert result.count(".epub:") == 3, result
    assert result.endswith(", ...")
    print("PASS: only the first 3 errors are shown, with a ', ...' suffix for the rest")


def test_summarize_errors_no_suffix_when_not_truncated_by_count():
    errors = ["a.epub: x", "b.epub: y", "c.epub: z"]
    result = summarize_errors(errors)
    assert not result.endswith(", ...")
    print("PASS: no ', ...' suffix when there are exactly max_shown errors, not more")


def test_summarize_errors_truncates_long_individual_message():
    """The actual bug this exists to prevent: a single error source
    (e.g. Calibre's own verbose stderr) producing one enormous message
    that would otherwise balloon a status label with no cap at all."""
    huge_message = "book.epub: " + ("x" * 5000)
    result = summarize_errors([huge_message])
    assert len(result) < 350, len(result)
    assert result.endswith("\u2026")
    print("PASS: a single very long error message is truncated, not shown in full")


def test_summarize_errors_custom_limits():
    errors = ["a: 1", "b: 2", "c: 3", "d: 4"]
    result = summarize_errors(errors, max_shown=2, max_chars=10)
    assert result.count(":") == 2
    assert result.endswith(", ...")
    print("PASS: custom max_shown/max_chars limits are respected")


def test_summarize_errors_exact_char_limit_not_truncated():
    message = "x" * 300  # exactly MAX_MESSAGE_CHARS
    result = summarize_errors([message])
    assert result == message
    assert "\u2026" not in result
    print("PASS: a message exactly at the character limit is not truncated")


if __name__ == "__main__":
    test_summarize_errors_empty()
    test_summarize_errors_few_short_messages_unchanged()
    test_summarize_errors_caps_count_shown()
    test_summarize_errors_no_suffix_when_not_truncated_by_count()
    test_summarize_errors_truncates_long_individual_message()
    test_summarize_errors_custom_limits()
    test_summarize_errors_exact_char_limit_not_truncated()
    print("\nALL ERROR SUMMARY TESTS PASSED")
