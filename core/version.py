"""
core/version.py

Single source of truth for the version info shown in the window title.

APP_VERSION format: YYYY-MM-DD#NN -- the date this build was produced,
and a counter for the Nth build delivered that day. Bump it by hand
whenever a new build is produced.

RELEASE_LABEL is the human-facing release designation (semantic-ish
version + stage), separate from the build identifier above.
"""

APP_NAME = "The \u018ePUB Redactor"  # "\u018e" = Ǝ, LATIN CAPITAL LETTER REVERSED E
RELEASE_LABEL = "v0.3 Public Beta (I \u2665 mobilism)"
APP_VERSION = "2026-09-04#01"
APP_REPO_URL = "https://github.com/erlbon/epubredactor"
