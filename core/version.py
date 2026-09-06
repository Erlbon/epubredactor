"""
core/version.py

Single source of truth for the version info shown in the window title.

APP_VERSION format: YYYY-MM-DD#NN -- the date this build was produced,
and a counter for the Nth build delivered that day. Bump it by hand
whenever a new build is produced.

RELEASE_LABEL is the human-facing release designation (semantic-ish
version + stage), separate from the build identifier above. Empty for
now -- the "Public Beta" tagline was dropped for a unified appearance
across the three sibling projects, none of which carry a stage/tagline
in their title bar or About dialog.
"""

APP_NAME = "The \u018ePUB Redactor"  # "\u018e" = Ǝ, LATIN CAPITAL LETTER REVERSED E
RELEASE_LABEL = ""
APP_VERSION = "2026-09-06#01"
APP_REPO_URL = "https://github.com/erlbon/epubredactor"
