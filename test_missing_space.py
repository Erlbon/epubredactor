"""Tests for core/missing_space.py."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from core.missing_space import find_missing_spaces, suggest_fix  # noqa: E402


def test_finds_period_missing_space():
    result = find_missing_spaces("Hello.World")
    assert result == [(5, ".W")], result
    print("PASS: detects a period directly followed by a letter")


def test_finds_comma_missing_space():
    result = find_missing_spaces("Foo,Bar")
    assert result == [(3, ",B")], result
    print("PASS: detects a comma directly followed by a letter")


def test_finds_multiple_occurrences():
    result = find_missing_spaces("One.Two,Three")
    assert result == [(3, ".T"), (7, ",T")], result
    print("PASS: finds every occurrence in the same string")


def test_no_false_positive_on_correctly_spaced_text():
    assert find_missing_spaces("Hello. World") == []
    assert find_missing_spaces("A normal, well-formed sentence.") == []
    print("PASS: correctly spaced text is never flagged")


def test_no_false_positive_on_decimal_numbers():
    # Punctuation followed by a DIGIT, not a letter -- must not match.
    assert find_missing_spaces("Book 3.5") == []
    assert find_missing_spaces("DDC 823.912") == []
    print("PASS: decimal numbers (punctuation followed by a digit) are never flagged")


def test_no_false_positive_on_apostrophes():
    assert find_missing_spaces("Don't Stop Believing") == []
    assert find_missing_spaces("The Cat's Cradle") == []
    print("PASS: apostrophes/contractions are never flagged (not in the punctuation set)")


def test_no_false_positive_on_hyphenated_words():
    assert find_missing_spaces("Spider-Man: Homecoming") == []
    print("PASS: hyphenated words are never flagged (hyphen not in the punctuation set)")


def test_period_at_end_of_string_not_flagged():
    # No letter follows the period, so nothing to match.
    assert find_missing_spaces("The End.") == []
    print("PASS: punctuation at the very end of the string (nothing follows) isn't flagged")


def test_empty_string():
    assert find_missing_spaces("") == []
    print("PASS: empty string yields no matches")


def test_suggest_fix_inserts_space():
    assert suggest_fix("Hello.World") == "Hello. World"
    print("PASS: suggest_fix inserts a space after the punctuation")


def test_suggest_fix_multiple_occurrences():
    assert suggest_fix("One.Two,Three") == "One. Two, Three"
    print("PASS: suggest_fix fixes every occurrence in the string")


def test_suggest_fix_no_matches_unchanged():
    assert suggest_fix("Nothing wrong here.") == "Nothing wrong here."
    print("PASS: text with nothing to fix is returned unchanged")


def test_suggest_fix_empty_string():
    assert suggest_fix("") == ""
    print("PASS: suggest_fix on empty string returns empty string")


if __name__ == "__main__":
    test_finds_period_missing_space()
    test_finds_comma_missing_space()
    test_finds_multiple_occurrences()
    test_no_false_positive_on_correctly_spaced_text()
    test_no_false_positive_on_decimal_numbers()
    test_no_false_positive_on_apostrophes()
    test_no_false_positive_on_hyphenated_words()
    test_period_at_end_of_string_not_flagged()
    test_empty_string()
    test_suggest_fix_inserts_space()
    test_suggest_fix_multiple_occurrences()
    test_suggest_fix_no_matches_unchanged()
    test_suggest_fix_empty_string()
    print("\nALL MISSING SPACE TESTS PASSED")
