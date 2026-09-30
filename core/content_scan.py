"""
core/content_scan.py

Scans the first few content documents of an EPUB (typically the title
page and copyright page), plus its last few (colophon / about-the-
publisher pages), for text patterns that commonly carry metadata:
"Copyright (c) 2020 by Jane Doe", "Published by Acme Press", "ISBN
978-...", "Dewey Decimal 823.912", "Utgitt av ...", "Traduit par ...",
"(The Expanse #2)", and so on, in English, Norwegian, Italian, German
and French. The text's language itself is guessed too (see
core/language_detect.py).

This is inherently a best-guess heuristic tool, NOT a reliable parser --
real book front matter varies enormously in wording and layout. Every
result is a suggestion for the user to review, never applied
automatically (same "find candidates, human decides" pattern as the
ISBN lookup feature). Each suggestion carries a 0..1 confidence in
ContentScanResult.confidence so a future automation could auto-apply
only the high-confidence ones; nothing consumes it that way today.
"""

from __future__ import annotations

import posixpath
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field

import lxml.html

from core.epub_metadata import EpubBook, href_to_archive_path
from core.isbn import best_isbn13, is_valid_isbn
from core.language_detect import detect_language

DEFAULT_MAX_DOCS = 4
DEFAULT_TAIL_DOCS = 3
DEFAULT_MAX_CHARS = 20000

# Matches found only in the back matter are a little less trustworthy
# (an "about the author" page can mention other books and publishers).
_BACK_MATTER_FACTOR = 0.9

_NS = {"opf": "http://www.idpf.org/2007/opf"}
_XML_DECL_RE = re.compile(r"^\s*<\?xml[^>]*\?>")


# ----------------------------------------------------------------------
# Pattern building blocks
# ----------------------------------------------------------------------

# Letters that stand in for accented/umlaut forms when a source was
# typed or converted without them ("Ubersetzt", "Utgitt pa", "Editions").
_TRANSLIT = {
    "ä": "(?:ä|a|ae)", "ö": "(?:ö|o|oe)", "ü": "(?:ü|u|ue)", "ß": "(?:ß|ss)",
    "æ": "(?:æ|ae)", "ø": "(?:ø|o|oe)", "å": "(?:å|a|aa)",
}


def _loose(phrase: str) -> str:
    """Regex for a phrase that also matches it without its accents (and
    umlauts spelled ae/oe/ue). Case is handled by the (?i:) wrapper in
    _kw(). Spaces match any whitespace, a dot is optional."""
    out = []
    for ch in phrase.lower():
        if ch in _TRANSLIT:
            out.append(_TRANSLIT[ch])
        elif ch.isspace():
            out.append(r"\s+")
        elif ch == ".":
            out.append(r"\.?")
        elif ch in "'’":
            out.append("['’]")
        elif ch.isalpha():
            base = unicodedata.normalize("NFD", ch)[0]
            out.append(f"[{ch}{base}]" if base != ch else ch)
        else:
            out.append(re.escape(ch))
    return "".join(out)


def _kw(*phrases: str) -> str:
    """Case- and accent-insensitive alternation of keyword phrases."""
    ordered = sorted(phrases, key=len, reverse=True)
    return "(?i:(?:" + "|".join(_loose(p) for p in ordered) + "))"


_CAP = "A-ZÀ-ÖØ-Þ"
_LOW = "a-zß-öø-ÿ"
_YEAR = r"(?:1[5-9]\d{2}|20\d{2})(?!\d)"
_YEAR_CAP = f"({_YEAR})"
_SEP = r"[ \t]*[:\-–—]?[ \t]*"

# Words that can follow a capitalised run without being part of a name.
_NOT_NAME = (
    r"(?!(?:All|Alle|Tous|Tutti|Tutte|Rights|Published|Utgitt|Translated|Illustrated|"
    r"Edited|Cover|Printed|Copyright|ISBN|First|Text|Chapter|Kapittel|Kapitel|Chapitre|"
    r"Capitolo|Part|Page|Section|Figure|Table)\b)"
)
_PERSON_TOKEN = (
    rf"{_NOT_NAME}(?:[{_CAP}]\.|[{_CAP}][{_LOW}'’]+(?:-[{_CAP}][{_LOW}]+)*(?:[{_CAP}][{_LOW}]+)?)"
)
_PARTICLE = r"(?:van|von|de|der|den|di|da|del|della|le|la|af|zu|ten|ter|el|al|du|des)"
_PERSON = rf"{_PERSON_TOKEN}(?:[ \t]+(?:{_PARTICLE}[ \t]+)?{_PERSON_TOKEN}){{0,4}}"
_PERSON_LIST = rf"{_PERSON}(?:[ \t]*(?:,|&|and|og|und|et|e)[ \t]+{_PERSON})*"
_LIST_SPLIT_RE = re.compile(r"[ \t]*(?:,|&|\band\b|\bog\b|\bund\b|\bet\b|\be\b)[ \t]+")

