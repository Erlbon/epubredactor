"""
core/author_clean.py

Clean-up of the Author(s) and Author Sort (opf:file-as) fields of a book:
real-world messes like "J.R.R.Tolkien", "Tolkien, J.R.R.", "Pratchett &
Gaiman", "Jane Doe (Editor)", "Jane Doe et al." or a missing / disagreeing
file-as. Pure logic, no Qt: shared by Repair > Clean Up Authors, the
Redact step and the duplicate finder (author_key).

Every rule is either SAFE (deterministic, loses nothing: applied by the
Redact step and ticked in the review) or REVIEW-ONLY (a guess a person
should look at: only applied when the caller passes allow_review=True, and
unticked in the review). clean_authors() reports what it did in `changes`
and what it held back in `review`.

Conventions (consistent with core/author_sort.py): Author(s) holds display
names "First Last"; Author Sort holds "Last, First" per author, aligned by
index (a name with a suffix is "Last, First, Jr."; a name with particles
keeps them with the surname: "van Gogh, Vincent"; a one-word name or a
corporate name is its own sort value). Initials are written spaced:
"J. R. R. Tolkien".

SAFE rules
  whitespace      stray / non-breaking / doubled spaces
  punctuation     stray leading/trailing punctuation, spacing around commas
  junk            role suffixes "(Editor)", ", translator", "Translated by",
                  "et al.", life dates "(1892-1973)"; a role-only entry is dropped
  split           "A; B" and "First Last & First Last" (every part two words+)
  flip            "Last, First" in Author(s) becomes "First Last"
  initials        "J.R.R.Tolkien" / "J R R Tolkien" -> "J. R. R. Tolkien"
  caps            "STEPHEN KING" -> "Stephen King" (plain names only)
  suffix          "Jr" -> "Jr."
  duplicate       the same author twice (order, case, punctuation, spacing)
  sort_fill       a missing file-as is generated
  sort_format     a file-as with sloppy spacing / initials is tidied
  sort_not_inverted  a file-as that is just the display name is inverted
REVIEW-ONLY rules
  split           a part is a single word ("Simon & Schuster")
  list_split      "Neil Gaiman, Terry Pratchett" (or "Last, First")
  honorific       "Dr." / ", PhD" removed
  caps            all-lowercase names, "MCDONALD" style names
  initials_caps   "JRR Tolkien" -> "J. R. R. Tolkien"
  sort_mismatch   the file-as disagrees with the author: regenerated
  sort_extra      file-as entries beyond the last author dropped
Flags (never applied): unusual characters left alone, an author list that
is only junk, an ambiguous comma list.
Corporate authors ("Simon & Schuster", "... Press", "... Inc."), placeholders
("Anonymous", "Various") and non-Latin names are left untouched.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Sequence

from redactor_common.core.local_db import normalize_words

# Surname particles: kept with the surname ("van Gogh, Vincent").
PARTICLES = frozenset({
    "van", "von", "der", "den", "de", "del", "della", "di", "da", "du", "des", "le", "la", "les", "el",
    "al", "bin", "ibn", "ter", "ten", "op", "dos", "das", "do", "zu", "zur", "af", "av", "y", "st",
})
SUFFIXES = {"jr": "Jr.", "sr": "Sr.", "ii": "II", "iii": "III", "iv": "IV"}
HONORIFIC_PREFIXES = frozenset({
    "dr", "prof", "professor", "mr", "mrs", "ms", "miss", "sir", "rev", "fr", "lady", "lord", "dame", "hon",
})
HONORIFIC_SUFFIXES = frozenset({"phd", "md", "msc", "dphil", "esq", "dds", "frs", "mba"})
PLACEHOLDERS = frozenset({
    "anonymous", "unknown", "various", "n a", "none", "unknown author", "various authors", "anon",
    "uncredited", "unknown artist",
})
CORPORATE_WORDS = frozenset({
    "inc", "incorporated", "ltd", "limited", "llc", "llp", "plc", "gmbh", "ag", "co", "corp", "corporation",
    "company", "press", "publishing", "publishers", "publisher", "publications", "books", "book",
    "university", "college", "school", "institute", "association", "society", "committee", "council",
    "department", "ministry", "magazine", "journal", "foundation", "group", "team", "staff", "editors",
    "editorial", "library", "museum", "agency", "bureau", "studio", "studios", "media", "network",
    "sons", "bros", "brothers", "verlag", "editions", "edizioni", "forlag", 
    "government", "commission", "organization", "organisation", "academy", "centre", "center", "fund",
    "service", "services", "labs", "software", "games", "comics", "entertainment",
    "international", "united", "national", "states", "nations", "authority", "administration",
})

_ROLE_WORD = (
    r"(?:editors?|eds?|translators?|translated|trans|illustrators?|illustrated|illus|foreword|introduction|"
    r"intro|afterword|preface|narrators?|narrated|photographer|contributors?|compiler|compiled|adapter|"
    r"adaptor|authors?|artist|cover\s+artist|contrib)"
)
_ROLES = rf"{_ROLE_WORD}\.?(?:\s*(?:,|and|&|/)\s*{_ROLE_WORD}\.?)*"
_ETAL = r"(?:et\.?\s*al\.?|and\s+others|and\s+co\.?)"
_YEARS = r"\d{3,4}\s*[-–—]\s*(?:\d{3,4})?"

# (rule name, pattern): each removes junk; applied until nothing changes.
_JUNK_PATTERNS = [
    re.compile(rf"\s*[\(\[]\s*{_ROLES}\s*[\)\]]", re.I),
    re.compile(rf"\s*(?:,|-|–|—)\s*{_ROLES}\s*$", re.I),
    re.compile(rf"^\s*(?:{_ROLE_WORD}\s+by|by)\s+", re.I),
    re.compile(rf"\s*(?:,\s*)?\b{_ETAL}\s*$", re.I),
    re.compile(rf"\s*,?\s*[\(\[]\s*{_YEARS}\s*[\)\]]\s*$"),
    re.compile(rf"\s*,?\s*{_YEARS}\s*$"),
    re.compile(r"\s*,?\s*[\(\[]\s*(?:b|d|born|died)\.?\s*\d{3,4}\s*[\)\]]\s*$", re.I),
]
_JUNK_ENTRY = re.compile(rf"^\s*(?:{_ROLES}|{_ETAL}|others|etc\.?)\s*$", re.I)
_ODD_SPACE_RE = re.compile("[  -​  　﻿\t]")
_EDGE_PUNCT = " ,;:-–—_|*\"“”<>/\\"
_JOIN_RE = re.compile(r"\s+(?:&|and)\s+")
_INITIAL_DOT_RE = re.compile(r"(?<![^\W\d_])([A-Z])\.(?=[^\W\d_])")
_INITIAL_TOKEN_RE = re.compile(r"^(?:[A-Za-z]\.)+$")
_ALLOWED_RE = re.compile(r"^[\w\s.,'’\-]+$")


# --- result types -------------------------------------------------------------


@dataclass
class Change:
    rule: str
    safe: bool
    detail: str

    def __str__(self) -> str:
        return f"{self.rule}: {self.detail}"


@dataclass
class AuthorResult:
    authors: list[str]
    author_sort: list[str]
    changes: list[Change] = field(default_factory=list)  # applied
    review: list[Change] = field(default_factory=list)  # held back (allow_review=False)
    flags: list[str] = field(default_factory=list)  # never applied, only reported
    changed: bool = False

    @property
    def needs_review(self) -> bool:
        """Review-only rules were applied, or held back, or something was flagged."""
        return any(not c.safe for c in self.changes) or bool(self.review) or bool(self.flags)

    @property
    def applied_review(self) -> bool:
        return any(not c.safe for c in self.changes)

    def summary(self) -> str:
        parts = [str(c) for c in self.changes] + [f"needs review - {c}" for c in self.review] + [
            f"flag - {f}" for f in self.flags]
        return "; ".join(parts)


class _Ctx:
    def __init__(self, allow_review: bool):
        self.allow_review = allow_review
        self.changes: list[Change] = []
        self.review: list[Change] = []
        self.flags: list[str] = []

    def gate(self, rule: str, safe: bool, detail: str) -> bool:
        """Record the rule; True when it may be applied."""
        if safe or self.allow_review:
            self.changes.append(Change(rule, safe, detail))
            return True
        self.review.append(Change(rule, safe, detail))
        return False

    def flag(self, text: str) -> None:
        if text not in self.flags:
            self.flags.append(text)


@dataclass
class _Name:
    kind: str  # "person" | "mono" | "opaque"
    given: str = ""
    surname: str = ""  # a mono name is kept here
    suffix: str = ""
    text: str = ""  # opaque: as it was

    @property
    def display(self) -> str:
        if self.kind == "opaque":
            return self.text
        return " ".join(p for p in (self.given, self.surname, self.suffix) if p)

    @property
    def sort(self) -> str:
        if self.kind == "opaque":
            return ""
        if self.kind == "mono":
            return " ".join(p for p in (self.surname, self.suffix) if p)
        return ", ".join(p for p in (self.surname, self.given, self.suffix) if p)


# --- small helpers --------------------------------------------------------------


def _bare(token: str) -> str:
    return token.replace(".", "").lower()


def _suffix_of(token: str) -> str:
    """The display form of a suffix token ("jr" -> "Jr."), "" when it is none."""
    return SUFFIXES.get(_bare(token), "")


def _is_script_without_order(text: str) -> bool:
    for ch in text:
        o = ord(ch)
        if (0x0590 <= o <= 0x0EFF or 0x1100 <= o <= 0x11FF or 0x2E80 <= o <= 0x9FFF
                or 0xAC00 <= o <= 0xD7AF or 0xF900 <= o <= 0xFAFF or 0xFF00 <= o <= 0xFFEF):
            return True
    return False


def _opaque_reason(text: str, joined_ok: bool = False) -> str:
    """Why the name is left untouched: "corporate", "placeholder", "script",
    "chars" (anything but letters, spaces, . , ' -), or "" for a person."""
    if normalize_words(text) in PLACEHOLDERS:
        return "placeholder"
    if _is_script_without_order(text):
        return "script"
    if not joined_ok and _JOIN_RE.search(text):
        return "corporate"  # a joiner that was not split ("Simon & Schuster")
    if set(normalize_words(text).split()) & CORPORATE_WORDS:
        return "corporate"
    if any(c.isdigit() for c in text) or not _ALLOWED_RE.match(text):
        return "chars"
    return ""


def _fmt_given(given: str) -> str:
    """Initials spaced and dotted: "J.R." / "J R" -> "J. R."."""
    given = _INITIAL_DOT_RE.sub(r"\1. ", given)
    return " ".join(t + "." if re.fullmatch(r"[A-Z]", t) else t for t in given.split())


def _particle(token: str) -> bool:
    return _bare(token) in PARTICLES


def _split_surname(tokens: list[str]) -> tuple[list[str], list[str]]:
    """(given tokens, surname tokens): the last word plus any particles
    directly before it, as long as a given name is left."""
    k = len(tokens) - 1
    while k - 1 >= 1 and _particle(tokens[k - 1]):
        k -= 1
    return tokens[:k], tokens[k:]


def _initials_only(text: str) -> bool:
    toks = text.split()
    return bool(toks) and all(re.fullmatch(r"[A-Za-z]\.?", t) or _INITIAL_TOKEN_RE.match(t) for t in toks)


def _comma_kind(segs: list[str]) -> str:
    """none | suffix | inverted | inverted_suffix | list2 | ambiguous"""
    n = len(segs)
    if n <= 1:
        return "none"
    if n == 2:
        if _suffix_of(segs[1]) and len(segs[1].split()) == 1:
            return "suffix"
        a, b = len(segs[0].split()), len(segs[1].split())
        first = segs[0].split()[0] if segs[0].split() else ""
        if a == 1 or _particle(first) or _initials_only(segs[1]) or b == 1:
            return "inverted"
        return "list2"
    if n == 3 and _suffix_of(segs[2]) and len(segs[2].split()) == 1:
        return "inverted_suffix" if _comma_kind(segs[:2]) == "inverted" else "ambiguous"
    return "ambiguous"


# --- cleaning one text ------------------------------------------------------------


def _clean_text(raw: str, ctx: _Ctx) -> str | None:
    """Whitespace, junk and punctuation cleaned. None when nothing is left
    or the entry is only a role / "et al."."""
    raw = raw or ""
    text = unicodedata.normalize("NFC", raw)
    text = " ".join(_ODD_SPACE_RE.sub(" ", text).split())
    if text != raw and raw:
        ctx.gate("whitespace", True, f"{raw!r} -> {text!r}")
    if not text:
        return None
    if _JUNK_ENTRY.match(text):
        return None
    before = text
    for _ in range(6):
        previous = text
        for pat in _JUNK_PATTERNS:
            text = pat.sub("", text).strip()
        if text == previous:
            break
    if text != before:
        ctx.gate("junk", True, f"{before!r} -> {text!r}")
    if not text:
        return None
    before = text
    text = text.strip(_EDGE_PUNCT)
    last = text.split()[-1] if text.split() else ""
    if last.endswith(".") and not _INITIAL_TOKEN_RE.match(last):
        core = last.rstrip(".")
        if len(core) >= 3 and "." not in core and _bare(core) not in SUFFIXES \
                and _bare(core) not in HONORIFIC_SUFFIXES and _bare(core) not in HONORIFIC_PREFIXES \
                and _bare(core) not in CORPORATE_WORDS:
            text = text[: -len(last)] + core
    text = re.sub(r"\s+,", ",", text)
    text = re.sub(r",(?=\S)", ", ", text)
    text = text.strip(_EDGE_PUNCT).strip()
    if text != before:
        ctx.gate("punctuation", True, f"{before!r} -> {text!r}")
    return text or None


# --- splitting an entry ------------------------------------------------------------


def _expand(text: str, ctx: _Ctx) -> list[str]:
    chunks = [c.strip() for c in text.split(";") if c.strip()]
    if len(chunks) > 1:
        ctx.gate("split", True, f"{text!r} -> {chunks}")
    parts: list[str] = []
    for chunk in chunks:
        if _opaque_reason(chunk, joined_ok=True) in ("corporate", "placeholder", "script"):
            parts.append(chunk)
            continue
        pieces = [p.strip() for p in _JOIN_RE.split(chunk) if p.strip()]
        sub = [chunk]
        if len(pieces) > 1:
            safe = all(len(p.split()) >= 2 for p in pieces)
            if ctx.gate("split", safe, f"{chunk!r} -> {pieces}"):
                sub = pieces
        for s in sub:
            parts.extend(_split_commas(s, ctx))
    return parts


def _split_commas(text: str, ctx: _Ctx) -> list[str]:
    segs = [s.strip() for s in text.split(",") if s.strip()]
    kind = _comma_kind(segs)
    if kind == "list2" or (kind == "ambiguous" and all(len(s.split()) >= 2 for s in segs)):
        if ctx.gate("list_split", False, f"{text!r} -> {segs}"):
            return segs
        ctx.flag(f"{text!r} could be several authors or 'Last, First'")
        return [text]
    if kind == "ambiguous":
        ctx.flag(f"{text!r} has commas that could not be read as a name")
    return [text]


# --- parsing one name ---------------------------------------------------------------


def _title_token(tok: str, keep_lower: bool) -> tuple[str, bool]:
    """(title-cased token, tricky): tricky = a Mc/Mac-style name or a letter
    run that might be initials, where a guess is not safe."""
    if re.fullmatch(r"[A-Za-z]\.?", tok) or _INITIAL_TOKEN_RE.match(tok):
        return tok.upper(), False
    if _bare(tok) in ("ii", "iii", "iv"):
        return tok.upper(), False
    if _bare(tok) in ("jr", "sr"):
        return tok[:1].upper() + tok[1:].lower(), False
    if keep_lower and _particle(tok):
        return tok.lower(), False
    tricky = bool(re.match(r"(?i)^mc[a-z]{2,}", tok)) or (
        len(tok) <= 3 and not re.search(r"(?i)[aeiouy]", tok) and tok.isalpha())
    parts = re.split(r"(['’\-])", tok)
    out = "".join(p.capitalize() if p.isalpha() else p for p in parts)
    return out, tricky


def _case_fix(given: str, surname: str, ctx: _Ctx) -> tuple[str, str]:
    whole = f"{given} {surname}".strip()
    letters = [c for c in whole if c.isalpha()]
    if not letters:
        return given, surname
    upper = whole == whole.upper()
    lower = whole == whole.lower()
    if not (upper or lower):
        return given, surname
    tricky = False

    def convert(text: str, first_idx: int) -> str:
        nonlocal tricky
        out = []
        for i, tok in enumerate(text.split()):
            new, t = _title_token(tok, keep_lower=(first_idx + i) > 0)
            tricky = tricky or t
            out.append(new)
        return " ".join(out)

    new_given = convert(given, 0)
    new_surname = convert(surname, len(given.split()))
    if (new_given, new_surname) == (given, surname):
        return given, surname
    single_word = len(whole.split()) == 1
    safe = upper and not tricky and not single_word
    which = "ALL CAPS" if upper else "all lowercase"
    if ctx.gate("caps", safe, f"{whole!r} ({which}) -> {(new_given + ' ' + new_surname).strip()!r}"):
        return new_given, new_surname
    return given, surname


def _expand_caps_initials(given: str, whole_upper: bool, ctx: _Ctx) -> str:
    if whole_upper:
        return given
    toks = given.split()
    new = []
    for t in toks:
        if 2 <= len(t) <= 3 and t.isalpha() and t.isupper() and t.lower() not in SUFFIXES:
            new.append(" ".join(c + "." for c in t))
        else:
            new.append(t)
    result = " ".join(new)
    if result != given and ctx.gate("initials_caps", False, f"{given!r} -> {result!r}"):
        return result
    return given


def _parse_part(text: str, ctx: _Ctx) -> _Name:
    reason = _opaque_reason(text)
    if reason:
        if reason == "chars":
            ctx.flag(f"{text!r} has unusual characters, left alone")
        return _Name("opaque", text=text)
    segs = [s.strip() for s in text.split(",") if s.strip()]
    kind = _comma_kind(segs)
    if kind in ("list2", "ambiguous"):
        return _Name("opaque", text=text)

    # honorifics: Dr. / PhD (review-only: "Dr. Seuss" is a real name)
    honorific = ""
    first_tokens = segs[0].split()
    if kind in ("none", "suffix") and len(first_tokens) >= 2 and _bare(first_tokens[0]) in HONORIFIC_PREFIXES:
        honorific = first_tokens[0]
        first_tokens = first_tokens[1:]
        segs[0] = " ".join(first_tokens)
    tail = segs[-1].split()
    if len(segs) >= 2 and len(tail) == 1 and _bare(tail[0]) in HONORIFIC_SUFFIXES:
        honorific = honorific or tail[0]
        segs = segs[:-1]
        kind = _comma_kind(segs)
    elif kind == "none" and len(first_tokens) >= 2 and _bare(first_tokens[-1]) in HONORIFIC_SUFFIXES:
        honorific = honorific or first_tokens[-1]
        first_tokens = first_tokens[:-1]
        segs[0] = " ".join(first_tokens)
    if honorific:
        if not ctx.gate("honorific", False, f"{text!r}: remove {honorific!r}"):
            ctx.flag(f"{text!r} has a title or degree ({honorific})")
            return _Name("opaque", text=text)

    suffix = ""
    if kind == "inverted_suffix":
        surname, given, suffix = segs[0], segs[1], segs[2]
        ctx.gate("flip", True, f"{text!r} -> First Last")
    elif kind == "inverted":
        surname, given = segs[0], segs[1]
        ctx.gate("flip", True, f"{text!r} -> First Last")
    else:
        if kind == "suffix":
            suffix = segs[1]
        tokens = segs[0].split()
        if len(tokens) >= 2 and _suffix_of(tokens[-1]) and not suffix:
            suffix = tokens[-1]
            tokens = tokens[:-1]
        text_before_dots = " ".join(tokens)
        spaced = _INITIAL_DOT_RE.sub(r"\1. ", text_before_dots)
        tokens = spaced.split()
        if len(tokens) == 1:
            surname, given = tokens[0], ""
        else:
            g, s = _split_surname(tokens)
            given, surname = " ".join(g), " ".join(s)
    whole_upper = f"{given} {surname}".strip() == f"{given} {surname}".strip().upper()

    given, surname = _case_fix(given, surname, ctx)
    if given:
        given = _expand_caps_initials(given, whole_upper, ctx)
        spaced = _fmt_given(given)
        if spaced != given:
            ctx.gate("initials", True, f"{given!r} -> {spaced!r}")
        given = spaced
    if suffix:
        norm = _suffix_of(suffix) or suffix
        if norm != suffix:
            ctx.gate("suffix", True, f"{suffix!r} -> {norm!r}")
        suffix = norm
    if not given:
        return _Name("mono", surname=surname, suffix=suffix)
    return _Name("person", given=given, surname=surname, suffix=suffix)


# --- the sort value --------------------------------------------------------------------


def _parse_sort(text: str) -> tuple[str, str, str] | None:
    """(surname, given, suffix) of "Last, First[, Jr.]"; a text with no comma
    is (text, "", "")."""
    segs = [s.strip() for s in text.split(",") if s.strip()]
    if len(segs) == 1:
        return segs[0], "", ""
    if len(segs) == 2:
        if _suffix_of(segs[1]) and len(segs[1].split()) == 1:
            return segs[0], "", segs[1]
        return segs[0], segs[1], ""
    if len(segs) == 3 and _suffix_of(segs[2]) and len(segs[2].split()) == 1:
        return segs[0], segs[1], segs[2]
    return None


def _words(text: str) -> list[str]:
    return normalize_words(text).split()


def _sort_agrees(name: _Name, parsed: tuple[str, str, str]) -> bool:
    s_sur, s_given, _s_suf = parsed
    name_tokens = _words(f"{name.given} {name.surname}")
    sur = _words(s_sur)
    if not sur or len(sur) > len(name_tokens) or name_tokens[len(name_tokens) - len(sur):] != sur:
        return False
    remaining = name_tokens[: len(name_tokens) - len(sur)]
    given = _words(s_given)
    if not remaining:
        return True  # the file-as may be richer than a surname-only name
    if len(given) < len(remaining):
        return False
    for have, want in zip(remaining, given):
        if have != want and not ((len(have) == 1 or len(want) == 1) and have[0] == want[0]):
            return False
    return True  # a longer given name in the file-as is fine


def _format_sort(parsed: tuple[str, str, str]) -> str:
    sur, given, suf = parsed
    given = _fmt_given(given) if given else ""
    suf = _suffix_of(suf) or suf
    return ", ".join(p for p in (sur, given, suf) if p)


def _decide_sort(name: _Name, sort_text: str, ctx: _Ctx) -> str:
    if name.kind == "opaque":
        return sort_text
    computed = name.sort
    if not sort_text:
        ctx.gate("sort_fill", True, f"{name.display!r} -> {computed!r}")
        return computed
    parsed = _parse_sort(sort_text)
    inverted = parsed is not None and "," in sort_text
    if parsed is not None and name.kind == "mono":
        if _words(parsed[0]) == _words(name.surname):
            fmt = _format_sort(parsed)
            if fmt != sort_text:
                ctx.gate("sort_format", True, f"{sort_text!r} -> {fmt!r}")
            return fmt
    elif parsed is not None and inverted and _sort_agrees(name, parsed):
        fmt = _format_sort(parsed)
        if fmt != sort_text:
            ctx.gate("sort_format", True, f"{sort_text!r} -> {fmt!r}")
        return fmt
    elif parsed is not None and not inverted and sorted(_words(sort_text)) == sorted(
            _words(f"{name.given} {name.surname}")):
        ctx.gate("sort_not_inverted", True, f"{sort_text!r} -> {computed!r}")
        return computed
    if ctx.gate("sort_mismatch", False, f"{name.display!r}: file-as {sort_text!r} -> {computed!r}"):
        return computed
    ctx.flag(f"{name.display!r}: author sort {sort_text!r} does not match the author")
    return sort_text


# --- keys ---------------------------------------------------------------------------------


def author_key(name: str) -> str:
    """An order-, case-, accent- and punctuation-independent key of one
    author for comparing: "Tolkien, J.R.R.", "J.R.R. Tolkien", "J. R. R.
    Tolkien" and "JRR Tolkien" all give "j r r tolkien". Words are sorted, so
    a misread 'Last, First' still agrees with its plain spelling."""
    text = unicodedata.normalize("NFC", name or "")
    toks = [t for t in re.split(r"[\s.,]+", text) if t]
    expand = len(toks) > 1 and text != text.upper()
    out: list[str] = []
    for t in toks:
        if expand and 2 <= len(t) <= 3 and t.isalpha() and t.isupper() and t.lower() not in SUFFIXES:
            out.extend(t)
        else:
            out.append(t)
    return " ".join(sorted(normalize_words(" ".join(out)).split()))


# --- the whole book ---------------------------------------------------------------------------


def _split_like(sort_text: str, n: int) -> list[str]:
    """The file-as of a split entry, cut the same way ("A, B & C, D"); blanks
    when it does not fit."""
    if n == 1:
        return [sort_text]
    pieces = [p.strip() for chunk in sort_text.split(";") for p in _JOIN_RE.split(chunk) if p.strip()]
    return pieces if len(pieces) == n else [""] * n


def clean_authors(authors: Sequence[str], author_sort: Sequence[str] = (), allow_review: bool = False) -> AuthorResult:
    """Clean the authors and their aligned sort values (see the module
    docstring for the rules). With allow_review False the review-only rules
    are only reported (`result.review`), never applied."""
    ctx = _Ctx(allow_review)
    authors = list(authors)
    sorts = list(author_sort)
    entries: list[tuple[_Name, str]] = []
    dropped: list[str] = []

    for i, raw in enumerate(authors):
        raw_sort = sorts[i] if i < len(sorts) else ""
        text = _clean_text(raw, ctx)
        sort_text = _clean_text(raw_sort, ctx) or ""
        if text is None:
            if (raw or "").strip():
                dropped.append(raw)
            continue
        parts = _expand(text, ctx)
        sort_parts = _split_like(sort_text, len(parts))
        for part, sort_part in zip(parts, sort_parts):
            name = _parse_part(part, ctx)
            entries.append((name, _decide_sort(name, sort_part, ctx)))

    if not entries:
        result = AuthorResult(list(authors), list(sorts))
        if dropped:
            result.flags.append(f"only role / placeholder entries ({', '.join(map(repr, dropped))}), left alone")
        return result
    for raw in dropped:
        ctx.gate("junk", True, f"{raw!r}: removed (a role or 'et al.', not a name)")

    seen: set[str] = set()
    out_names: list[_Name] = []
    out_sorts: list[str] = []
    for name, sort_text in entries:
        key = author_key(name.display)
        if key in seen:
            ctx.gate("duplicate", True, f"{name.display!r} listed twice")
            continue
        seen.add(key)
        out_names.append(name)
        out_sorts.append(sort_text)

    extras = [s for s in sorts[len(authors):] if s.strip()]
    if extras:
        if ctx.gate("sort_extra", False, f"author sort entries without an author: {extras}"):
            extras = []
        else:
            ctx.flag(f"author sort has entries without an author: {extras}")
    new_authors = [n.display for n in out_names]
    new_sorts = out_sorts + extras
    while new_sorts and not new_sorts[-1]:
        new_sorts.pop()
    old_sorts = list(sorts)
    while old_sorts and not old_sorts[-1]:
        old_sorts.pop()
    return AuthorResult(
        new_authors, new_sorts, ctx.changes, ctx.review, ctx.flags,
        changed=(new_authors != authors or new_sorts != old_sorts),
    )
