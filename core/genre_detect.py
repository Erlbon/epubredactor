"""
core/genre_detect.py

Suggests genres for a book from four places it commonly already says
what it is:

- its folder path (".../Fantasy/Epic/...", ".../Sci-Fi/...") and any
  bracketed tag in its filename ("Dune [Science Fiction].epub"),
- its description ("a gripping psychological thriller", "the first
  novel in an epic fantasy series"),
- its first few pages, same text the metadata content scan reads (see
  core/content_scan.py): Library of Congress CIP subject headings
  ("1. Science fiction. 2. Space warfare--Fiction."), BISAC-style subject
  lines ("FICTION / Fantasy / Epic") and "This is a work of fiction.",
- its DDC classification, when it has one (823 -> Fiction, 641 ->
  Cooking, 920 -> Biography, ...).

Same "find candidates, human decides" rule as the content scan: every
result is a suggestion only. Suggestions never include a genre the book
already has, and applying them only ever ADDS to the Genre field (see
core/genres.add_genres) -- nothing here replaces or removes an existing
genre tag.

Only genres in the caller's vocabulary (the Genre quick-pick list:
visible defaults plus custom genres) are ever suggested, so a default
genre the user hid in Settings > Add/Remove Genres is never proposed,
and a custom genre is matched by its own name.

Description and first-page text are matched conservatively: an
ambiguous word like "history", "war" or "romance" only counts when it
reads as a genre ("a war novel", "romance series"), not as an ordinary
word in a plot summary. Folder names are matched loosely, since a
folder called "Romance" is a deliberate label.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Iterable

from core.genres import COMMON_GENRES

SOURCE_FOLDER = "folder"
SOURCE_FILENAME = "filename"
SOURCE_DESCRIPTION = "description"
SOURCE_CONTENT = "first pages"
SOURCE_DDC = "DDC"

# How many trailing folders of a book's path count as labels. Deeper
# ancestors (drive, user folder, "Download", ...) aren't genre labels.
PATH_FOLDER_DEPTH = 3

_SNIPPET_RADIUS = 40


@dataclass
class GenreSuggestion:
    genre: str
    sources: list[tuple[str, str]] = field(default_factory=list)  # (source, matched text)

    @property
    def source_kinds(self) -> list[str]:
        kinds: list[str] = []
        for source, _snippet in self.sources:
            if source not in kinds:
                kinds.append(source)
        return kinds

    def describe(self) -> str:
        """'Fantasy (folder, description)' -- for the review table."""
        return f"{self.genre} ({', '.join(self.source_kinds)})"


# ----------------------------------------------------------------------
# Pattern tables. Keys must be names from COMMON_GENRES; a key missing
# from the caller's vocabulary is simply never suggested. Regexes are
# case-insensitive and get word boundaries added around them.

# Unambiguous on their own, anywhere (description, folder names).
_STRONG: dict[str, list[str]] = {
    "Science Fiction": [r"science[\s\-]fiction", r"sci[\s\-]?fi"],
    "Hard Science Fiction": [r"hard (?:science[\s\-]fiction|sci[\s\-]?fi|sf)"],
    "Space Opera": [r"space[\s\-]operas?"],
    "Cyberpunk": [r"cyberpunk"],
    "Dystopian": [r"dystopian", r"dystopias?"],
    "Post-Apocalyptic": [r"post[\s\-]?apocalyptic"],
    "Military Science Fiction": [r"military (?:science[\s\-]fiction|sci[\s\-]?fi|sf)"],
    "Alternate History": [r"alternate[\s\-]history", r"alternative[\s\-]history"],
    "First Contact": [r"first[\s\-]contact novel"],
    "Epic Fantasy": [r"epic fantasy"],
    "High Fantasy": [r"high fantasy"],
    "Dark Fantasy": [r"dark fantasy"],
    "Urban Fantasy": [r"urban fantasy"],
    "Sword & Sorcery": [r"sword (?:&|and) sorcery"],
    "Portal Fantasy": [r"portal fantasy"],
    "Fantasy Romance": [r"fantasy romance", r"romantasy"],
    "Fairy Tale Retelling": [r"fairy[\s\-]?tale retellings?", r"retelling of (?:the )?(?:classic )?fairy[\s\-]?tale"],
    "Magical Realism": [r"magic(?:al)? realism"],
    "Cozy Mystery": [r"cozy mystery", r"cosy mystery", r"cozy mysteries", r"cosy mysteries"],
    "Police Procedural": [r"police procedurals?"],
    "Psychological Thriller": [r"psychological thrillers?", r"psychological suspense"],
    "Legal Thriller": [r"legal thrillers?", r"courtroom (?:drama|thriller)s?"],
    "Spy Thriller": [r"spy (?:thriller|novel|story)s?", r"espionage (?:thriller|novel)s?"],
    "Thriller": [r"thrillers?"],
    "Mystery": [r"whodunn?its?", r"murder myster(?:y|ies)"],
    "Detective": [r"detective (?:novel|story|stories|fiction|series)"],
    "True Crime": [r"true[\s\-]crime"],
    "Noir": [r"noir"],
    "Heist": [r"heist (?:novel|thriller|story|caper)s?"],
    "Romantic Suspense": [r"romantic suspense"],
    "Romantic Comedy": [r"romantic comed(?:y|ies)", r"rom[\s\-]?com"],
    "Paranormal Romance": [r"paranormal romance"],
    "Historical Romance": [r"historical romance", r"regency romance"],
    "Contemporary Romance": [r"contemporary romance"],
    "Erotica": [r"erotica", r"erotic (?:novel|fiction|romance)"],
    "Ghost Story": [r"ghost stor(?:y|ies)"],
    "Gothic": [r"gothic (?:novel|horror|romance|tale|fiction)s?"],
    "Coming of Age": [r"coming[\s\-]of[\s\-]age"],
    "Young Adult": [r"young[\s\-]adult", r"YA (?:novel|fantasy|fiction|series)"],
    "Middle Grade": [r"middle[\s\-]grade"],
    "New Adult": [r"new[\s\-]adult (?:novel|romance|fiction)"],
    "Historical Fiction": [r"historical (?:novel|fiction|saga)s?"],
    "Literary Fiction": [r"literary (?:novel|fiction)"],
    "Graphic Novel": [r"graphic novels?"],
    "Light Novel": [r"light novels?"],
    "Novella": [r"novellas?"],
    "Short Stories": [r"short[\s\-]stor(?:y|ies) collection", r"collection of (?:\w+ )?(?:short )?stories"],
    "Anthology": [r"anthology", r"anthologies"],
    "Poetry": [r"poetry collection", r"collection of (?:\w+ )?poe(?:ms|try)", r"book of poems"],
    "Memoir": [r"memoirs?"],
    "Autobiography": [r"autobiograph(?:y|ies)"],
    "Biography": [r"biograph(?:y|ies)"],
    "Military History": [r"military history"],
    "Self-Help": [r"self[\s\-]help"],
    "Cooking": [r"cookbooks?", r"cookery"],
    "Travel": [r"travel(?:ogue| guide| writing| memoir)s?"],
    "Language Learning": [r"language learning"],
    "Romance": [r"love stor(?:y|ies)", r"romance novels?"],
    "Essays": [r"essay collection", r"collection of (?:\w+ )?essays"],
    "Letters & Diaries": [r"(?:collected|selected) letters", r"diaries of"],
    "Western": [r"westerns?(?= (?:novel|story|stories|series|saga|classic|adventure))"],
}

# Ambiguous words that only count as a genre in genre-like context:
# followed by a "kind of book" noun ("romance novel", "crime series"),
# optionally with one word between ("horror comedy novel").
_CONTEXTUAL: dict[str, list[str]] = {
    "Fantasy": [r"fantasy"],
    "Science Fiction": [r"sf"],
    "Mystery": [r"myster(?:y|ies)"],
    "Crime": [r"crime"],
    "Horror": [r"horror"],
    "Romance": [r"romance"],
    "Adventure": [r"adventure"],
    "Action": [r"action"],
    "War": [r"war"],
    "Supernatural": [r"supernatural"],
    "Survival": [r"survival"],
    "Humor": [r"humou?r(?:ous)?"],
    "Satire": [r"satir(?:e|ical)"],
    "Time Travel": [r"time[\s\-]travel"],
    "Contemporary Fiction": [r"contemporary"],
    "Women's Fiction": [r"women'?s"],
    "Drama": [r"drama"],
    "Children's": [r"children'?s"],
}
_CONTEXT_NOUNS = (
    r"(?:novels?|novellas?|series|sagas?|trilogy|trilogies|books?|stor(?:y|ies)|fiction|tales?"
    r"|thrillers?|epics?|romances?|classics?|debut|yarns?)"
)

# Extra names that only make sense as a folder label.
_FOLDER_ALIASES: dict[str, list[str]] = {
    "Science Fiction": [r"sf", r"scifi", r"sff"],
    "Fantasy": [r"sff"],
    "Nonfiction": [r"non[\s\-]?fiction"],
    "Fiction": [r"novels"],
    "Young Adult": [r"ya"],
    "Short Stories": [r"short[\s\-]?stories"],
    "Children's": [r"kids", r"childrens"],
    "Biography": [r"biographies", r"bio"],
    "Mystery": [r"mysteries"],
    "Religion & Spirituality": [r"religion", r"spirituality"],
    "Health & Wellness": [r"health", r"wellness"],
    "Art & Design": [r"art", r"design"],
    "Crafts & Hobbies": [r"crafts", r"hobbies"],
    "Sports & Recreation": [r"sports?"],
    "Film & Media": [r"film", r"movies"],
    "Letters & Diaries": [r"letters", r"diaries"],
    "Cooking": [r"cookbooks?", r"recipes", r"food"],
}

# Library of Congress genre/subject headings (CIP data on a copyright
# page: "Space warfare--Fiction.") and BISAC-style "FICTION / ..."
# subject lines, for the first-page scan. URLs are blanked out of the
# text first so ".../history/..." can't read as a subject line.
_DASH = r"(?:--|—|–)"
_CATALOG_HEADINGS: dict[str, list[str]] = {
    "Science Fiction": [r"science fiction\.", r"fiction\s*/\s*science fiction"],
    "Space Opera": [r"space opera(?: \(fiction\))?\.", r"fiction\s*/\s*science fiction\s*/\s*space opera"],
    "Military Science Fiction": [r"fiction\s*/\s*science fiction\s*/\s*military"],
    "Cyberpunk": [r"fiction\s*/\s*science fiction\s*/\s*cyberpunk"],
    "Dystopian": [r"dystopias\.", r"fiction\s*/\s*dystopian"],
    "Fantasy": [r"fantasy fiction\.", r"fiction\s*/\s*fantasy"],
    "Epic Fantasy": [r"fiction\s*/\s*fantasy\s*/\s*epic"],
    "Urban Fantasy": [r"fiction\s*/\s*fantasy\s*/\s*urban"],
    "Dark Fantasy": [r"fiction\s*/\s*fantasy\s*/\s*dark"],
    "Mystery": [r"detective and mystery (?:fiction|stories)\.", r"fiction\s*/\s*mystery"],
    "Cozy Mystery": [r"fiction\s*/\s*mystery (?:&|and) detective\s*/\s*cozy"],
    "Police Procedural": [r"fiction\s*/\s*mystery (?:&|and) detective\s*/\s*police procedural"],
    "Thriller": [r"thrillers \(fiction\)\.", r"suspense fiction\.", r"fiction\s*/\s*thrillers"],
    "Psychological Thriller": [r"psychological fiction\.", r"fiction\s*/\s*thrillers\s*/\s*psychological"],
    "Legal Thriller": [r"legal stories\.", r"fiction\s*/\s*thrillers\s*/\s*legal"],
    "Spy Thriller": [r"spy stories\.", r"fiction\s*/\s*thrillers\s*/\s*espionage"],
    "Horror": [r"horror (?:fiction|tales)\.", r"fiction\s*/\s*horror"],
    "Ghost Story": [r"ghost stories\."],
    "Romance": [r"love stories\.", r"romance fiction\.", r"fiction\s*/\s*romance"],
    "Historical Romance": [r"fiction\s*/\s*romance\s*/\s*historical"],
    "Paranormal Romance": [r"fiction\s*/\s*romance\s*/\s*paranormal"],
    "Contemporary Romance": [r"fiction\s*/\s*romance\s*/\s*contemporary"],
    "Historical Fiction": [r"historical fiction\.", r"fiction\s*/\s*historical"],
    "Adventure": [r"adventure stories\.", r"fiction\s*/\s*action (?:&|and) adventure"],
    "War": [r"war stories\.", r"fiction\s*/\s*war (?:&|and) military"],
    "Western": [r"western stories\.", r"fiction\s*/\s*westerns?"],
    "Humor": [r"humorous (?:fiction|stories)\.", r"fiction\s*/\s*humorous"],
    "Short Stories": [r"short stories\.", r"fiction\s*/\s*short stories"],
    "Young Adult": [r"young adult fiction\s*/"],
    "Literary Fiction": [r"fiction\s*/\s*literary"],
    "Coming of Age": [r"fiction\s*/\s*coming of age", r"bildungsromans\."],
    "Alternate History": [r"alternative histories \(fiction\)\.", r"fiction\s*/\s*alternative history"],
    "Biography": [r"biography\s*(?:&|and)\s*autobiography\s*/", rf"{_DASH}\s*biography\."],
    "Memoir": [r"biography (?:&|and) autobiography\s*/\s*personal memoirs"],
    "Poetry": [r"poetry\s*/\s*[a-z]", rf"{_DASH}\s*poetry\."],
    "History": [r"history\s*/\s*[a-z]"],
    "Cooking": [r"cooking\s*/\s*[a-z]", r"cookery\."],
    "Self-Help": [r"self-help\s*/\s*[a-z]", r"self-help techniques\."],
    "True Crime": [r"true crime\s*/\s*[a-z]"],
    "Fiction": [r"this (?:book )?is a work of fiction", rf"{_DASH}\s*fiction\.", r"fiction\s*/\s*general"],
}

# DDC ranges, most specific first. Only broad, reliable mappings.
_DDC_RULES: list[tuple[float, float, str]] = [
    (4.0, 6.999, "Technology"),
    (150.0, 159.999, "Psychology"),
    (100.0, 199.999, "Philosophy"),
    (200.0, 289.999, "Religion & Spirituality"),
    (290.0, 299.999, "Mythology"),
    (320.0, 329.999, "Politics"),
    (332.0, 332.999, "Finance"),
    (330.0, 339.999, "Economics"),
    (340.0, 349.999, "Law"),
    (364.1, 364.199, "True Crime"),
    (370.0, 379.999, "Education"),
    (300.0, 399.999, "Social Science"),
    (400.0, 499.999, "Language Learning"),
    (510.0, 519.999, "Mathematics"),
    (500.0, 599.999, "Science"),
    (613.0, 613.999, "Health & Wellness"),
    (610.0, 619.999, "Medicine"),
    (635.0, 635.999, "Gardening"),
    (641.0, 641.999, "Cooking"),
    (649.0, 649.999, "Parenting"),
    (650.0, 659.999, "Business"),
    (600.0, 699.999, "Technology"),
    (745.0, 746.999, "Crafts & Hobbies"),
    (770.0, 779.999, "Photography"),
    (780.0, 789.999, "Music"),
    (791.4, 791.499, "Film & Media"),
    (796.0, 799.999, "Sports & Recreation"),
    (700.0, 769.999, "Art & Design"),
    (910.0, 919.999, "Travel"),
    (920.0, 929.999, "Biography"),
    (930.0, 999.999, "History"),
    (900.0, 909.999, "History"),
]
# Literature (800s): the third digit is the form, in every language's
# own subdivision (811 American poetry, 823 English fiction, ...).
_DDC_LITERATURE_FORMS = {
    "1": "Poetry",
    "2": "Drama",
    "3": "Fiction",
    "4": "Essays",
    "6": "Letters & Diaries",
    "7": "Humor",
}

_DDC_RE = re.compile(r"^\s*(\d{3})(?:\.(\d+))?")
_BRACKETED_RE = re.compile(r"[\[(]([^\[\]()]{2,60})[\])]")


def _wb(pattern: str) -> str:
    return rf"(?<![\w'])(?:{pattern})(?![\w'])"


def _compile(patterns: Iterable[str]) -> list[re.Pattern]:
    return [re.compile(_wb(p), re.IGNORECASE) for p in patterns]


_STRONG_RE = {g: _compile(ps) for g, ps in _STRONG.items()}
_CONTEXTUAL_RE = {
    g: [re.compile(_wb(rf"(?:{p})(?:\s+[\w\-']+)?\s+{_CONTEXT_NOUNS}"), re.IGNORECASE) for p in ps]
    for g, ps in _CONTEXTUAL.items()
}
_CONTEXTUAL_BARE_RE = {g: _compile(ps) for g, ps in _CONTEXTUAL.items()}
_FOLDER_ALIAS_RE = {g: _compile(ps) for g, ps in _FOLDER_ALIASES.items()}
_CATALOG_RE = {
    g: [re.compile(p, re.IGNORECASE) for p in ps] for g, ps in _CATALOG_HEADINGS.items()
}


@lru_cache(maxsize=1024)
def _name_regex(name: str) -> re.Pattern:
    """A genre's own name as a whole-word pattern, tolerant of the
    separators and plurals folder names use: 'Science_Fiction',
    'Short-Stories', 'Thrillers', 'Arts and Crafts'-style '&'."""
    words = re.split(r"\s+", name.strip())
    parts = []
    for word in words:
        escaped = re.escape(word).replace(r"\&", "&")
        if word == "&":
            parts.append(r"(?:&|and)")
        else:
            parts.append(escaped)
    body = r"[\s_\-]+".join(parts)
    last = words[-1]
    if last[-1:].lower() == "y" and len(last) > 2 and last[-2:-1].lower() not in "aeiou":
        body = body[:-1] + r"(?:y|ies)"
    elif last[-1:].isalpha() and last[-1:].lower() != "s":
        body += r"s?"
    return re.compile(_wb(body), re.IGNORECASE)


def _snippet(text: str, match: re.Match) -> str:
    start = max(0, match.start() - _SNIPPET_RADIUS)
    end = min(len(text), match.end() + _SNIPPET_RADIUS)
    snippet = " ".join(text[start:end].split())
    return ("…" if start > 0 else "") + snippet + ("…" if end < len(text) else "")


class _Collector:
    def __init__(self, vocabulary: Iterable[str], existing_tags: Iterable[str]):
        self.canonical = {g.strip().lower(): g.strip() for g in vocabulary if g and g.strip()}
        self.existing = {t.strip().lower() for t in existing_tags if t and t.strip()}
        self.found: dict[str, GenreSuggestion] = {}

    def add(self, genre: str, source: str, snippet: str) -> None:
        key = genre.lower()
        name = self.canonical.get(key)
        if name is None or key in self.existing:
            return
        suggestion = self.found.setdefault(key, GenreSuggestion(name))
        if all(existing_source != source for existing_source, _ in suggestion.sources):
            suggestion.sources.append((source, snippet))

    def add_matches(
        self, text: str, source: str, matchers: list[tuple[str, re.Pattern]], whole_label: bool = False
    ) -> None:
        """Runs every (genre, regex) over `text` and adds the genres
        found -- except a genre whose every hit sits inside a longer hit
        for a different genre: "psychological thriller" suggests
        Psychological Thriller, not also Thriller; a "Non-Fiction"
        folder suggests Nonfiction, not Fiction."""
        hits: list[tuple[str, re.Match]] = []
        for genre, regex in matchers:
            if genre.lower() in self.canonical:
                hits.extend((genre, match) for match in regex.finditer(text))
        for genre, match in hits:
            start, end = match.span()
            covered = any(
                other.lower() != genre.lower()
                and other_match.start() <= start
                and end <= other_match.end()
                and other_match.end() - other_match.start() > end - start
                for other, other_match in hits
            )
            if not covered:
                self.add(genre, source, text if whole_label else _snippet(text, match))


def _flatten(*tables: dict[str, list[re.Pattern]]) -> list[tuple[str, re.Pattern]]:
    return [(genre, regex) for table in tables for genre, regexes in table.items() for regex in regexes]


_PATH_MATCHERS = _flatten(_STRONG_RE, _CONTEXTUAL_BARE_RE, _FOLDER_ALIAS_RE)
_DESCRIPTION_MATCHERS = _flatten(_STRONG_RE, _CONTEXTUAL_RE)
_CONTENT_MATCHERS = _flatten(_CATALOG_RE)
_URL_RE = re.compile(r"\S+://\S+|www\.\S+", re.IGNORECASE)


def _name_matchers(collector: _Collector, custom_only: bool = False) -> list[tuple[str, re.Pattern]]:
    builtin = {g.lower() for g in COMMON_GENRES} if custom_only else set()
    return [(name, _name_regex(name)) for key, name in collector.canonical.items() if key not in builtin]


def _path_labels(path: str) -> list[tuple[str, str]]:
    """(source, text) for the trailing folders and any bracketed tags in
    the filename, with '_'/'.' turned into spaces."""
    parts = [p for p in re.split(r"[\\/]+", path or "") if p]
    if not parts:
        return []
    *folders, filename = parts
    labels = [(SOURCE_FOLDER, f) for f in folders[-PATH_FOLDER_DEPTH:] if not f.endswith(":")]
    stem = re.sub(r"\.[A-Za-z0-9]{2,5}$", "", filename)
    labels += [(SOURCE_FILENAME, m.group(1)) for m in _BRACKETED_RE.finditer(stem)]
    return [(source, re.sub(r"[_.]+", " ", text).strip()) for source, text in labels]


def _scan_path(collector: _Collector, path: str) -> None:
    labels = _path_labels(path)
    if not labels:
        return
    matchers = _name_matchers(collector) + _PATH_MATCHERS
    for source, text in labels:
        collector.add_matches(text, source, matchers, whole_label=True)


def _scan_description(collector: _Collector, description: str) -> None:
    if not description:
        return
    # Custom genres (not in the built-in list) are the user's own
    # labels, so they're matched by name here too.
    matchers = _DESCRIPTION_MATCHERS + _name_matchers(collector, custom_only=True)
    collector.add_matches(description, SOURCE_DESCRIPTION, matchers)


def _scan_content(collector: _Collector, text: str) -> None:
    if text:
        collector.add_matches(_URL_RE.sub(" ", text), SOURCE_CONTENT, _CONTENT_MATCHERS)


def genre_for_ddc(ddc: str) -> str:
    """The broad genre a DDC number implies, or '' if none/unknown."""
    match = _DDC_RE.match(ddc or "")
    if not match:
        return ""
    whole = match.group(1)
    number = float(f"{whole}.{match.group(2) or '0'}")
    if whole[0] == "8":
        return _DDC_LITERATURE_FORMS.get(whole[2], "")
    for low, high, genre in _DDC_RULES:
        if low <= number <= high:
            return genre
    return ""


def suggest_genres(
    *,
    path: str = "",
    description: str = "",
    content_text: str = "",
    ddc: str = "",
    existing_tags: Iterable[str] = (),
    vocabulary: Iterable[str] | None = None,
) -> list[GenreSuggestion]:
    """Genre suggestions for one book, best first (found in more places
    first, then folder/filename before description before first pages,
    then by name). Never includes a genre already in `existing_tags`
    (case-insensitive) or one outside `vocabulary` (default: the
    built-in list)."""
    collector = _Collector(COMMON_GENRES if vocabulary is None else vocabulary, existing_tags)
    _scan_path(collector, path)
    _scan_description(collector, description)
    _scan_content(collector, content_text)
    ddc_genre = genre_for_ddc(ddc)
    if ddc_genre:
        collector.add(ddc_genre, SOURCE_DDC, ddc.strip())

    order = [SOURCE_FOLDER, SOURCE_FILENAME, SOURCE_DESCRIPTION, SOURCE_CONTENT, SOURCE_DDC]
    return sorted(
        collector.found.values(),
        key=lambda s: (-len(s.source_kinds), min(order.index(k) for k in s.source_kinds), s.genre.lower()),
    )


def scan_book_genres(book, vocabulary: Iterable[str] | None = None) -> list[GenreSuggestion]:
    """suggest_genres() for a loaded EpubBook: its path, description,
    DDC, existing Genre tags, and the text of its first few pages."""
    from core.content_scan import extract_text_from_epub
    from core.description_html import strip_html

    try:
        content_text = extract_text_from_epub(book)
    except Exception:  # noqa: BLE001 - unreadable content still leaves path/description/DDC
        content_text = ""
    metadata = book.metadata
    return suggest_genres(
        path=book.path,
        description=strip_html(metadata.description or ""),
        content_text=content_text,
        ddc=metadata.ddc,
        existing_tags=metadata.tags,
        vocabulary=vocabulary,
    )
