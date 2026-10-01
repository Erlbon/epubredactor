"""Tests for Repair > Find Duplicates' finder (core/epub_duplicates.py): each
tier on synthetic EPUBs, what must NOT match (series volumes, an omnibus
with a partial title overlap), name normalisation, combined signals, and
the dismissal behaviour of the shared store with the groups it makes."""

import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(__file__))

from core.epub_duplicates import (  # noqa: E402
    COLUMNS,
    find_duplicate_groups,
    normalize_author,
    normalize_title,
    read_identity,
)
from core.epub_metadata import EpubBook  # noqa: E402
from redactor_common.core.duplicates import (  # noqa: E402
    TIER_IDENTICAL,
    TIER_POSSIBLE,
    TIER_WEAK,
    JsonDismissStore,
)

CONTAINER = (
    '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
    '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
    "</rootfiles></container>"
)


def make_epub(folder, name, *, title="Book", authors=("Jane Doe",), isbn="", body="Hello.", series="", series_index=""):
    """A small valid EPUB; `body` is the only content, so equal bodies mean
    equal content however the OPF metadata differs."""
    md = ['<dc:identifier id="BookId">urn:uuid:1234</dc:identifier>', f"<dc:title>{title}</dc:title>",
          "<dc:language>en</dc:language>"]
    md += [f'<dc:creator opf:role="aut">{a}</dc:creator>' for a in authors]
    if isbn:
        md.append(f'<dc:identifier opf:scheme="ISBN">{isbn}</dc:identifier>')
    if series:
        md.append(f'<meta name="calibre:series" content="{series}"/>')
        md.append(f'<meta name="calibre:series_index" content="{series_index}"/>')
    opf = (
        '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="BookId">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">'
        + "".join(md) + '</metadata><manifest><item id="p0" href="ch1.xhtml" media-type="application/xhtml+xml"/>'
        '</manifest><spine><itemref idref="p0"/></spine></package>'
    )
    path = os.path.join(str(folder), name)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/ch1.xhtml", f"<html><body><p>{body}</p></body></html>")
    return path


def load(*paths):
    books = [EpubBook(p) for p in paths]
    assert all(not b.load_error for b in books)
    return books


def names(group):
    return sorted(os.path.basename(m.path) for m in group.members)


# --- normalisation ------------------------------------------------------------

def test_title_normalisation_folds_case_accents_punctuation_and_article():
    assert normalize_title("The Hobbit") == normalize_title("hobbit!") == "hobbit"
    assert normalize_title("Amélie: A Story") == normalize_title("amelie - a story")
    # Volume numbers are part of the title.
    assert normalize_title("Dune 1") != normalize_title("Dune 2")
    assert normalize_title("The") == "the"   # nothing left over: keep it


def test_author_normalisation_handles_last_first_and_order():
    assert normalize_author(["Tolkien, J.R.R."]) == normalize_author(["J.R.R. Tolkien"]) != ""
    assert normalize_author(["j r r TOLKIEN"]) == normalize_author(["J.R.R. Tolkien"])
    assert normalize_author(["Smith, John, Jr."]) == normalize_author(["John Smith, Jr."])
    # Only the first author counts; author sort is the fallback.
    assert normalize_author(["A B", "C D"]) == normalize_author(["A B"])
    assert normalize_author([], ["Doe, Jane"]) == normalize_author(["Jane Doe"])
    assert normalize_author([]) == ""


# --- tiers ---------------------------------------------------------------------

def test_identical_content_with_different_metadata(tmp_path):
    a = make_epub(tmp_path, "a.epub", title="One", authors=("A A",), isbn="9780306406157")
    b = make_epub(tmp_path, "b.epub", title="Totally Different", authors=("Z Z",))
    (group,) = find_duplicate_groups(load(a, b))
    assert group.tier == TIER_IDENTICAL
    assert names(group) == ["a.epub", "b.epub"]
    assert "only the metadata differs" in group.reason
    assert all(m.fingerprint for m in group.members)
    # Fields for every column the dialog shows.
    assert set(COLUMNS[i][0] for i in range(len(COLUMNS))) <= set(group.members[0].fields)


