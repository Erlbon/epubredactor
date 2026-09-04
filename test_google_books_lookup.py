"""Tests for core/google_books_lookup.py -- all network access is faked
via the injectable `fetch` parameter, using response shapes matching
the real, documented Google Books API schema."""
import json
import os
import sys
import urllib.error

sys.path.insert(0, os.path.dirname(__file__))
from core.google_books_lookup import (  # noqa: E402
    GoogleBooksLookupError,
    build_query_url,
    download_cover_image,
    parse_response,
    search_google_books,
)

SAMPLE_RESPONSE = {
    "kind": "books#volumes",
    "totalItems": 2,
    "items": [
        {
            "kind": "books#volume",
            "volumeInfo": {
                "title": "The Hobbit",
                "authors": ["J.R.R. Tolkien"],
                "publisher": "George Allen & Unwin",
                "publishedDate": "1937-09-21",
                "industryIdentifiers": [
                    {"type": "ISBN_10", "identifier": "0261102214"},
                    {"type": "ISBN_13", "identifier": "9780261102217"},
                ],
                "categories": ["Fiction / Fantasy / Epic"],
                "language": "en",
                "description": "A hobbit goes on an adventure.",
                "imageLinks": {
                    "smallThumbnail": "http://books.google.com/books/small.jpg",
                    "thumbnail": "http://books.google.com/books/thumb.jpg",
                },
            },
        },
        {
            # Real API responses sometimes have entries with NO industry
            # identifiers, no categories, no imageLinks at all -- must
            # not crash, and must NOT be skipped (unlike the old
            # ISBN-only version) since title/author/etc are still useful.
            "kind": "books#volume",
            "volumeInfo": {
                "title": "The Hobbit (bare-bones entry)",
                "authors": ["Someone"],
            },
        },
    ],
}

EMPTY_RESPONSE = {"kind": "books#volumes", "totalItems": 0}


def test_build_query_url_basic():
    url = build_query_url("The Hobbit", "J.R.R. Tolkien")
    assert url.startswith("https://www.googleapis.com/books/v1/volumes?q=")
    assert "intitle%3AThe%20Hobbit" in url or "intitle%3AThe+Hobbit" in url
    assert "inauthor" in url
    print("PASS: query URL includes title and author")


def test_build_query_url_no_author():
    url = build_query_url("Dune", "")
    assert "inauthor" not in url
    print("PASS: query URL omits author when none given")


def test_build_query_url_requires_title():
    try:
        build_query_url("", "Someone")
        assert False, "should have raised"
    except GoogleBooksLookupError:
        pass
    print("PASS: empty title raises GoogleBooksLookupError")


def test_build_query_url_multi_author_uses_first():
    url = build_query_url("Good Omens", "Terry Pratchett; Neil Gaiman")
    assert "Pratchett" in url
    assert "Gaiman" not in url
    print("PASS: only the first author (before ';') is used in the query")


def test_parse_response_extracts_all_fields():
    raw = json.dumps(SAMPLE_RESPONSE).encode()
    candidates = parse_response(raw)
    assert len(candidates) == 2, "an entry with no ISBN must NOT be skipped anymore"
    c = candidates[0]
    assert c.title == "The Hobbit"
    assert c.authors_str == "J.R.R. Tolkien"
    assert c.publisher == "George Allen & Unwin"
    assert c.pub_year == "1937"
    assert c.isbn13 == "9780261102217"
    assert c.isbn10 == "0261102214"
    assert c.best_isbn == "9780261102217"  # prefers isbn13
    assert c.tags_str == "Fiction / Fantasy / Epic"
    assert c.language == "en"
    assert c.description == "A hobbit goes on an adventure."
    print("PASS: parses title/authors/publisher/year/isbn/tags/language/description/cover")


def test_parse_response_cover_url_normalized_to_https():
    raw = json.dumps(SAMPLE_RESPONSE).encode()
    c = parse_response(raw)[0]
    assert c.cover_url == "https://books.google.com/books/thumb.jpg", c.cover_url
    print("PASS: a plain http:// cover URL is normalized to https://")


def test_parse_response_bare_entry_no_crash():
    raw = json.dumps(SAMPLE_RESPONSE).encode()
    c = parse_response(raw)[1]
    assert c.title == "The Hobbit (bare-bones entry)"
    assert c.isbn13 == "" and c.isbn10 == ""
    assert c.cover_url == ""
    assert c.tags_str == ""
    print("PASS: an entry missing ISBN/categories/imageLinks doesn't crash, fields are just empty")


def test_parse_response_empty():
    raw = json.dumps(EMPTY_RESPONSE).encode()
    assert parse_response(raw) == []
    print("PASS: empty result set parses to an empty list, not an error")


def test_parse_response_garbage():
    try:
        parse_response(b"not json at all {{{")
        assert False, "should have raised"
    except GoogleBooksLookupError:
        pass
    print("PASS: unparseable response raises GoogleBooksLookupError")


def test_search_google_books_with_fake_fetch():
    def fake_fetch(url):
        assert "intitle" in url
        return json.dumps(SAMPLE_RESPONSE).encode()

    results = search_google_books("The Hobbit", "J.R.R. Tolkien", fetch=fake_fetch)
    assert len(results) == 2
    assert results[0].best_isbn == "9780261102217"
    print("PASS: search_google_books wires query building + fetch + parsing together")


