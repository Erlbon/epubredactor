"""Tests for core/author_clean.py: every rule, safe vs review-only, idempotence,
the duplicate finder's use of author_key, and the review dialog's rows."""

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(__file__))

from core.author_clean import author_key, clean_authors  # noqa: E402
from core.epub_duplicates import normalize_author  # noqa: E402


def safe(authors, sort=()):
    return clean_authors(authors, sort, allow_review=False)


def full(authors, sort=()):
    return clean_authors(authors, sort, allow_review=True)


def rules(result):
    return {c.rule for c in result.changes}


def review_rules(result):
    return {c.rule for c in result.review}


# --- whitespace / punctuation ----------------------------------------------------


def test_whitespace_is_collapsed():
    r = safe(["  Jane   Doe  "], ["Doe,   Jane"])
    assert r.authors == ["Jane Doe"] and r.author_sort == ["Doe, Jane"]
    assert "whitespace" in rules(r)


def test_stray_punctuation_and_comma_spacing():
    assert safe(["Jane Doe,"]).authors == ["Jane Doe"]
    assert safe(["Jane Doe."]).authors == ["Jane Doe"]
    assert safe(["Doe ,Jane"]).authors == ["Jane Doe"]
    assert "punctuation" in rules(safe(["Doe,Jane"]))
    # a period that belongs to the name stays
    assert safe(["Martin Luther King Jr."]).authors == ["Martin Luther King Jr."]
    assert safe(["Ursula K."]).authors == ["Ursula K."]


# --- initials ---------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["J.R.R.Tolkien", "J.R.R. Tolkien", "J R R Tolkien", "J. R. R. Tolkien"])
def test_initials_are_spaced_and_dotted(raw):
    r = safe([raw])
    assert r.authors == ["J. R. R. Tolkien"]
    assert r.author_sort == ["Tolkien, J. R. R."]


def test_initials_in_the_middle_and_hyphenated():
    assert safe(["George R.R. Martin"]).authors == ["George R. R. Martin"]
    assert safe(["Ursula K Le Guin"]).authors == ["Ursula K. Le Guin"]
    assert safe(["J.-P. Sartre"]).authors == ["J.-P. Sartre"]


def test_all_caps_run_of_initials_is_review_only():
    s, f = safe(["JRR Tolkien"]), full(["JRR Tolkien"])
    assert s.authors == ["JRR Tolkien"] and "initials_caps" in review_rules(s)
    assert f.authors == ["J. R. R. Tolkien"] and "initials_caps" in rules(f)


# --- Last, First vs First Last -------------------------------------------------------


def test_last_first_display_becomes_first_last():
    r = safe(["Tolkien, J.R.R."], ["Tolkien, J.R.R."])
    assert r.authors == ["J. R. R. Tolkien"] and r.author_sort == ["Tolkien, J. R. R."]
    assert "flip" in rules(r)
    assert safe(["Smith, John, Jr."]).authors == ["John Smith Jr."]
    assert safe(["Smith, John, Jr."]).author_sort == ["Smith, John, Jr."]


def test_a_single_last_first_is_never_split():
    r = safe(["Le Guin, Ursula K."])
    assert r.authors == ["Ursula K. Le Guin"] and "split" not in rules(r)
    assert safe(["van Gogh, Vincent"]).author_sort == ["van Gogh, Vincent"]
    assert safe(["García Márquez, Gabriel"]).author_sort == ["García Márquez, Gabriel"]


# --- sort-form values in the Authors box become the Author Sort ------------------------------


@pytest.mark.parametrize("raw,display,sort", [
    ("Tolkien, J.R.R.", "J. R. R. Tolkien", "Tolkien, J. R. R."),
    ("van Gogh, Vincent", "Vincent van Gogh", "van Gogh, Vincent"),
    ("King, Martin Luther, Jr.", "Martin Luther King Jr.", "King, Martin Luther, Jr."),
    ("King, Martin Luther, Jr", "Martin Luther King Jr.", "King, Martin Luther, Jr."),
    ("Le Guin, Ursula K.", "Ursula K. Le Guin", "Le Guin, Ursula K."),
    ("TOLKIEN, J.R.R.", "J. R. R. Tolkien", "Tolkien, J. R. R."),
])
def test_sort_form_in_authors_moves_to_the_sort(raw, display, sort):
    r = safe([raw])
    assert r.authors == [display] and r.author_sort == [sort]
    assert "sort_from_author" in rules(r) and not r.review
    assert not safe(r.authors, r.author_sort).changed  # idempotent


