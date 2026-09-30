"""
core/language_detect.py

Dependency-free language guess for exactly English, Norwegian, Italian,
German and French, from how much of a text is made of each language's
most common function words ("stopwords"). Deliberately small: it only
has to tell apart the five languages in the user's library, not name
every language on earth.

Danish and Swedish are loaded as *competitors only*. Norwegian shares
most of its stopwords with them, so without them a Danish book would be
reported as Norwegian. They are never returned: a text that is really
Danish or Swedish yields nothing rather than a wrong 'no'. Bokmal and
Nynorsk both report 'no' (the code the app's language picker uses).

Like everything in core/content_scan.py this is a suggestion for a human
to review: it needs enough text and a clear margin, otherwise it says
nothing instead of guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MIN_WORDS = 40          # below this the stopword ratios are noise
MIN_COVERAGE = 0.18     # winner's stopwords must be at least this share of all words
MIN_REL_MARGIN = 0.25   # (winner - runner-up) / winner
MAX_CONFIDENCE = 0.95   # a statistical guess is never certain

# A "word" is a run of letters, so l'homme -> l, homme and don't -> don, t.
_WORD_RE = re.compile(r"[^\W\d_]+")

_STOPWORDS_RAW = {
    "en": """the of and to in is that it was for on with as he she his her they be at by
        this had not are but from or have an which you were all we there their been has one
        would can if will what who no when said out up its about into than them could these
        then do my our me your how so did where just him i a""",
    "de": """der die das und in zu den nicht von ist mit sich des auf für dem ein eine als auch
        es an werden aus er hat dass sie nach wird bei einer um am sind noch wie einem über
        einen so zum war haben nur oder aber vor zur bis mehr durch man sein wurde sei ich wir
        ihr ihre mich mir dich uns eines kann wenn dann schon immer hier sehr dieser diese
        dieses weil wieder doch denn ihm ihn ihnen seine seiner nun jetzt da was wer wo mein
        dein kein keine""",
    "fr": """le la les de des du un une et en à est que qui dans pour pas sur au aux il elle ils
        elles ce cette ces se ne ou mais avec son sa ses par plus je tu nous vous leur leurs
        était été être avait avoir fait comme tout tous toute toutes sans sous entre bien aussi
        même mon ma mes ton moi lui y où dont quand alors très peu encore lorsque cela ça cet si
        qu j jusqu lorsqu puisqu""",
    "it": """il lo la le gli i un uno una di del dello della dei degli delle da dal dalla in nel
        nella con su sul per tra fra e ed o ma che chi non è sono era erano ha hanno hai ho si se
        ci mi ti lei lui loro noi voi io tu questo questa questi quello quella come più anche
        molto tutto tutti tutta ogni suo sua suoi sue mio mia nostro essere stato stata fatto
        quando dove perché così già solo sempre ancora cosa dell nell all sull dall quest quell""",
    "no": """og i jeg det at en et til er som på de med han av ikke der så var meg seg men ett har
        om vi min mitt ha hadde hun nå over da ved fra du ut sin dem oss opp man kan hans hvor
        eller hva skal selv sjøl her alle vil bli ble blitt kunne inn når være kom noen noe bare
        deg dette denne disse også etter mot under ingen mange sine mer mye hele slik sammen vært
        aldri mellom gjennom eg ikkje ein ei eit kva frå ho dei desse vore korleis berre òg kor
        nokon noko meir mykje hjå blei""",
    # Competitors only, never returned (see module docstring).
    "da": """og i jeg det at en et til er som på de med han af ikke der så var mig sig men har om
        vi min mit have havde hun nu over da ved fra du ud sin dem os op man kan hans hvor eller
        hvad skal selv her alle vil blive blev blevet kunne ind når være kom nogen noget bare dig
        dette denne disse også efter mod under ingen mange sine mere meget hele sådan sammen
        været aldrig mellem gennem ham ja nej""",
    "sv": """och i jag det att en ett till är som på de med han av inte där så var mig sig men har
        om vi min mitt ha hade hon nu över då vid från du ut sin dem oss upp man kan hans eller
        vad ska själv här alla vill bli blev blivit kunde in när vara kom någon något bara dig
        detta denna dessa också efter mot under ingen många sina mer mycket hela sådan
        tillsammans varit aldrig mellan genom honom ja nej""",
}
_STOPWORDS = {lang: frozenset(words.split()) for lang, words in _STOPWORDS_RAW.items()}

_REPORTABLE = ("en", "de", "fr", "it")
_SCANDINAVIAN = ("no", "da", "sv")


@dataclass
class LanguageGuess:
    code: str            # ISO 639-1
    confidence: float    # 0..1, margin-based
    evidence: str        # human-readable, shown for review


def _distinctive_words(lang: str) -> frozenset:
    """Stopwords of one Scandinavian language that neither of the other two has."""
    others = set().union(*(_STOPWORDS[o] for o in _SCANDINAVIAN if o != lang))
    return _STOPWORDS[lang] - others


_DISTINCTIVE = {lang: _distinctive_words(lang) for lang in _SCANDINAVIAN}


def detect_language(text: str) -> LanguageGuess | None:
    """The text's language as en/no/it/de/fr, or None when there are too
    few words or no clear winner."""
    words = _WORD_RE.findall(text.lower())
    total = len(words)
    if total < MIN_WORDS:
        return None

    hits = {lang: 0 for lang in _STOPWORDS}
    for word in words:
        for lang, stop in _STOPWORDS.items():
            if word in stop:
                hits[lang] += 1
    ratio = {lang: n / total for lang, n in hits.items()}

    # The three Scandinavian languages compete as one block first; which
    # member wins is decided afterwards from their distinctive words.
    scandi_best = max(_SCANDINAVIAN, key=lambda lang: ratio[lang])
    block = {lang: ratio[lang] for lang in _REPORTABLE}
    block["scandinavian"] = ratio[scandi_best]
    ranked = sorted(block.items(), key=lambda kv: kv[1], reverse=True)
    (top_name, top), (second_name, second) = ranked[0], ranked[1]
    if top < MIN_COVERAGE:
        return None
    margin = (top - second) / top
    if margin < MIN_REL_MARGIN:
        return None
    confidence = margin * min(1.0, top / 0.30)

    if top_name == "scandinavian":
        distinct = {lang: sum(1 for w in words if w in _DISTINCTIVE[lang]) for lang in _SCANDINAVIAN}
        order = sorted(_SCANDINAVIAN, key=lambda lang: distinct[lang], reverse=True)
        best, runner = order[0], order[1]
        if best != "no" or distinct[best] < 3 or distinct[runner] * 2 > distinct[best]:
            return None  # Danish, Swedish, or too close to tell
        confidence *= 1 - distinct[runner] / distinct[best]
        code = "no"
        evidence = (
            f"{top:.0%} of {total} words are Scandinavian stopwords; "
            f"Norwegian-only words {distinct['no']} vs Danish {distinct['da']}, Swedish {distinct['sv']}"
        )
    else:
        code = top_name
        found = sorted({w for w in words if w in _STOPWORDS[code]},
                       key=lambda w: -words.count(w))[:5]
        evidence = (
            f"{top:.0%} of {total} words are {code} stopwords ({', '.join(found)}); "
            f"next best {second_name} {second:.0%}"
        )
    return LanguageGuess(code, round(min(MAX_CONFIDENCE, confidence), 2), evidence)
