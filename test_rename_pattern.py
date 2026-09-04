"""Tests for core/rename_pattern.py."""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(__file__))
from core.epub_metadata import EpubMetadata  # noqa: E402
from core.rename_pattern import (  # noqa: E402
    rename_book_file,
    render_filename,
    sanitize_filename,
    unique_path,
    validate_filename_stem,
)


def make_meta(**kwargs) -> EpubMetadata:
    m = EpubMetadata()
    for k, v in kwargs.items():
        setattr(m, k, v)
    return m


class _FakeBook:
    """Minimal stand-in for EpubBook -- rename_book_file() only ever
    reads/writes .path, so constructing a full EpubBook (which requires
    a real, parseable EPUB zip on disk) isn't needed for these tests."""

    def __init__(self, path: str):
        self.path = path


def test_basic_render():
    m = make_meta(title="The Hobbit", authors=["J.R.R. Tolkien"], series="Middle-earth", series_index="1")
    result = render_filename(m, "%series% %series_index% - %title%")
    assert result == "Middle-earth 1 - The Hobbit", result
    print("PASS: basic render")


def test_empty_field_cleanup():
    # No series set -- pattern references %series% %series_index% which
    # should collapse cleanly instead of leaving "- - Title" artifacts.
    m = make_meta(title="Standalone Book", authors=["Author X"], series="", series_index="")
    result = render_filename(m, "%series% %series_index% - %title%")
    assert result == "Standalone Book", result
    print("PASS: empty fields collapse cleanly")


def test_authors_pattern():
    m = make_meta(title="Dune", authors=["Frank Herbert"])
    result = render_filename(m, "%authors% - %title%")
    assert result == "Frank Herbert - Dune", result
    print("PASS: author placeholder")


def test_illegal_characters_stripped():
    m = make_meta(title='Question: What/Why? "Really"', authors=["A"])
    result = render_filename(m, "%title%")
    for bad in '\\/:*?"<>|':
        assert bad not in result, f"{bad!r} leaked into {result!r}"
    print("PASS: illegal Windows filename characters stripped:", result)


def test_zero_pad_decimal_series_index():
    # A "5.5" sub-index (e.g. a novella between books 5 and 6) must have
    # only its integer part padded -- "05.5", not left unpadded or having
    # the fractional part mangled.
    m = make_meta(title="Interlude", series="Saga", series_index="5.5")
    result = render_filename(m, "%series% %series_index% - %title%", zero_pad_series=True)
    assert result == "Saga 05.5 - Interlude", result

    m2 = make_meta(title="Book Twelve Point Five", series="Saga", series_index="12.5")
    result2 = render_filename(m2, "%series% %series_index% - %title%", zero_pad_series=True)
    assert result2 == "Saga 12.5 - Book Twelve Point Five", result2
    print("PASS: decimal series index gets its integer part padded correctly")


def test_genres_placeholder():
    m = make_meta(title="Book", tags=["Fantasy", "Adventure"])
    result = render_filename(m, "%title% [%genres%]")
    assert result == "Book [Fantasy; Adventure]", result
    print("PASS: %genres% placeholder renders the Genre field")


def test_legacy_tags_placeholder_still_works():
    # "%tags%" was the original token before the field was relabeled
    # Genre and "%genres%" became the advertised token -- must keep
    # rendering correctly for anyone with an old saved pattern.
    m = make_meta(title="Book", tags=["Fantasy"])
    result = render_filename(m, "%title% [%tags%]")
    assert result == "Book [Fantasy]", result
    print("PASS: legacy %tags% placeholder still renders (backward compatibility)")


def test_collection_placeholder():
    m = make_meta(title="Novella")
    m.collection = "The Anthology Collection"
    result = render_filename(m, "%collection% - %title%")
    assert result == "The Anthology Collection - Novella", result
    print("PASS: %collection% placeholder renders the Collection field")


def test_pub_date_and_ddc_placeholders():
    m = make_meta(
        title="Old Book", pub_year="1955", pub_month="7", pub_day="3", ddc="823.912"
    )
    result = render_filename(m, "%pub_year%-%pub_month%-%pub_day% %ddc% - %title%")
    assert result == "1955-7-3 823.912 - Old Book", result
    print("PASS: legacy %pub_year%/%pub_month%/%pub_day% placeholders still render (backward compatibility)")


def test_year_month_day_placeholders():
    m = make_meta(title="Old Book", pub_year="1955", pub_month="7", pub_day="3")
    result = render_filename(m, "%year%-%month%-%day% - %title%")
    assert result == "1955-7-3 - Old Book", result
    print("PASS: %year%/%month%/%day% (the advertised tokens) render the same date fields")


