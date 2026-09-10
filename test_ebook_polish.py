"""Tests for core/ebook_polish.py. Subprocess interaction faked via the
injectable run_fn parameter, no real Calibre needed."""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
from core.ebook_polish import (  # noqa: E402
    EbookPolishError,
    PolishOptions,
    is_supported_polish_target,
    polish_book,
)

TEST_DIR = "/tmp/ebook_polish_test"
os.makedirs(TEST_DIR, exist_ok=True)


class _FakeCompletedProcess:
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _make_file(name: str) -> str:
    path = os.path.join(TEST_DIR, name)
    with open(path, "w") as f:
        f.write("fake epub content")
    return path


# ----------------------------------------------------------------------
# PolishOptions
# ----------------------------------------------------------------------

def test_any_selected_false_by_default():
    assert PolishOptions().any_selected() is False
    print("PASS: no options selected by default")


def test_any_selected_true_with_one_flag():
    assert PolishOptions(smarten_punctuation=True).any_selected() is True
    print("PASS: any_selected true when at least one flag is set")


def test_to_args_maps_each_flag_correctly():
    opts = PolishOptions(
        smarten_punctuation=True, subset_fonts=True, embed_fonts=True,
        compress_images=True, remove_unused_css=True, upgrade_book=True,
    )
    args = opts.to_args()
    for flag in (
        "--smarten-punctuation", "--subset-fonts", "--embed-fonts",
        "--compress-images", "--remove-unused-css", "--upgrade-book",
    ):
        assert flag in args, f"{flag} missing from {args}"
    assert "--add-soft-hyphens" not in args
    assert "--jacket" not in args
    print("PASS: to_args() includes exactly the selected flags")


def test_to_args_soft_hyphens_and_jacket_variants():
    add = PolishOptions(add_soft_hyphens=True).to_args()
    assert add == ["--add-soft-hyphens"]
    remove = PolishOptions(remove_soft_hyphens=True).to_args()
    assert remove == ["--remove-soft-hyphens"]
    insert_j = PolishOptions(insert_jacket=True).to_args()
    assert insert_j == ["--jacket"]
    remove_j = PolishOptions(remove_jacket=True).to_args()
    assert remove_j == ["--remove-jacket"]
    print("PASS: soft-hyphen and jacket flags map to the correct distinct CLI options")


def test_validate_rejects_contradictory_hyphens():
    try:
        PolishOptions(add_soft_hyphens=True, remove_soft_hyphens=True).validate()
        assert False, "should have raised"
    except EbookPolishError:
        pass
    print("PASS: can't both add and remove soft hyphens at once")


def test_validate_rejects_contradictory_jacket():
    try:
        PolishOptions(insert_jacket=True, remove_jacket=True).validate()
        assert False, "should have raised"
    except EbookPolishError:
        pass
    print("PASS: can't both insert and remove the jacket at once")


def test_validate_passes_for_normal_options():
    PolishOptions(smarten_punctuation=True).validate()  # should not raise
    print("PASS: normal non-contradictory options validate cleanly")


# ----------------------------------------------------------------------
# is_supported_polish_target
# ----------------------------------------------------------------------

def test_is_supported_polish_target():
    assert is_supported_polish_target("book.epub")
    assert is_supported_polish_target("book.EPUB")
    assert is_supported_polish_target("book.azw3")
    assert is_supported_polish_target("book.kepub")
    assert not is_supported_polish_target("book.mobi")
    assert not is_supported_polish_target("book.pdf")
    print("PASS: recognizes only epub/azw3/kepub as polish targets")


# ----------------------------------------------------------------------
# polish_book
# ----------------------------------------------------------------------

def test_polish_book_success():
    source = _make_file("book.epub")
    output = os.path.join(TEST_DIR, "book_polished.epub")
    captured_args = []

    def fake_run(args, capture_output, timeout, **kwargs):
        captured_args.extend(args)
        return _FakeCompletedProcess(returncode=0)

    polish_book(
        "/fake/ebook-polish", source, output,
        PolishOptions(smarten_punctuation=True), run_fn=fake_run,
    )
    assert captured_args[0] == "/fake/ebook-polish"
    assert "--smarten-punctuation" in captured_args
    assert captured_args[-2:] == [source, output]
    print("PASS: successful polish calls ebook-polish with flags then source/output paths")


