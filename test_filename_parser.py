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


def test_missing_space_now_tolerated():
    """Spaces don't count as meaningful characters of their own -- a
    space in the pattern matches a space in the filename, but also NO
    space at all, not just "one or more." Superseded the earlier,
    stricter design (a missing space used to be rejected outright) at
    the user's explicit request: real filenames are inconsistent enough
    about spacing that treating a missing space as a hard failure was
    more often an annoyance than a useful safeguard."""
    result = parse_filename("Jane Doe -My Book", "%authors% - %title%")
    assert result is not None
    assert result["authors"] == "Jane Doe"
    assert result["title"] == "My Book"
    print("PASS: a missing space where the pattern expects one is now tolerated, not rejected")


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


def test_series_index_bounded_to_0_999_distinct_from_year():
    # A series index is 1-3 digits, never 4 -- so it can never be
    # confused with a 4-digit year purely by shape. Tested against the
    # field alone (anchored both ends) rather than inside a bigger
    # pattern, since a neighboring ".+?" field can otherwise backtrack
    # to absorb a stray digit and mask what the field's own regex would
    # or wouldn't accept on its own.
    assert parse_filename("999", "%series_index%") == {"series_index": "999"}
    assert parse_filename("2020", "%series_index%") is None
    print("PASS: series_index matches up to 3 digits (0-999) but not a bare 4-digit number like a year")


# ----------------------------------------------------------------------
# Optional [...] bracket segments (the "standard template")
# ----------------------------------------------------------------------

STANDARD_TEMPLATE = "%authors% - [%series% %series_index%] - %title% (%year%)"


def test_standard_template_matches_with_series():
    # The user's own real example: author, bracketed series+index, title, year.
    parsed = parse_filename(
        "Patty Jansen - [Ambassador 10] - Lost Forest Secrets (2020)", STANDARD_TEMPLATE
    )
    assert parsed == {
        "authors": "Patty Jansen", "series": "Ambassador", "series_index": "10",
        "title": "Lost Forest Secrets", "year": "2020",
    }, parsed
    print("PASS: the standard template matches a real author/series/title/year filename")


def test_standard_template_matches_without_series():
    # No bracket section at all for a standalone book -- must still
    # match, since render_filename() would have produced exactly this
    # (collapsed) shape for a book with no series. The bracket's own
    # fields come back as empty strings (an unmatched optional group),
    # same as any other field with nothing to capture -- downstream
    # code (see FilenameParseDialog._refresh_preview) already filters
    # those out before offering them for Apply.
    parsed = parse_filename("Richard Swan - The Justice of Kings (2022)", STANDARD_TEMPLATE)
    assert parsed["authors"] == "Richard Swan"
    assert parsed["title"] == "The Justice of Kings"
    assert parsed["year"] == "2022"
    assert not parsed["series"]
    assert not parsed["series_index"]
    print("PASS: the standard template also matches a standalone book with no bracketed series section")


def test_bracket_roundtrip_through_render_filename():
    m = EpubMetadata()
    m.authors = ["Patty Jansen"]
    m.series = "Ambassador"
    m.series_index = "10"
    m.title = "Lost Forest Secrets"
    m.pub_year = "2020"
    pattern = "%authors% - [%series% %series_index%] - %title% (%year%)"
    filename = render_filename(m, pattern)
    assert filename == "Patty Jansen - [Ambassador 10] - Lost Forest Secrets (2020)", filename
    parsed = parse_filename(filename, pattern)
    assert parsed["authors"] == "Patty Jansen"
    assert parsed["series"] == "Ambassador"
    assert parsed["series_index"] == "10"
    assert parsed["title"] == "Lost Forest Secrets"
    assert parsed["year"] == "2020"

    m2 = EpubMetadata()
    m2.authors = ["Richard Swan"]
    m2.title = "The Justice of Kings"
    m2.pub_year = "2022"
    filename2 = render_filename(m2, pattern)
    assert filename2 == "Richard Swan - The Justice of Kings (2022)", filename2
    parsed2 = parse_filename(filename2, pattern)
    assert parsed2["authors"] == "Richard Swan"
    assert parsed2["title"] == "The Justice of Kings"
    assert parsed2["year"] == "2022"
    assert not parsed2["series"]
    print("PASS: render_filename() -> parse_filename() round trip works for both the with-series "
          "and without-series shapes of the standard template")


