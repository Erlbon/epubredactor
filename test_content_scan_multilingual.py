"""Tests for the multilingual / language-detection / series / contributor /
back-matter extensions of core/content_scan.py and its dialog."""
import os
import sys
import zipfile

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from core.content_scan import (  # noqa: E402
    ContentScanResult,
    extract_text_from_epub,
    extract_text_segments,
    guess_metadata_from_text,
    scan_book,
)
from core.epub_metadata import EpubBook  # noqa: E402
from core.language_detect import detect_language  # noqa: E402

# ~60-word running prose per language (the detector needs real sentences).
PROSE = {
    "en": (
        "It was a cold morning when she finally decided that the old house on the hill was not "
        "going to be sold, and that they would have to find another way to pay for the repairs. "
        "He said that there was nothing more to do, but she did not believe him, because she "
        "had seen what was in the letter and knew that it could change everything for them all."
    ),
    "no": (
        "Det var en kald morgen da hun endelig bestemte seg for at det gamle huset på bakken "
        "ikke skulle selges, og at de måtte finne en annen måte å betale for reparasjonene på. "
        "Han sa at det ikke var noe mer å gjøre, men hun trodde ham ikke, fordi hun hadde sett "
        "hva som stod i brevet og visste at det kunne forandre alt for dem alle sammen."
    ),
    "nn": (
        "Det var ein kald morgon då ho endeleg bestemte seg for at det gamle huset på bakken "
        "ikkje skulle seljast, og at dei måtte finne ein annan måte å betale for reparasjonane på. "
        "Han sa at det ikkje var noko meir å gjere, men ho trudde han ikkje, fordi ho hadde sett "
        "kva som stod i brevet og visste at det kunne forandre alt for dei alle saman."
    ),
    "it": (
        "Era una fredda mattina quando finalmente decise che la vecchia casa sulla collina non "
        "sarebbe stata venduta, e che avrebbero dovuto trovare un altro modo per pagare le "
        "riparazioni. Lui disse che non c'era più niente da fare, ma lei non gli credette, perché "
        "aveva visto che cosa c'era scritto nella lettera e sapeva che poteva cambiare tutto per loro."
    ),
    "de": (
        "Es war ein kalter Morgen, als sie sich endlich entschied, dass das alte Haus auf dem "
        "Hügel nicht verkauft werden würde und dass sie einen anderen Weg finden müssten, um die "
        "Reparaturen zu bezahlen. Er sagte, es gebe nichts mehr zu tun, aber sie glaubte ihm nicht, "
        "weil sie gesehen hatte, was in dem Brief stand, und wusste, dass er für sie alle alles ändern konnte."
    ),
    "fr": (
        "C'était un matin froid quand elle décida enfin que la vieille maison sur la colline ne "
        "serait pas vendue, et qu'ils devraient trouver un autre moyen de payer les réparations. "
        "Il dit qu'il n'y avait plus rien à faire, mais elle ne le crut pas, parce qu'elle avait "
        "vu ce qui était écrit dans la lettre et savait que cela pouvait tout changer pour eux."
    ),
    "da": (
        "Det var en kold morgen, da hun endelig besluttede, at det gamle hus på bakken ikke skulle "
        "sælges, og at de måtte finde en anden måde at betale for reparationerne på. Han sagde, at "
        "der ikke var mere at gøre, men hun troede ham ikke, fordi hun havde set, hvad der stod i "
        "brevet, og vidste, at det kunne ændre alt for dem alle sammen."
    ),
    "sv": (
        "Det var en kall morgon när hon äntligen bestämde sig för att det gamla huset på kullen "
        "inte skulle säljas, och att de måste hitta ett annat sätt att betala för reparationerna. "
        "Han sa att det inte fanns något mer att göra, men hon trodde honom inte, eftersom hon hade "
        "sett vad som stod i brevet och visste att det kunde förändra allt för dem alla tillsammans."
    ),
}


# ----------------------------------------------------------------------
# Language detection
# ----------------------------------------------------------------------

