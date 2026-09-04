"""Tests for core/ebook_convert.py. Subprocess interaction faked via the
injectable run_fn parameter, no real Calibre needed."""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
from core.ebook_convert import (  # noqa: E402
    EbookConvertError,
    convert_to_epub,
    is_supported_source,
)

TEST_DIR = "/tmp/ebook_convert_test"
os.makedirs(TEST_DIR, exist_ok=True)


class _FakeCompletedProcess:
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _make_file(name: str) -> str:
    path = os.path.join(TEST_DIR, name)
    with open(path, "w") as f:
        f.write("fake content")
    return path


def test_is_supported_source():
    assert is_supported_source("book.mobi")
    assert is_supported_source("book.docx")
    assert not is_supported_source("book.epub")  # already epub, not a conversion source
    assert not is_supported_source("book.xyz")
    print("PASS: recognizes supported source extensions, case-insensitively")


def test_pdf_not_supported_by_default():
    # Deliberate: PDF -> EPUB conversion quality is inconsistent (PDFs
    # have no real text-flow structure), so it's excluded from the
    # default set rather than offered as an ordinary option.
    assert not is_supported_source("book.pdf")
    assert not is_supported_source("book.PDF")
    print("PASS: PDF is deliberately excluded from the default supported formats")


def test_convert_success():
    source = _make_file("book.mobi")
    output = os.path.join(TEST_DIR, "book.epub")
    captured_args = []

    def fake_run(args, capture_output, timeout):
        captured_args.extend(args)
        return _FakeCompletedProcess(returncode=0)

    convert_to_epub("/fake/ebook-convert", source, output, run_fn=fake_run)
    assert captured_args == ["/fake/ebook-convert", source, output]
    print("PASS: successful conversion calls ebook-convert with source and output paths")


def test_convert_missing_source_raises():
    try:
        convert_to_epub("/fake/exe", "/nonexistent/book.mobi", "/tmp/out.epub", run_fn=lambda *a, **k: None)
        assert False, "should have raised"
    except EbookConvertError as exc:
        assert "not found" in str(exc).lower()
    print("PASS: a missing source file raises before even trying to run the tool")


def test_convert_unsupported_format_raises():
    source = _make_file("book.xyz")
    try:
        convert_to_epub("/fake/exe", source, "/tmp/out.epub", run_fn=lambda *a, **k: None)
        assert False, "should have raised"
    except EbookConvertError as exc:
        assert "unsupported" in str(exc).lower()
    print("PASS: an unsupported source format raises before running the tool")


def test_convert_nonzero_returncode_raises():
    source = _make_file("book.docx")

    def fake_run(args, capture_output, timeout):
        return _FakeCompletedProcess(returncode=1, stderr=b"Conversion failed: corrupt input file")

    try:
        convert_to_epub("/fake/exe", source, "/tmp/out.epub", run_fn=fake_run)
        assert False, "should have raised"
    except EbookConvertError as exc:
        assert "corrupt input file" in str(exc)
    print("PASS: a failed conversion raises with the tool's own error message")


def test_convert_timeout_raises():
    source = _make_file("book.mobi")

    def fake_run(args, capture_output, timeout):
        raise subprocess.TimeoutExpired(cmd=args, timeout=timeout)

    try:
        convert_to_epub("/fake/exe", source, "/tmp/out.epub", run_fn=fake_run)
        assert False, "should have raised"
    except EbookConvertError as exc:
        assert "timed out" in str(exc).lower()
    print("PASS: a subprocess timeout is wrapped in a clear EbookConvertError")


def test_convert_missing_executable_raises():
    source = _make_file("book.mobi")

    def fake_run(args, capture_output, timeout):
        raise OSError("No such file or directory")

    try:
        convert_to_epub("/fake/does-not-exist", source, "/tmp/out.epub", run_fn=fake_run)
        assert False, "should have raised"
    except EbookConvertError as exc:
        assert "Could not run" in str(exc)
    print("PASS: a missing/unrunnable executable raises a clear EbookConvertError")


if __name__ == "__main__":
    test_is_supported_source()
    test_pdf_not_supported_by_default()
    test_convert_success()
    test_convert_missing_source_raises()
    test_convert_unsupported_format_raises()
    test_convert_nonzero_returncode_raises()
    test_convert_timeout_raises()
    test_convert_missing_executable_raises()
    print("\nALL EBOOK CONVERT TESTS PASSED")