def test_zero_pad_series():
    m = make_meta(title="Book Two", series="Saga", series_index="2")
    result = render_filename(m, "%series% %series_index% - %title%", zero_pad_series=True)
    assert result == "Saga 02 - Book Two", result
    # non-numeric series_index left alone
    m2 = make_meta(title="Special", series="Saga", series_index="Extra")
    result2 = render_filename(m2, "%series% %series_index% - %title%", zero_pad_series=True)
    assert result2 == "Saga Extra - Special", result2
    print("PASS: zero-padding series index")


def test_fallback_when_pattern_empty():
    m = make_meta(title="", authors=[])
    result = render_filename(m, "%title%", fallback="untitled")
    assert result == "untitled", result
    print("PASS: falls back to placeholder name when pattern renders empty")


def test_reserved_windows_name():
    m = make_meta(title="CON")
    result = render_filename(m, "%title%")
    assert result != "CON", result
    assert result == "_CON", result
    print("PASS: reserved Windows device names get escaped")


def test_long_filename_truncated():
    m = make_meta(title="X" * 300)
    result = render_filename(m, "%title%")
    assert len(result) <= 150, len(result)
    print("PASS: very long filenames truncated")


def test_unique_path_collision_on_disk(tmp_dir="/tmp/rename_test"):
    os.makedirs(tmp_dir, exist_ok=True)
    existing = os.path.join(tmp_dir, "Book.epub")
    open(existing, "w").close()
    taken = set()
    p1 = unique_path(tmp_dir, "Book", ".epub", taken)
    assert p1 == os.path.join(tmp_dir, "Book (2).epub"), p1
    print("PASS: collision with existing file on disk avoided")


def test_unique_path_collision_within_batch(tmp_dir="/tmp/rename_test2"):
    os.makedirs(tmp_dir, exist_ok=True)
    taken = set()

    def norm(p):
        return os.path.normcase(os.path.abspath(p))

    p1 = unique_path(tmp_dir, "Same Title", ".epub", taken)
    taken.add(norm(p1))
    p2 = unique_path(tmp_dir, "Same Title", ".epub", taken)
    taken.add(norm(p2))
    p3 = unique_path(tmp_dir, "Same Title", ".epub", taken)
    assert p1 != p2 != p3, (p1, p2, p3)
    assert p1 == os.path.join(tmp_dir, "Same Title.epub"), p1
    assert p2 == os.path.join(tmp_dir, "Same Title (2).epub"), p2
    assert p3 == os.path.join(tmp_dir, "Same Title (3).epub"), p3
    print("PASS: collisions within the same batch (not yet on disk) avoided")


def test_sanitize_trailing_dot_space():
    result = sanitize_filename("My Book.  ")
    assert result == "My Book", repr(result)
    print("PASS: trailing dots/spaces stripped (invalid on Windows)")


# ----------------------------------------------------------------------
# validate_filename_stem
# ----------------------------------------------------------------------

def test_validate_filename_stem_valid_name():
    assert validate_filename_stem("My Corrected Title") == ""
    print("PASS: an ordinary valid filename has no error")


def test_validate_filename_stem_empty():
    assert validate_filename_stem("") != ""
    assert validate_filename_stem("   ") != ""
    print("PASS: an empty or whitespace-only name is rejected")


def test_validate_filename_stem_illegal_characters():
    error = validate_filename_stem('Book: A "Story"?')
    assert error != ""
    assert ":" in error and '"' in error and "?" in error
    print("PASS: illegal Windows filename characters are rejected, listed in the message")


def test_validate_filename_stem_trailing_space():
    assert validate_filename_stem("My Book ") != ""
    print("PASS: a trailing space is rejected (invalid on Windows)")


def test_validate_filename_stem_trailing_dot():
    assert validate_filename_stem("My Book.") != ""
    print("PASS: a trailing dot is rejected (invalid on Windows)")


def test_validate_filename_stem_reserved_name():
    assert validate_filename_stem("CON") != ""
    assert validate_filename_stem("con") != ""  # case-insensitive
    print("PASS: a Windows-reserved name (CON, any case) is rejected")


def test_validate_filename_stem_too_long():
    assert validate_filename_stem("X" * 200) != ""
    print("PASS: an excessively long name is rejected")


