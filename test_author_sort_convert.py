"""Tests for core/author_sort.py."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from core.author_sort import author_sort_to_authors, authors_to_author_sort  # noqa: E402


# ----------------------------------------------------------------------
# authors_to_author_sort (the original direction)
# ----------------------------------------------------------------------

def test_authors_to_author_sort_basic():
    assert authors_to_author_sort("Jane Doe") == "Doe, Jane"
    print("PASS: basic first/last split")


def test_authors_to_author_sort_middle_initial():
    assert authors_to_author_sort("Jane Q. Doe") == "Doe, Jane Q."
    print("PASS: splits on the LAST space, keeping a middle initial with the first name")


def test_authors_to_author_sort_multiple_authors():
    assert authors_to_author_sort("Jane Doe; John Smith") == "Doe, Jane; Smith, John"
    print("PASS: multiple semicolon-separated authors each get converted")


def test_authors_to_author_sort_single_name_unchanged():
    assert authors_to_author_sort("Prince") == "Prince"
    print("PASS: a single-word name (no space) passes through unchanged")


def test_authors_to_author_sort_empty():
    assert authors_to_author_sort("") == ""
    print("PASS: empty input yields empty output")


def test_authors_to_author_sort_trims_whitespace():
    assert authors_to_author_sort("  Jane Doe  ;  John Smith  ") == "Doe, Jane; Smith, John"
    print("PASS: stray whitespace around entries is trimmed")


# ----------------------------------------------------------------------
# author_sort_to_authors (the new inverse direction)
# ----------------------------------------------------------------------

def test_author_sort_to_authors_basic():
    assert author_sort_to_authors("Doe, Jane") == "Jane Doe"
    print("PASS: basic last/first split back to First Last")


def test_author_sort_to_authors_middle_initial():
    assert author_sort_to_authors("Doe, Jane Q.") == "Jane Q. Doe"
    print("PASS: splits on the FIRST comma, keeping the middle initial with the first name")


def test_author_sort_to_authors_multiple_authors():
    assert author_sort_to_authors("Doe, Jane; Smith, John") == "Jane Doe; John Smith"
    print("PASS: multiple semicolon-separated entries each get converted")


def test_author_sort_to_authors_single_name_unchanged():
    assert author_sort_to_authors("Prince") == "Prince"
    print("PASS: an entry with no comma passes through unchanged")


def test_author_sort_to_authors_empty():
    assert author_sort_to_authors("") == ""
    print("PASS: empty input yields empty output")


def test_author_sort_to_authors_trims_whitespace():
    assert author_sort_to_authors("  Doe,  Jane  ;  Smith,  John  ") == "Jane Doe; John Smith"
    print("PASS: stray whitespace around entries and around the comma is trimmed")


def test_author_sort_to_authors_trailing_comma_no_first_name():
    # "Doe," with nothing after the comma -- shouldn't produce "Doe "
    # with a stray trailing space.
    assert author_sort_to_authors("Doe,") == "Doe"
    print("PASS: a trailing comma with no first name doesn't leave stray whitespace")


# ----------------------------------------------------------------------
# Round-trip: the two directions should undo each other for the common,
# unambiguous case (no compound surnames, no non-Western name order).
# ----------------------------------------------------------------------

def test_round_trip_authors_to_sort_to_authors():
    original = "Jane Q. Doe; John Smith"
    round_tripped = author_sort_to_authors(authors_to_author_sort(original))
    assert round_tripped == original, round_tripped
    print("PASS: Author -> Author Sort -> Author round-trips for straightforward names")


def test_round_trip_sort_to_authors_to_sort():
    original = "Doe, Jane Q.; Smith, John"
    round_tripped = authors_to_author_sort(author_sort_to_authors(original))
    assert round_tripped == original, round_tripped
    print("PASS: Author Sort -> Author -> Author Sort round-trips for straightforward names")


if __name__ == "__main__":
    test_authors_to_author_sort_basic()
    test_authors_to_author_sort_middle_initial()
    test_authors_to_author_sort_multiple_authors()
    test_authors_to_author_sort_single_name_unchanged()
    test_authors_to_author_sort_empty()
    test_authors_to_author_sort_trims_whitespace()
    test_author_sort_to_authors_basic()
    test_author_sort_to_authors_middle_initial()
    test_author_sort_to_authors_multiple_authors()
    test_author_sort_to_authors_single_name_unchanged()
    test_author_sort_to_authors_empty()
    test_author_sort_to_authors_trims_whitespace()
    test_author_sort_to_authors_trailing_comma_no_first_name()
    test_round_trip_authors_to_sort_to_authors()
    test_round_trip_sort_to_authors_to_sort()
    print("\nALL AUTHOR SORT TESTS PASSED")
