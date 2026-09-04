#!/usr/bin/env python3
"""
bump_version.py

Maintainer utility -- run this immediately before packaging each
delivery, instead of hand-editing core/version.py's APP_VERSION string.

Why this exists: the previous process was "Claude types the date it
believes today to be" -- which drifted stale more than once across a
long development session (the date got frozen while only the trailing
counter kept incrementing, sometimes for many deliveries in a row,
because nothing ever re-checked the actual calendar). This script
removes that failure mode structurally by reading the date from the
system clock (datetime.date.today()) instead of anyone's memory of
what day it is.

Behavior: if today's date matches what's already stored in
APP_VERSION, the counter increments (another build today). If it's a
new day, the counter resets to #01. Either way, the date portion is
never typed by hand again.

Usage:
    python3 bump_version.py
"""

from __future__ import annotations

import datetime
import re
import sys
from pathlib import Path

VERSION_FILE = Path(__file__).parent / "core" / "version.py"
VERSION_PATTERN = re.compile(r'APP_VERSION = "(\d{4}-\d{2}-\d{2})#(\d+)"')


def main() -> None:
    today = datetime.date.today().isoformat()  # from the actual system clock, not typed by hand

    text = VERSION_FILE.read_text(encoding="utf-8")
    match = VERSION_PATTERN.search(text)
    if not match:
        print(
            f"ERROR: no APP_VERSION line matching the expected "
            f'"YYYY-MM-DD#NN" format found in {VERSION_FILE}',
            file=sys.stderr,
        )
        sys.exit(1)

    stored_date, stored_counter = match.group(1), int(match.group(2))
    new_counter = stored_counter + 1 if stored_date == today else 1
    new_version = f"{today}#{new_counter:02d}"

    new_text = VERSION_PATTERN.sub(f'APP_VERSION = "{new_version}"', text, count=1)
    VERSION_FILE.write_text(new_text, encoding="utf-8")

    old_version = f"{stored_date}#{stored_counter:02d}"
    if stored_date == today:
        print(f"Same-day build: {old_version} -> {new_version}")
    else:
        print(f"New day (was stuck on {stored_date}): {old_version} -> {new_version}")


if __name__ == "__main__":
    main()