@pytest.mark.parametrize("key,code", [("en", "en"), ("no", "no"), ("nn", "no"),
                                      ("it", "it"), ("de", "de"), ("fr", "fr")])
def test_language_detection_each_language(key, code):
    guess = detect_language(PROSE[key])
    assert guess is not None, key
    assert guess.code == code, (key, guess)
    assert 0.25 <= guess.confidence <= 0.95
    assert guess.evidence


@pytest.mark.parametrize("key", ["da", "sv"])
def test_danish_and_swedish_are_not_reported_as_norwegian(key):
    assert detect_language(PROSE[key]) is None


def test_short_text_returns_nothing():
    assert detect_language("Det var en kald morgen da hun bestemte seg.") is None
    assert detect_language("") is None


def test_ambiguous_mixed_text_returns_nothing():
    mixed = PROSE["en"][:200] + " " + PROSE["fr"][:200] + " " + PROSE["de"][:200]
    assert detect_language(mixed) is None


def test_non_prose_returns_nothing():
    names = " ".join(["Rowohlt Gallimard Einaudi Gyldendal Aschehoug Penguin Hachette Suhrkamp"] * 8)
    assert detect_language(names) is None


def test_guess_metadata_reports_language_and_confidence():
    result = guess_metadata_from_text(PROSE["de"])
    assert result.language == "de"
    assert result.language_confidence == result.confidence["language"] > 0
    assert result.language_evidence
    assert result.as_dict()["language"] == "de"


# ----------------------------------------------------------------------
# Multilingual front-matter patterns
# ----------------------------------------------------------------------

NO_FRONT = (
    "© Jon Fosse 2012\nUtgitt av Gyldendal Norsk Forlag AS\nFørste utgave 2012\n"
    "Oversatt av Kari Nordmann og Ola Hansen\nIllustrert av Per Spelemann\nRedigert av Eva Berg\n"
)
DE_FRONT = (
    "Erstausgabe 1987\nVerlag: C.H. Beck\nAlle Rechte vorbehalten\n"
    "Übersetzt von Hans Müller\nHerausgegeben von Anna Schmidt\n2. Auflage\n"
    "Illustriert von Karl Bild\n"
)
FR_FRONT = (
    "© Éditions Gallimard, 2012\nTous droits réservés\nTraduit par Marie Dupont\n"
    "Première édition\nIllustré par Jean Martin\nSous la direction de Paul Durand\n"
)
IT_FRONT = (
    "© 2015 Giulio Einaudi Editore\nTutti i diritti riservati\nTraduzione di Luca Bianchi\n"
    "Prima edizione 2015\nA cura di Paola Rossi\nIllustrazioni di Anna Verdi\n"
)


def test_norwegian_front_matter():
    r = guess_metadata_from_text(NO_FRONT)
    assert r.publisher == "Gyldendal Norsk Forlag AS"
    assert r.pub_year == "2012"
    assert r.authors_str == "Jon Fosse"
    assert r.edition == "Første utgave"
    assert r.contributors == {
        "translator": ["Kari Nordmann", "Ola Hansen"],
        "editor": ["Eva Berg"],
        "illustrator": ["Per Spelemann"],
    }


def test_german_front_matter():
    r = guess_metadata_from_text(DE_FRONT)
    assert r.publisher == "C.H. Beck"
    assert r.pub_year == "1987"
    assert r.edition == "2. Auflage"
    assert r.contributors["translator"] == ["Hans Müller"]
    assert r.contributors["editor"] == ["Anna Schmidt"]
    assert r.contributors["illustrator"] == ["Karl Bild"]


def test_french_front_matter():
    r = guess_metadata_from_text(FR_FRONT)
    assert r.publisher == "Éditions Gallimard"
    assert r.pub_year == "2012"
    assert r.edition == "Première édition"
    assert r.contributors["translator"] == ["Marie Dupont"]
    assert r.contributors["illustrator"] == ["Jean Martin"]
    assert r.contributors["editor"] == ["Paul Durand"]
    assert r.authors_str == "", "a publisher named in the (c) line is not an author"


