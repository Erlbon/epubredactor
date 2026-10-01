"""Initials are written spaced ("J. R. R. Tolkien") by everything that
produces or converts author values; matching keys ignore the spacing."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from core.author_clean import author_key  # noqa: E402
from core.author_sort import author_sort_to_authors, authors_to_author_sort, space_initials  # noqa: E402
from core.filename_parser import folder_authors_to_display, split_author_ampersands  # noqa: E402
from core.openlibrary_local import row_to_candidate  # noqa: E402


def test_space_initials():
    assert space_initials("J.R.R.Tolkien") == "J. R. R. Tolkien"
    assert space_initials("J.R.R. Tolkien; A.J. Cronin") == "J. R. R. Tolkien; A. J. Cronin"
    assert space_initials("Tolkien, J.R.R.") == "Tolkien, J. R. R."
    assert space_initials("J. R. R. Tolkien") == "J. R. R. Tolkien"
    assert space_initials("Jane Doe") == "Jane Doe" and space_initials("") == ""


def test_convert_author_sort_writes_spaced_initials():
    assert authors_to_author_sort("J.R.R. Tolkien") == "Tolkien, J. R. R."
    assert author_sort_to_authors("Tolkien, J.R.R.") == "J. R. R. Tolkien"
    assert author_sort_to_authors("Tolkien, J.R.R.; King, S.") == "J. R. R. Tolkien; S. King"


def test_filename_and_folder_parsing_write_spaced_initials():
    assert split_author_ampersands("J.R.R. Tolkien & C.S. Lewis") == "J. R. R. Tolkien; C. S. Lewis"
    assert folder_authors_to_display("Tolkien, J.R.R.") == "J. R. R. Tolkien"


def test_local_open_library_candidates_have_spaced_initials():
    row = (1, "9780000000002", "", "The Hobbit", "", "J.R.R. Tolkien", "", "", 1937, "eng", 300, "", 0)
    assert row_to_candidate(row).authors_str == "J. R. R. Tolkien"


def test_matching_keys_ignore_the_spacing():
    assert author_key("J.R.R. Tolkien") == author_key("J. R. R. Tolkien") == author_key("Tolkien, J.R.R.")
