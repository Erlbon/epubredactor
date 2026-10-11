"""core/page_headers.py: running headers, page numbers and cut sentences left by a scan-and-OCR conversion."""

import zipfile

import pytest

from core.epub_metadata import EpubBook
from core.page_headers import apply_page_furniture, find_page_furniture, paragraph_blocks
from test_redact_steps import make_epub

BOOK = "THE LOST MINE"
CHAPTERS = ["THE FIRST DAY", "THE RIVER"]


def _p(text):
    return f'<p class="c1"><span class="c2">{text}</span></p>'


def scanned_chapter(number, title, pages, start_page, sentences_cut=True):
    """A chapter as the OCR left it: a CHAPTER marker and a Title Case title, then pages of text with a
    running header between them (left pages "N BOOK", right pages "TITLE N"), and a sentence cut at every break."""
    body = [_p(f"CHAPTER {number}"), _p(title.title())]
    page = start_page
    for i in range(pages):
        body += [_p(f"Page {page} starts here and the story goes on for a good while until the line"), ]
        body += [_p(f"stops at the page end, mid-sentence, and ends properly in text {i}.")] if not sentences_cut else []
        if sentences_cut:
            body += [_p("And then he said that the rain would"), "<p><span>&nbsp;</span></p>"]
            header = f"{page} {BOOK}" if page % 2 == 0 else f"{title} {page}"
            body += [_p(header), _p("come before the night was over, and so it did.")]
        page += 1
    return "".join(body), page


def scanned_book(tmp_path, name="scanned.epub", chapters=CHAPTERS, pages=6):
    pages_html, page = [], 3
    front = _p(BOOK) + _p("By Someone") + _p("ALL RIGHTS RESERVED")
    pages_html.append(("front.xhtml", front))
    for n, title in enumerate(chapters, start=1):
        body, page = scanned_chapter(n, title, pages, page)
        pages_html.append((f"ch{n}.xhtml", body))
    return make_epub(str(tmp_path / name), pages=pages_html)


def texts(path, doc):
    with zipfile.ZipFile(path) as zf:
        return [b.text for b in paragraph_blocks(zf.read(doc).decode("utf-8"))]


def test_a_scanned_book_is_found_and_its_plan_says_what_would_change(tmp_path):
    book = EpubBook(scanned_book(tmp_path))
    plan = find_page_furniture(book)
    assert plan.changed and plan.headers == 12 and plan.removed >= 12 and plan.joins == 12
    assert sorted(plan.headings) == ["the first day", "the lost mine", "the river"]
    assert any(example.startswith("header with page number") for example in plan.examples)
    assert plan.confidence == 0.85  # twelve headers: evidence, but not the twenty that make it high confidence
    assert "12 split sentence(s) rejoined" in plan.summary()


def test_applying_the_plan_removes_the_headers_joins_the_sentences_and_keeps_the_rest(tmp_path):
    path = scanned_book(tmp_path)
    book = EpubBook(path)
    apply_page_furniture(book, find_page_furniture(book))
    out = tmp_path / "clean.epub"
    book.save(str(out))
    fresh = EpubBook(str(out))
    chapter = texts(str(out), "OEBPS/ch1.xhtml")
    assert not any("THE LOST MINE" in t for t in chapter)  # no running header left
    assert "And then he said that the rain would come before the night was over, and so it did." in chapter
    assert chapter[0] == "CHAPTER 1" and chapter[1] == "The First Day"  # the chapter marker and its Title Case title stay
    assert texts(str(out), "OEBPS/front.xhtml")[0] == BOOK  # the title page is front matter: untouched
    assert fresh.validation_status == "OK" and not find_page_furniture(fresh).changed  # nothing left to do: idempotent


def test_the_rest_of_the_document_is_kept_byte_for_byte(tmp_path):
    book = EpubBook(scanned_book(tmp_path))
    plan = find_page_furniture(book)
    original = book.read_archive_file("OEBPS/ch1.xhtml").decode("utf-8")
    new = next(d for d in plan.docs if d.path == "OEBPS/ch1.xhtml").new_text
    assert new.startswith(original[: original.index("<p")])  # everything before the first paragraph is identical
    assert new.count('<p class="c1">') < original.count('<p class="c1">') and "</html>" in new