_NAME_TOKEN = rf"{_NOT_NAME}[{_CAP}][\w'’\-&]*"
_NAME_CONNECTOR = r"(?:of|the|and|og|und|et|de|du|des|la|le|les|von|der|die|das|di|del|della|dei|om|e|i)"
_NAME = rf"{_NAME_TOKEN}(?:[ \t]+(?:{_NAME_CONNECTOR}[ \t]+)?{_NAME_TOKEN}){{0,6}}"


# ----------------------------------------------------------------------
# ISBN / DDC
# ----------------------------------------------------------------------

_ISBN_RE = re.compile(
    r"ISBN(?:-1[03])?\s*[:#]?\s*([0-9][0-9\- ]{8,18}[0-9Xx])", re.IGNORECASE
)
_DDC_RE = re.compile(
    r"(?:Dewey\s*Decimal(?:\s*Classification)?|DDC)\s*[:#]?\s*(\d{3}(?:\.\d+)?)",
    re.IGNORECASE,
)


# ----------------------------------------------------------------------
# Year (first match wins, in this order) -> (regex, confidence)
# ----------------------------------------------------------------------

_COPYRIGHT_WORD = _kw("Copyright", "Opphavsrett", "Urheberrecht")
_COPYRIGHT_MARK = rf"(?:©|(?i:\(c\))|{_COPYRIGHT_WORD})"
_FIRST_PUBLISHED = _kw(
    "First published in", "First published", "First edition", "Første utgave",
    "Førsteutgave", "Første gang utgitt", "Utgitt første gang", "Første opplag",
    "Erstausgabe", "Erstmals erschienen", "Erstveröffentlichung", "Erstveröffentlicht",
    "Première édition", "Première publication", "Première parution",
    "Prima edizione", "Prima pubblicazione", "Prima uscita",
)
_YEAR_PATTERNS = [
    (re.compile(rf"{_COPYRIGHT_WORD}\s*(?:©|(?i:\(c\)))?\s*(?:(?i:by|av|von|par)\s+)?{_YEAR_CAP}"), 0.65),
    (re.compile(rf"{_FIRST_PUBLISHED}[^\d\n]{{0,25}}?{_YEAR_CAP}"), 0.75),
    (re.compile(rf"(?:©|(?i:\(c\)))[^\d\n]{{0,60}}?{_YEAR_CAP}"), 0.55),
    (re.compile(rf"{_kw('Dépôt légal', 'Legal deposit')}[^\d\n]{{0,25}}?{_YEAR_CAP}"), 0.5),
]

# ----------------------------------------------------------------------
# Copyright holder / author -> (regex, confidence); group 1 is the name
# ----------------------------------------------------------------------

_BY = _kw("by", "av", "von", "par", "di")
_HOLDER_PATTERNS = [
    # "Copyright (c) 2019 by Jane A. Smith", "© 2019 av Jon Fosse"
    (re.compile(rf"{_COPYRIGHT_MARK}[ \t]*(?:©|(?i:\(c\)))?[ \t]*{_YEAR}[ \t]*,?[ \t]*{_BY}[ \t]+({_PERSON})"), 0.6),
    # "© Jon Fosse 2019", "Copyright Jon Fosse, 2019"
    (re.compile(rf"{_COPYRIGHT_MARK}[ \t]*(?:{_BY}[ \t]+)?({_PERSON})[ \t]*,?[ \t]*{_YEAR}"), 0.5),
    # "© 2019 Jane Smith"
    (re.compile(rf"{_COPYRIGHT_MARK}[ \t]*(?:©|(?i:\(c\)))?[ \t]*{_YEAR}[ \t]*,?[ \t]+({_PERSON})"), 0.45),
]

