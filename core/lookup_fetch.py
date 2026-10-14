"""
core/lookup_fetch.py

The one thing epubredactor's online searches (Google Books, Open
Library) add on top of redactor_common's fetch_json(): when the service
cannot be reached at all, the message says "(check your internet
connection)", as it always has. fetch_json() has no way to word that
case (status_messages only covers HTTP status codes), so the shared
message's prefix is reworded here; everything else -- the 429 retries,
the HTTP status messages, the unreadable-response message and the
query-string redaction -- is redactor_common's.
"""

from __future__ import annotations

from redactor_common.core.lookup_client import fetch_json


def fetch_json_with_hint(url, fetch, error_cls, source_name: str, **kwargs):
    """fetch_json(url, fetch, error_cls, source_name, **kwargs), with
    "Could not reach <source>:" reworded to "Could not reach <source>
    (check your internet connection):"."""
    try:
        return fetch_json(url, fetch, error_cls, source_name, **kwargs)
    except error_cls as exc:
        prefix = f"Could not reach {source_name}:"
        message = str(exc)
        if not message.startswith(prefix):
            raise
        reworded = f"Could not reach {source_name} (check your internet connection):" + message[len(prefix):]
        raise error_cls(reworded) from exc.__cause__
