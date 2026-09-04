"""Tests for core/search_replace.py."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from core.search_replace import (  # noqa: E402
    SearchReplaceError,
    apply_replace,
    would_change,
)


def test_plain_replace():
    assert apply_replace("The Hobbit", "Hobbit", "Fellowship") == "The Fellowship"
    print("PASS: plain text replace")


def test_plain_replace_case_insensitive_by_default():
    assert apply_replace("THE HOBBIT", "hobbit", "Fellowship") == "THE Fellowship"
    print("PASS: case-insensitive by default")


def test_plain_replace_case_sensitive():
    assert apply_replace("THE HOBBIT", "hobbit", "X", case_sensitive=True) == "THE HOBBIT"
    assert apply_replace("THE HOBBIT", "HOBBIT", "X", case_sensitive=True) == "THE X"
    print("PASS: case-sensitive mode respects case")


def test_plain_mode_treats_regex_chars_literally():
    # A literal "." in plain mode should not act as a regex wildcard.
    assert apply_replace("A.B.C", ".", "-") == "A-B-C"
    assert apply_replace("AxBxC", ".", "-") == "AxBxC"  # unchanged: no literal "." present
    print("PASS: plain mode escapes regex special characters")


def test_regex_replace_with_backreference():
    result = apply_replace(
        "John Smith", r"(\w+) (\w+)", r"\2, \1", use_regex=True
    )
    assert result == "Smith, John", result
    print("PASS: regex mode supports backreferences")


def test_regex_replace_case_insensitive():
    result = apply_replace("Fantasy; SCIENCE FICTION", "science fiction", "Sci-Fi", use_regex=True)
    assert result == "Fantasy; Sci-Fi", result
    print("PASS: regex mode is also case-insensitive by default")


def test_empty_search_is_noop():
    assert apply_replace("Unchanged", "", "X") == "Unchanged"
    print("PASS: empty search string is a no-op")


def test_no_match_is_noop():
    assert apply_replace("Unrelated Text", "zzz", "X") == "Unrelated Text"
    print("PASS: no match leaves the value unchanged")


def test_invalid_regex_raises():
    try:
        apply_replace("text", "(unclosed", "X", use_regex=True)
        assert False, "should have raised"
    except SearchReplaceError:
        pass
    print("PASS: invalid regex raises SearchReplaceError")


def test_would_change():
    assert would_change("The Hobbit", "Hobbit", "Fellowship") is True
    assert would_change("The Hobbit", "zzz", "Fellowship") is False
    assert would_change("The Hobbit", "", "Fellowship") is False
    assert would_change("text", "(unclosed", "X", use_regex=True) is False  # invalid regex -> no crash
    print("PASS: would_change correctly detects whether a replace does anything")


def test_literal_backslash_in_plain_replacement_not_treated_as_group():
    # In plain (non-regex) mode, a literal backslash in the replacement
    # text should stay a literal backslash, not be interpreted as a regex
    # backreference/escape.
    result = apply_replace("C:\\Books", "Books", "New\\Path")
    assert result == "C:\\New\\Path", result
    print("PASS: literal backslashes in plain-mode replacement text survive intact")


if __name__ == "__main__":
    test_plain_replace()
    test_plain_replace_case_insensitive_by_default()
    test_plain_replace_case_sensitive()
    test_plain_mode_treats_regex_chars_literally()
    test_regex_replace_with_backreference()
    test_regex_replace_case_insensitive()
    test_empty_search_is_noop()
    test_no_match_is_noop()
    test_invalid_regex_raises()
    test_would_change()
    test_literal_backslash_in_plain_replacement_not_treated_as_group()
    print("\nALL SEARCH/REPLACE TESTS PASSED")
