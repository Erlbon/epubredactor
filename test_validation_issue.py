"""Tests for core/validation_issue.py."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from core.validation_issue import (  # noqa: E402
    SEVERITY_LOCKED,
    STATUS_DRM,
    STATUS_INVALID,
    STATUS_ISSUES,
    STATUS_OK,
    ValidationIssue,
    status_for_issues,
)


def test_no_issues_is_ok():
    assert status_for_issues([]) == STATUS_OK
    print("PASS: no issues -> OK")


def test_only_warnings_is_issues():
    issues = [ValidationIssue("X", "warning", "minor thing")]
    assert status_for_issues(issues) == STATUS_ISSUES
    print("PASS: only warnings -> ISSUES")


def test_any_error_is_invalid():
    issues = [
        ValidationIssue("A", "warning", "minor"),
        ValidationIssue("B", "error", "serious"),
    ]
    assert status_for_issues(issues) == STATUS_INVALID
    print("PASS: any error present -> INVALID, even alongside warnings")


def test_locked_severity_is_its_own_status():
    issues = [ValidationIssue("DRM_DETECTED", SEVERITY_LOCKED, "protected")]
    assert status_for_issues(issues) == STATUS_DRM
    print("PASS: SEVERITY_LOCKED maps to its own DRM status, not INVALID")


def test_locked_plus_warning_is_still_drm():
    issues = [
        ValidationIssue("DRM_DETECTED", SEVERITY_LOCKED, "protected"),
        ValidationIssue("NO_TOC", "warning", "no toc"),
    ]
    assert status_for_issues(issues) == STATUS_DRM
    print("PASS: DRM outranks plain warnings")


def test_error_outranks_locked():
    issues = [
        ValidationIssue("DRM_DETECTED", SEVERITY_LOCKED, "protected"),
        ValidationIssue("MANIFEST_FILE_MISSING", "error", "broken"),
    ]
    assert status_for_issues(issues) == STATUS_INVALID
    print("PASS: a genuine error still outranks DRM -- the worse problem wins")


if __name__ == "__main__":
    test_no_issues_is_ok()
    test_only_warnings_is_issues()
    test_any_error_is_invalid()
    test_locked_severity_is_its_own_status()
    test_locked_plus_warning_is_still_drm()
    test_error_outranks_locked()
    print("\nALL VALIDATION ISSUE TESTS PASSED")
