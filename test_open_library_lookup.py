"""Tests for core/open_library_lookup.py -- all network access faked via
the injectable `fetch` parameter, using response shapes matching the
real, documented Open Library search API schema."""
import json
import os
import sys
import urllib.error

sys.path.insert(0, os.path.dirname(__file__))
from core.open_library_lookup import (  # noqa: E402
    MAX_SUBJECTS,
    OpenLibraryLookupError,
    build_search_url,
    download_cover_image,
    parse_search_response,
    search_open_library,
)

SAMPLE_RESPONSE = {
    "numFound": 2,
    "docs": [
        {
            "title": "The Hobbit",
            "author_name": ["J.R.R. Tolkien"],
            "publisher": ["George Allen & Unwin", "HarperCollins"],
            "first_publish_year": 1937,
            "isbn": ["9780261102217", "0261102214"],
            "subject": [f"Subject {i}" for i in range(10)],  # more than MAX_SUBJECTS
            "cover_i": 258027,
        },
        {
            # Real responses often include docs with no cover, no
            # publisher, no isbn at all -- must not crash, and must NOT
            # be skipped (unlike the old cover-only version) since
            # title/author/etc are still useful on their own.
            "title": "The Hobbit (bare-bones entry)",
            "author_name": ["Someone"],
        },
    ],
}

EMPTY_RESPONSE = {"numFound": 0, "docs": []}


def test_build_search_url_basic():
    url = build_search_url("The Hobbit", "J.R.R. Tolkien")
    assert url.startswith("https://openlibrary.org/search.json?")
    assert "title=" in url
    assert "author=" in url
    print("PASS: search URL includes title and author")


def test_build_search_url_no_author():
    url = build_search_url("Dune", "")
    assert "author=" not in url
    print("PASS: search URL omits author when none given")


def test_build_search_url_requires_title():
    try:
        build_search_url("", "Someone")
        assert False, "should have raised"
    except OpenLibraryLookupError:
        pass
    print("PASS: empty title raises OpenLibraryLookupError")


def test_build_search_url_multi_author_uses_first():
    url = build_search_url("Good Omens", "Terry Pratchett; Neil Gaiman")
    assert "Pratchett" in url
    assert "Gaiman" not in url
    print("PASS: only the first author is used in the query")


def test_parse_response_extracts_all_fields():
    raw = json.dumps(SAMPLE_RESPONSE).encode()
    candidates = parse_search_response(raw)
    assert len(candidates) == 2, "an entry with no cover must NOT be skipped anymore"
    c = candidates[0]
    assert c.title == "The Hobbit"
    assert c.authors_str == "J.R.R. Tolkien"
    assert c.publisher == "George Allen & Unwin"  # first of the list
    assert c.pub_year == "1937"
    assert c.isbn == "9780261102217"  # first of the list
    assert c.cover_id == 258027
    assert c.image_url() == "https://covers.openlibrary.org/b/id/258027-L.jpg"
    print("PASS: parses title/authors/publisher/year/isbn/subjects/cover")


def test_parse_response_subjects_capped():
    c = parse_search_response(json.dumps(SAMPLE_RESPONSE).encode())[0]
    tags = c.tags_str.split("; ")
    assert len(tags) == MAX_SUBJECTS, tags
    print(f"PASS: subject list is capped at MAX_SUBJECTS ({MAX_SUBJECTS}), not dumped wholesale")


def test_parse_response_bare_entry_no_crash():
    c = parse_search_response(json.dumps(SAMPLE_RESPONSE).encode())[1]
    assert c.title == "The Hobbit (bare-bones entry)"
    assert c.publisher == ""
    assert c.isbn == ""
    assert c.cover_id == 0
    assert c.tags_str == ""
    print("PASS: an entry missing publisher/isbn/subject/cover doesn't crash, fields are just empty")


def test_parse_response_empty():
    assert parse_search_response(json.dumps(EMPTY_RESPONSE).encode()) == []
    print("PASS: empty result set parses to an empty list, not an error")


def test_parse_response_garbage():
    try:
        parse_search_response(b"not json {{{")
        assert False, "should have raised"
    except OpenLibraryLookupError:
        pass
    print("PASS: unparseable response raises OpenLibraryLookupError")


def test_search_open_library_with_fake_fetch():
    def fake_fetch(url):
        assert "title=" in url
        return json.dumps(SAMPLE_RESPONSE).encode()

    results = search_open_library("The Hobbit", "J.R.R. Tolkien", fetch=fake_fetch)
    assert len(results) == 2
    assert results[0].cover_id == 258027
    print("PASS: search_open_library wires query building + fetch + parsing together")


def test_search_open_library_network_error_wrapped():
    def failing_fetch(url):
        raise urllib.error.URLError("no internet")

    try:
        search_open_library("Some Book", fetch=failing_fetch)
        assert False, "should have raised"
    except OpenLibraryLookupError as exc:
        assert "reach" in str(exc).lower() or "internet" in str(exc).lower()
    print("PASS: network errors are wrapped in a clear OpenLibraryLookupError")


