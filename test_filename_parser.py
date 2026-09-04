"""Tests for core/filename_parser.py."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from core.filename_parser import (  # noqa: E402
    best_matching_pattern,
    build_parser_regex,
    count_matching_filenames,
    parse_filename,
)
from core.rename_pattern import render_filename  # noqa: E402
from core.epub_metadata import EpubMetadata  # noqa: E402


def test_basic_extraction():
    result = parse_filename("Middle-earth 1 - The Hobbit", "%series% %series_index% - %title%")
    assert result == {"series": "Middle-earth", "series_index": "1", "title": "The Hobbit"}, result
    print("PASS: basic extraction with clear separators")


def test_author_title_extraction():
    result = parse_filename("Frank Herbert - Dune", "%authors% - %title%")
    assert result == {"authors": "Frank Herbert", "title": "Dune"}, result
    print("PASS: author-title pattern extracts correctly even with spaces inside a field")


def test_no_match_returns_none():
    result = parse_filename("Completely Different Shape", "%series% %series_index% - %title%")
    assert result is None
    print("PASS: filename that doesn't match the pattern shape returns None")


def test_pattern_with_no_fields():
    result = parse_filename("SomeBook", "SomeBook")
    assert result == {}
    print("PASS: a pattern with no %field% tokens matches literally, extracts nothing")


def test_duplicate_field_in_pattern_does_not_crash():
    # Using %title% twice would normally break a naive regex (duplicate
    # group names) -- must degrade gracefully instead of raising.
    regex = build_parser_regex("%title% - %title%")
    assert regex is not None
    result = parse_filename("Echo - Echo", "%title% - %title%")
    # Only the first occurrence becomes a real group; the second is
    # matched as literal text "%title%", so this specific input won't
    # match (that's fine -- the point is it doesn't crash).
    assert result is None or "title" in result
    print("PASS: duplicate field token in pattern doesn't crash the regex compiler")


def test_unknown_field_treated_as_literal():
    result = parse_filename("literally %bogus% text", "literally %bogus% text")
    assert result == {}
    print("PASS: unrecognized %field% token is treated as literal text")


def test_roundtrip_with_render_filename():
    """The practical use case: render a filename from metadata, then
    parse the SAME pattern back out of it, and recover the original
    values for fields that were actually in the pattern."""
    m = EpubMetadata()
    m.title = "The Fellowship of the Ring"
    m.series = "Lord of the Rings"
    m.series_index = "1"

    pattern = "%series% %series_index% - %title%"
    filename = render_filename(m, pattern)
    parsed = parse_filename(filename, pattern)

    assert parsed is not None
    assert parsed["series"] == "Lord of the Rings"
    assert parsed["series_index"] == "1"
    assert parsed["title"] == "The Fellowship of the Ring"
    print("PASS: round trip through render_filename -> parse_filename recovers original values")


def test_roundtrip_with_isbn_and_year():
    m = EpubMetadata()
    m.title = "Dune"
    m.pub_year = "1965"
    m.isbn = "9780441013593"

    pattern = "%pub_year% - %title% [%isbn%]"
    filename = render_filename(m, pattern)
    parsed = parse_filename(filename, pattern)
    assert parsed["pub_year"] == "1965"
    assert parsed["title"] == "Dune"
    assert parsed["isbn"] == "9780441013593"
    print("PASS: round trip works with bracket-style literal separators too")


def test_extra_whitespace_trimmed():
    result = parse_filename("  Series  1  -  Title  ", "%series% %series_index% - %title%")
    # Now that literal whitespace in the pattern matches any RUN of
    # whitespace in the filename (not an exact character count), this
    # actually matches -- and each captured group's own leading/trailing
    # whitespace is trimmed too.
    assert result is not None
    assert result["series"] == "Series"
    assert result["series_index"] == "1"
    assert result["title"] == "Title"
    print("PASS: captured values are trimmed of stray whitespace")


def test_double_space_in_filename_still_matches():
    """The user-reported bug: a pattern like '%author% - %title%' (one
    space on each side of the dash) previously failed outright against a
    filename with a stray double space anywhere near that separator,
    since the literal ' - ' had to match character-for-character."""
    result = parse_filename("Jane Doe  -  My Book", "%authors% - %title%")
    assert result is not None
    assert result["authors"] == "Jane Doe"
    assert result["title"] == "My Book"
    print("PASS: a doubled space around a literal separator no longer breaks the match")


def test_missing_space_not_tolerated_by_design():
    """The flexible-whitespace fix only loosens how MUCH whitespace is
    required where the pattern already has some (one-or-more, not an
    exact count) -- it deliberately does NOT also allow zero whitespace
    where the pattern expects some. Doing that too would make an
    ordinary "%field% %field%" pattern (very common in this app)
    genuinely ambiguous about where one field ends and the next
    begins, which is a real regression risk the reported "extra space"
    complaint doesn't call for."""
    result = parse_filename("Jane Doe -My Book", "%authors% - %title%")
    assert result is None
    print("PASS: a missing space where the pattern expects one is still not matched, by design")