# ----------------------------------------------------------------------
# Publisher
# ----------------------------------------------------------------------

_PUBLISHER_WORDS = (
    "Press", "Publishing", "Publications", "Publishers", "Books", "Forlag", "Forlaget",
    "Verlag", "Éditions", "Editions", "Editore", "Editrice", "Edizioni", "Libri",
)
_PUB_TERMINATOR = rf"(?:(?<!\b[{_CAP}])\.|\n|$)"
# A dot ends the name, except after a single capital ("C.H. Beck").
_PUB_BODY = rf"([{_CAP}](?:[\w&,'’\s\-]|(?<=\b[{_CAP}])\.){{2,60}}?){_PUB_TERMINATOR}"
# Labels that are unambiguous on their own ...
_PUB_LABEL_FREE = _kw(
    "Published by", "Utgitt av", "Utgitt på", "Erschienen bei", "Erschienen im", "Verlegt bei",
    "Publié par", "Pubblicato da", "Edito da", "Casa editrice", "Casa Editrice",
)
# ... and ones that are also ordinary words in a name ("Gyldendal Norsk
# Forlag"), so they only count when followed by a colon or dash.
_PUB_LABEL_STRICT = _kw(
    "Publisher", "Publishers", "Utgiver", "Forlag", "Verlag", "Éditeur", "Editore", "Editrice",
)
_PUBLISHED_BY_RE = re.compile(rf"{_PUB_LABEL_FREE}[ \t]*:?\s+{_PUB_BODY}")
_PUBLISHER_LABEL_RE = re.compile(rf"{_PUB_LABEL_STRICT}[ \t]*[:\-–]\s*{_PUB_BODY}")
_PUBLISHER_PREFIX_RE = re.compile(
    rf"(?<!\w)({_kw('Éditions', 'Editions', 'Edizioni', 'Forlaget', 'Verlag')}"
    rf"[ \t]+{_NAME_TOKEN}(?:[ \t]+(?:{_NAME_CONNECTOR}[ \t]+)?{_NAME_TOKEN}){{0,2}})"
)
_PUBLISHER_SUFFIX_RE = re.compile(
    rf"(?<!\w)({_NAME_TOKEN}(?:[ \t]+(?:{_NAME_CONNECTOR}[ \t]+)?{_NAME_TOKEN}){{0,4}}"
    rf"[ \t]+{_kw(*_PUBLISHER_WORDS)})\b"
)
_PUBLISHER_WORD_RE = re.compile(_kw(*_PUBLISHER_WORDS))
_TRAILING_YEAR_RE = re.compile(r"[,\s]+(?:1[5-9]|20)\d\d$")

# ----------------------------------------------------------------------
# Edition (informational: the app has no edition field)
# ----------------------------------------------------------------------

_EDITION_RE = re.compile(
    r"(?i:"
    r"\b(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|\d{1,2}(?:st|nd|rd|th))"
    r"(?:[ \t]+(?:revised|updated|expanded|new|paperback|ebook|e-book))*[ \t]+edition\b"
    r"|\b(?:første|andre|tredje|fjerde|femte|sjette|\d{1,2}\.)[ \t]+(?:utgave|opplag)\b"
    r"|\b(?:erste|zweite|dritte|vierte|fünfte|funfte|\d{1,2}\.)[ \t]+(?:auflage|ausgabe)\b"
    r"|\b(?:première|premiere|deuxième|deuxieme|seconde|troisième|troisieme|quatrième|\d{1,2}(?:e|ème|eme|re))"
    r"[ \t]+[ée]dition\b"
    r"|\b(?:prima|seconda|terza|quarta|quinta|\d{1,2}[aª°])[ \t]+edizione\b"
    r")"
)

# ----------------------------------------------------------------------
# Series / volume
# ----------------------------------------------------------------------