def test_byte_identical_copies_say_so(tmp_path):
    a = make_epub(tmp_path, "a.epub")
    b = os.path.join(str(tmp_path), "copy.epub")
    with open(a, "rb") as src, open(b, "wb") as dst:
        dst.write(src.read())
    (group,) = find_duplicate_groups(load(a, b))
    assert group.tier == TIER_IDENTICAL
    assert group.reason.startswith("identical files")


def test_same_title_and_author_different_edition(tmp_path):
    a = make_epub(tmp_path, "a.epub", title="The Hobbit", authors=("Tolkien, J.R.R.",), body="first edition")
    b = make_epub(tmp_path, "b.epub", title="hobbit", authors=("J.R.R. Tolkien",), body="second edition")
    (group,) = find_duplicate_groups(load(a, b))
    assert group.tier == TIER_POSSIBLE
    assert group.reason == "same title and author — may be a different edition"


def test_same_isbn_different_title_is_weak(tmp_path):
    a = make_epub(tmp_path, "a.epub", title="Alpha", authors=("A A",), isbn="978-0-306-40615-7", body="x")
    b = make_epub(tmp_path, "b.epub", title="Beta", authors=("B B",), isbn="0306406152", body="y")  # ISBN-10 form
    (group,) = find_duplicate_groups(load(a, b))
    assert group.tier == TIER_WEAK
    assert "same ISBN" in group.reason and "different title" in group.reason
    assert "may be wrong" in group.reason


def test_invalid_isbn_is_ignored(tmp_path):
    a = make_epub(tmp_path, "a.epub", title="Alpha", isbn="9780306406158", body="x")   # bad check digit
    b = make_epub(tmp_path, "b.epub", title="Beta", isbn="9780306406158", body="y")
    assert find_duplicate_groups(load(a, b)) == []


# --- non-matches -----------------------------------------------------------------

def test_series_volumes_are_not_duplicates(tmp_path):
    a = make_epub(tmp_path, "a.epub", title="Dune 1", authors=("Frank Herbert",), body="x")
    b = make_epub(tmp_path, "b.epub", title="Dune 2", authors=("Frank Herbert",), body="y")
    c = make_epub(tmp_path, "c.epub", title="Dune", authors=("Frank Herbert",), body="z")
    d = make_epub(tmp_path, "d.epub", title="Dune Messiah", authors=("Frank Herbert",), body="w")
    assert find_duplicate_groups(load(a, b, c, d)) == []


def test_omnibus_with_partial_title_overlap_is_not_matched(tmp_path):
    a = make_epub(tmp_path, "a.epub", title="The Fellowship of the Ring", authors=("J.R.R. Tolkien",), body="x")
    b = make_epub(tmp_path, "b.epub", title="The Lord of the Rings: Fellowship of the Ring and The Two Towers",
                  authors=("J.R.R. Tolkien",), body="y")
    assert find_duplicate_groups(load(a, b)) == []


def test_empty_titles_and_missing_authors_are_ignored(tmp_path):
    a = make_epub(tmp_path, "a.epub", title="", authors=("A A",), body="x")
    b = make_epub(tmp_path, "b.epub", title="", authors=("A A",), body="y")
    c = make_epub(tmp_path, "c.epub", title="Same", authors=(), body="x2")
    d = make_epub(tmp_path, "d.epub", title="Same", authors=(), body="y2")
    assert find_duplicate_groups(load(a, b, c, d)) == []


def test_unreadable_book_is_skipped(tmp_path):
    a = make_epub(tmp_path, "a.epub", title="T", body="x")
    b = make_epub(tmp_path, "b.epub", title="T", body="y")
    books = load(a, b)
    books[1].load_error = "broken"
    assert find_duplicate_groups(books) == []


# --- combining signals ---------------------------------------------------------------

def test_combined_signals_report_the_strongest_tier_with_all_reasons(tmp_path):
    # identical content AND same title/author AND same ISBN: ONE group.
    a = make_epub(tmp_path, "a.epub", title="Same", authors=("A A",), isbn="9780306406157")
    b = make_epub(tmp_path, "b.epub", title="Same", authors=("A A",), isbn="0-306-40615-2")
    (group,) = find_duplicate_groups(load(a, b))
    assert group.tier == TIER_IDENTICAL
    assert "same title and author" in group.reason and "same ISBN 9780306406157" in group.reason