def test_bracket_with_literal_text_still_required_as_literal():
    result = parse_filename("Book [notes]", "%title% [notes]")
    assert result == {"title": "Book"}, result
    assert parse_filename("Book", "%title% [notes]") is None
    print("PASS: a [...] segment with no field inside stays required literal text when parsing too")


def test_parens_and_braces_are_optional_wrappers_too():
    # Not just [...] -- (...) and {...} work exactly the same way, so
    # SUGGESTED_PATTERNS' own "(%year%)" is optional without needing to
    # be rewritten with brackets.
    pattern = "%title% (%year%)"
    assert parse_filename("Dune (1965)", pattern) == {"title": "Dune", "year": "1965"}
    assert parse_filename("Dune", pattern) == {"title": "Dune", "year": ""}
    pattern_braces = "%title% {%year%}"
    assert parse_filename("Dune {1965}", pattern_braces) == {"title": "Dune", "year": "1965"}
    assert parse_filename("Dune", pattern_braces) == {"title": "Dune", "year": ""}
    print("PASS: (...) and {...} are optional wrappers exactly like [...]")


def test_bare_field_with_no_wrapper_stays_required():
    # Deliberate: a field with NO wrapper of its own is always required,
    # even a distinctively-shaped one like %year% -- see _compile_tokens()'s
    # docstring for why making a bare field optional turned out to be
    # unsafe next to a greedy neighbor.
    result = parse_filename("Dune", "%title% %year%")
    assert result is None
    print("PASS: a bare (unwrapped) field with no match in the filename fails, by design -- "
          "wrap it to make it optional")


# ----------------------------------------------------------------------
# %year%/%month% smarter regex
# ----------------------------------------------------------------------

def test_year_matches_four_digits():
    parsed = parse_filename("2020 - Title", "%year% - %title%")
    assert parsed == {"year": "2020", "title": "Title"}, parsed
    print("PASS: a 4-digit year is captured as a whole, not just its first 2 digits")


def test_year_matches_two_digits():
    parsed = parse_filename("87 - Title", "%year% - %title%")
    assert parsed == {"year": "87", "title": "Title"}, parsed
    print("PASS: a 2-digit year is also accepted")


def test_year_does_not_swallow_extra_digits():
    # A 5+ digit run isn't a plausible year -- must fail to match rather
    # than silently accept the first 4 digits and leave one dangling.
    assert parse_filename("20201 - Title", "%year% - %title%") is None
    print("PASS: a year field doesn't loosely match a longer run of digits")


def test_month_name_normalized_to_number():
    parsed = parse_filename("2020-Jan - Title", "%year%-%month% - %title%")
    assert parsed["month"] == "1", parsed
    print("PASS: a text month name (\"Jan\") is normalized to its plain digit form")


def test_month_full_name_normalized_to_number():
    parsed = parse_filename("2020-September - Title", "%year%-%month% - %title%")
    assert parsed["month"] == "9", parsed
    print("PASS: a full month name (\"September\") is also normalized correctly")


def test_month_digit_form_unaffected():
    parsed = parse_filename("2020-07 - Title", "%year%-%month% - %title%")
    assert parsed["month"] == "07", parsed
    print("PASS: a digit-form month is left exactly as captured, not stripped or padded")


def test_month_year_either_order():
    # No special-case code needed for this -- it falls straight out of
    # the pattern the caller writes, in whichever order they use it.
    parsed_my = parse_filename("Jan-2020 - Title", "%month%-%year% - %title%")
    assert parsed_my == {"month": "1", "year": "2020", "title": "Title"}, parsed_my
    parsed_ym = parse_filename("2020-Jan - Title", "%year%-%month% - %title%")
    assert parsed_ym == {"month": "1", "year": "2020", "title": "Title"}, parsed_ym
    print("PASS: %month%-%year% and %year%-%month% both work, in whichever order the pattern uses")


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
    test_missing_space_now_tolerated()
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
    test_series_index_bounded_to_0_999_distinct_from_year()
    test_standard_template_matches_with_series()
    test_standard_template_matches_without_series()
    test_bracket_roundtrip_through_render_filename()
    test_bracket_with_literal_text_still_required_as_literal()
    test_parens_and_braces_are_optional_wrappers_too()
    test_bare_field_with_no_wrapper_stays_required()
    test_year_matches_four_digits()
    test_year_matches_two_digits()
    test_year_does_not_swallow_extra_digits()
    test_month_name_normalized_to_number()
    test_month_full_name_normalized_to_number()
    test_month_digit_form_unaffected()
    test_month_year_either_order()
    print("\nALL FILENAME PARSER TESTS PASSED")
