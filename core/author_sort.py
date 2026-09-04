"""
core/author_sort.py

Naive, semicolon-per-author guesses between the Author(s) and Author
Sort fields -- "Firstname Lastname" <-> "Lastname, Firstname". Neither
direction is a real name parser (compound surnames, single names, and
non-Western name order all defeat the last-space/first-comma heuristic
they're built on), so both are meant as a starting point to review and
correct, not a final answer.
"""

from __future__ import annotations


def authors_to_author_sort(authors_str: str) -> str:
    """"Jane Q. Doe" -> "Doe, Jane Q.", per semicolon-separated author.
    Splits each name on its LAST space."""
    names = [n.strip() for n in authors_str.split(";") if n.strip()]
    result = []
    for name in names:
        if " " in name:
            first, last = name.rsplit(" ", 1)
            result.append(f"{last}, {first}")
        else:
            result.append(name)
    return "; ".join(result)


def author_sort_to_authors(author_sort_str: str) -> str:
    """The exact inverse of authors_to_author_sort(): "Doe, Jane Q." ->
    "Jane Q. Doe", per semicolon-separated entry. Splits each entry on
    its FIRST comma."""
    entries = [n.strip() for n in author_sort_str.split(";") if n.strip()]
    result = []
    for entry in entries:
        if "," in entry:
            last, first = entry.split(",", 1)
            last = last.strip()
            first = first.strip()
            result.append(f"{first} {last}" if first else last)
        else:
            result.append(entry)
    return "; ".join(result)