def test_tab_or_mixed_whitespace_matches():
    result = parse_filename("Jane Doe \t- My Book", "%authors% - %title%")
    assert result is not None
    assert result["authors"] == "Jane Doe"
    assert result["title"] == "My Book"
    print("PASS: a stray tab or other whitespace character also matches")


def test_leading_trailing_filename_whitespace_stripped():
    result = parse_filename("  Jane Doe - My Book  ", "%authors% - %title%")
    assert result is not None
    assert result["authors"] == "Jane Doe"
    assert result["title"] == "My Book"
    print("PASS: leading/trailing whitespace on the whole filename doesn't break matching")


def test_no_whitespace_boundary_still_requires_no_whitespace_flexibility():
    """A separator with NO whitespace in the pattern (e.g. a bare dash)
    is unaffected by this change -- only literal segments that already
    contain whitespace get the \\s+ treatment; this doesn't loosen
    anything about non-whitespace literal text."""
    result = parse_filename("JaneDoe-MyBook", "%authors%-%title%")
    assert result is not None
    assert result["authors"] == "JaneDoe"
    assert result["title"] == "MyBook"
    print("PASS: a whitespace-free literal separator is unaffected, still matches exactly")


# ----------------------------------------------------------------------
# count_matching_filenames / best_matching_pattern
# ----------------------------------------------------------------------

def test_count_matching_filenames_basic():
    filenames = ["Doe, Jane - My Book", "Smith, John - Other Book", "not matching at all"]
    count = count_matching_filenames(filenames, "%author_sort% - %title%")
    assert count == 2, count
    print("PASS: counts only the filenames that actually match the pattern")


def test_count_matching_filenames_no_matches():
    filenames = ["nothing here", "or here either"]
    assert count_matching_filenames(filenames, "%author_sort% - %title%") == 0
    print("PASS: zero matches when nothing in the list fits the pattern")


def test_count_matching_filenames_empty_list():
    assert count_matching_filenames([], "%title%") == 0
    print("PASS: an empty filename list yields a count of zero, not an error")


def test_best_matching_pattern_picks_highest_count():
    filenames = ["Doe, Jane - Book One", "Doe, Jane - Book Two", "Smith, John # Book Three"]
    patterns = ["%author_sort% # %title%", "%author_sort% - %title%"]
    result = best_matching_pattern(filenames, patterns)
    assert result is not None
    pattern, count = result
    assert pattern == "%author_sort% - %title%"
    assert count == 2
    print("PASS: picks the pattern that matches the most filenames")


def test_best_matching_pattern_none_match():
    filenames = ["totally unrelated text", "more unrelated text"]
    patterns = ["%author_sort% - %title%", "%series% #%series_index%"]
    assert best_matching_pattern(filenames, patterns) is None
    print("PASS: returns None when no candidate pattern matches anything")


def test_best_matching_pattern_empty_inputs():
    assert best_matching_pattern([], ["%title%"]) is None
    assert best_matching_pattern(["Some Title"], []) is None
    print("PASS: an empty filename list or pattern list both yield None, not an error")


def test_best_matching_pattern_tie_prefers_earlier_in_list():
    """History is passed newest-first, so a tie should favor whichever
    pattern comes first -- i.e. the more recently used one. Uses two
    patterns that differ only in how many literal spaces they have (1
    vs 2) -- both compile to the same \\s+ match (see the flexible-
    whitespace fix above), so they genuinely tie on this filename."""
    filenames = ["Foundation 1"]
    patterns = ["%series% %series_index%", "%series%  %series_index%"]
    result = best_matching_pattern(filenames, patterns)
    assert result is not None
    pattern, count = result
    assert pattern == "%series% %series_index%"  # the first one in the list
    assert count == 1
    print("PASS: a tie in match count is broken toward the earlier (more recent) pattern")


def test_multiword_series_disambiguated_by_numeric_index():
    """Regression test for a real bug: with only a single space between
    %series% and %series_index%, a multi-word series name used to be
    mis-split because a generic ".+?" for series_index could swallow part
    of the series name too. Requiring series_index to look like a number
    resolves it."""
    result = parse_filename(
        "Lord of the Rings 1 - The Fellowship of the Ring",
        "%series% %series_index% - %title%",
    )
    assert result == {
        "series": "Lord of the Rings",
        "series_index": "1",
        "title": "The Fellowship of the Ring",
    }, result
    print("PASS: multi-word series name no longer confused with the numeric series index")


def test_parsed_to_metadata_kwargs_translates_multivalue_keys():
    from core.filename_parser import parsed_to_metadata_kwargs
    parsed = {"authors": "Jane Doe", "tags": "Fantasy", "author_sort": "Doe, Jane", "title": "Book"}
    result = parsed_to_metadata_kwargs(parsed)
    assert result == {
        "authors_str": "Jane Doe",
        "tags_str": "Fantasy",
        "author_sort_str": "Doe, Jane",
        "title": "Book",
    }, result
    print("PASS: multi-value field keys translated to their _str property names for apply_metadata")