def test_polish_book_no_options_raises():
    source = _make_file("book2.epub")
    try:
        polish_book("/fake/exe", source, "/tmp/out.epub", PolishOptions(), run_fn=lambda *a, **k: None)
        assert False, "should have raised"
    except EbookPolishError as exc:
        assert "no polish actions" in str(exc).lower()
    print("PASS: no options selected raises before running the tool")


def test_polish_book_missing_source_raises():
    try:
        polish_book(
            "/fake/exe", "/nonexistent/book.epub", "/tmp/out.epub",
            PolishOptions(smarten_punctuation=True), run_fn=lambda *a, **k: None,
        )
        assert False, "should have raised"
    except EbookPolishError as exc:
        assert "not found" in str(exc).lower()
    print("PASS: a missing source file raises before running the tool")


def test_polish_book_unsupported_format_raises():
    source = _make_file("book3.mobi")
    try:
        polish_book(
            "/fake/exe", source, "/tmp/out.mobi",
            PolishOptions(smarten_punctuation=True), run_fn=lambda *a, **k: None,
        )
        assert False, "should have raised"
    except EbookPolishError as exc:
        assert "unsupported" in str(exc).lower()
    print("PASS: an unsupported source format raises before running the tool")


def test_polish_book_contradictory_options_raise_before_running():
    source = _make_file("book4.epub")
    called = []

    def fake_run(args, capture_output, timeout, **kwargs):
        called.append(True)
        return _FakeCompletedProcess(returncode=0)

    try:
        polish_book(
            "/fake/exe", source, "/tmp/out.epub",
            PolishOptions(add_soft_hyphens=True, remove_soft_hyphens=True), run_fn=fake_run,
        )
        assert False, "should have raised"
    except EbookPolishError:
        pass
    assert not called, "the tool should never have actually been invoked"
    print("PASS: contradictory options are caught before ever running the tool")


def test_polish_book_nonzero_returncode_raises():
    source = _make_file("book5.epub")

    def fake_run(args, capture_output, timeout, **kwargs):
        return _FakeCompletedProcess(returncode=1, stderr=b"Polishing failed: corrupt input")

    try:
        polish_book(
            "/fake/exe", source, "/tmp/out.epub",
            PolishOptions(smarten_punctuation=True), run_fn=fake_run,
        )
        assert False, "should have raised"
    except EbookPolishError as exc:
        assert "corrupt input" in str(exc)
    print("PASS: a failed polish raises with the tool's own error message")


def test_polish_book_timeout_raises():
    source = _make_file("book6.epub")

    def fake_run(args, capture_output, timeout, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args, timeout=timeout)

    try:
        polish_book(
            "/fake/exe", source, "/tmp/out.epub",
            PolishOptions(smarten_punctuation=True), run_fn=fake_run,
        )
        assert False, "should have raised"
    except EbookPolishError as exc:
        assert "timed out" in str(exc).lower()
    print("PASS: a subprocess timeout is wrapped in a clear EbookPolishError")


def test_polish_book_missing_executable_raises():
    source = _make_file("book7.epub")

    def fake_run(args, capture_output, timeout, **kwargs):
        raise OSError("No such file or directory")

    try:
        polish_book(
            "/fake/does-not-exist", source, "/tmp/out.epub",
            PolishOptions(smarten_punctuation=True), run_fn=fake_run,
        )
        assert False, "should have raised"
    except EbookPolishError as exc:
        assert "Could not run" in str(exc)
    print("PASS: a missing/unrunnable executable raises a clear EbookPolishError")


if __name__ == "__main__":
    test_any_selected_false_by_default()
    test_any_selected_true_with_one_flag()
    test_to_args_maps_each_flag_correctly()
    test_to_args_soft_hyphens_and_jacket_variants()
    test_validate_rejects_contradictory_hyphens()
    test_validate_rejects_contradictory_jacket()
    test_validate_passes_for_normal_options()
    test_is_supported_polish_target()
    test_polish_book_success()
    test_polish_book_no_options_raises()
    test_polish_book_missing_source_raises()
    test_polish_book_unsupported_format_raises()
    test_polish_book_contradictory_options_raise_before_running()
    test_polish_book_nonzero_returncode_raises()
    test_polish_book_timeout_raises()
    test_polish_book_missing_executable_raises()
    print("\nALL EBOOK POLISH TESTS PASSED")