def _http_error(code, reason="Error"):
    return urllib.error.HTTPError(url="https://example.com", code=code, msg=reason, hdrs=None, fp=None)


def test_search_open_library_429_retries_then_succeeds():
    calls = {"count": 0}

    def flaky_fetch(url):
        calls["count"] += 1
        if calls["count"] < 3:
            raise _http_error(429, "Too Many Requests")
        return json.dumps(SAMPLE_RESPONSE).encode()

    sleeps = []
    results = search_open_library("The Hobbit", fetch=flaky_fetch, sleep_fn=sleeps.append)
    assert len(results) == 2
    assert calls["count"] == 3
    assert sleeps == [1.0, 2.0], sleeps
    print("PASS: a 429 that clears within the retry budget succeeds automatically")


def test_search_open_library_429_exhausted_gives_clear_message():
    def always_429(url):
        raise _http_error(429, "Too Many Requests")

    sleeps = []
    try:
        search_open_library("Some Book", fetch=always_429, sleep_fn=sleeps.append)
        assert False, "should have raised"
    except OpenLibraryLookupError as exc:
        message = str(exc).lower()
        assert "rate" in message or "429" in message
        assert "internet connection" not in message
    assert sleeps == [1.0, 2.0], sleeps
    print("PASS: a persistent 429 gives a clear rate-limit message, not a misleading connectivity one")


def test_search_open_library_non_429_http_error_not_retried():
    calls = {"count": 0}

    def server_error(url):
        calls["count"] += 1
        raise _http_error(500, "Internal Server Error")

    try:
        search_open_library("Some Book", fetch=server_error, sleep_fn=lambda s: None)
        assert False, "should have raised"
    except OpenLibraryLookupError as exc:
        assert "500" in str(exc)
    assert calls["count"] == 1, "a non-429 HTTP error should fail immediately, not retry"
    print("PASS: a non-429 HTTP error is reported immediately without retrying")


def test_display_label():
    c = parse_search_response(json.dumps(SAMPLE_RESPONSE).encode())[0]
    label = c.display_label()
    assert "The Hobbit" in label
    assert "Tolkien" in label
    assert "1937" in label
    print("PASS: display_label reads sensibly:", label)


def test_as_dict_excludes_cover_and_empty_fields():
    c = parse_search_response(json.dumps(SAMPLE_RESPONSE).encode())[0]
    result = c.as_dict()
    assert "cover_id" not in result, "cover isn't a plain metadata field, must be excluded"
    assert result["title"] == "The Hobbit"
    assert result["isbn"] == "9780261102217"
    assert "language" not in result, "Open Library's 3-letter codes are deliberately not mapped"
    print("PASS: as_dict() returns apply_metadata-ready fields, excludes cover_id and language")


def test_as_dict_bare_entry_only_has_title_and_authors():
    c = parse_search_response(json.dumps(SAMPLE_RESPONSE).encode())[1]
    result = c.as_dict()
    assert result == {"title": "The Hobbit (bare-bones entry)", "authors_str": "Someone"}, result
    print("PASS: as_dict() omits fields that came back empty")


def test_download_cover_image():
    fake_bytes = b"\x89PNG-fake-image-data"

    def fake_fetch(url):
        assert url == "https://covers.openlibrary.org/b/id/258027-L.jpg"
        return fake_bytes

    c = parse_search_response(json.dumps(SAMPLE_RESPONSE).encode())[0]
    data = download_cover_image(c, fetch=fake_fetch)
    assert data == fake_bytes
    print("PASS: downloads the correct cover image URL for a chosen candidate")


def test_download_cover_image_no_cover_id_raises():
    c = parse_search_response(json.dumps(SAMPLE_RESPONSE).encode())[1]  # bare entry, no cover_i
    try:
        download_cover_image(c, fetch=lambda url: b"unused")
        assert False, "should have raised"
    except OpenLibraryLookupError as exc:
        assert "no cover" in str(exc).lower()
    print("PASS: downloading a cover for a candidate with no cover_id raises clearly")


if __name__ == "__main__":
    test_build_search_url_basic()
    test_build_search_url_no_author()
    test_build_search_url_requires_title()
    test_build_search_url_multi_author_uses_first()
    test_parse_response_extracts_all_fields()
    test_parse_response_subjects_capped()
    test_parse_response_bare_entry_no_crash()
    test_parse_response_empty()
    test_parse_response_garbage()
    test_search_open_library_with_fake_fetch()
    test_search_open_library_network_error_wrapped()
    test_search_open_library_429_retries_then_succeeds()
    test_search_open_library_429_exhausted_gives_clear_message()
    test_search_open_library_non_429_http_error_not_retried()
    test_display_label()
    test_as_dict_excludes_cover_and_empty_fields()
    test_as_dict_bare_entry_only_has_title_and_authors()
    test_download_cover_image()
    test_download_cover_image_no_cover_id_raises()
    print("\nALL OPEN LIBRARY LOOKUP TESTS PASSED")