def test_italian_front_matter():
    r = guess_metadata_from_text(IT_FRONT)
    assert r.publisher == "Giulio Einaudi Editore"
    assert r.pub_year == "2015"
    assert r.edition == "Prima edizione"
    assert r.contributors["translator"] == ["Luca Bianchi"]
    assert r.contributors["editor"] == ["Paola Rossi"]
    assert r.contributors["illustrator"] == ["Anna Verdi"]
    assert r.authors_str == ""


def test_english_contributors_and_edition():
    r = guess_metadata_from_text(
        "Translated from the Norwegian by Jane Smith\nEdited by Tom Jones and Ann Lee\n"
        "Illustrations by Bob Ross\nSecond revised edition\n"
    )
    assert r.contributors["translator"] == ["Jane Smith"]
    assert r.contributors["editor"] == ["Tom Jones", "Ann Lee"]
    assert r.contributors["illustrator"] == ["Bob Ross"]
    assert r.edition.lower() == "second revised edition"


def test_accent_and_case_tolerance():
    r = guess_metadata_from_text("UTGITT AV Aschehoug Forlag\nUBERSETZT VON Hans Muller\nTRADUIT PAR Marie Dupont\n")
    assert r.publisher == "Aschehoug Forlag"
    assert r.contributors["translator"] == ["Hans Muller"]  # first label wins within a role
    r2 = guess_metadata_from_text("Premiere edition\nEditions Gallimard\n")
    assert r2.edition == "Premiere edition"
    assert r2.publisher == "Editions Gallimard"


def test_publisher_suffix_words():
    assert guess_metadata_from_text("Bokklubben Gyldendal Norsk Forlag.").publisher.endswith("Forlag")
    assert guess_metadata_from_text("Carl Hanser Verlag, München").publisher == "Carl Hanser Verlag"
    assert guess_metadata_from_text("Edizioni Mondadori").publisher == "Edizioni Mondadori"
    assert guess_metadata_from_text("Casa editrice Adelphi.").publisher == "Adelphi"


def test_info_dict_is_review_only_and_not_in_as_dict():
    r = guess_metadata_from_text(NO_FRONT)
    assert "translator" not in r.as_dict() and "edition" not in r.as_dict()
    assert r.info_dict()["translator"] == "Kari Nordmann; Ola Hansen"
    assert r.info_dict()["edition"] == "Første utgave"


def test_isbn_skips_an_invalid_one_before_a_valid_one():
    r = guess_metadata_from_text("ISBN 978-0-14-143951-9 (print) ISBN 978-0-14-143951-8 (ebook)")
    assert r.isbn == "9780141439518"


# ----------------------------------------------------------------------
# Series and volume
# ----------------------------------------------------------------------

@pytest.mark.parametrize("text,series,index", [
    ("(The Expanse #2)", "The Expanse", "2"),
    ("(Expanse, Book 2)", "Expanse", "2"),
    ("Book 3 of the Expanse series", "The Expanse", "3"),
    ("Book Three of The Expanse", "The Expanse", "3"),
    ("Bok 3 av Isfolket", "Isfolket", "3"),
    ("Isfolket, Bind 2", "Isfolket", "2"),
    ("Die Chroniken - Band III", "Die Chroniken", "3"),
    ("Tome 4 de la série Les Annales", "Les Annales", "4"),
    ("Libro 2 della serie Il Ciclo", "Il Ciclo", "2"),
    ("The Expanse #7", "The Expanse", "7"),
    ("Sagaen om Isfolket - Volume IV", "Sagaen om Isfolket", "4"),
])
def test_series_and_volume_variants(text, series, index):
    r = guess_metadata_from_text(text)
    assert (r.series, r.series_index) == (series, index), r
    assert r.as_dict()["series"] == series and r.as_dict()["series_index"] == index
    assert 0.5 <= r.confidence["series"] <= 0.8


@pytest.mark.parametrize("text,index", [("Volume II", "2"), ("Libro 2", "2"), ("Volume 5", "5"),
                                        ("Tome 4", "4"), ("Band 3", "3"), ("Bind 2", "2")])
