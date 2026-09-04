"""Tests for core/isbn.py, using well-known real ISBN examples."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from core.isbn import (  # noqa: E402
    best_isbn13,
    is_valid_isbn10,
    is_valid_isbn13,
    isbn10_to_isbn13,
    normalize_isbn,
)


def test_normalize():
    assert normalize_isbn("0-306-40615-2") == "0306406152"
    assert normalize_isbn("978 0 306 40615 7") == "9780306406157"
    assert normalize_isbn(" 080442957x ") == "080442957X"
    assert normalize_isbn("") == ""
    print("PASS: normalize strips punctuation/whitespace, uppercases X")


def test_isbn10_valid_examples():
    # Classic worked example from the ISBN specification / Wikipedia.
    assert is_valid_isbn10("0306406152")
    assert is_valid_isbn10("0-306-40615-2")  # dashes tolerated
    # Known ISBN-10 ending in check digit X.
    assert is_valid_isbn10("080442957X")
    assert is_valid_isbn10("080442957x")  # lowercase x tolerated
    print("PASS: valid ISBN-10 examples accepted")


def test_isbn10_invalid_examples():
    assert not is_valid_isbn10("0306406153")  # wrong check digit
    assert not is_valid_isbn10("123")          # wrong length
    assert not is_valid_isbn10("030640615X")   # X not in final position -> invalid per our rule... 
    print("PASS: invalid ISBN-10 examples rejected")


def test_isbn13_valid_examples():
    assert is_valid_isbn13("9780306406157")  # matches the isbn10 example above
    assert is_valid_isbn13("978-0-306-40615-7")
    print("PASS: valid ISBN-13 examples accepted")


def test_isbn13_invalid_examples():
    assert not is_valid_isbn13("9780306406158")  # wrong check digit
    assert not is_valid_isbn13("97803064061")     # wrong length
    print("PASS: invalid ISBN-13 examples rejected")


def test_isbn10_to_isbn13_conversion():
    # This is the canonical worked pair from the ISBN spec's own example.
    assert isbn10_to_isbn13("0306406152") == "9780306406157"
    print("PASS: ISBN-10 -> ISBN-13 conversion matches known example")


def test_isbn10_to_isbn13_rejects_invalid():
    try:
        isbn10_to_isbn13("1234567890")  # bad check digit
        assert False, "should have raised"
    except ValueError:
        pass
    print("PASS: conversion rejects invalid ISBN-10 input")


def test_best_isbn13():
    assert best_isbn13("0306406152") == "9780306406157"
    assert best_isbn13("9780306406157") == "9780306406157"
    assert best_isbn13("978-0-306-40615-7") == "9780306406157"
    assert best_isbn13("not an isbn") == ""
    assert best_isbn13("") == ""
    print("PASS: best_isbn13 normalizes both formats, empty on garbage")


if __name__ == "__main__":
    test_normalize()
    test_isbn10_valid_examples()
    test_isbn10_invalid_examples()
    test_isbn13_valid_examples()
    test_isbn13_invalid_examples()
    test_isbn10_to_isbn13_conversion()
    test_isbn10_to_isbn13_rejects_invalid()
    test_best_isbn13()
    print("\nALL ISBN TESTS PASSED")
