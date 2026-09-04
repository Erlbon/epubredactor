"""Tests for core/series_numbering.py."""
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(__file__))
from core.series_numbering import (  # noqa: E402
    format_series_number,
    generate_series_numbers,
    parse_decimal,
)


# ----------------------------------------------------------------------
# parse_decimal
# ----------------------------------------------------------------------

def test_parse_decimal_basic():
    assert parse_decimal("5", "1") == Decimal("5")
    print("PASS: parses a plain integer string")


def test_parse_decimal_fractional():
    assert parse_decimal("1.5", "1") == Decimal("1.5")
    print("PASS: parses a fractional string")


def test_parse_decimal_blank_falls_back_to_default():
    assert parse_decimal("", "3") == Decimal("3")
    assert parse_decimal("   ", "3") == Decimal("3")
    print("PASS: blank/whitespace-only input falls back to the default")


def test_parse_decimal_invalid_falls_back_to_default():
    assert parse_decimal("not a number", "2") == Decimal("2")
    print("PASS: unparseable input falls back to the default rather than raising")


def test_parse_decimal_negative():
    assert parse_decimal("-2", "1") == Decimal("-2")
    print("PASS: negative numbers parse correctly")


# ----------------------------------------------------------------------
# format_series_number
# ----------------------------------------------------------------------

def test_format_whole_number_no_trailing_zero():
    assert format_series_number(Decimal("1")) == "1"
    assert format_series_number(Decimal("1.0")) == "1"
    assert format_series_number(Decimal("1.00")) == "1"
    print("PASS: whole numbers format with no trailing .0, regardless of input precision")


def test_format_large_whole_number_not_scientific_notation():
    # Decimal("100").normalize() would produce "1E+2" -- must not do that.
    assert format_series_number(Decimal("100")) == "100"
    assert format_series_number(Decimal("1000")) == "1000"
    print("PASS: large round numbers format plainly, not in scientific notation")


def test_format_fractional_number():
    assert format_series_number(Decimal("1.5")) == "1.5"
    print("PASS: a genuine fractional value keeps its decimal part")


def test_format_fractional_trailing_zeros_stripped():
    assert format_series_number(Decimal("1.50")) == "1.5"
    assert format_series_number(Decimal("1.2000")) == "1.2"
    print("PASS: unnecessary trailing zeros in the fractional part are stripped")


def test_format_negative_number():
    assert format_series_number(Decimal("-1")) == "-1"
    print("PASS: negative whole numbers format correctly")


# ----------------------------------------------------------------------
# generate_series_numbers
# ----------------------------------------------------------------------

def test_generate_basic_sequence():
    assert generate_series_numbers(5) == ["1", "2", "3", "4", "5"]
    print("PASS: default start=1/step=1 generates a plain 1..N sequence")


def test_generate_custom_start():
    assert generate_series_numbers(3, start="10") == ["10", "11", "12"]
    print("PASS: custom start value is honored")


def test_generate_custom_step():
    assert generate_series_numbers(4, start="1", step="2") == ["1", "3", "5", "7"]
    print("PASS: custom step value is honored")


def test_generate_fractional_step_no_float_drift():
    """The classic float-accumulation trap: 1 + 0.5 + 0.5 + 0.5 in
    binary float can drift to something like 2.4999999999999996. Decimal
    must not have this problem."""
    result = generate_series_numbers(5, start="1", step="0.5")
    assert result == ["1", "1.5", "2", "2.5", "3"], result
    print("PASS: fractional steps accumulate exactly, no floating-point drift")


def test_generate_zero_count():
    assert generate_series_numbers(0) == []
    print("PASS: a count of zero yields an empty list")


def test_generate_negative_count_is_empty_not_error():
    assert generate_series_numbers(-3) == []
    print("PASS: a negative count yields an empty list rather than raising")


def test_generate_blank_inputs_use_defaults():
    assert generate_series_numbers(3, start="", step="") == ["1", "2", "3"]
    print("PASS: blank start/step fields fall back to the 1/1 default")


def test_generate_invalid_inputs_use_defaults():
    assert generate_series_numbers(3, start="abc", step="xyz") == ["1", "2", "3"]
    print("PASS: unparseable start/step fields fall back to the 1/1 default")


def test_generate_decimal_start():
    assert generate_series_numbers(3, start="0.5", step="1") == ["0.5", "1.5", "2.5"]
    print("PASS: a fractional starting value works correctly")


if __name__ == "__main__":
    test_parse_decimal_basic()
    test_parse_decimal_fractional()
    test_parse_decimal_blank_falls_back_to_default()
    test_parse_decimal_invalid_falls_back_to_default()
    test_parse_decimal_negative()
    test_format_whole_number_no_trailing_zero()
    test_format_large_whole_number_not_scientific_notation()
    test_format_fractional_number()
    test_format_fractional_trailing_zeros_stripped()
    test_format_negative_number()
    test_generate_basic_sequence()
    test_generate_custom_start()
    test_generate_custom_step()
    test_generate_fractional_step_no_float_drift()
    test_generate_zero_count()
    test_generate_negative_count_is_empty_not_error()
    test_generate_blank_inputs_use_defaults()
    test_generate_invalid_inputs_use_defaults()
    test_generate_decimal_start()
    print("\nALL SERIES NUMBERING TESTS PASSED")