def test_bare_volume_gives_index_but_is_not_applied_without_a_series(text, index):
    r = guess_metadata_from_text(text)
    assert r.series == "" and r.series_index == index
    assert "series_index" not in r.as_dict()


def test_roman_numerals():
    assert guess_metadata_from_text("(Saga, Book XIV)").series_index == "14"
    assert guess_metadata_from_text("(Saga, Book IX)").series_index == "9"


def test_chapter_hash_is_not_a_series():
    assert guess_metadata_from_text("See Chapter #2 for details.").series == ""


# ----------------------------------------------------------------------
# Front vs back matter merging
# ----------------------------------------------------------------------

def test_front_wins_and_back_fills_gaps_with_discount():
    front = "Published by Front Press.\nCopyright 2001"
    back = "Published by Back Press.\nISBN 978-0-14-143951-8\nTranslated by Jane Smith"
    r = guess_metadata_from_text(front, back)
    assert r.publisher == "Front Press"
    assert r.confidence["publisher"] == 0.7
    assert r.isbn == "9780141439518"
    assert r.confidence["isbn"] == 0.9   # 1.0 * back-matter factor
    assert r.contributors["translator"] == ["Jane Smith"]
    assert r.confidence["translator"] == 0.54


# ----------------------------------------------------------------------
# Confidence
# ----------------------------------------------------------------------

def test_confidence_rules():
    r = guess_metadata_from_text(
        "Copyright © 2019 by Jane A. Smith\nPublished by Acme Publishing.\nISBN 978-0-14-143951-8\n"
        "Dewey Decimal 813.6"
    )
    assert r.confidence["isbn"] == 1.0
    assert r.confidence["publisher"] == 0.7
    assert r.confidence["ddc"] == 0.8
    assert r.confidence["pub_year"] == 0.65
    assert r.confidence["authors_str"] == 0.6
    assert all(0 <= v <= 1 for v in r.confidence.values())


# ----------------------------------------------------------------------
# Reading the last spine documents (synthetic EPUB)
# ----------------------------------------------------------------------

CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""


def build_epub(path, pages):
    """pages: list of (name, body_html) in spine order."""
    items = "".join(f'<item id="{n}" href="{n}.xhtml" media-type="application/xhtml+xml"/>' for n, _ in pages)
    refs = "".join(f'<itemref idref="{n}"/>' for n, _ in pages)
    opf = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="b">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        '<dc:identifier id="b">urn:uuid:x</dc:identifier><dc:title>T</dc:title></metadata>'
        f"<manifest>{items}</manifest><spine>{refs}</spine></package>"
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", opf)
        for n, body in pages:
            full = body if body.startswith("<?xml") else f"<html><body>{body}</body></html>"
            zf.writestr(f"OEBPS/{n}.xhtml", full)
    return EpubBook(str(path))


def _long_book(tmp_path, n_docs=10):
    pages = [(f"p{i}", f"<p>Filler paragraph {i}.</p>") for i in range(n_docs)]
    pages[0] = ("p0", "<p>Copyright 2001</p>")
    pages[-1] = ("p9", "<p>Colophon. Published by Back Press.</p><p>Illustrated by Bob Ross</p>")
    return build_epub(tmp_path / "long.epub", pages)


def test_last_documents_are_read(tmp_path):
    book = _long_book(tmp_path)
    front, back = extract_text_segments(book)
    assert "Copyright 2001" in front and "Back Press" not in front
    assert "Back Press" in back and "Filler paragraph 5" not in back and "Filler paragraph 7" in back
    assert "Filler paragraph 5" not in extract_text_from_epub(book)


def test_back_matter_only_match_is_not_lost(tmp_path):
    result = scan_book(_long_book(tmp_path))
    assert result.pub_year == "2001"                # front
    assert result.publisher == "Back Press"         # back only
    assert result.confidence["publisher"] == 0.63   # 0.7 * 0.9
    assert result.contributors["illustrator"] == ["Bob Ross"]


def test_tail_docs_zero_restores_front_only_reading(tmp_path):
    result = scan_book(_long_book(tmp_path), tail_docs=0)
    assert result.publisher == ""


