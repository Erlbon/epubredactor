"""Tests for core/genre_detect.py (pure suggestion logic) and the
add-only Suggest Genres wiring in MainWindow."""
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(__file__))
from PyQt6.QtWidgets import QApplication, QDialog  # noqa: E402

import gui.main_window as mw  # noqa: E402
from core.epub_metadata import EpubBook, EpubMetadata  # noqa: E402
from core.genre_detect import genre_for_ddc, scan_book_genres, suggest_genres  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)


def _genres(**kwargs) -> list[str]:
    return [s.genre for s in suggest_genres(**kwargs)]


# ---------------------------------------------------------------- path

def test_folder_names_suggest_genres():
    found = _genres(path=r"D:\Books\Fiction\Science Fiction\Space Opera\Leckie - Ancillary Justice.epub")
    assert "Space Opera" in found and "Science Fiction" in found and "Fiction" in found, found


def test_folder_aliases_and_plurals():
    assert "Science Fiction" in _genres(path="/books/Sci-Fi/x.epub")
    assert "Thriller" in _genres(path="/books/Thrillers/x.epub")
    found = _genres(path=r"D:\Books\Mysteries_and_Thrillers\x.epub")
    assert "Mystery" in found and "Thriller" in found, found


def test_non_fiction_folder_is_not_fiction():
    found = _genres(path=r"D:\Books\Non-Fiction\Hawking - A Brief History of Time.epub")
    assert "Nonfiction" in found and "Fiction" not in found, found


def test_filename_only_counts_bracketed_tags():
    # "History" and "War" in a title aren't genre labels...
    assert _genres(path="/lib/misc/The War of the Worlds - A History.epub") == []
    # ...but an explicit bracketed tag is.
    assert "Science Fiction" in _genres(path="/lib/misc/Dune [Sci-Fi].epub")


def test_only_trailing_folders_count():
    found = _genres(path="/Fantasy/a/b/c/d/x.epub")
    assert "Fantasy" not in found, found


# --------------------------------------------------------- description

def test_description_strong_terms():
    found = _genres(description="A gripping psychological thriller from a bestselling author.")
    assert found == ["Psychological Thriller"], found


def test_description_ambiguous_words_need_genre_context():
    plot = "He fought in the war and studied history at Oxford, where romance bloomed. A mystery surrounds him."
    assert _genres(description=plot) == []
    found = _genres(description="A sweeping war novel, and the first book in an epic fantasy series.")
    assert "War" in found and "Epic Fantasy" in found, found


def test_custom_genre_matched_by_name_in_description():
    found = _genres(description="A LitRPG adventure.", vocabulary=["Fantasy", "LitRPG"])
    assert found == ["LitRPG"], found


# ------------------------------------------------------- first pages

def test_cip_and_bisac_lines():
    cip = ("Library of Congress Cataloging-in-Publication Data "
           "1. Space warfare\u2014Fiction. 2. Science fiction. I. Title.")
    found = _genres(content_text=cip)
    assert "Science Fiction" in found and "Fiction" in found, found
    found = _genres(content_text="FICTION / Fantasy / Epic. This is a work of fiction.")
    assert "Epic Fantasy" in found and "Fiction" in found, found


def test_urls_are_not_subject_lines():
    assert _genres(content_text="Visit http://example.com/history/abc for more.") == []


# ---------------------------------------------------------------- DDC

def test_ddc_mapping():
    assert genre_for_ddc("823.914") == "Fiction"
    assert genre_for_ddc("811.54") == "Poetry"
    assert genre_for_ddc("641.5") == "Cooking"
    assert genre_for_ddc("920") == "Biography"
    assert genre_for_ddc("940.53") == "History"
    assert genre_for_ddc("[Fic]") == ""
    assert genre_for_ddc("") == ""


# ------------------------------------------------ safety / vocabulary

def test_existing_genres_are_never_suggested_again():
    found = _genres(path="/b/Fantasy/Horror/x.epub", existing_tags=["fantasy"])
    assert "Fantasy" not in found and "Horror" in found, found


def test_hidden_default_genre_is_never_suggested():
    vocabulary = ["Horror", "Fiction"]  # "Fantasy" hidden by the user
    found = _genres(path="/b/Fantasy/Horror/x.epub", vocabulary=vocabulary)
    assert found == ["Horror"], found


def test_multiple_sources_rank_first_and_are_listed():
    suggestions = suggest_genres(
        path="/b/Horror/x.epub",
        description="A chilling horror novel. Also a romance novel.",
    )
    assert suggestions[0].genre == "Horror", [s.describe() for s in suggestions]
    assert suggestions[0].source_kinds == ["folder", "description"], suggestions[0].sources


