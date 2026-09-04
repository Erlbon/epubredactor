"""Tests for core/kobo_usb.py. Drive detection faked via the injectable
isdir_fn/drive_letters params; file copying tested against real tmp
directories (standing in for a Kobo's drive root)."""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(__file__))
from core.kobo_usb import KoboSendError, find_connected_kobos, send_to_kobo  # noqa: E402

TEST_DIR = "/tmp/kobo_usb_test"
shutil.rmtree(TEST_DIR, ignore_errors=True)  # clean slate each run, avoids stale-file collisions
os.makedirs(TEST_DIR, exist_ok=True)


def test_find_connected_kobos_detects_one():
    def fake_isdir(path):
        return path == "E:\\.kobo"

    result = find_connected_kobos(isdir_fn=fake_isdir)
    assert result == ["E:\\"], result
    print("PASS: finds a single connected Kobo by its .kobo marker folder")


def test_find_connected_kobos_multiple():
    def fake_isdir(path):
        return path in ("E:\\.kobo", "G:\\.kobo")

    result = find_connected_kobos(isdir_fn=fake_isdir)
    assert result == ["E:\\", "G:\\"], result
    print("PASS: finds multiple connected Kobos")


def test_find_connected_kobos_none():
    result = find_connected_kobos(isdir_fn=lambda path: False)
    assert result == []
    print("PASS: no Kobo connected -> empty list, not an error")


def test_find_connected_kobos_custom_drive_letters():
    result = find_connected_kobos(drive_letters="XY", isdir_fn=lambda path: path == "Y:\\.kobo")
    assert result == ["Y:\\"], result
    print("PASS: only checks the given drive letters when a custom set is provided")


def test_send_to_kobo_copies_file():
    source = os.path.join(TEST_DIR, "book.epub")
    with open(source, "w") as f:
        f.write("fake epub content")
    kobo_root = os.path.join(TEST_DIR, "fake_kobo_root")
    os.makedirs(kobo_root, exist_ok=True)

    dest = send_to_kobo(kobo_root, source)
    assert dest == os.path.join(kobo_root, "book.epub"), dest
    assert os.path.isfile(dest)
    with open(dest) as f:
        assert f.read() == "fake epub content"
    print("PASS: send_to_kobo copies the file onto the Kobo's root")


def test_send_to_kobo_missing_source_raises():
    kobo_root = os.path.join(TEST_DIR, "fake_kobo_root2")
    os.makedirs(kobo_root, exist_ok=True)
    try:
        send_to_kobo(kobo_root, "/nonexistent/book.epub")
        assert False, "should have raised"
    except KoboSendError as exc:
        assert "not found" in str(exc).lower()
    print("PASS: a missing source file raises before attempting the copy")


def test_send_to_kobo_collision_auto_numbers():
    source = os.path.join(TEST_DIR, "book2.epub")
    with open(source, "w") as f:
        f.write("new content")
    kobo_root = os.path.join(TEST_DIR, "fake_kobo_root3")
    os.makedirs(kobo_root, exist_ok=True)
    # Pre-existing file with the same name already on the "Kobo"
    with open(os.path.join(kobo_root, "book2.epub"), "w") as f:
        f.write("existing content, must not be overwritten")

    dest = send_to_kobo(kobo_root, source)
    assert dest == os.path.join(kobo_root, "book2 (2).epub"), dest
    with open(os.path.join(kobo_root, "book2.epub")) as f:
        assert f.read() == "existing content, must not be overwritten"
    print("PASS: a filename collision on the Kobo is auto-numbered, doesn't overwrite")


def test_send_to_kobo_copy_failure_wrapped():
    source = os.path.join(TEST_DIR, "book3.epub")
    with open(source, "w") as f:
        f.write("content")

    def failing_copy(src, dst):
        raise OSError("disk full")

    try:
        send_to_kobo(os.path.join(TEST_DIR, "fake_kobo_root4"), source, copy_fn=failing_copy)
        assert False, "should have raised"
    except KoboSendError as exc:
        assert "disk full" in str(exc)
    print("PASS: a copy failure (e.g. disk full) is wrapped in a clear KoboSendError")


if __name__ == "__main__":
    test_find_connected_kobos_detects_one()
    test_find_connected_kobos_multiple()
    test_find_connected_kobos_none()
    test_find_connected_kobos_custom_drive_letters()
    test_send_to_kobo_copies_file()
    test_send_to_kobo_missing_source_raises()
    test_send_to_kobo_collision_auto_numbers()
    test_send_to_kobo_copy_failure_wrapped()
    print("\nALL KOBO USB TESTS PASSED")
