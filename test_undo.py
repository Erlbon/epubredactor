"""Tests for MainWindow._snapshot_book()/_restore_book() (the callables
that adapt redactor_common.core.undo.UndoManager -- a generic, item-
type-agnostic stack -- to this project's own EpubBook), using real
EpubBook instances (via a synthetic epub) rather than mocks, so
snapshot/restore is exercised against the actual object shape.

Used to test a local, EpubBook-specific core/undo.py -- that module
was itself generalized OUT of this exact code (once cbzredactor needed
the same "last N in-memory edits" behavior for its own CbzBook) into
redactor_common.core.undo, but this project was never actually
switched onto the result, so there were two near-identical
implementations to maintain. Migrated 2026-09-07; this file's own
tests are what confirmed the migration didn't change behavior."""
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(__file__))
from core.epub_metadata import EpubBook  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402
from redactor_common.core.undo import UndoManager  # noqa: E402

_snapshot_book = MainWindow._snapshot_book
_restore_book = MainWindow._restore_book

TEST_DIR = "/tmp/epub_test_undo"
os.makedirs(TEST_DIR, exist_ok=True)

CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

OPF = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="BookId">urn:uuid:xyz</dc:identifier>
    <dc:title>Original Title</dc:title>
    <dc:creator>Original Author</dc:creator>
  </metadata>
  <manifest>
    <item id="chap1" href="chap1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="chap1"/></spine>
</package>
"""


def make_book(name="book.epub"):
    path = os.path.join(TEST_DIR, name)
    if os.path.exists(path):
        os.remove(path)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", OPF)
        zf.writestr("OEBPS/chap1.xhtml", "<html></html>")
    return EpubBook(path)


def test_push_and_undo_restores_metadata():
    book = make_book()
    mgr = UndoManager(max_entries=5)

    mgr.push("edit title", [book], _snapshot_book)
    book.apply_metadata({"title": "New Title"})
    assert book.metadata.title == "New Title"
    assert book.dirty

    affected = mgr.undo(_restore_book)
    assert affected == [book]
    assert book.metadata.title == "Original Title", book.metadata.title
    assert not book.dirty
    print("PASS: undo restores metadata and dirty flag")


def test_undo_on_empty_stack_is_safe():
    mgr = UndoManager(max_entries=5)
    assert mgr.can_undo() is False
    assert mgr.undo(_restore_book) == []
    print("PASS: undo on an empty stack returns an empty list, doesn't crash")


def test_multiple_undos_pop_in_lifo_order():
    book = make_book("lifo.epub")
    mgr = UndoManager(max_entries=5)

    mgr.push("step1", [book], _snapshot_book)
    book.apply_metadata({"title": "Step 1 Title"})

    mgr.push("step2", [book], _snapshot_book)
    book.apply_metadata({"title": "Step 2 Title"})

    assert book.metadata.title == "Step 2 Title"
    mgr.undo(_restore_book)
    assert book.metadata.title == "Step 1 Title", book.metadata.title
    mgr.undo(_restore_book)
    assert book.metadata.title == "Original Title", book.metadata.title
    print("PASS: successive undos step back through history in reverse order")


def test_capped_at_max_entries():
    book = make_book("capped.epub")
    mgr = UndoManager(max_entries=5)

    for i in range(7):  # push more than the cap
        mgr.push(f"step{i}", [book], _snapshot_book)
        book.apply_metadata({"title": f"Title {i}"})

    undo_count = 0
    while mgr.can_undo():
        mgr.undo(_restore_book)
        undo_count += 1
    assert undo_count == 5, undo_count
    # After exhausting the 5 remembered steps, we should land on whatever
    # title existed when the 3rd push happened (steps 0,1 fell off the cap).
    assert book.metadata.title == "Title 1", book.metadata.title
    print("PASS: history caps at max_entries, oldest changes silently drop off")


def test_undo_restores_cover_state():
    book = make_book("cover.epub")
    mgr = UndoManager(max_entries=5)

    assert book.cover_bytes is None
    mgr.push("add cover", [book], _snapshot_book)
    book.set_cover(b"fake-image-bytes", "image/png")
    assert book.cover_bytes == b"fake-image-bytes"
    assert book.cover_changed

    mgr.undo(_restore_book)
    assert book.cover_bytes is None
    assert not book.cover_changed
    print("PASS: undo restores cover_bytes/cover_changed state too")


def test_push_snapshots_independent_of_later_mutation():
    """The snapshot must be a real copy -- mutating the metadata object
    after pushing must not also mutate the stored snapshot."""
    book = make_book("independence.epub")
    mgr = UndoManager(max_entries=5)

    mgr.push("edit", [book], _snapshot_book)
    book.metadata.tags.append("ShouldNotLeakIntoSnapshot")
    mgr.undo(_restore_book)
    assert "ShouldNotLeakIntoSnapshot" not in book.metadata.tags
    print("PASS: snapshot is a deep copy, immune to later in-place mutation")


if __name__ == "__main__":
    test_push_and_undo_restores_metadata()
    test_undo_on_empty_stack_is_safe()
    test_multiple_undos_pop_in_lifo_order()
    test_capped_at_max_entries()
    test_undo_restores_cover_state()
    test_push_snapshots_independent_of_later_mutation()
    print("\nALL UNDO TESTS PASSED")