_ROMAN_RE = re.compile(r"^[IVXLC]+$")
_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
_WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
_NUM = r"(?P<num>\d{1,3}|[IVXLC]{1,7}|(?i:one|two|three|four|five|six|seven|eight|nine|ten))(?![\w])"
_VOL_KW = r"(?i:(?:book|bok|volume|volum|vol|bind|band|tome|libro|livre|buch)\b\.?)"
# Generic words ("Book", "Buch") are too common bare; these alone may
# give a volume number with no series name.
_VOL_KW_BARE = r"(?i:(?:volume|volum|vol|bind|band|tome|libro|livre)\b\.?)"
_NO_KW = r"(?i:(?:no|nr|n°)\.?)"
_SERIES_WORD = r"(?i:(?:(?:la|le|les|il|lo|die|der|den)[ \t]+)?(?:serien?|série|reihe|saga|cycle)[ \t]+)"
_OF_WORD = r"(?i:(?:of|in|av|i|der|von|de|du|di|della|del|dell['’]|d['’]))"
_TRAILING_SERIES_WORD_RE = re.compile(
    r"[ \t]+(?:Series|Trilogy|Saga|Serie|Serien|Reihe|Série|Cycle|Quartet|Duology)$"
)

_SERIES_PATTERNS = [
    # "(The Expanse #2)", "(Expanse, Book 2)"
    (re.compile(
        rf"\(\s*(?P<name>{_NAME})[ \t]*(?:[,:;\-–—][ \t]*)?(?:#[ \t]*|{_NO_KW}[ \t]*|{_VOL_KW}[ \t]*){_NUM}\s*\)"
    ), 0.8),
    # "Book 3 of the Expanse", "Bind 2 av Isfolket", "Tome 4 de la série X"
    (re.compile(
        rf"{_VOL_KW}[ \t]*{_NUM}[ \t]+{_OF_WORD}(?:[ \t]+|(?<=['’])){_SERIES_WORD}*"
        rf"(?P<name>(?:[Tt]he[ \t]+)?{_NAME})"
    ), 0.75),
    # "Isfolket, Bind 3", "The Expanse - Volume 5"
    (re.compile(
        rf"(?<!\w)(?P<name>{_NAME})[ \t]*[,:;\-–—][ \t]*{_VOL_KW}[ \t]*{_NUM}(?![\w])"
    ), 0.55),
    # "The Expanse #2"
    (re.compile(rf"(?<![\w#])(?P<name>{_NAME})[ \t]*#[ \t]*(?P<num>\d{{1,3}})(?!\d)"), 0.6),
]
_VOLUME_ONLY_RE = re.compile(rf"(?<!\w){_VOL_KW_BARE}[ \t]*{_NUM}")

# ----------------------------------------------------------------------
# Contributors (translator / editor / illustrator)
# ----------------------------------------------------------------------

# Extra role phrases that need a variable middle part ("Translated from
# the Norwegian by ...", "Aus dem Englischen von ...", "Traduit de
# l'anglais par ...").
_CONTRIBUTOR_LABELS = {
    "translator": [
        _kw(
            "Translated by", "Translation by", "Translators", "Translator", "Oversatt av",
            "Oversettelse ved", "Oversettelse av", "Oversetter", "Übersetzt von", "Übersetzung von",
            "Übersetzer", "Übertragen von", "Traduit par", "Traduction de", "Traduction par",
            "Traducteur", "Traduzione di", "Traduzione a cura di", "Tradotto da", "Traduttore",
        ),
        r"(?i:translated[ \t]+from[ \t]+(?:the[ \t]+)?\w+[ \t]+by)",
        r"(?i:oversatt[ \t]+fra[ \t]+\w+[ \t]+av)",
        r"(?i:aus[ \t]+dem[ \t]+\w+[ \t]+(?:(?:ü|u|ue)bersetzt[ \t]+)?von)",
        r"(?i:traduit[ \t]+(?:de[ \t]+l['’]|du[ \t]+|de[ \t]+)\w+[ \t]+par)",
        r"(?i:traduzione[ \t]+dall['’]\w+[ \t]+di)",
    ],
    "editor": [
        _kw(
            "Edited by", "Editors", "Editor", "Redigert av", "Redaktør", "Redaksjon",
            "Herausgegeben von", "Herausgeber", "Hrsg. von", "Hrsg.", "Lektorat", "Édité par",
            "Sous la direction de", "Direction éditoriale", "A cura di", "Curato da", "Redazione",
        ),
    ],
    "illustrator": [
        _kw(
            "Illustrated by", "Illustrations by", "Illustration by", "Illustrator", "Illustrators",
            "Illustrert av", "Illustrasjoner av", "Illustrasjon av", "Tegninger av",
            "Omslagsillustrasjon", "Illustriert von", "Illustrationen von", "Illustré par",
            "Illustrations de", "Illustration de", "Dessins de", "Illustrato da",
            "Illustrazioni di", "Illustrazione di", "Illustrazioni a cura di",
        ),
        r"(?i:illustrations?[ \t]*:)",
    ],
}
_CONTRIBUTOR_RES = {
    role: re.compile(rf"(?<!\w)(?:{'|'.join(labels)}){_SEP}({_PERSON_LIST})")
    for role, labels in _CONTRIBUTOR_LABELS.items()
}
_CONTRIBUTOR_CONFIDENCE = 0.6