# ------------------------------------------------- scan_book_genres

_CONTAINER = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>"""
_OPF = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="BookId">urn:uuid:genre-test</dc:identifier>
    <dc:title>Genre Test</dc:title>
    <dc:language>en</dc:language>
    <dc:subject>Adventure</dc:subject>
    <dc:description>&lt;p&gt;A classic &lt;b&gt;space opera&lt;/b&gt;.&lt;/p&gt;</dc:description>
  </metadata>
  <manifest><item id="c" href="copyright.xhtml" media-type="application/xhtml+xml"/></manifest>
  <spine><itemref idref="c"/></spine>
</package>"""
_COPYRIGHT = "<html><body><p>1. Interstellar travel--Fiction. 2. Science fiction.</p></body></html>"


def test_scan_book_genres_reads_all_sources(tmp_path):
    folder = tmp_path / "Military SF"
    folder.mkdir()
    path = folder / "book.epub"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", _CONTAINER)
        zf.writestr("OEBPS/content.opf", _OPF)
        zf.writestr("OEBPS/copyright.xhtml", _COPYRIGHT)
    book = EpubBook(str(path))
    found = {s.genre: s.source_kinds for s in scan_book_genres(book)}
    assert found.get("Military Science Fiction") == ["folder"], found
    assert found.get("Space Opera") == ["description"], found
    assert "first pages" in found.get("Science Fiction", []), found
    assert "Adventure" not in found, found  # already tagged


# ----------------------------------------------------- MainWindow wiring

def _fake_book(path: str, **metadata_kwargs) -> EpubBook:
    book = EpubBook.__new__(EpubBook)
    book.path = path
    book.load_error = None
    book.save_error = ""
    book.dirty = False
    book.cover_bytes = None
    book.cover_mime = ""
    book.cover_changed = False
    book.cover_removed = False
    book._cover_hash_cache = None
    book._orphan_files_to_remove = set()
    book._image_replacements = {}
    book.validation_issues = []
    book.validation_status = "OK"
    meta = EpubMetadata()
    for key, value in metadata_kwargs.items():
        setattr(meta, key, value)
    book.metadata = meta
    return book


def _fake_dialog_class(additions: dict, exec_result=QDialog.DialogCode.Accepted):
    class _Fake(QDialog):
        def __init__(self, books, vocabulary=None, parent=None):
            super().__init__(parent)

        def exec(self):
            return exec_result

        def accepted_additions(self):
            return additions

    return _Fake


def _run_with_fake(window, fake):
    original = mw.GenreSuggestDialog
    mw.GenreSuggestDialog = fake
    try:
        window.open_genre_suggest_dialog()
    finally:
        mw.GenreSuggestDialog = original


def _window_with_books(*books):
    window = MainWindow()
    window.books = list(books)
    window._rebuild_table()
    return window


def test_suggested_genres_are_added_not_replaced():
    book = _fake_book("/x/a.epub", title="A", tags=["Fiction", "My Own Tag"])
    window = _window_with_books(book)
    _run_with_fake(window, _fake_dialog_class({0: ["Fantasy", "fiction"]}))
    assert book.metadata.tags == ["Fiction", "My Own Tag", "Fantasy"], book.metadata.tags
    assert book.dirty
    window.on_undo()
    assert book.metadata.tags == ["Fiction", "My Own Tag"], book.metadata.tags


def test_nothing_new_to_add_is_a_clean_noop():
    book = _fake_book("/x/b.epub", title="B", tags=["Fantasy"])
    window = _window_with_books(book)
    _run_with_fake(window, _fake_dialog_class({0: ["fantasy"]}))
    assert book.metadata.tags == ["Fantasy"]
    assert not book.dirty
    assert not window.undo_manager.can_undo()


def test_cancel_applies_nothing():
    book = _fake_book("/x/c.epub", title="C", tags=[])
    window = _window_with_books(book)
    _run_with_fake(window, _fake_dialog_class({0: ["Horror"]}, QDialog.DialogCode.Rejected))
    assert book.metadata.tags == []
    assert not book.dirty


def test_real_dialog_starts_unticked_for_already_tagged_books(tmp_path):
    from gui.genre_suggest_dialog import GenreSuggestDialog

    tagged = _fake_book(str(tmp_path / "Horror" / "a.epub"), title="A", tags=["Gothic"])
    untagged = _fake_book(str(tmp_path / "Horror" / "b.epub"), title="B", tags=[])
    dialog = GenreSuggestDialog([tagged, untagged], ["Horror", "Gothic"])
    assert dialog.accepted_additions() == {1: ["Horror"]}, dialog.accepted_additions()
