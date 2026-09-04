"""Tests for core/genres.py."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from core.genres import COMMON_GENRES, add_genre  # noqa: E402


def test_genre_list_sane():
    assert len(COMMON_GENRES) > 0
    assert len(COMMON_GENRES) == len(set(COMMON_GENRES)), "duplicate genres in list"
    assert all(g.strip() == g and g for g in COMMON_GENRES), "blank/untrimmed entry"
    print(f"PASS: genre list sane ({len(COMMON_GENRES)} entries, no dupes/blanks)")


def test_add_genre_to_empty():
    assert add_genre("", "Fantasy") == "Fantasy"
    print("PASS: add to empty field")


def test_add_genre_appends():
    assert add_genre("Fiction", "Fantasy") == "Fiction; Fantasy"
    print("PASS: appends to existing free-text content")


def test_add_genre_dedups():
    assert add_genre("Fiction; Fantasy", "Fantasy") == "Fiction; Fantasy"
    print("PASS: picking an already-present genre doesn't duplicate it")


def test_add_genre_preserves_freetext_entries():
    # Anything typed manually that isn't in COMMON_GENRES must survive.
    result = add_genre("My Custom Tag", "Horror")
    assert result == "My Custom Tag; Horror", result
    print("PASS: manually typed free-text tags are preserved alongside picks")


def test_add_genre_handles_messy_whitespace():
    result = add_genre("Fiction ;  Fantasy ;", "Horror")
    assert result == "Fiction; Fantasy; Horror", result
    print("PASS: cleans up stray whitespace/trailing separators while merging")


if __name__ == "__main__":
    test_genre_list_sane()
    test_add_genre_to_empty()
    test_add_genre_appends()
    test_add_genre_dedups()
    test_add_genre_preserves_freetext_entries()
    test_add_genre_handles_messy_whitespace()
    print("\nALL GENRE TESTS PASSED")
