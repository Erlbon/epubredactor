"""Tests for the pure history-list logic in gui/app_settings.py.
Doesn't touch QSettings (would need a real Qt platform backend) --
just the list manipulation, which is where the actual logic lives."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from gui.app_settings import _dedupe_and_trim  # noqa: E402


def test_add_to_empty():
    assert _dedupe_and_trim([], "%title%") == ["%title%"]
    print("PASS: adding to empty history")


def test_new_pattern_goes_first():
    result = _dedupe_and_trim(["%author% - %title%"], "%series% %title%")
    assert result == ["%series% %title%", "%author% - %title%"], result
    print("PASS: newest pattern goes to the front")


def test_repeat_pattern_moves_to_front_not_duplicated():
    history = ["%title%", "%series% %title%", "%author%"]
    result = _dedupe_and_trim(history, "%author%")
    assert result == ["%author%", "%title%", "%series% %title%"], result
    assert result.count("%author%") == 1
    print("PASS: re-using a pattern moves it up without duplicating it")


def test_trims_to_max():
    history = [f"pattern-{i}" for i in range(15)]
    result = _dedupe_and_trim(history, "new-pattern", max_history=15)
    assert len(result) == 15
    assert result[0] == "new-pattern"
    assert "pattern-14" not in result  # oldest fell off the end
    print("PASS: history trims to the configured max, dropping the oldest")


def test_blank_pattern_ignored():
    history = ["%title%"]
    assert _dedupe_and_trim(history, "   ") == history
    assert _dedupe_and_trim(history, "") == history
    print("PASS: blank/whitespace patterns are not recorded")


def test_merge_languages_appends_custom():
    from gui.app_settings import _merge_languages
    defaults = [("en", "English"), ("de", "German")]
    custom = [("pt", "Portuguese")]
    result = _merge_languages(defaults, custom)
    assert result == [("en", "English"), ("de", "German"), ("pt", "Portuguese")], result
    print("PASS: custom languages appended after defaults")


def test_merge_languages_defaults_win_on_conflict():
    from gui.app_settings import _merge_languages
    defaults = [("en", "English")]
    custom = [("en", "Definitely Not English")]
    result = _merge_languages(defaults, custom)
    assert result == [("en", "English")], result
    print("PASS: a custom language can't override a default with the same code")


def test_merge_languages_skips_blank_entries():
    from gui.app_settings import _merge_languages
    defaults = [("en", "English")]
    custom = [("", "Nothing"), ("pt", "")]
    result = _merge_languages(defaults, custom)
    assert result == [("en", "English")], result
    print("PASS: blank code/name entries are skipped")


def test_merge_genres_appends_custom():
    from gui.app_settings import _merge_genres
    defaults = ["Fantasy", "Horror"]
    custom = ["Western"]
    result = _merge_genres(defaults, custom)
    assert result == ["Fantasy", "Horror", "Western"], result
    print("PASS: custom genres appended after defaults")


def test_merge_genres_defaults_win_on_conflict_case_insensitive():
    from gui.app_settings import _merge_genres
    defaults = ["Fantasy"]
    custom = ["fantasy"]  # same genre, different case
    result = _merge_genres(defaults, custom)
    assert result == ["Fantasy"], result
    print("PASS: a custom genre can't duplicate a default, case-insensitively")


def test_merge_genres_skips_blank_entries():
    from gui.app_settings import _merge_genres
    defaults = ["Fantasy"]
    custom = ["", "   "]
    result = _merge_genres(defaults, custom)
    assert result == ["Fantasy"], result
    print("PASS: blank genre entries are skipped")


def test_merge_genres_dedupes_custom_against_itself():
    from gui.app_settings import _merge_genres
    defaults = ["Fantasy"]
    custom = ["Western", "western"]  # duplicate of each other
    result = _merge_genres(defaults, custom)
    assert result == ["Fantasy", "Western"], result
    print("PASS: duplicate custom genres (case-insensitive) are only added once")


def test_exclude_hidden_languages():
    from gui.app_settings import _exclude_hidden_languages
    defaults = [("en", "English"), ("de", "German"), ("fr", "French")]
    result = _exclude_hidden_languages(defaults, ["de"])
    assert result == [("en", "English"), ("fr", "French")], result
    print("PASS: a hidden default language code is excluded, others untouched")


def test_exclude_hidden_languages_nothing_hidden_is_noop():
    from gui.app_settings import _exclude_hidden_languages
    defaults = [("en", "English"), ("de", "German")]
    assert _exclude_hidden_languages(defaults, []) == defaults
    print("PASS: no hidden codes leaves the default list unchanged")


def test_exclude_hidden_genres_case_insensitive():
    from gui.app_settings import _exclude_hidden_genres
    defaults = ["Fantasy", "Horror", "Western"]
    result = _exclude_hidden_genres(defaults, ["horror"])  # different case than the default
    assert result == ["Fantasy", "Western"], result
    print("PASS: a hidden default genre is excluded case-insensitively")


def test_exclude_hidden_genres_nothing_hidden_is_noop():
    from gui.app_settings import _exclude_hidden_genres
    defaults = ["Fantasy", "Horror"]
    assert _exclude_hidden_genres(defaults, []) == defaults
    print("PASS: no hidden genres leaves the default list unchanged")


def test_hidden_default_and_custom_merge_pipeline():
    """The realistic end-to-end shape: hide a default, then merge in a
    custom entry -- both stages compose correctly."""
    from gui.app_settings import _exclude_hidden_genres, _merge_genres
    defaults = ["Fantasy", "Horror", "Western"]
    visible_defaults = _exclude_hidden_genres(defaults, ["Horror"])
    result = _merge_genres(visible_defaults, ["Steampunk"])
    assert result == ["Fantasy", "Western", "Steampunk"], result
    print("PASS: hiding a default and adding a custom genre compose correctly together")


def test_add_server_appends():
    from gui.app_settings import _add_server
    result = _add_server(["https://send.djazz.se"], "https://my-own-host.example")
    assert result == ["https://send.djazz.se", "https://my-own-host.example"], result
    print("PASS: adding a new server appends it")


def test_add_server_moves_existing_to_end_case_insensitive():
    from gui.app_settings import _add_server
    result = _add_server(["https://a.example", "https://b.example"], "HTTPS://A.EXAMPLE")
    # Matches case-insensitively (no duplicate), but uses the casing of
    # whatever was just typed, not stale casing from before.
    assert result == ["https://b.example", "HTTPS://A.EXAMPLE"], result
    print("PASS: re-adding an existing server (any case) moves it to the end, no duplicate")


def test_add_server_normalizes_trailing_slash_and_whitespace():
    from gui.app_settings import _add_server
    result = _add_server([], "  https://send.djazz.se/  ")
    assert result == ["https://send.djazz.se"], result
    print("PASS: server URLs are trimmed and have trailing slashes stripped")


def test_add_server_blank_is_noop():
    from gui.app_settings import _add_server
    result = _add_server(["https://a.example"], "   ")
    assert result == ["https://a.example"], result
    print("PASS: adding a blank/whitespace-only URL is a no-op")


def test_remove_server():
    from gui.app_settings import _remove_server
    result = _remove_server(["https://a.example", "https://b.example"], "https://a.example")
    assert result == ["https://b.example"], result
    print("PASS: removing a server drops just that one")


def test_remove_server_never_leaves_list_empty():
    from gui.app_settings import DEFAULT_EREADER_SERVERS, _remove_server
    result = _remove_server(["https://only-one.example"], "https://only-one.example")
    assert result == DEFAULT_EREADER_SERVERS, result
    print("PASS: removing the last server falls back to the default suggestions")


def test_parse_column_widths_valid():
    from gui.app_settings import _parse_column_widths
    result = _parse_column_widths('{"0": 120, "3": 200}')
    assert result == {0: 120, 3: 200}, result
    print("PASS: valid column-width JSON parses to {logical_index: width}")


def test_parse_column_widths_empty_string():
    from gui.app_settings import _parse_column_widths
    assert _parse_column_widths("") == {}
    print("PASS: empty string parses to an empty dict, not an error")


def test_parse_column_widths_garbage_json():
    from gui.app_settings import _parse_column_widths
    assert _parse_column_widths("not json {{{") == {}
    print("PASS: unparseable JSON parses to an empty dict, not a crash")


def test_parse_column_widths_not_a_dict():
    from gui.app_settings import _parse_column_widths
    assert _parse_column_widths("[1, 2, 3]") == {}
    print("PASS: valid JSON that isn't a dict (e.g. a list) parses to an empty dict")


def test_parse_column_widths_drops_malformed_entries():
    from gui.app_settings import _parse_column_widths
    result = _parse_column_widths('{"0": 120, "bad": 50, "2": "not_a_number", "3": -10, "4": 0}')
    assert result == {0: 120}, result
    print("PASS: non-numeric keys/values and non-positive widths are dropped, valid entries kept")


def test_parse_hidden_columns_valid():
    from gui.app_settings import _parse_hidden_columns
    result = _parse_hidden_columns("[0, 3, 5]")
    assert result == {0, 3, 5}, result
    print("PASS: valid hidden-columns JSON parses to a set of logical indices")


def test_parse_hidden_columns_empty_string():
    from gui.app_settings import _parse_hidden_columns
    assert _parse_hidden_columns("") == set()
    print("PASS: empty string parses to an empty set, not an error")


def test_parse_hidden_columns_garbage_json():
    from gui.app_settings import _parse_hidden_columns
    assert _parse_hidden_columns("not json [[[") == set()
    print("PASS: unparseable JSON parses to an empty set, not a crash")


def test_parse_hidden_columns_not_a_list():
    from gui.app_settings import _parse_hidden_columns
    assert _parse_hidden_columns('{"0": true}') == set()
    print("PASS: valid JSON that isn't a list (e.g. a dict) parses to an empty set")


def test_parse_hidden_columns_drops_malformed_entries():
    from gui.app_settings import _parse_hidden_columns
    result = _parse_hidden_columns('[0, "bad", -1, 3, null]')
    assert result == {0, 3}, result
    print("PASS: non-numeric and negative entries are dropped, valid ones kept")


def test_parse_session_files_valid():
    from gui.app_settings import _parse_session_files
    result = _parse_session_files('["/a/book1.epub", "/a/book2.epub"]')
    assert result == ["/a/book1.epub", "/a/book2.epub"], result
    print("PASS: valid session-files JSON parses to a list of paths")


def test_parse_session_files_empty_list_preserved():
    from gui.app_settings import _parse_session_files
    result = _parse_session_files("[]")
    assert result == []
    print("PASS: an explicitly empty saved session parses to an empty list")


def test_parse_session_files_empty_string():
    from gui.app_settings import _parse_session_files
    assert _parse_session_files("") == []
    print("PASS: no saved value at all parses to an empty list, not an error")


def test_parse_session_files_garbage_json():
    from gui.app_settings import _parse_session_files
    assert _parse_session_files("not json [[[") == []
    print("PASS: unparseable JSON parses to an empty list, not a crash")


def test_parse_session_files_not_a_list():
    from gui.app_settings import _parse_session_files
    assert _parse_session_files('{"0": "book.epub"}') == []
    print("PASS: valid JSON that isn't a list (e.g. a dict) parses to an empty list")


def test_parse_session_files_drops_malformed_entries():
    from gui.app_settings import _parse_session_files
    result = _parse_session_files('["/a/book1.epub", 5, null, "", "  ", "/a/book2.epub"]')
    assert result == ["/a/book1.epub", "/a/book2.epub"], result
    print("PASS: non-string and blank entries are dropped, valid paths kept")


if __name__ == "__main__":
    test_add_to_empty()
    test_new_pattern_goes_first()
    test_repeat_pattern_moves_to_front_not_duplicated()
    test_trims_to_max()
    test_blank_pattern_ignored()
    test_merge_languages_appends_custom()
    test_merge_languages_defaults_win_on_conflict()
    test_merge_languages_skips_blank_entries()
    test_merge_genres_appends_custom()
    test_merge_genres_defaults_win_on_conflict_case_insensitive()
    test_merge_genres_skips_blank_entries()
    test_merge_genres_dedupes_custom_against_itself()
    test_exclude_hidden_languages()
    test_exclude_hidden_languages_nothing_hidden_is_noop()
    test_exclude_hidden_genres_case_insensitive()
    test_exclude_hidden_genres_nothing_hidden_is_noop()
    test_hidden_default_and_custom_merge_pipeline()
    test_add_server_appends()
    test_add_server_moves_existing_to_end_case_insensitive()
    test_add_server_normalizes_trailing_slash_and_whitespace()
    test_add_server_blank_is_noop()
    test_remove_server()
    test_remove_server_never_leaves_list_empty()
    test_parse_column_widths_valid()
    test_parse_column_widths_empty_string()
    test_parse_column_widths_garbage_json()
    test_parse_column_widths_not_a_dict()
    test_parse_column_widths_drops_malformed_entries()
    test_parse_hidden_columns_valid()
    test_parse_hidden_columns_empty_string()
    test_parse_hidden_columns_garbage_json()
    test_parse_hidden_columns_not_a_list()
    test_parse_hidden_columns_drops_malformed_entries()
    test_parse_session_files_valid()
    test_parse_session_files_empty_list_preserved()
    test_parse_session_files_empty_string()
    test_parse_session_files_garbage_json()
    test_parse_session_files_not_a_list()
    test_parse_session_files_drops_malformed_entries()
    print("\nALL APP SETTINGS TESTS PASSED")