def test_sort_form_agreeing_with_existing_sort_is_kept_and_tidied():
    r = safe(["Tolkien, J. R. R."], ["Tolkien, J.R.R."])
    assert r.authors == ["J. R. R. Tolkien"] and r.author_sort == ["Tolkien, J. R. R."]
    assert "sort_from_author" not in rules(r) and not r.review
    r = safe(["Tolkien, J. R. R."], ["Tolkien, John Ronald Reuel"])  # richer sort wins, no review
    assert r.author_sort == ["Tolkien, John Ronald Reuel"] and not r.review


def test_several_sort_form_authors_each_move_to_the_sort():
    for raw in ("Tolkien, J.R.R.; King, Stephen", "Tolkien, J.R.R. & King, Stephen"):
        r = safe([raw])
        assert r.authors == ["J. R. R. Tolkien", "Stephen King"]
        assert r.author_sort == ["Tolkien, J. R. R.", "King, Stephen"]
    r = safe(["Tolkien, J.R.R.", "King, Stephen"])
    assert r.author_sort == ["Tolkien, J. R. R.", "King, Stephen"]


def test_a_different_existing_sort_is_kept_and_reviewed():
    s, f = safe(["Tolkien, J. R. R."], ["Foo, Bar"]), full(["Tolkien, J. R. R."], ["Foo, Bar"])
    assert s.authors == ["J. R. R. Tolkien"] and s.author_sort == ["Foo, Bar"]
    assert "sort_mismatch" in review_rules(s) and s.flags
    assert f.author_sort == ["Tolkien, J. R. R."]


def test_comma_lists_are_not_taken_as_sort_forms():
    for raw in ("Neil Gaiman, Terry Pratchett", "Neil Gaiman, Terry Pratchett, Stephen King"):
        r = safe([raw])
        assert r.authors == [raw] and r.author_sort == [] and "sort_from_author" not in rules(r)
        assert "list_split" in review_rules(r) or r.flags


# --- splitting ---------------------------------------------------------------------------


def test_split_on_ampersand_and_and_semicolon():
    assert safe(["Terry Pratchett & Neil Gaiman"]).authors == ["Terry Pratchett", "Neil Gaiman"]
    assert safe(["Terry Pratchett and Neil Gaiman"]).authors == ["Terry Pratchett", "Neil Gaiman"]
    assert safe(["Terry Pratchett; Neil Gaiman"]).authors == ["Terry Pratchett", "Neil Gaiman"]
    assert safe(["Pratchett, Terry & Gaiman, Neil"]).authors == ["Terry Pratchett", "Neil Gaiman"]
    assert "split" in rules(safe(["Terry Pratchett & Neil Gaiman"]))


def test_split_cuts_the_file_as_the_same_way():
    r = safe(["Terry Pratchett & Neil Gaiman"], ["Pratchett, Terry & Gaiman, Neil"])
    assert r.author_sort == ["Pratchett, Terry", "Gaiman, Neil"]
    r = safe(["Terry Pratchett & Neil Gaiman"], ["Pratchett, Terry"])  # does not fit: regenerated
    assert r.author_sort == ["Pratchett, Terry", "Gaiman, Neil"]


def test_a_single_word_part_makes_the_split_review_only():
    s, f = safe(["Mary and John Smith"]), full(["Mary and John Smith"])
    assert s.authors == ["Mary and John Smith"] and "split" in review_rules(s)
    assert f.authors == ["Mary", "John Smith"]


def test_corporate_authors_are_not_split_or_touched():
    for name in ("Simon & Schuster", "Penguin Books & Co", "Oxford University Press", "Acme Inc."):
        r = safe([name])
        assert r.authors == [name] and r.author_sort == [] and not r.changed, name
    assert full(["Penguin Books & Co"]).authors == ["Penguin Books & Co"]


def test_comma_list_of_full_names_is_review_only_and_flagged():
    s, f = safe(["Neil Gaiman, Terry Pratchett"]), full(["Neil Gaiman, Terry Pratchett"])
    assert s.authors == ["Neil Gaiman, Terry Pratchett"]
    assert "list_split" in review_rules(s) and s.flags
    assert f.authors == ["Neil Gaiman", "Terry Pratchett"]


# --- roles and junk -------------------------------------------------------------------------


@pytest.mark.parametrize("raw", [
    "Jane Doe (Editor)", "Jane Doe [Translator]", "Jane Doe (ed.)", "Jane Doe, editor", "Jane Doe - Translator",
    "Jane Doe (ed. and trans.)", "Translated by Jane Doe", "By Jane Doe", "Jane Doe et al.", "Jane Doe, et al.",
    "Jane Doe and others", "Jane Doe (1900-1980)", "Jane Doe, 1900-", "Jane Doe (b. 1950)",
])
def test_role_suffixes_and_junk_are_removed(raw):
    r = safe([raw])
    assert r.authors == ["Jane Doe"], raw
    assert "junk" in rules(r)