def test_isbn_agreement_is_added_to_the_title_group_not_a_second_group(tmp_path):
    a = make_epub(tmp_path, "a.epub", title="Same", authors=("A A",), isbn="9780306406157", body="x")
    b = make_epub(tmp_path, "b.epub", title="Same", authors=("A A",), isbn="9780306406157", body="y")
    (group,) = find_duplicate_groups(load(a, b))
    assert group.tier == TIER_POSSIBLE
    assert "may be a different edition" in group.reason and "same ISBN 9780306406157" in group.reason


def test_identical_group_hides_the_weaker_group_inside_it(tmp_path):
    a = make_epub(tmp_path, "a.epub", title="One", authors=("A A",), isbn="9780306406157")
    b = make_epub(tmp_path, "b.epub", title="Two", authors=("B B",), isbn="9780306406157")
    c = make_epub(tmp_path, "c.epub", title="Three", authors=("C C",), isbn="9780306406157")
    groups = find_duplicate_groups(load(a, b, c))
    assert [g.tier for g in groups] == [TIER_IDENTICAL]   # the ISBN group is the same three books
    assert len(groups[0].members) == 3


def test_partly_overlapping_groups_stay_separate(tmp_path):
    a = make_epub(tmp_path, "a.epub", title="Same", authors=("A A",), body="x")
    b = make_epub(tmp_path, "b.epub", title="Same", authors=("A A",), body="x")           # identical to a
    c = make_epub(tmp_path, "c.epub", title="Same", authors=("A A",), body="other")       # same title only
    tiers = {g.tier: names(g) for g in find_duplicate_groups(load(a, b, c))}
    assert tiers == {TIER_IDENTICAL: ["a.epub", "b.epub"], TIER_POSSIBLE: ["a.epub", "b.epub", "c.epub"]}


# --- progress, cancel, identity ----------------------------------------------------------

def test_progress_and_cancel(tmp_path):
    a = make_epub(tmp_path, "a.epub")
    b = make_epub(tmp_path, "b.epub")
    seen = []
    find_duplicate_groups(load(a, b), progress=lambda done, total, label: seen.append((done, total)))
    assert seen == [(1, 2), (2, 2)]
    assert find_duplicate_groups(load(a, b), cancelled=lambda: True) == []


def test_read_identity_survives_rename_and_ignores_the_opf(tmp_path):
    a = make_epub(tmp_path, "a.epub", title="One")
    b = make_epub(tmp_path, "renamed.epub", title="Two")
    fp_a, opf_a = read_identity(a, "OEBPS/content.opf")
    fp_b, opf_b = read_identity(b, "OEBPS/content.opf")
    assert fp_a == fp_b and fp_a and opf_a != opf_b
    assert read_identity(str(tmp_path / "missing.epub"), "OEBPS/content.opf") == ("", "")
    assert read_identity(a, "") == ("", "")


# --- dismissal with the groups this finder makes ---------------------------------------

def test_dismissal_persists_and_a_third_copy_brings_the_group_back(tmp_path):
    a = make_epub(tmp_path, "a.epub", title="Same", authors=("A A",), body="x")
    b = make_epub(tmp_path, "b.epub", title="Same", authors=("A A",), body="y")
    store_path = str(tmp_path / "dismissed.json")

    (group,) = find_duplicate_groups(load(a, b))
    JsonDismissStore(store_path).dismiss(group.identities)

    # A new run (a new store object on the same file) still hides it ...
    (again,) = find_duplicate_groups(load(a, b))
    assert JsonDismissStore(store_path).is_dismissed(again.identities)
    # ... also after a rename (the fingerprint is content, not the path) ...
    renamed = str(tmp_path / "renamed.epub")
    os.rename(a, renamed)
    (moved,) = find_duplicate_groups(load(renamed, b))
    assert JsonDismissStore(store_path).is_dismissed(moved.identities)
    # ... but a third copy makes it a different set, so it reappears.
    c = make_epub(tmp_path, "c.epub", title="Same", authors=("A A",), body="z")
    (three,) = find_duplicate_groups(load(renamed, b, c))
    assert len(three.members) == 3
    assert not JsonDismissStore(store_path).is_dismissed(three.identities)
