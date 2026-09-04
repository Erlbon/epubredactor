"""
core/undo.py

A small bounded undo stack for in-memory metadata/cover edits (bulk
edits, single-cell edits, search & replace, cover add/replace/delete,
ISBN lookup apply).

Deliberately OUT of scope: physical file operations (Rename/Export,
Save). Those are already deliberate, explicitly-confirmed actions with
their own safety dialogs, and reverting a completed rename or overwrite
would mean re-touching the filesystem in ways that could surprise the
user or collide with changes made outside the app. Undo here only ever
restores in-memory state.
"""

from __future__ import annotations

import copy
from collections import deque
from dataclasses import dataclass

from core.epub_metadata import EpubBook, EpubMetadata


@dataclass
class _BookSnapshot:
    book: EpubBook
    metadata: EpubMetadata
    dirty: bool
    cover_bytes: bytes | None
    cover_mime: str
    cover_changed: bool
    cover_removed: bool


@dataclass
class UndoEntry:
    label: str
    snapshots: list[_BookSnapshot]


class UndoManager:
    def __init__(self, max_entries: int = 5):
        self._stack: deque[UndoEntry] = deque(maxlen=max_entries)

    def push(self, label: str, books: list[EpubBook]) -> None:
        """Call BEFORE mutating `books`, to capture their pre-change state.
        Pushing a 6th entry (beyond max_entries) silently drops the
        oldest one -- that's the "last N changes" behavior."""
        snapshots = [
            _BookSnapshot(
                book=b,
                metadata=copy.deepcopy(b.metadata),
                dirty=b.dirty,
                cover_bytes=b.cover_bytes,
                cover_mime=b.cover_mime,
                cover_changed=b.cover_changed,
                cover_removed=b.cover_removed,
            )
            for b in books
        ]
        self._stack.append(UndoEntry(label=label, snapshots=snapshots))

    def can_undo(self) -> bool:
        return bool(self._stack)

    def peek_label(self) -> str | None:
        return self._stack[-1].label if self._stack else None

    def undo(self) -> list[EpubBook]:
        """Restore the most recently pushed entry. Returns the list of
        books that were restored (empty if there was nothing to undo)."""
        if not self._stack:
            return []
        entry = self._stack.pop()
        affected = []
        for snap in entry.snapshots:
            snap.book.metadata = snap.metadata
            snap.book.dirty = snap.dirty
            snap.book.cover_bytes = snap.cover_bytes
            snap.book.cover_mime = snap.cover_mime
            snap.book.cover_changed = snap.cover_changed
            snap.book.cover_removed = snap.cover_removed
            affected.append(snap.book)
        return affected