def test_inverted_name_with_role_and_dates():
    assert safe(["Tolkien, J. R. R. (1892-1973)"]).authors == ["J. R. R. Tolkien"]
    assert safe(["Doe, Jane, ed."]).authors == ["Jane Doe"]


def test_role_only_and_et_al_entries_are_dropped_when_authors_remain():
    r = safe(["Translator", "Jane Doe", "et al."])
    assert r.authors == ["Jane Doe"] and "junk" in rules(r)


def test_only_junk_is_left_alone_and_flagged():
    r = safe(["Translator"])
    assert r.authors == ["Translator"] and r.flags and not r.changed


def test_honorifics_are_review_only():
    s, f = safe(["Dr. Jane Doe"]), full(["Dr. Jane Doe"])
    assert s.authors == ["Dr. Jane Doe"] and "honorific" in review_rules(s) and s.flags
    assert f.authors == ["Jane Doe"]
    assert full(["Jane Doe, PhD"]).authors == ["Jane Doe"]


# --- case ------------------------------------------------------------------------------------


def test_all_caps_plain_name_is_fixed_safely():
    r = safe(["STEPHEN KING"])
    assert r.authors == ["Stephen King"] and "caps" in rules(r)
    assert safe(["J.K. ROWLING"]).authors == ["J. K. Rowling"]


def test_tricky_or_lowercase_case_fixes_are_review_only():
    s, f = safe(["RONALD MCDONALD"]), full(["RONALD MCDONALD"])
    assert s.authors == ["RONALD MCDONALD"] and "caps" in review_rules(s)
    assert f.authors == ["Ronald McDonald"] or f.authors == ["Ronald Mcdonald"]
    assert safe(["bell hooks"]).authors == ["bell hooks"] and "caps" in review_rules(safe(["bell hooks"]))
    assert full(["bell hooks"]).authors == ["Bell Hooks"]


def test_mixed_case_names_are_left_alone():
    for name in ("Ian McEwan", "Don DeLillo", "Ursula K. Le Guin"):
        assert safe([name]).authors == [name]


# --- suffixes, particles, mononyms ------------------------------------------------------------------


def test_suffix_gets_its_period_and_sorts_last():
    r = safe(["Martin Luther King Jr"])
    assert r.authors == ["Martin Luther King Jr."] and r.author_sort == ["King, Martin Luther, Jr."]
    assert safe(["Henry Ford iii"]).authors == ["Henry Ford III"]
    assert safe(["Henry Ford III"]).author_sort == ["Ford, Henry, III"]


def test_particles_stay_with_the_surname():
    assert safe(["Ludwig van Beethoven"]).author_sort == ["van Beethoven, Ludwig"]
    assert safe(["Johan van der Berg"]).author_sort == ["van der Berg, Johan"]
    assert safe(["Ursula K. Le Guin"]).author_sort == ["Le Guin, Ursula K."]
    assert safe(["Van Morrison"]).author_sort == ["Morrison, Van"]


def test_mononyms_sort_as_themselves():
    r = safe(["Voltaire"])
    assert r.authors == ["Voltaire"] and r.author_sort == ["Voltaire"]


def test_placeholders_and_non_latin_names_are_untouched():
    for name in ("Anonymous", "Various", "Unknown", "村上春樹", "สมชาย"):
        r = safe([name])
        assert r.authors == [name] and not r.changed, name


def test_unusual_characters_are_left_alone_and_flagged():
    r = safe(["J. K. Rowling (Robert Galbraith)"], [])
    assert r.authors == ["J. K. Rowling (Robert Galbraith)"] and r.flags


# --- duplicates ----------------------------------------------------------------------------------


def test_duplicate_authors_are_dropped():
    r = safe(["John Smith", "Smith, John", "JOHN SMITH", "Jane Doe"])
    assert r.authors == ["John Smith", "Jane Doe"] and "duplicate" in rules(r)


def test_initial_spelling_variants_are_duplicates():
    assert safe(["J.R.R. Tolkien", "J. R. R. Tolkien"]).authors == ["J. R. R. Tolkien"]


def test_different_people_are_not_duplicates():
    assert safe(["John Smith", "Jane Smith"]).authors == ["John Smith", "Jane Smith"]
    assert safe(["John Smith", "John Smith Jr."]).authors == ["John Smith", "John Smith Jr."]


# --- author sort ---------------------------------------------------------------------------------------


def test_missing_sort_is_generated_for_every_author():
    r = safe(["Terry Pratchett", "Neil Gaiman"], ["Pratchett, Terry"])
    assert r.author_sort == ["Pratchett, Terry", "Gaiman, Neil"] and "sort_fill" in rules(r)