def test_a_hyphenated_word_at_the_page_end_is_made_whole(tmp_path):
    pages = []
    for n in range(8):
        header = f"{2 * n + 10} {BOOK}"
        pages.append(_p("The expedition set out into the jungle and was soon ex-") + _p(header) + _p("hausted by the heat."))
    book = EpubBook(make_epub(str(tmp_path / "h.epub"), pages=[("a.xhtml", "".join(pages))]))
    plan = find_page_furniture(book)
    assert plan.hyphen_joins == 8
    apply_page_furniture(book, plan)
    joined = [b.text for b in paragraph_blocks(book.read_archive_file("OEBPS/a.xhtml").decode("utf-8"))]
    assert joined == ["The expedition set out into the jungle and was soon exhausted by the heat."] * 8


def test_without_joining_only_the_headers_go(tmp_path):
    book = EpubBook(scanned_book(tmp_path))
    plan = find_page_furniture(book, join_sentences=False)
    assert plan.changed and plan.joins == 0
    apply_page_furniture(book, plan)
    chapter = [b.text for b in paragraph_blocks(book.read_archive_file("OEBPS/ch1.xhtml").decode("utf-8"))]
    assert "And then he said that the rain would" in chapter and "come before the night was over, and so it did." in chapter


def test_an_ordinary_book_is_left_alone(tmp_path):
    body = "".join(_p(f"Paragraph {i} of an ordinary story, with no page furniture at all.") for i in range(60))
    body += _p("3 BLIND MICE") + _p("THE END 7")  # a stray line that looks like a header, once
    book = EpubBook(make_epub(str(tmp_path / "plain.epub"), pages=[("a.xhtml", body)]))
    plan = find_page_furniture(book)
    assert not plan.changed and plan.reason


def test_numbers_that_do_not_rise_are_not_page_numbers(tmp_path):
    body = "".join(_p(f"{n} THE SAME HEADING") + _p("some story text that goes on") for n in (50, 3, 90, 4, 77, 2, 61, 9))
    book = EpubBook(make_epub(str(tmp_path / "x.epub"), pages=[("a.xhtml", body)]))
    assert not find_page_furniture(book).changed


def test_a_chapter_title_in_title_case_is_not_the_running_header_in_capitals(tmp_path):
    book = EpubBook(scanned_book(tmp_path))
    plan = find_page_furniture(book)
    removed = [text for d in plan.docs for _kind, text in d.removed]
    assert "The First Day" not in removed and "The River" not in removed and "CHAPTER 1" not in removed


def test_page_numbers_on_their_own_are_removed_only_between_the_pages_around_them(tmp_path):
    chapters = []
    for page in range(10, 30, 2):
        chapters.append(_p("Text before the break that ends properly.") + _p(f"{page} {BOOK}") + _p("Text after the break."))
    chapters.insert(4, _p("Text.") + _p("17") + _p("More text."))  # sits after the 16 header and before the 18 one
    chapters.append(_p("There were 400") + _p("400") + _p("soldiers."))  # far outside the sequence: story text
    book = EpubBook(make_epub(str(tmp_path / "n.epub"), pages=[("a.xhtml", "".join(chapters))]))
    plan = find_page_furniture(book)
    removed = [text for d in plan.docs for _k, text in d.removed]
    assert "17" in removed and "400" not in removed


def test_an_encrypted_or_unreadable_document_is_skipped_not_fatal(tmp_path):
    book = EpubBook(scanned_book(tmp_path))
    book.stage_content_replacement("OEBPS/ch2.xhtml", b"\xff\xfe not utf-8 at all \x00")
    plan = find_page_furniture(book)
    assert plan.changed and {d.path for d in plan.docs} == {"OEBPS/ch1.xhtml"}
