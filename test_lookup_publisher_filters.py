import json

from core.google_books_lookup import build_query_url, search_google_books
from core.open_library_lookup import build_search_url, search_open_library


def test_open_library_url_carries_the_publisher_only_when_given():
    assert "publisher=Tor" in build_search_url("Dune", "Herbert", 6, "Tor")
    assert "publisher" not in build_search_url("Dune", "Herbert")


def test_open_library_search_falls_back_without_the_publisher():
    urls = []

    def fetch(url):
        urls.append(url)
        return json.dumps({"docs": [] if "publisher=" in url else [{"title": "Dune"}]}).encode()

    found = search_open_library("Dune", "Herbert", fetch=fetch, publisher="Tor")
    assert [c.title for c in found] == ["Dune"] and len(urls) == 2 and "publisher=" not in urls[1]


def test_google_books_url_carries_publisher_and_a_two_letter_language():
    url = build_query_url("Dune", "Herbert", 5, "Ace", "en")
    assert "inpublisher%3AAce" in url and url.endswith("&langRestrict=en")
    assert "langRestrict" not in build_query_url("Dune", "", 5, "", "eng")  # three letters: skipped
    assert "inpublisher" not in build_query_url("Dune")


def test_google_books_search_falls_back_without_the_filters():
    urls = []

    def fetch(url):
        urls.append(url)
        return json.dumps({"items": [] if "inpublisher" in url else [{"volumeInfo": {"title": "Dune"}}]}).encode()

    found = search_google_books("Dune", "Herbert", fetch=fetch, publisher="Ace", language="en")
    assert [c.title for c in found] == ["Dune"] and len(urls) == 2 and "inpublisher" not in urls[1]


def test_search_with_no_filters_is_one_request():
    urls = []
    search_google_books("Dune", fetch=lambda u: urls.append(u) or b"{}")
    assert len(urls) == 1
