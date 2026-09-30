"""
core/epub_fingerprint.py

The content fingerprint stored in an EPUB's validation stamp (see
redactor_common.core.scan_stamp): a hash of the zip central directory's
(name, CRC32, size) for every entry EXCEPT the OPF, so it needs no data
reads and costs a few microseconds per book.

A raw-byte fingerprint would be wrong here: every save rewrites the OPF,
which shifts the bytes of everything after it. Leaving the OPF out means a
metadata-only save by this app keeps the stamp current, while a changed,
added or removed content file (chapter, image, stylesheet, toc) makes it
stale. The OPF itself is excluded because its bytes are what a save
legitimately changes (the stamp lives inside it).
"""

from __future__ import annotations

import hashlib
import zipfile
from typing import Iterable


def entries_fingerprint(entries: Iterable[tuple[str, int, int]], opf_path: str) -> str:
    """"<count>-<hash>" over (name, crc32, size) of every entry but the
    OPF, order-independent. `entries` is what a zip's infolist() yields,
    or the predicted list of a file about to be written."""
    rows = sorted((name, crc, size) for name, crc, size in entries if name != opf_path)
    digest = hashlib.sha256()
    for name, crc, size in rows:
        digest.update(f"{name}\0{crc:08x}\0{size}\n".encode("utf-8"))
    return f"{len(rows)}-{digest.hexdigest()[:16]}"


def zip_fingerprint(zf: zipfile.ZipFile, opf_path: str) -> str:
    return entries_fingerprint(((i.filename, i.CRC, i.file_size) for i in zf.infolist()), opf_path)


def file_fingerprint(path: str, opf_path: str) -> str:
    """Fingerprint of the EPUB at `path`, or "" when it can't be read."""
    try:
        with zipfile.ZipFile(path, "r") as zf:
            return zip_fingerprint(zf, opf_path)
    except (zipfile.BadZipFile, OSError):
        return ""