# ----------------------------------------------------------------------
# Result
# ----------------------------------------------------------------------

@dataclass
class ContentScanResult:
    title: str = ""
    authors_str: str = ""
    publisher: str = ""
    pub_year: str = ""
    isbn: str = ""
    ddc: str = ""
    language: str = ""            # ISO 639-1, one of en/no/it/de/fr
    language_confidence: float = 0.0
    language_evidence: str = ""
    series: str = ""
    series_index: str = ""        # may be set without a series name ("Volume II")
    edition: str = ""             # informational only, no app field for it
    contributors: dict = field(default_factory=dict)  # role -> [names], informational only
    confidence: dict = field(default_factory=dict)    # field/role key -> 0..1
    source_snippets: dict = field(default_factory=dict)  # field -> matched text, for review

    def as_dict(self) -> dict:
        """Suggestions that map onto a real app field, i.e. the ones the
        dialog may apply. A volume number with no series name is left out
        (writing a bare series index would mean nothing)."""
        fields = {
            "title": self.title,
            "authors_str": self.authors_str,
            "publisher": self.publisher,
            "pub_year": self.pub_year,
            "isbn": self.isbn,
            "ddc": self.ddc,
            "language": self.language,
            "series": self.series,
            "series_index": self.series_index if self.series else "",
        }
        return {k: v for k, v in fields.items() if v}

    def info_dict(self) -> dict:
        """Review-only findings the app has no field to write to: the
        edition, and contributors (the app's OPF writer only rebuilds
        dc:creator as authors, there is no contributor/role field)."""
        info = {}
        if self.edition:
            info["edition"] = self.edition
        for role, names in self.contributors.items():
            if names:
                info[role] = "; ".join(names)
        return info


def _set(result: ContentScanResult, key: str, value: str, confidence: float, snippet: str) -> None:
    setattr(result, key, value)
    result.confidence[key] = round(confidence, 2)
    result.source_snippets[key] = snippet.strip()


# ----------------------------------------------------------------------
# Text extraction
# ----------------------------------------------------------------------

def _read_doc_text(zf: zipfile.ZipFile, archive_path: str) -> str | None:
    try:
        raw = zf.read(archive_path)
    except KeyError:
        return None
    try:
        # XHTML without a charset hint is UTF-8 by definition, but lxml.html
        # guesses Latin-1 for bytes, which turns "Første" into mojibake and
        # defeats every non-English pattern. Decode first; lxml refuses a
        # str that still carries an XML encoding declaration, so drop that.
        try:
            markup: str | bytes = _XML_DECL_RE.sub("", raw.decode("utf-8-sig"), count=1)
        except UnicodeDecodeError:
            markup = raw
        doc = lxml.html.fromstring(markup)
        return " ".join(doc.itertext())
    except Exception:  # noqa: BLE001 - malformed content shouldn't crash a scan
        return None