def test_sloppy_sort_is_tidied():
    r = safe(["J. R. R. Tolkien"], ["Tolkien,J.R.R."])
    assert r.author_sort == ["Tolkien, J. R. R."] and "sort_format" in rules(r)


def test_sort_that_is_just_the_display_name_is_inverted():
    r = safe(["John Smith"], ["John Smith"])
    assert r.author_sort == ["Smith, John"] and "sort_not_inverted" in rules(r)


def test_a_deliberate_surname_choice_in_the_sort_is_kept():
    r = safe(["Gabriel García Márquez"], ["García Márquez, Gabriel"])
    assert not r.changed
    r = safe(["J. R. R. Tolkien"], ["Tolkien, John Ronald Reuel"])  # richer than the author: fine
    assert not r.changed


def test_a_sort_that_disagrees_is_flagged_and_replaced_only_in_review():
    s, f = safe(["John Smith"], ["Doe, Jane"]), full(["John Smith"], ["Doe, Jane"])
    assert s.author_sort == ["Doe, Jane"] and "sort_mismatch" in review_rules(s) and s.flags
    assert f.author_sort == ["Smith, John"] and "sort_mismatch" in rules(f)
    assert "sort_mismatch" in review_rules(safe(["John Smith"], ["Smith, Jon"]))


def test_sort_entries_without_an_author_are_dropped_only_in_review():
    s, f = safe(["Jane Doe"], ["Doe, Jane", "Smith, John"]), full(["Jane Doe"], ["Doe, Jane", "Smith, John"])
    assert s.author_sort == ["Doe, Jane", "Smith, John"] and "sort_extra" in review_rules(s)
    assert f.author_sort == ["Doe, Jane"]


def test_role_junk_in_the_sort_is_removed():
    assert safe(["Jane Doe"], ["Doe, Jane (Editor)"]).author_sort == ["Doe, Jane"]


# --- cross-cutting ------------------------------------------------------------------------------------------


MESSES = [
    (["J.R.R.Tolkien"], []), (["Tolkien, J.R.R. (Editor)"], ["Tolkien, J.R.R."]),
    (["Pratchett & Gaiman"], []), (["Terry Pratchett & Neil Gaiman et al."], []),
    (["STEPHEN KING", "stephen king"], []), (["Simon & Schuster"], []), (["Dr. Seuss"], ["Seuss"]),
    (["Mary and John Smith"], []), (["Neil Gaiman, Terry Pratchett"], []), (["John Smith"], ["Doe, Jane"]),
    (["Jane Doe"], ["Doe, Jane", "Extra, Name"]), (["bell hooks"], []), (["Anonymous", "Jane  Doe"], []),
    (["Henry Ford III", "ford, henry iii"], []),
]


@pytest.mark.parametrize("authors,sort", MESSES)
@pytest.mark.parametrize("allow_review", [False, True])
def test_cleaning_is_idempotent(authors, sort, allow_review):
    once = clean_authors(authors, sort, allow_review)
    twice = clean_authors(once.authors, once.author_sort, allow_review)
    assert not twice.changed, (once.authors, once.author_sort, twice.summary())


def test_clean_input_reports_nothing():
    r = safe(["J. R. R. Tolkien", "Ursula K. Le Guin"], ["Tolkien, J. R. R.", "Le Guin, Ursula K."])
    assert not r.changed and not r.changes and not r.review and not r.flags and not r.needs_review


def test_safe_mode_never_applies_a_review_rule():
    for authors, sort in MESSES:
        r = safe(authors, sort)
        assert all(c.safe for c in r.changes), (authors, r.summary())


# --- author_key and the duplicate finder -----------------------------------------------------------------------


def test_author_key_folds_initial_spellings():
    keys = {author_key(n) for n in ("JRR Tolkien", "J.R.R. Tolkien", "J. R. R. Tolkien", "Tolkien, J.R.R.",
                                    "j r r TOLKIEN", "J.R.R.Tolkien")}
    assert keys == {"j r r tolkien"}


def test_author_key_keeps_different_people_apart():
    assert author_key("John Smith") != author_key("Jane Smith")
    assert author_key("John Smith") != author_key("John Smith Jr.")
    assert author_key("STEPHEN KING") == author_key("Stephen King")
    assert author_key("") == ""


def test_duplicates_finder_matches_jrr_with_j_r_r():
    assert normalize_author(["JRR Tolkien"]) == normalize_author(["J.R.R. Tolkien"]) != ""
    assert normalize_author([], ["Tolkien, J.R.R."]) == normalize_author(["JRR Tolkien"])
