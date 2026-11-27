"""
core/xml_text.py

Characters XML 1.0 cannot hold. lxml refuses a string with NUL, most other
control characters, lone surrogates or U+FFFE/U+FFFF, so one such character
in a field (typed, pasted from a PDF, or in a lookup answer or a dump)
would make the whole save fail. Strip them before they reach the OPF.
"""

from __future__ import annotations

import re

# Tab, line feed and carriage return are allowed; every other C0 control is not.
_XML_ILLEGAL_RE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]")


def strip_xml_illegal(text: str) -> str:
    """`text` without the characters XML 1.0 forbids (anything else unchanged)."""
    if not text:
        return text
    return _XML_ILLEGAL_RE.sub("", text)
