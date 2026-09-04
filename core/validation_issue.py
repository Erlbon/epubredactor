"""
core/validation_issue.py

Plain data types for EPUB validation results. Kept dependency-free (no
import of core.epub_metadata) so it can sit underneath EpubBook without
any circular-import concerns.
"""

from __future__ import annotations

from dataclasses import dataclass

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
# DRM-protected is deliberately its own severity, not an error: the file
# itself is perfectly valid and readable (by something with the right
# keys) -- it's just off-limits to editing by this tool. Lumping it in
# with genuine corruption under INVALID would be misleading.
SEVERITY_LOCKED = "locked"

STATUS_OK = "OK"
STATUS_ISSUES = "ISSUES"
STATUS_DRM = "DRM"
STATUS_INVALID = "INVALID"

# Priority order when multiple severities are present in the same book's
# issue list -- the worst one wins. A book that's both DRM-protected AND
# has a genuine structural error (e.g. a missing manifest file) still
# shows INVALID, since that's the more fundamental problem.
_SEVERITY_TO_STATUS = {
    SEVERITY_ERROR: STATUS_INVALID,
    SEVERITY_LOCKED: STATUS_DRM,
    SEVERITY_WARNING: STATUS_ISSUES,
}
_STATUS_PRIORITY = [STATUS_INVALID, STATUS_DRM, STATUS_ISSUES, STATUS_OK]


@dataclass
class ValidationIssue:
    code: str
    severity: str  # SEVERITY_ERROR, SEVERITY_WARNING, or SEVERITY_LOCKED
    message: str
    fixable: bool = False


def status_for_issues(issues: list[ValidationIssue]) -> str:
    """The worst status implied by this book's issues, per the priority
    order above. OK if there are none."""
    statuses = {_SEVERITY_TO_STATUS.get(i.severity, STATUS_ISSUES) for i in issues}
    for status in _STATUS_PRIORITY:
        if status in statuses:
            return status
    return STATUS_OK