def test_validate_filename_stem_normal_punctuation_allowed():
    # Only the specifically-illegal characters are rejected -- ordinary
    # punctuation that's fine in a Windows filename must not be flagged.
    assert validate_filename_stem("Book - Part 1 (Revised)") == ""
    assert validate_filename_stem("It's a Book!") == ""
    print("PASS: ordinary punctuation that's actually legal on Windows is never rejected")


# ----------------------------------------------------------------------
# rename_book_file
# ----------------------------------------------------------------------

RENAME_TEST_DIR = "/tmp/rename_book_file_test"
shutil.rmtree(RENAME_TEST_DIR, ignore_errors=True)  # clean slate each run, avoids stale-file collisions


def _make_fake_file(name: str) -> str:
    os.makedirs(RENAME_TEST_DIR, exist_ok=True)
    path = os.path.join(RENAME_TEST_DIR, name)
    with open(path, "w") as f:
        f.write("fake epub content")
    return path


def test_rename_book_file_renames_and_updates_path():
    path = _make_fake_file("Original Title.epub")
    book = _FakeBook(path)
    rename_book_file(book, "Corrected Title")
    expected = os.path.join(RENAME_TEST_DIR, "Corrected Title.epub")
    assert book.path == expected, book.path
    assert os.path.isfile(expected)
    assert not os.path.exists(path)
    print("PASS: renames the file on disk and updates book.path to match")


def test_rename_book_file_preserves_extension():
    path = _make_fake_file("Weird Extension.EPUB")
    book = _FakeBook(path)
    rename_book_file(book, "New Name")
    assert book.path == os.path.join(RENAME_TEST_DIR, "New Name.EPUB"), book.path
    print("PASS: the original extension (including its exact case) is always preserved")


def test_rename_book_file_same_name_is_noop():
    path = _make_fake_file("Unchanged.epub")
    book = _FakeBook(path)
    rename_book_file(book, "Unchanged")
    assert book.path == path
    assert os.path.isfile(path)
    print("PASS: renaming to the exact current name is a harmless no-op")


def test_rename_book_file_invalid_name_raises_and_does_not_touch_disk():
    path = _make_fake_file("Stays Put.epub")
    book = _FakeBook(path)
    try:
        rename_book_file(book, "Bad: Name?")
        assert False, "should have raised"
    except ValueError as exc:
        assert ":" in str(exc)
    assert book.path == path
    assert os.path.isfile(path)
    print("PASS: an invalid new name raises ValueError, leaves the file and book.path untouched")


def test_rename_book_file_collision_raises_and_does_not_overwrite():
    path = _make_fake_file("Book A.epub")
    other_path = _make_fake_file("Book B.epub")
    with open(other_path, "w") as f:
        f.write("this must not be overwritten")
    book = _FakeBook(path)
    try:
        rename_book_file(book, "Book B")
        assert False, "should have raised"
    except FileExistsError as exc:
        assert "Book B.epub" in str(exc)
    assert book.path == path
    assert os.path.isfile(path)
    with open(other_path) as f:
        assert f.read() == "this must not be overwritten"
    print("PASS: a collision with an existing file raises FileExistsError, doesn't overwrite it")


if __name__ == "__main__":
    test_basic_render()
    test_empty_field_cleanup()
    test_authors_pattern()
    test_illegal_characters_stripped()
    test_pub_date_and_ddc_placeholders()
    test_year_month_day_placeholders()
    test_zero_pad_decimal_series_index()
    test_genres_placeholder()
    test_legacy_tags_placeholder_still_works()
    test_collection_placeholder()
    test_zero_pad_series()
    test_fallback_when_pattern_empty()
    test_reserved_windows_name()
    test_long_filename_truncated()
    test_unique_path_collision_on_disk()
    test_unique_path_collision_within_batch()
    test_sanitize_trailing_dot_space()
    test_validate_filename_stem_valid_name()
    test_validate_filename_stem_empty()
    test_validate_filename_stem_illegal_characters()
    test_validate_filename_stem_trailing_space()
    test_validate_filename_stem_trailing_dot()
    test_validate_filename_stem_reserved_name()
    test_validate_filename_stem_too_long()
    test_validate_filename_stem_normal_punctuation_allowed()
    test_rename_book_file_renames_and_updates_path()
    test_rename_book_file_preserves_extension()
    test_rename_book_file_same_name_is_noop()
    test_rename_book_file_invalid_name_raises_and_does_not_touch_disk()
    test_rename_book_file_collision_raises_and_does_not_overwrite()
    print("\nALL RENAME-PATTERN TESTS PASSED")
