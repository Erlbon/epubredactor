"""Tests for core/description_html.py."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from core.description_html import has_html_markup, strip_html  # noqa: E402


def test_plain_text_untouched():
    text = "Just a plain description, no markup at all."
    assert strip_html(text) == text
    print("PASS: plain text with no '<' is returned completely unchanged")


def test_empty_string():
    assert strip_html("") == ""
    print("PASS: empty string returns empty string")


def test_compact_paragraphs_get_separated():
    # Real-world descriptions are often written with zero whitespace
    # between tags -- naive text_content() would mash these together
    # into "Paragraph AParagraph BParagraph C".
    text = "<p>Paragraph A</p><p>Paragraph B</p><p>Paragraph C</p>"
    assert strip_html(text) == "Paragraph A\n\nParagraph B\n\nParagraph C"
    print("PASS: compact (no whitespace between tags) paragraphs are still separated")


def test_matches_the_reported_bug_example():
    # The exact shape that triggered this feature: pretty-printed HTML
    # with empty <p></p> spacer paragraphs that should be dropped.
    text = (
        "<div>\n<p>1942. The Second World War.</p>\n<p></p>\n"
        "<p>The Axis reigns supreme.</p>\n<p></p>\n<p>Germany advances.</p>"
    )
    assert strip_html(text) == (
        "1942. The Second World War.\n\nThe Axis reigns supreme.\n\nGermany advances."
    )
    print("PASS: matches the exact real-world example that reported this bug")


def test_inline_formatting_stays_inline():
    text = "<p>A <b>bold</b> word and <i>italic</i> too.</p>"
    assert strip_html(text) == "A bold word and italic too."
    print("PASS: inline tags (b/i) are stripped without inserting a paragraph break")


def test_entities_decoded():
    text = "<p>Tom &amp; Jerry&#39;s adventure &lt;fun&gt;</p>"
    assert strip_html(text) == "Tom & Jerry's adventure <fun>"
    print("PASS: HTML entities are decoded, including numeric ones")


def test_stray_angle_bracket_not_mistaken_for_markup():
    text = "A book about 5 < 10 and other math facts."
    assert strip_html(text) == text
    print("PASS: a stray '<' used mathematically isn't treated as a broken tag")


def test_embedded_newlines_collapsed_within_a_paragraph():
    text = "<p>Line one\nLine two\nLine three</p>"
    assert strip_html(text) == "Line one Line two Line three"
    print("PASS: newlines inside a single paragraph's own text collapse to spaces")


def test_has_html_markup_true_for_real_html():
    assert has_html_markup("<p>Some text</p>")
    print("PASS: has_html_markup is True for a description with real tags")


def test_has_html_markup_false_for_plain_text():
    assert not has_html_markup("Just plain text.")
    print("PASS: has_html_markup is False for plain text")


def test_has_html_markup_false_for_empty():
    assert not has_html_markup("")
    print("PASS: has_html_markup is False for an empty string")


def test_has_html_markup_false_when_stripping_would_be_a_noop():
    # Malformed/incomplete markup that lxml can't actually resolve into
    # anything different from the original shouldn't be flagged --
    # nothing would change if "stripped".
    text = "Unclosed tag and 5 < 10 mixed in"
    assert not has_html_markup(text)
    print("PASS: has_html_markup is False when stripping wouldn't actually change anything")


if __name__ == "__main__":
    test_plain_text_untouched()
    test_empty_string()
    test_compact_paragraphs_get_separated()
    test_matches_the_reported_bug_example()
    test_inline_formatting_stays_inline()
    test_entities_decoded()
    test_stray_angle_bracket_not_mistaken_for_markup()
    test_embedded_newlines_collapsed_within_a_paragraph()
    test_has_html_markup_true_for_real_html()
    test_has_html_markup_false_for_plain_text()
    test_has_html_markup_false_for_empty()
    test_has_html_markup_false_when_stripping_would_be_a_noop()
    print("\nALL DESCRIPTION HTML TESTS PASSED")
