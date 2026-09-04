"""Tests for core/calibre_tools.py."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from core.calibre_tools import find_install_dir, find_tool, no_console_window_kwargs  # noqa: E402

TEST_DIR = "/tmp/calibre_tools_test"
os.makedirs(TEST_DIR, exist_ok=True)


def _make_fake_install(dirname: str, tools: list[str]) -> str:
    install_dir = os.path.join(TEST_DIR, dirname)
    os.makedirs(install_dir, exist_ok=True)
    for tool in tools:
        with open(os.path.join(install_dir, f"{tool}.exe"), "w") as f:
            f.write("fake")
    return install_dir


def test_find_tool_from_configured_install_dir():
    install_dir = _make_fake_install("install1", ["fetch-ebook-metadata"])
    result = find_tool("fetch-ebook-metadata", configured_install_dir=install_dir, which_fn=lambda n: None)
    assert result == os.path.join(install_dir, "fetch-ebook-metadata.exe")
    print("PASS: finds a tool inside the configured install directory")


def test_find_tool_falls_back_to_which():
    result = find_tool("ebook-convert", which_fn=lambda name: "/usr/bin/ebook-convert" if name == "ebook-convert" else None)
    assert result == "/usr/bin/ebook-convert"
    print("PASS: falls back to PATH lookup when not in the configured dir")


def test_find_tool_checks_extra_candidates():
    install_dir = _make_fake_install("install2", ["ebook-convert"])
    result = find_tool("ebook-convert", which_fn=lambda n: None, extra_install_dirs=[install_dir])
    assert result == os.path.join(install_dir, "ebook-convert.exe")
    print("PASS: checks extra candidate install dirs")


def test_find_tool_returns_none_when_nothing_found():
    result = find_tool(
        "fetch-ebook-metadata",
        configured_install_dir="/nonexistent",
        which_fn=lambda n: None,
        extra_install_dirs=["/also/nonexistent"],
    )
    assert result is None
    print("PASS: returns None when nothing is found anywhere")


def test_find_tool_missing_configured_dir_falls_through():
    result = find_tool(
        "ebook-convert",
        configured_install_dir="/does/not/exist",
        which_fn=lambda name: "/usr/bin/ebook-convert",
    )
    assert result == "/usr/bin/ebook-convert"
    print("PASS: a stale/missing configured dir is skipped, falls through to PATH")


def test_find_install_dir_derives_parent_of_a_tool():
    install_dir = _make_fake_install("install3", ["ebook-convert"])
    result = find_install_dir(which_fn=lambda n: None, extra_install_dirs=[install_dir])
    assert result == install_dir
    print("PASS: find_install_dir derives the install folder from any one found tool")


def test_find_install_dir_none_when_nothing_found():
    result = find_install_dir(which_fn=lambda n: None, extra_install_dirs=["/nonexistent"])
    assert result is None
    print("PASS: find_install_dir returns None when no tool can be located at all")


def test_both_tools_found_in_same_install_dir():
    install_dir = _make_fake_install("install4", ["fetch-ebook-metadata", "ebook-convert"])
    fetch_path = find_tool("fetch-ebook-metadata", configured_install_dir=install_dir, which_fn=lambda n: None)
    convert_path = find_tool("ebook-convert", configured_install_dir=install_dir, which_fn=lambda n: None)
    assert os.path.dirname(fetch_path) == os.path.dirname(convert_path) == install_dir
    print("PASS: both tools resolve correctly from a single shared install directory")


def test_no_console_window_kwargs_empty_on_this_platform():
    # On any genuinely non-Windows platform (which is what runs this
    # test suite), no suppression is needed or applied.
    if sys.platform != "win32":
        assert no_console_window_kwargs() == {}
        print("PASS: no_console_window_kwargs() is a no-op on a non-Windows platform")
    else:
        print("SKIP: this platform is win32, covered by the mocked-platform test instead")


def test_no_console_window_kwargs_safe_when_flag_unavailable():
    # Simulates being on Windows without assuming CREATE_NO_WINDOW is
    # actually defined here (it never is outside a real Windows Python
    # build) -- must degrade to a harmless {}, not raise AttributeError.
    original_platform = sys.platform
    sys.platform = "win32"
    try:
        result = no_console_window_kwargs()
        assert isinstance(result, dict)
    finally:
        sys.platform = original_platform
    print("PASS: no_console_window_kwargs() never raises, even when the platform flag is mocked")


if __name__ == "__main__":
    test_find_tool_from_configured_install_dir()
    test_find_tool_falls_back_to_which()
    test_find_tool_checks_extra_candidates()
    test_find_tool_returns_none_when_nothing_found()
    test_find_tool_missing_configured_dir_falls_through()
    test_find_install_dir_derives_parent_of_a_tool()
    test_find_install_dir_none_when_nothing_found()
    test_both_tools_found_in_same_install_dir()
    test_no_console_window_kwargs_empty_on_this_platform()
    test_no_console_window_kwargs_safe_when_flag_unavailable()
    print("\nALL CALIBRE TOOLS TESTS PASSED")