def test_short_book_is_not_read_twice(tmp_path):
    book = build_epub(tmp_path / "short.epub", [("a", "<p>Alpha unique</p>"), ("b", "<p>Beta unique</p>")])
    front, back = extract_text_segments(book)
    assert front.count("Alpha unique") == 1 and front.count("Beta unique") == 1
    assert back == ""
    assert extract_text_from_epub(book).count("Beta unique") == 1


def test_partial_overlap_reads_each_document_once(tmp_path):
    pages = [(f"d{i}", f"<p>Doc marker {i}</p>") for i in range(6)]
    book = build_epub(tmp_path / "six.epub", pages)
    text = extract_text_from_epub(book, max_docs=4, tail_docs=3)
    for i in range(6):
        assert text.count(f"Doc marker {i}") == 1, i


def test_character_cap_holds_with_tail(tmp_path):
    pages = [(f"d{i}", "<p>" + ("lorem ipsum " * 400) + f"END{i}</p>") for i in range(8)]
    book = build_epub(tmp_path / "big.epub", pages)
    front, back = extract_text_segments(book, max_chars=2000)
    assert len(front) + len(back) <= 2000
    assert back, "tail keeps a reserved share of the budget"


# ----------------------------------------------------------------------
# Dialog smoke test
# ----------------------------------------------------------------------

def test_dialog_shows_suggestions_and_applies_language_and_series(tmp_path):
    from PyQt6.QtWidgets import QApplication

    from gui.content_scan_dialog import APPLY_COL, FOUND_COL, ContentScanDialog

    _app = QApplication.instance() or QApplication(sys.argv)
    body = (
        "<p>Copyright 2019 by Jane A. Smith</p><p>(The Expanse #2)</p>"
        "<p>Translated by Kari Nordmann</p><p>Første utgave</p><p>" + PROSE["no"] + "</p>"
    )
    book = build_epub(tmp_path / "d.epub", [("a", body)])
    book.metadata.language = "en"

    dialog = ContentScanDialog([book])
    shown = dialog.table.item(0, FOUND_COL).text()
    assert "language: no" in shown and "series: The Expanse" in shown and "series_index: 2" in shown
    assert "translator: Kari Nordmann" in shown and "edition: Første utgave" in shown
    assert "not applied" in shown

    changes = dialog.accepted_changes()
    assert changes[0]["language"] == "no"
    assert changes[0]["series"] == "The Expanse" and changes[0]["series_index"] == "2"
    assert "translator" not in changes[0] and "edition" not in changes[0]

    # Apply the way main_window does (apply_metadata + undo snapshot is the
    # caller's job); the language lands in the real metadata field.
    book.apply_metadata(changes[0])
    assert book.metadata.language == "no" and book.metadata.series == "The Expanse"

    dialog.table.cellWidget(0, APPLY_COL).setChecked(False)
    assert dialog.accepted_changes() == {}


def test_dialog_drops_language_suggestion_equal_to_current(tmp_path):
    from PyQt6.QtWidgets import QApplication

    from gui.content_scan_dialog import ContentScanDialog

    _app = QApplication.instance() or QApplication(sys.argv)
    book = build_epub(tmp_path / "e.epub", [("a", "<p>" + PROSE["en"] + "</p>")])
    book.metadata.language = "en-GB"
    dialog = ContentScanDialog([book])
    assert dialog.accepted_changes() == {}


def test_result_defaults_are_empty():
    r = ContentScanResult()
    assert r.as_dict() == {} and r.info_dict() == {} and r.confidence == {}


def test_utf8_documents_with_and_without_xml_declaration_keep_their_accents(tmp_path):
    decl = ('<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml">'
            "<body><p>Første utgave</p></body></html>")
    book = build_epub(tmp_path / "x.epub", [("a", decl), ("b", "<p>Übersetzt von Hans Müller</p>")])
    text = extract_text_from_epub(book)
    assert "Første utgave" in text and "Hans Müller" in text
    assert guess_metadata_from_text(text).contributors["translator"] == ["Hans Müller"]