def extract_text_segments(
    book: EpubBook,
    max_docs: int = DEFAULT_MAX_DOCS,
    max_chars: int = DEFAULT_MAX_CHARS,
    tail_docs: int = DEFAULT_TAIL_DOCS,
) -> tuple[str, str]:
    """(front, back) plain text: the first max_docs spine documents, and
    separately the last tail_docs ones (colophon, about the publisher).
    A short book never reads a document twice. Together they stay within
    max_chars; when there is a tail a quarter of the budget is reserved
    for it so long front matter cannot crowd it out."""
    if book.load_error or book._opf_tree is None:  # noqa: SLF001 -- same package
        return "", ""

    root = book._opf_tree.getroot()  # noqa: SLF001
    manifest = root.find("opf:manifest", namespaces=_NS)
    spine = root.find("opf:spine", namespaces=_NS)
    if manifest is None or spine is None:
        return "", ""

    id_to_href = {item.get("id"): item.get("href") for item in manifest.findall("opf:item", namespaces=_NS)}
    opf_dir = posixpath.dirname(book.opf_path)
    hrefs = [id_to_href.get(ref.get("idref")) for ref in spine.findall("opf:itemref", namespaces=_NS)]
    hrefs = [h for h in hrefs if h]

    # Positions in `hrefs`; the tail never overlaps what the head may read.
    tail_start = max(len(hrefs) - max(tail_docs, 0), max_docs)
    tail_hrefs = hrefs[tail_start:] if tail_docs > 0 else []
    head_cap = max_chars - (max_chars // 4 if tail_hrefs else 0)

    def read_some(candidates: list[str], zf: zipfile.ZipFile, cap: int, limit: int | None) -> str:
        parts: list[str] = []
        total = 0
        read = 0
        for href in candidates:
            if (limit is not None and read >= limit) or total >= cap:
                break
            text = _read_doc_text(zf, href_to_archive_path(opf_dir, href))
            if text is None:
                continue
            parts.append(text)
            total += len(text)
            read += 1
        return " ".join(parts)[:cap]

    try:
        with zipfile.ZipFile(book.path, "r") as zf:
            front = read_some(hrefs, zf, head_cap, max_docs)
            back = read_some(tail_hrefs, zf, max_chars - len(front), None) if tail_hrefs else ""
    except (zipfile.BadZipFile, KeyError, OSError):
        return "", ""
    return front, back


def extract_text_from_epub(
    book: EpubBook,
    max_docs: int = DEFAULT_MAX_DOCS,
    max_chars: int = DEFAULT_MAX_CHARS,
    tail_docs: int = DEFAULT_TAIL_DOCS,
) -> str:
    """Plain text from the first few and last few spine documents, in reading order."""
    front, back = extract_text_segments(book, max_docs, max_chars, tail_docs)
    return f"{front} {back}" if back else front


# ----------------------------------------------------------------------
# Matching
# ----------------------------------------------------------------------

def _roman_value(text: str) -> int:
    total = 0
    for i, ch in enumerate(text):
        value = _ROMAN_VALUES[ch]
        nxt = _ROMAN_VALUES.get(text[i + 1], 0) if i + 1 < len(text) else 0
        total += -value if value < nxt else value
    return total


def _volume_number(token: str) -> str:
    """'3' -> '3', 'III' -> '3', 'three' -> '3'; '' if it isn't a sane number."""
    token = token.strip()
    if token.isdigit():
        number = int(token)
    elif _ROMAN_RE.match(token):
        number = _roman_value(token)
    else:
        number = _WORD_NUMBERS.get(token.lower(), 0)
    return str(number) if 0 < number < 1000 else ""


def _clean_series_name(name: str) -> str:
    name = _TRAILING_SERIES_WORD_RE.sub("", name.strip()).strip(" ,;:-–—")
    if name.lower().startswith("the "):
        name = "The " + name[4:]
    return name


def _followed_by_publisher_word(text: str, end: int) -> bool:
    following = re.match(r"[ \t]*,?[ \t]*(\w+)", text[end:])
    return bool(following and _PUBLISHER_WORD_RE.fullmatch(following.group(1)))


def _scan_segment(text: str) -> ContentScanResult:
    """All pattern-based suggestions from one stretch of text (no language)."""
    result = ContentScanResult()
    if not text:
        return result

    # The first checksum-valid ISBN wins; a copyright page often lists
    # several (print, ebook) and an invalid one shouldn't hide a valid one.
    for isbn_match in _ISBN_RE.finditer(text):
        candidate = isbn_match.group(1)
        if is_valid_isbn(candidate):
            _set(result, "isbn", best_isbn13(candidate) or candidate, 1.0, isbn_match.group(0))
            break

    ddc_match = _DDC_RE.search(text)
    if ddc_match:
        _set(result, "ddc", ddc_match.group(1), 0.8, ddc_match.group(0))

    for regex, confidence in _YEAR_PATTERNS:
        year_match = regex.search(text)
        if year_match:
            _set(result, "pub_year", year_match.group(1), confidence, year_match.group(0))
            break

    for regex, confidence in _HOLDER_PATTERNS:
        found = False
        for holder_match in regex.finditer(text):
            # "(c) 2012 Aschehoug Forlag" is a publisher, not a person.
            holder = holder_match.group(1)
            if _followed_by_publisher_word(text, holder_match.end(1)) or any(
                _PUBLISHER_WORD_RE.fullmatch(word) for word in holder.split()
            ):
                continue
            _set(result, "authors_str", holder.strip(), confidence, holder_match.group(0))
            found = True
            break
        if found:
            break

    publisher_match = _PUBLISHED_BY_RE.search(text) or _PUBLISHER_LABEL_RE.search(text)
    if publisher_match:
        _set(result, "publisher", _clean_publisher(publisher_match.group(1)), 0.7, publisher_match.group(0))
    else:
        publisher_match = _PUBLISHER_PREFIX_RE.search(text) or _PUBLISHER_SUFFIX_RE.search(text)
        if publisher_match:
            _set(result, "publisher", _clean_publisher(publisher_match.group(1)), 0.4, publisher_match.group(0))

    edition_match = _EDITION_RE.search(text)
    if edition_match:
        _set(result, "edition", " ".join(edition_match.group(0).split()), 0.6, edition_match.group(0))

    _scan_series(text, result)

    for role, regex in _CONTRIBUTOR_RES.items():
        contributor_match = regex.search(text)
        if contributor_match:
            names = [n.strip() for n in _LIST_SPLIT_RE.split(contributor_match.group(1)) if n.strip()]
            if names:
                result.contributors[role] = names
                result.confidence[role] = _CONTRIBUTOR_CONFIDENCE
                result.source_snippets[role] = contributor_match.group(0).strip()
    return result


def _clean_publisher(name: str) -> str:
    return _TRAILING_YEAR_RE.sub("", name.strip()).strip().rstrip(".,")


def _scan_series(text: str, result: ContentScanResult) -> None:
    for regex, confidence in _SERIES_PATTERNS:
        for match in regex.finditer(text):
            index = _volume_number(match.group("num"))
            name = _clean_series_name(match.group("name"))
            if index and len(name) >= 2:
                _set(result, "series", name, confidence, match.group(0))
                _set(result, "series_index", index, confidence, match.group(0))
                return
    match = _VOLUME_ONLY_RE.search(text)
    if match:
        index = _volume_number(match.group("num"))
        if index:
            _set(result, "series_index", index, 0.4, match.group(0))


# Fields merged from the back matter only when the front has none of them.
_MERGE_GROUPS = (
    ("isbn",), ("ddc",), ("pub_year",), ("authors_str",), ("publisher",), ("edition",),
    ("series", "series_index"),
)


def _merge_back(front: ContentScanResult, back: ContentScanResult) -> None:
    """Fill what the front matter left empty from the back matter,
    slightly discounted. Front matches always win."""
    for group in _MERGE_GROUPS:
        # A lone volume number in the front does not block a full series from the back.
        if group == ("series", "series_index"):
            if front.series:
                continue
        elif any(getattr(front, key) for key in group):
            continue
        for key in group:
            if getattr(back, key):
                _set(front, key, getattr(back, key), back.confidence[key] * _BACK_MATTER_FACTOR,
                     back.source_snippets[key])
    for role, names in back.contributors.items():
        if role not in front.contributors:
            front.contributors[role] = names
            front.confidence[role] = round(back.confidence[role] * _BACK_MATTER_FACTOR, 2)
            front.source_snippets[role] = back.source_snippets[role]


def guess_metadata_from_text(text: str, tail_text: str = "") -> ContentScanResult:
    """Suggestions from front-matter text, with `tail_text` (back matter)
    only filling in what the front did not provide."""
    result = _scan_segment(text)
    if tail_text:
        _merge_back(result, _scan_segment(tail_text))

    guess = detect_language(f"{text} {tail_text}" if tail_text else text)
    if guess:
        result.language = guess.code
        result.language_confidence = guess.confidence
        result.language_evidence = guess.evidence
        result.confidence["language"] = guess.confidence
        result.source_snippets["language"] = guess.evidence
    return result


def scan_book(
    book: EpubBook,
    max_docs: int = DEFAULT_MAX_DOCS,
    max_chars: int = DEFAULT_MAX_CHARS,
    tail_docs: int = DEFAULT_TAIL_DOCS,
) -> ContentScanResult:
    front, back = extract_text_segments(book, max_docs, max_chars, tail_docs)
    return guess_metadata_from_text(front, back)