def test_year_month_day_parse_and_translate():
    """%year%/%month%/%day% are the advertised tokens now (see
    rename_pattern.py) -- parsing must recognize them AND translate them
    to the real pub_year/pub_month/pub_day attribute names."""
    from core.filename_parser import parsed_to_metadata_kwargs
    parsed = parse_filename("1955-07-03 - Old Book", "%year%-%month%-%day% - %title%")
    assert parsed == {"year": "1955", "month": "07", "day": "03", "title": "Old Book"}, parsed
    result = parsed_to_metadata_kwargs(parsed)
    assert result == {
        "pub_year": "1955", "pub_month": "07", "pub_day": "03", "title": "Old Book",
    }, result
    print("PASS: %year%/%month%/%day% parse and translate to pub_year/pub_month/pub_day")


def test_legacy_pub_year_still_parses():
    from core.filename_parser import parsed_to_metadata_kwargs
    parsed = parse_filename("1955 - Old Book", "%pub_year% - %title%")
    assert parsed == {"pub_year": "1955", "title": "Old Book"}, parsed
    result = parsed_to_metadata_kwargs(parsed)
    assert result == {"pub_year": "1955", "title": "Old Book"}, result
    print("PASS: legacy %pub_year% pattern still parses and translates correctly")


def test_series_index_leading_zeros_stripped():
    parsed = parse_filename("Series 03 - Title", "%series% %series_index% - %title%")
    assert parsed["series_index"] == "3", parsed
    print("PASS: a zero-padded series index (\"03\") has its leading zero stripped on parse")


def test_series_index_leading_zeros_stripped_multiple():
    parsed = parse_filename("Series 007 - Title", "%series% %series_index% - %title%")
    assert parsed["series_index"] == "7", parsed
    print("PASS: multiple leading zeros are all stripped (\"007\" -> \"7\")")


def test_series_index_decimal_leading_zero_stripped_fraction_preserved():
    """The exact case the user described: a novella numbered between two
    main entries, e.g. "03.5", zero-padded for filename sort order."""
    parsed = parse_filename("Series 03.5 - Title", "%series% %series_index% - %title%")
    assert parsed["series_index"] == "3.5", parsed
    print("PASS: a zero-padded decimal series index (\"03.5\") strips the leading zero, keeps the decimal exactly")


def test_series_index_plain_decimal_still_parses():
    """Confirms the underlying regex already accepted a decimal series
    index before this change too -- '.' was never actually rejected."""
    parsed = parse_filename("Series 3.5 - Title", "%series% %series_index% - %title%")
    assert parsed["series_index"] == "3.5", parsed
    print("PASS: an unpadded decimal series index (\"3.5\") parses correctly")


def test_series_index_zero_alone_not_stripped_to_empty():
    parsed = parse_filename("Series 0 - Title", "%series% %series_index% - %title%")
    assert parsed["series_index"] == "0", parsed
    print("PASS: a lone \"0\" series index stays \"0\", not stripped to an empty string")


def test_series_index_zero_point_something_preserved():
    parsed = parse_filename("Series 0.5 - Title", "%series% %series_index% - %title%")
    assert parsed["series_index"] == "0.5", parsed
    print("PASS: \"0.5\" is preserved correctly, not mangled into \".5\"")


def test_series_index_no_leading_zero_unaffected():
    parsed = parse_filename("Series 12 - Title", "%series% %series_index% - %title%")
    assert parsed["series_index"] == "12", parsed
    print("PASS: a series index with no leading zero is left exactly as-is")


if __name__ == "__main__":
    test_basic_extraction()
    test_author_title_extraction()
    test_no_match_returns_none()
    test_pattern_with_no_fields()
    test_duplicate_field_in_pattern_does_not_crash()
    test_unknown_field_treated_as_literal()
    test_roundtrip_with_render_filename()
    test_roundtrip_with_isbn_and_year()
    test_extra_whitespace_trimmed()
    test_double_space_in_filename_still_matches()
    test_missing_space_not_tolerated_by_design()
    test_tab_or_mixed_whitespace_matches()
    test_leading_trailing_filename_whitespace_stripped()
    test_no_whitespace_boundary_still_requires_no_whitespace_flexibility()
    test_count_matching_filenames_basic()
    test_count_matching_filenames_no_matches()
    test_count_matching_filenames_empty_list()
    test_best_matching_pattern_picks_highest_count()
    test_best_matching_pattern_none_match()
    test_best_matching_pattern_empty_inputs()
    test_best_matching_pattern_tie_prefers_earlier_in_list()
    test_multiword_series_disambiguated_by_numeric_index()
    test_parsed_to_metadata_kwargs_translates_multivalue_keys()
    test_year_month_day_parse_and_translate()
    test_legacy_pub_year_still_parses()
    test_series_index_leading_zeros_stripped()
    test_series_index_leading_zeros_stripped_multiple()
    test_series_index_decimal_leading_zero_stripped_fraction_preserved()
    test_series_index_plain_decimal_still_parses()
    test_series_index_zero_alone_not_stripped_to_empty()
    test_series_index_zero_point_something_preserved()
    test_series_index_no_leading_zero_unaffected()
    print("\nALL FILENAME PARSER TESTS PASSED")
