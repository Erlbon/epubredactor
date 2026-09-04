"""Tests for core/cover_generator.py."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from core.cover_generator import COVER_PALETTE, color_for_title, cover_text_lines  # noqa: E402


def test_color_for_title_deterministic():
    a = color_for_title("The Hobbit")
    b = color_for_title("The Hobbit")
    assert a == b
    print("PASS: the same title always yields the same color")


def test_color_for_title_case_and_whitespace_insensitive():
    a = color_for_title("The Hobbit")
    b = color_for_title("  the hobbit  ")
    assert a == b
    print("PASS: color choice ignores case and surrounding whitespace differences")


def test_color_for_title_from_palette():
    color = color_for_title("Some Book")
    assert color in COVER_PALETTE
    print("PASS: the chosen color always comes from the curated palette")


def test_color_for_title_different_titles_vary():
    titles = [f"Book {i}" for i in range(20)]
    colors = {color_for_title(t) for t in titles}
    # Not asserting every one is unique (a palette of 12 with 20 titles
    # must have some repeats), just that it's not collapsing to one color.
    assert len(colors) > 1
    print(f"PASS: {len(colors)} distinct colors across 20 different titles, not all identical")


def test_color_for_title_empty_title_does_not_crash():
    color = color_for_title("")
    assert color in COVER_PALETTE
    print("PASS: an empty title still yields a valid palette color, no crash")


def test_cover_text_lines_title_only():
    result = cover_text_lines("The Hobbit")
    assert result == {"title": "The Hobbit", "author_line": "", "series_line": ""}
    print("PASS: title-only metadata produces just a title line")


def test_cover_text_lines_with_author():
    result = cover_text_lines("The Hobbit", "J.R.R. Tolkien")
    assert result["title"] == "The Hobbit"
    assert result["author_line"] == "by J.R.R. Tolkien"
    assert result["series_line"] == ""
    print("PASS: author line is prefixed with 'by '")


def test_cover_text_lines_with_series_and_index():
    result = cover_text_lines("Fellowship of the Ring", "J.R.R. Tolkien", "Lord of the Rings", "1")
    assert result["series_line"] == "Lord of the Rings #1"
    print("PASS: series + index combine into one line")


def test_cover_text_lines_series_without_index():
    result = cover_text_lines("Some Book", series="A Trilogy")
    assert result["series_line"] == "A Trilogy"
    print("PASS: series alone (no index) is shown without a stray '#'")


def test_cover_text_lines_empty_title_falls_back():
    result = cover_text_lines("")
    assert result["title"] == "(Untitled)"
    print("PASS: an empty/missing title falls back to a placeholder label, not a blank cover")


def test_cover_text_lines_whitespace_only_title_falls_back():
    result = cover_text_lines("   ")
    assert result["title"] == "(Untitled)"
    print("PASS: a whitespace-only title also falls back to the placeholder label")


def test_cover_text_lines_blank_author_omitted():
    result = cover_text_lines("Some Book", "   ")
    assert result["author_line"] == ""
    print("PASS: a blank/whitespace-only author string produces no author line, not 'by '")


if __name__ == "__main__":
    test_color_for_title_deterministic()
    test_color_for_title_case_and_whitespace_insensitive()
    test_color_for_title_from_palette()
    test_color_for_title_different_titles_vary()
    test_color_for_title_empty_title_does_not_crash()
    test_cover_text_lines_title_only()
    test_cover_text_lines_with_author()
    test_cover_text_lines_with_series_and_index()
    test_cover_text_lines_series_without_index()
    test_cover_text_lines_empty_title_falls_back()
    test_cover_text_lines_whitespace_only_title_falls_back()
    test_cover_text_lines_blank_author_omitted()
    print("\nALL COVER GENERATOR TESTS PASSED")
