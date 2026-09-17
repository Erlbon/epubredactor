"""Tests for core/perf_log.py."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import core.perf_log as perf_log  # noqa: E402

TEST_DIR = "/tmp/epub_test_perf_log"
os.makedirs(TEST_DIR, exist_ok=True)


def _isolated_log_path():
    return os.path.join(TEST_DIR, "test_perf.log")


def test_disabled_by_default():
    assert not perf_log.is_enabled()
    print("PASS: performance logging is disabled by default")


def test_timed_writes_nothing_when_disabled():
    perf_log.set_enabled(False)
    path = _isolated_log_path()
    if os.path.exists(path):
        os.remove(path)
    orig_log_path = perf_log.log_path
    perf_log.log_path = lambda: path
    try:
        with perf_log.timed("should not appear"):
            time.sleep(0.001)
    finally:
        perf_log.log_path = orig_log_path
    assert not os.path.exists(path)
    print("PASS: timed() writes nothing at all when disabled")


def test_timed_writes_a_block_when_enabled():
    path = _isolated_log_path()
    if os.path.exists(path):
        os.remove(path)
    orig_log_path = perf_log.log_path
    perf_log.log_path = lambda: path
    perf_log.set_enabled(True)
    try:
        with perf_log.timed("a real section"):
            time.sleep(0.01)
    finally:
        perf_log.set_enabled(False)
        perf_log.log_path = orig_log_path
    assert os.path.exists(path)
    content = open(path, encoding="utf-8").read()
    assert "a real section:" in content
    assert "s" in content  # the seconds suffix
    print("PASS: timed() writes a block with the label and elapsed time when enabled")


def test_accumulator_collapses_many_calls_into_one_summary():
    path = _isolated_log_path()
    if os.path.exists(path):
        os.remove(path)
    orig_log_path = perf_log.log_path
    perf_log.log_path = lambda: path
    perf_log.set_enabled(True)
    try:
        acc = perf_log.Accumulator()
        for _ in range(50):
            with acc.section("per_row_work"):
                pass
        acc.dump("Test Rebuild Summary")
    finally:
        perf_log.set_enabled(False)
        perf_log.log_path = orig_log_path
    content = open(path, encoding="utf-8").read()
    assert "Test Rebuild Summary" in content
    assert "per_row_work: " in content
    assert "50 call(s)" in content
    # Only ONE summary block, not 50 individual lines.
    assert content.count("Test Rebuild Summary") == 1
    print("PASS: Accumulator collapses many section() calls into one summary block")


def test_accumulator_sorts_by_total_time_descending():
    path = _isolated_log_path()
    if os.path.exists(path):
        os.remove(path)
    orig_log_path = perf_log.log_path
    perf_log.log_path = lambda: path
    perf_log.set_enabled(True)
    try:
        acc = perf_log.Accumulator()
        with acc.section("fast"):
            pass
        with acc.section("slow"):
            time.sleep(0.02)
        acc.dump("Sorted Summary")
    finally:
        perf_log.set_enabled(False)
        perf_log.log_path = orig_log_path
    content = open(path, encoding="utf-8").read()
    assert content.index("slow:") < content.index("fast:")
    print("PASS: Accumulator.dump() lists sections slowest-total-time first")


def test_accumulator_dump_is_noop_when_disabled():
    path = _isolated_log_path()
    if os.path.exists(path):
        os.remove(path)
    orig_log_path = perf_log.log_path
    perf_log.log_path = lambda: path
    perf_log.set_enabled(False)
    acc = perf_log.Accumulator()
    with acc.section("x"):
        pass
    acc.dump("Should not appear")
    perf_log.log_path = orig_log_path
    assert not os.path.exists(path)
    print("PASS: Accumulator.dump() writes nothing when disabled")


def test_set_enabled_toggles_is_enabled():
    perf_log.set_enabled(True)
    assert perf_log.is_enabled()
    perf_log.set_enabled(False)
    assert not perf_log.is_enabled()
    print("PASS: set_enabled()/is_enabled() round-trip correctly")


if __name__ == "__main__":
    test_disabled_by_default()
    test_timed_writes_nothing_when_disabled()
    test_timed_writes_a_block_when_enabled()
    test_accumulator_collapses_many_calls_into_one_summary()
    test_accumulator_sorts_by_total_time_descending()
    test_accumulator_dump_is_noop_when_disabled()
    test_set_enabled_toggles_is_enabled()
    print("\nALL PERF LOG TESTS PASSED")
