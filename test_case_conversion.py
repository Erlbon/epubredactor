"""Tests for core/case_conversion.py."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from core.case_conversion import (  # noqa: E402
    apply_case_conversion,
    to_lower,
    to_sentence_case,
    to_title_case,
    to_upper,
)


def test_to_upper():
    assert to_upper("the hobbit") == "THE HOBBIT"
    print("PASS: uppercase conversion")


def test_to_lower():
    assert to_lower("THE HOBBIT") == "the hobbit"
    print("PASS: lowercase conversion")


def test_title_case_basic():
    assert to_title_case("the lord of the rings") == "The Lord of the Rings"
    print("PASS: title case capitalizes correctly, lowercasing minor mid-sentence words")


def test_title_case_first_and_last_word_always_capitalized():
    # "of" as the very first or last word should still be capitalized,
    # even though it's normally a minor word.
    assert to_title_case("of mice and men") == "Of Mice and Men"
    print("PASS: minor words at the start/end of the title are still capitalized")


def test_title_case_preserves_apostrophes():
    assert to_title_case("don't stop believing") == "Don't Stop Believing"
    print("PASS: apostrophes survive correctly (str.title() would break this)")


def test_title_case_handles_multiple_spaces():
    result = to_title_case("the  hobbit")  # double space
    assert result == "The  Hobbit", repr(result)
    print("PASS: multiple consecutive spaces are preserved exactly")


def test_sentence_case_basic():
    assert to_sentence_case("THE HOBBIT") == "The hobbit"
    print("PASS: sentence case capitalizes only the first letter")


def test_sentence_case_preserves_leading_whitespace():
    assert to_sentence_case("  the hobbit") == "  The hobbit"
    print("PASS: sentence case preserves leading whitespace exactly")


def test_sentence_case_empty_string():
    assert to_sentence_case("") == ""
    assert to_sentence_case("   ") == "   "
    print("PASS: empty/whitespace-only input doesn't crash")


def test_apply_case_conversion_dispatch():
    assert apply_case_conversion("the hobbit", "UPPERCASE") == "THE HOBBIT"
    assert apply_case_conversion("THE HOBBIT", "lowercase") == "the hobbit"
    assert apply_case_conversion("the hobbit", "Title Case") == "The Hobbit"
    assert apply_case_conversion("THE HOBBIT", "Sentence case") == "The hobbit"
    print("PASS: apply_case_conversion dispatches to the correct transform by name")


def test_apply_case_conversion_unknown_mode_is_noop():
    assert apply_case_conversion("Unchanged Text", "Not A Real Mode") == "Unchanged Text"
    print("PASS: an unrecognized mode name is a safe no-op, not a crash")


if __name__ == "__main__":
    test_to_upper()
    test_to_lower()
    test_title_case_basic()
    test_title_case_first_and_last_word_always_capitalized()
    test_title_case_preserves_apostrophes()
    test_title_case_handles_multiple_spaces()
    test_sentence_case_basic()
    test_sentence_case_preserves_leading_whitespace()
    test_sentence_case_empty_string()
    test_apply_case_conversion_dispatch()
    test_apply_case_conversion_unknown_mode_is_noop()
    print("\nALL CASE CONVERSION TESTS PASSED")
