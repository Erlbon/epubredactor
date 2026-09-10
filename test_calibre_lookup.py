"""Tests for core/calibre_lookup.py. All subprocess interaction is faked
via the injectable `run_fn`/`which_fn` parameters, matching realistic
output shapes based on Calibre's own documented OPF conventions (the
same ones this app's own core/epub_metadata.py already implements, since
Calibre is the reference implementation for the calibre:series meta
convention and the opf:file-as attribute)."""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
from core.calibre_lookup import (  # noqa: E402
    CalibreLookupError,
    fetch_metadata,
    parse_calibre_opf,
)

TEST_DIR = "/tmp/calibre_lookup_test"
os.makedirs(TEST_DIR, exist_ok=True)

REALISTIC_OPF = b"""<?xml version='1.0' encoding='utf-8'?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="uuid_id" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier opf:scheme="ISBN" id="isbn">9780261102217</dc:identifier>
    <dc:identifier opf:scheme="GOODREADS" id="goodreads">12345</dc:identifier>
    <dc:title>The Hobbit</dc:title>
    <dc:creator opf:file-as="Tolkien, J.R.R." opf:role="aut">J.R.R. Tolkien</dc:creator>
    <dc:subject>Fantasy</dc:subject>
    <dc:subject>Fiction</dc:subject>
    <dc:publisher>George Allen &amp; Unwin</dc:publisher>
    <dc:language>eng</dc:language>
    <dc:date>1937-09-21T00:00:00+00:00</dc:date>
    <dc:description>A hobbit goes on an adventure.</dc:description>
    <meta name="calibre:series" content="Middle-earth"/>
    <meta name="calibre:series_index" content="1"/>
  </metadata>
</package>
"""

MINIMAL_OPF = b"""<?xml version='1.0' encoding='utf-8'?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Bare Bones Book</dc:title>
  </metadata>
</package>
"""


# ----------------------------------------------------------------------
# parse_calibre_opf
# ----------------------------------------------------------------------

def test_parse_realistic_opf():
    result = parse_calibre_opf(REALISTIC_OPF)
    assert result.title == "The Hobbit"
    assert result.authors_str == "J.R.R. Tolkien"
    assert result.author_sort_str == "Tolkien, J.R.R."
    assert result.series == "Middle-earth"
    assert result.series_index == "1"
    assert result.tags_str == "Fantasy; Fiction"
    assert result.publisher == "George Allen & Unwin"
    assert result.language == "eng"
    assert result.pub_year == "1937"
    assert result.pub_month == "09"
    assert result.pub_day == "21"
    assert result.isbn == "9780261102217"  # ISBN scheme picked, not GOODREADS
    assert result.description == "A hobbit goes on an adventure."
    print("PASS: parses a realistic Calibre OPF into all expected fields")


def test_parse_minimal_opf():
    result = parse_calibre_opf(MINIMAL_OPF)
    assert result.title == "Bare Bones Book"
    assert result.authors_str == ""
    assert result.isbn == ""
    assert result.as_dict() == {"title": "Bare Bones Book"}
    print("PASS: minimal OPF with only a title parses cleanly, empty fields excluded from as_dict")


def test_parse_garbage_input():
    result = parse_calibre_opf(b"not xml at all {{{")
    assert result.as_dict() == {}
    print("PASS: unparseable input yields an empty result, doesn't crash")


def test_parse_empty_input():
    result = parse_calibre_opf(b"")
    assert result.as_dict() == {}
    print("PASS: empty input yields an empty result")


def test_multiple_authors():
    opf = b"""<?xml version='1.0' encoding='utf-8'?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:title>Good Omens</dc:title>
    <dc:creator opf:file-as="Pratchett, Terry">Terry Pratchett</dc:creator>
    <dc:creator opf:file-as="Gaiman, Neil">Neil Gaiman</dc:creator>
  </metadata>
</package>
"""
    result = parse_calibre_opf(opf)
    assert result.authors_str == "Terry Pratchett; Neil Gaiman"
    assert result.author_sort_str == "Pratchett, Terry; Gaiman, Neil"
    print("PASS: multiple authors and their sort-names are collected in order")


# ----------------------------------------------------------------------
# fetch_metadata (subprocess interaction faked via run_fn)
# ----------------------------------------------------------------------