def test_search_google_books_network_error_wrapped():
    def failing_fetch(url):
        raise urllib.error.URLError("no internet")

    try:
        search_google_books("Some Book", fetch=failing_fetch)
        assert False, "should have raised"
    except GoogleBooksLookupError as exc:
        assert "internet" in str(exc).lower() or "reach" in str(exc).lower()
    print("PASS: network errors are wrapped in a clear GoogleBooksLookupError")


def _http_error(code, reason="Error"):
    return urllib.error.HTTPError(url="https://example.com", code=code, msg=reason, hdrs=None, fp=None)


def test_search_google_books_429_retries_then_succeeds():
    """The realistic case: a transient rate limit that clears up after
    a short wait -- should recover automatically, not fail outright."""
    calls = {"count": 0}

    def flaky_fetch(url):
        calls["count"] += 1
        if calls["count"] < 3:
            raise _http_error(429, "Too Many Requests")
        return json.dumps(SAMPLE_RESPONSE).encode()

    sleeps = []
    results = search_google_books("The Hobbit", fetch=flaky_fetch, sleep_fn=sleeps.append)
    assert len(results) == 2
    assert calls["count"] == 3
    assert sleeps == [1.0, 2.0], sleeps
    print("PASS: a 429 that clears within the retry budget succeeds automatically")


def test_search_google_books_429_exhausted_gives_clear_message():
    """When it doesn't clear up in time, the error message must say
    it's a rate limit, not "check your internet connection" -- that
    would be actively misleading, since the connection is fine."""
    def always_429(url):
        raise _http_error(429, "Too Many Requests")

    sleeps = []
    try:
        search_google_books("Some Book", fetch=always_429, sleep_fn=sleeps.append)
        assert False, "should have raised"
    except GoogleBooksLookupError as exc:
        message = str(exc).lower()
        assert "rate" in message or "429" in message
        assert "internet connection" not in message
    assert sleeps == [1.0, 2.0], sleeps
    print("PASS: a persistent 429 gives a clear rate-limit message, not a misleading connectivity one")


def test_search_google_books_non_429_http_error_not_retried():
    calls = {"count": 0}

    def server_error(url):
        calls["count"] += 1
        raise _http_error(500, "Internal Server Error")

    try:
        search_google_books("Some Book", fetch=server_error, sleep_fn=lambda s: None)
        assert False, "should have raised"
    except GoogleBooksLookupError as exc:
        assert "500" in str(exc)
    assert calls["count"] == 1, "a non-429 HTTP error should fail immediately, not retry"
    print("PASS: a non-429 HTTP error is reported immediately without retrying")


def test_display_label():
    c = parse_response(json.dumps(SAMPLE_RESPONSE).encode())[0]
    label = c.display_label()
    assert "The Hobbit" in label
    assert "Tolkien" in label
    assert "1937" in label
    print("PASS: display_label reads sensibly:", label)


def test_as_dict_excludes_cover_and_empty_fields():
    c = parse_response(json.dumps(SAMPLE_RESPONSE).encode())[0]
    result = c.as_dict()
    assert "cover_url" not in result, "cover isn't a plain metadata field, must be excluded"
    assert result["title"] == "The Hobbit"
    assert result["isbn"] == "9780261102217"
    assert result["tags_str"] == "Fiction / Fantasy / Epic"
    assert result["language"] == "en"
    assert result["description"] == "A hobbit goes on an adventure."
    print("PASS: as_dict() returns apply_metadata-ready fields, excluding cover_url")


def test_as_dict_bare_entry_has_no_isbn_key():
    c = parse_response(json.dumps(SAMPLE_RESPONSE).encode())[1]
    result = c.as_dict()
    assert "isbn" not in result, result
    assert result == {"title": "The Hobbit (bare-bones entry)", "authors_str": "Someone"}
    print("PASS: as_dict() omits fields that came back empty")


def test_download_cover_image():
    fake_bytes = b"\x89PNG-fake-image-data"

    def fake_fetch(url):
        assert url == "https://books.google.com/books/thumb.jpg"
        return fake_bytes

    c = parse_response(json.dumps(SAMPLE_RESPONSE).encode())[0]
    data = download_cover_image(c, fetch=fake_fetch)
    assert data == fake_bytes
    print("PASS: downloads the correct (https-normalized) cover URL")


def test_download_cover_image_no_cover_url_raises():
    c = parse_response(json.dumps(SAMPLE_RESPONSE).encode())[1]  # bare entry, no imageLinks
    try:
        download_cover_image(c, fetch=lambda url: b"unused")
        assert False, "should have raised"
    except GoogleBooksLookupError as exc:
        assert "no cover" in str(exc).lower()
    print("PASS: downloading a cover for a candidate with no cover_url raises clearly")


if __name__ == "__main__":
    test_build_query_url_basic()
    test_build_query_url_no_author()
    test_build_query_url_requires_title()
    test_build_query_url_multi_author_uses_first()
    test_parse_response_extracts_all_fields()
    test_parse_response_cover_url_normalized_to_https()
    test_parse_response_bare_entry_no_crash()
    test_parse_response_empty()
    test_parse_response_garbage()
    test_search_google_books_with_fake_fetch()
    test_search_google_books_network_error_wrapped()
    test_search_google_books_429_retries_then_succeeds()
    test_search_google_books_429_exhausted_gives_clear_message()
    test_search_google_books_non_429_http_error_not_retried()
    test_display_label()
    test_as_dict_excludes_cover_and_empty_fields()
    test_as_dict_bare_entry_has_no_isbn_key()
    test_download_cover_image()
    test_download_cover_image_no_cover_url_raises()
    print("\nALL GOOGLE BOOKS LOOKUP TESTS PASSED")