class _FakeCompletedProcess:
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_fetch_metadata_success():
    captured_args = []

    def fake_run(args, capture_output, timeout, **kwargs):
        captured_args.extend(args)
        return _FakeCompletedProcess(returncode=0, stdout=REALISTIC_OPF)

    result = fetch_metadata(
        "/fake/fetch-ebook-metadata", title="The Hobbit", authors="Tolkien", run_fn=fake_run
    )
    assert result.title == "The Hobbit"
    assert "--opf" in captured_args
    assert "--title" in captured_args
    assert "The Hobbit" in captured_args
    assert "--authors" in captured_args
    print("PASS: fetch_metadata builds correct args and parses a successful result")


def test_fetch_metadata_requires_some_search_criteria():
    try:
        fetch_metadata("/fake/exe", run_fn=lambda *a, **k: None)
        assert False, "should have raised"
    except CalibreLookupError as exc:
        assert "title, author, or ISBN" in str(exc)
    print("PASS: refuses to run with no title/authors/isbn at all")


def test_fetch_metadata_nonzero_returncode_raises():
    def fake_run(args, capture_output, timeout, **kwargs):
        return _FakeCompletedProcess(returncode=1, stdout=b"", stderr=b"No matches found")

    try:
        fetch_metadata("/fake/exe", title="Nonexistent Book Xyz", run_fn=fake_run)
        assert False, "should have raised"
    except CalibreLookupError as exc:
        assert "No matches found" in str(exc)
    print("PASS: non-zero return code raises with the tool's own stderr message")


def test_fetch_metadata_verbose_stderr_truncated():
    """Regression test: Calibre's fetch-ebook-metadata can log hundreds
    of very verbose lines to stderr on a "nothing found" search (every
    plugin's search attempts, URLs queried, etc.) -- that must not end
    up verbatim in the raised error, or it balloons this app's own
    results table/status area to an unusable size."""
    huge_stderr = b"SyntaxWarning: something\n" + (b"some verbose plugin log line\n" * 200)

    def fake_run(args, capture_output, timeout, **kwargs):
        return _FakeCompletedProcess(returncode=1, stdout=b"", stderr=huge_stderr)

    try:
        fetch_metadata("/fake/exe", title="Some Book", run_fn=fake_run)
        assert False, "should have raised"
    except CalibreLookupError as exc:
        assert len(str(exc)) < 550, len(str(exc))
        assert str(exc).endswith("\u2026")
    print("PASS: an unusually verbose stderr dump is truncated in the raised error")


def test_fetch_metadata_timeout_raises():
    def fake_run(args, capture_output, timeout, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args, timeout=timeout)

    try:
        fetch_metadata("/fake/exe", title="Slow Book", run_fn=fake_run)
        assert False, "should have raised"
    except CalibreLookupError as exc:
        assert "timed out" in str(exc).lower()
    print("PASS: a subprocess timeout is wrapped in a clear CalibreLookupError")


def test_fetch_metadata_missing_executable_raises():
    def fake_run(args, capture_output, timeout, **kwargs):
        raise OSError("No such file or directory")

    try:
        fetch_metadata("/fake/does-not-exist", title="Book", run_fn=fake_run)
        assert False, "should have raised"
    except CalibreLookupError as exc:
        assert "Could not run" in str(exc)
    print("PASS: a missing/unrunnable executable raises a clear CalibreLookupError")


def test_fetch_metadata_isbn_only_search():
    captured_args = []

    def fake_run(args, capture_output, timeout, **kwargs):
        captured_args.extend(args)
        return _FakeCompletedProcess(returncode=0, stdout=REALISTIC_OPF)

    fetch_metadata("/fake/exe", isbn="9780261102217", run_fn=fake_run)
    assert "--isbn" in captured_args
    assert "9780261102217" in captured_args
    assert "--title" not in captured_args
    print("PASS: an ISBN-only search only passes --isbn, no empty --title/--authors")


if __name__ == "__main__":
    test_parse_realistic_opf()
    test_parse_minimal_opf()
    test_parse_garbage_input()
    test_parse_empty_input()
    test_multiple_authors()
    test_fetch_metadata_success()
    test_fetch_metadata_requires_some_search_criteria()
    test_fetch_metadata_nonzero_returncode_raises()
    test_fetch_metadata_verbose_stderr_truncated()
    test_fetch_metadata_timeout_raises()
    test_fetch_metadata_missing_executable_raises()
    test_fetch_metadata_isbn_only_search()
    print("\nALL CALIBRE LOOKUP TESTS PASSED")
