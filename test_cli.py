"""The command line (epubcli/): every command on real small EPUBs, text and --json output, exit codes,
--dry-run. Settings are the test-isolated ones (conftest)."""

import json
import os
import shutil

import pytest

from core.epub_metadata import EpubBook
from epubcli import cmd_files, cmd_redact, files as cli_files
from epubcli.main import main
from redactor_common.cli import CliError
from test_redact_steps import make_epub


def run(capsys, *argv):
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def run_json(capsys, *argv):
    code, out, _err = run(capsys, *argv, "--json")
    return code, json.loads(out)


@pytest.fixture
def book(tmp_path):
    return make_epub(str(tmp_path / "dune.epub"), title="Dune", authors=("Frank Herbert",), publisher="Chilton")


# --- info -------------------------------------------------------------------------------------


def test_info_shows_the_default_fields(book, capsys):
    code, out, _ = run(capsys, "info", book)
    assert code == 0 and "[OK, cover]" in out and "title: Dune" in out and "authors: Frank Herbert" in out


def test_info_json_fields_and_all(book, tmp_path, capsys):
    code, document = run_json(capsys, "info", str(tmp_path), "--fields", "title,Publisher,genre")
    assert code == 0 and document["files"] == 1 and document["failed"] == 0
    row = document["results"][0]
    assert row["fields"] == {"title": "Dune", "publisher": "Chilton"} and row["has_cover"] is True and row["status"] == "OK"
    _code, document = run_json(capsys, "info", book, "--all")
    assert {"title", "authors", "language", "publisher"} <= set(document["results"][0]["fields"])


def test_info_reports_an_unreadable_book_and_exits_1(tmp_path, capsys):
    bad = tmp_path / "bad.epub"
    bad.write_bytes(b"this is not a zip file")
    code, document = run_json(capsys, "info", str(bad))
    assert code == 1 and document["failed"] == 1 and document["results"][0]["status"]


def test_info_with_nothing_found_is_a_usage_error(tmp_path):
    with pytest.raises(CliError, match="no EPUB files"):
        main(["info", str(tmp_path / "nope.epub")])


# --- set ----------------------------------------------------------------------------------------


def test_set_changes_fields_and_saves(book, capsys):
    code, document = run_json(
        capsys, "set", book, "-s", "series=Dune Chronicles", "-s", "Series #=1", "-s", "author=Frank Herbert; Brian Herbert",
        "-s", "genre=Science fiction; Adventure", "-s", "year=1965", "--clear", "publisher",
    )
    assert code == 0 and document["results"][0]["status"] == "changed"
    saved = EpubBook(book).metadata
    assert (saved.series, saved.series_index, saved.pub_year, saved.publisher) == ("Dune Chronicles", "1", "1965", "")
    assert saved.authors == ["Frank Herbert", "Brian Herbert"] and saved.tags == ["Science fiction", "Adventure"]
    assert saved.title == "Dune"  # the rest is untouched


def test_set_dry_run_writes_nothing_and_same_value_is_unchanged(book, capsys):
    before = open(book, "rb").read()
    code, out, _ = run(capsys, "set", book, "-s", "title=Else", "-n")
    assert code == 0 and "planned" in out and "'Dune' -> 'Else'" in out and open(book, "rb").read() == before
    _code, document = run_json(capsys, "set", book, "-s", "title=Dune")
    assert document["results"][0]["status"] == "unchanged"


@pytest.mark.parametrize("argv, message", [
    (["-s", "Nonsense=1"], "unknown field"),
    (["-s", "isbn=12345"], "valid ISBN"),
    (["-s", "series_index=abc"], "must be a number"),
    (["-s", "month=13"], "1 to 12"),
    (["-s", "year=abc"], "whole number"),
    (["-s", "language=english"], "language code"),
    (["-s", "novalue"], "FIELD=VALUE"),
    ([], "nothing to change"),
])
def test_set_refuses_bad_input_before_touching_anything(book, argv, message):
    before = open(book, "rb").read()
    with pytest.raises(CliError, match=message):
        main(["set", book, *argv])
    assert open(book, "rb").read() == before


def test_set_accepts_an_isbn_with_hyphens_and_normalises_it(book, capsys):
    run(capsys, "set", book, "-s", "isbn=978-0-441-17271-9")
    assert EpubBook(book).metadata.isbn == "9780441172719"


def test_set_on_an_unreadable_book_fails_with_exit_1(tmp_path, capsys):
    bad = tmp_path / "bad.epub"
    bad.write_bytes(b"not a zip")
    code, document = run_json(capsys, "set", str(bad), "-s", "title=X")
    assert code == 1 and document["failed"] == 1


# --- rename / move -----------------------------------------------------------------------------------


def test_rename_by_pattern_with_padding(tmp_path, capsys):
    path = make_epub(str(tmp_path / "x.epub"), title="Dune", authors=("Frank Herbert",))
    run(capsys, "set", path, "-s", "series=Dune", "-s", "series_index=2")
    code, document = run_json(capsys, "rename", path, "-p", "%series% %series_index% - %title%", "--zero-pad", "3")
    new_path = str(tmp_path / "Dune 002 - Dune.epub")
    assert code == 0 and document["results"][0]["status"] == "renamed" and os.path.exists(new_path)


def test_rename_dry_run_collisions_and_nameless(tmp_path, capsys):
    a = make_epub(str(tmp_path / "a.epub"), title="Same", authors=("A",))
    b = make_epub(str(tmp_path / "b.epub"), title="Same", authors=("A",))
    _code, dry = run_json(capsys, "rename", a, b, "-p", "%title%", "-n")
    assert sorted(os.path.basename(r["new_path"]) for r in dry["results"]) == ["Same (2).epub", "Same.epub"]
    run(capsys, "rename", a, b, "-p", "%title%")
    assert sorted(n for n in os.listdir(tmp_path) if n.endswith(".epub")) == ["Same (2).epub", "Same.epub"]
    nameless = make_epub(str(tmp_path / "n.epub"), title="T", authors=("A",))
    _code, document = run_json(capsys, "rename", nameless, "-p", "%series%")  # no series: nothing to name it by
    assert document["results"][0]["status"] == "skipped" and os.path.exists(nameless)


def test_rename_default_pattern(book, tmp_path, capsys):
    _code, document = run_json(capsys, "rename", book, "-n")
    assert document["pattern"] == "%series% %series_index% - %title%"


def test_move_into_folders_by_pattern_then_copy(book, tmp_path, capsys):
    lib = tmp_path / "library"
    lib.mkdir()
    pattern = "%authors%/%title%"
    _code, dry = run_json(capsys, "move", book, "-p", pattern, "--root", str(lib), "-n")
    assert dry["results"][0]["status"] == "planned" and os.path.exists(book)
    code, document = run_json(capsys, "move", book, "-p", pattern, "--root", str(lib))
    moved = lib / "Frank Herbert" / "Dune.epub"
    assert code == 0 and document["results"][0]["status"] == "moved" and moved.exists() and not os.path.exists(book)
    _code, document = run_json(capsys, "move", str(moved), "-p", "Copies/%title%", "--root", str(lib), "--copy")
    assert document["results"][0]["status"] == "copied" and (lib / "Copies" / "Dune.epub").exists() and moved.exists()


def test_move_checks_the_library_folder(book, tmp_path):
    with pytest.raises(CliError, match="--root"):
        main(["move", book, "-p", "%title%"])
    with pytest.raises(CliError, match="does not exist"):
        main(["move", book, "-p", "%title%", "--root", str(tmp_path / "missing")])


# --- convert ---------------------------------------------------------------------------------------------


def test_convert_dry_run_skips_and_a_missing_calibre_is_reported(tmp_path, capsys, monkeypatch):
    mobi = tmp_path / "old.mobi"
    mobi.write_bytes(b"mobi")
    epub = make_epub(str(tmp_path / "real.epub"))
    done = tmp_path / "done.azw3"
    done.write_bytes(b"x")
    (tmp_path / "done.epub").write_bytes(b"already")
    _code, document = run_json(capsys, "convert", str(mobi), epub, str(done), "-n")
    by_name = {os.path.basename(r["path"]): r["status"] for r in document["results"]}
    assert by_name == {"old.mobi": "planned", "real.epub": "skipped", "done.azw3": "skipped"}
    monkeypatch.setattr(cmd_files, "find_tool", lambda *a, **k: None)
    with pytest.raises(CliError, match="ebook-convert was not found") as info:
        main(["convert", str(mobi)])
    assert info.value.code == 1


def test_convert_with_calibre_keeps_or_trashes_the_original(tmp_path, capsys, monkeypatch):
    mobi = tmp_path / "old.mobi"
    mobi.write_bytes(b"mobi")
    monkeypatch.setattr(cmd_files, "find_tool", lambda *a, **k: "ebook-convert")
    monkeypatch.setattr(cmd_files, "convert_to_epub", lambda tool, src, dst: make_epub(dst))
    code, document = run_json(capsys, "convert", str(mobi))
    assert code == 0 and document["results"][0]["status"] == "converted" and (tmp_path / "old.epub").exists() and mobi.exists()
    (tmp_path / "old.epub").unlink()
    trashed = []
    monkeypatch.setattr(cmd_files, "move_to_trash", trashed.append)
    run(capsys, "convert", str(mobi), "--trash-original")
    assert trashed == [str(mobi)]


def test_convert_failure_is_exit_1_and_changes_nothing(tmp_path, capsys, monkeypatch):
    from core.ebook_convert import EbookConvertError

    mobi = tmp_path / "old.mobi"
    mobi.write_bytes(b"mobi")
    monkeypatch.setattr(cmd_files, "find_tool", lambda *a, **k: "ebook-convert")

    def broken(tool, src, dst):
        raise EbookConvertError("Conversion failed")

    monkeypatch.setattr(cmd_files, "convert_to_epub", broken)
    code, document = run_json(capsys, "convert", str(mobi))
    assert code == 1 and document["results"][0]["status"] == "failed" and mobi.exists()


# --- redact -----------------------------------------------------------------------------------------------


def test_redact_lists_its_steps(capsys):
    code, document = run_json(capsys, "redact", "--list-steps")
    steps = {r["step"]: r["enabled"] for r in document["results"]}
    assert code == 0 and steps["validate_fix"] is True and steps["move_into_folders"] is False
    _code, document = run_json(capsys, "redact", "--list-steps", "--disable", "validate_fix", "--enable", "move_into_folders")
    steps = {r["step"]: r["enabled"] for r in document["results"]}
    assert steps["validate_fix"] is False and steps["move_into_folders"] is True


def _only(capsys, step):
    steps = [r["step"] for r in run_json(capsys, "redact", "--list-steps")[1]["results"]]
    return [arg for s in steps if s != step for arg in ("--disable", s)] + ["--enable", step]


def test_redact_with_every_step_off_changes_nothing(book, tmp_path, capsys):
    before = open(book, "rb").read()
    steps = [r["step"] for r in run_json(capsys, "redact", "--list-steps")[1]["results"]]
    argv = ["redact", book, "--trash-dir", str(tmp_path / "trash")]
    for step in steps:
        argv += ["--disable", step]
    code, document = run_json(capsys, *argv)
    assert code == 0 and document["files"] == 1 and document["failed"] == 0
    assert document["results"][0]["status"] == "unchanged" and open(book, "rb").read() == before


def test_redact_runs_a_step_saves_in_place_and_keeps_the_original_in_the_trash_dir(tmp_path, capsys):
    path = make_epub(str(tmp_path / "html.epub"), title="Marked", authors=("A",), description="&lt;p&gt;Hello &lt;b&gt;world&lt;/b&gt;&lt;/p&gt;")
    assert "<" in EpubBook(path).metadata.description
    bin_dir = tmp_path / "trash"
    code, document = run_json(capsys, "redact", path, *_only(capsys, "strip_description_html"), "--trash-dir", str(bin_dir))
    entry = document["results"][0]
    assert code == 0 and entry["status"] == "changed" and entry["applied"]
    assert EpubBook(path).metadata.description == "Hello world"
    assert len(os.listdir(bin_dir)) == 1  # the original, kept


def test_redact_text_report_and_a_broken_file(tmp_path, capsys):
    bad = tmp_path / "bad.epub"
    bad.write_bytes(b"not a zip")
    code, out, _ = run(capsys, "redact", str(bad), "--disable", "metadata_lookup")
    assert "Redact report" in out and code == 0 and "could not be loaded" in out and bad.read_bytes() == b"not a zip"


def test_redact_rejects_unknown_steps_and_thresholds(book):
    with pytest.raises(CliError, match="unknown step"):
        main(["redact", book, "--disable", "nonsense"])
    with pytest.raises(CliError, match="threshold"):
        main(["redact", book, "--threshold", "250"])
    with pytest.raises(CliError, match="give the EPUB"):
        main(["redact"])


# --- validate -------------------------------------------------------------------------------------------


def test_validate_a_clean_book_is_ok_and_a_broken_one_exits_1(book, tmp_path, capsys):
    code, document = run_json(capsys, "validate", book)
    assert code == 0 and document["problems"] == 0 and document["results"][0]["status"] == "OK"
    broken = make_epub(str(tmp_path / "broken.epub"), missing_item=True)
    code, document = run_json(capsys, "validate", broken)
    row = document["results"][0]
    assert code == 1 and row["problem"] is True and row["status"] == "INVALID"
    assert row["issues"][0]["code"] == "MANIFEST_FILE_MISSING" and row["issues"][0]["fixable"] is False


def test_validate_fix_repairs_what_can_be_repaired_and_dry_run_only_lists_it(tmp_path, capsys):
    path = make_epub(str(tmp_path / "nolang.epub"), language="")
    assert EpubBook(path).validation_status == "ISSUES"
    before = open(path, "rb").read()
    code, document = run_json(capsys, "validate", path, "--fix", "-n")
    assert code == 1 and document["results"][0]["fixed"] and open(path, "rb").read() == before
    code, document = run_json(capsys, "validate", path, "--fix")
    row = document["results"][0]
    assert code == 0 and row["status"] == "OK" and row["fixed"] and row["problem"] is False
    assert EpubBook(path).validation_status == "OK" and EpubBook(path).metadata.language


def test_validate_text_output_and_drm(tmp_path, capsys):
    drm = make_epub(str(tmp_path / "drm.epub"), encrypted=True)
    code, out, _ = run(capsys, "validate", drm)
    assert "drm" in out.lower() and code == 0  # locked, but not a failure
    broken = make_epub(str(tmp_path / "b.epub"), dup_ids=True)
    code, out, _ = run(capsys, "validate", broken)
    assert code == 1 and "PROBLEM" in out and "DUPLICATE_MANIFEST_ID" in out


# --- one exe ------------------------------------------------------------------------------------------


def test_a_command_name_starts_the_command_line_and_a_path_starts_the_window():
    from epubcli import COMMANDS, cli_requested

    assert set(COMMANDS) == {"info", "set", "rename", "move", "convert", "redact", "validate"}
    assert cli_requested(["epubredactor.exe", "info", "x.epub"]) and cli_requested(["epubredactor.exe", "--version"])
    assert not cli_requested(["epubredactor.exe"]) and not cli_requested(["epubredactor.exe", "D:/Books/a.epub"])


def test_the_app_entry_point_runs_the_command_line_without_a_window(book, monkeypatch, capsys):
    import main as app

    monkeypatch.setattr(app.sys, "argv", ["epubredactor", "info", book, "--json"])
    monkeypatch.setattr(app, "run_app", lambda **kw: pytest.fail("the window was started"))
    assert app.main() == 0
    assert json.loads(capsys.readouterr().out)["results"][0]["fields"]["title"] == "Dune"


def test_the_app_entry_point_still_starts_the_window_for_no_command(monkeypatch):
    import main as app

    started = []
    monkeypatch.setattr(app.sys, "argv", ["epubredactor"])
    monkeypatch.setattr(app, "run_app", lambda **kw: started.append(kw["app_name"]) or 0)
    assert app.main() == 0 and started


def test_output_writes_the_result_to_a_file_for_scripts(book, tmp_path, capsys):
    target = tmp_path / "result.json"
    assert main(["info", book, "--json", "--output", str(target)]) == 0 and capsys.readouterr().out == ""
    assert json.loads(target.read_text(encoding="utf-8"))["results"][0]["fields"]["title"] == "Dune"


# --- the documentation covers every option --------------------------------------------------------------


def _readme_cli_section() -> str:
    text = open(os.path.join(os.path.dirname(__file__), "README.md"), encoding="utf-8").read()
    start = text.index("## Command line")
    end = text.find("\n## ", start + 5)
    return text[start:end if end != -1 else None]


def test_the_readme_documents_every_command_option_step_and_field():
    import argparse

    from core.redact_steps import build_catalogue
    from epubcli.fields import FIELD_NAMES
    from epubcli.main import build_parser

    section = _readme_cli_section()
    parser = build_parser()
    missing = [o for action in parser._actions for o in action.option_strings if o not in section]
    subparsers = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    for name, sub in subparsers.choices.items():
        if f"### {name}" not in section:
            missing.append(f"### {name}")
        missing += [f"{name} {o}" for action in sub._actions for o in action.option_strings if o not in section]
    missing += [f"step {s.key}" for s in build_catalogue() if not s.hidden and s.key not in section]
    missing += [f"field {f}" for f in FIELD_NAMES if f not in section]
    assert missing == [], f"the README's Command line section does not mention: {missing}"


def test_the_readme_lists_the_exit_codes_and_the_scripting_ways():
    section = _readme_cli_section()
    for code in ("| 0 |", "| 1 |", "| 2 |", "| 70 |", "| 130 |"):
        assert code in section
    for way in ("start /wait", "Start-Process", "Out-Null", "--output"):
        assert way in section


# --- second review -------------------------------------------------------------------------------------------


def test_convert_trashes_the_original_only_after_the_new_epub_opens(tmp_path, capsys, monkeypatch):
    mobi = tmp_path / "old.mobi"
    mobi.write_bytes(b"mobi")
    monkeypatch.setattr(cmd_files, "find_tool", lambda *a, **k: "ebook-convert")
    monkeypatch.setattr(cmd_files, "convert_to_epub", lambda tool, src, dst: open(dst, "wb").write(b"not an epub"))
    trashed = []
    monkeypatch.setattr(cmd_files, "move_to_trash", trashed.append)
    code, document = run_json(capsys, "convert", str(mobi), "--trash-original")
    row = document["results"][0]
    assert trashed == [] and mobi.exists() and "original was kept" in row["message"]
    (tmp_path / "old.epub").unlink()
    monkeypatch.setattr(cmd_files, "convert_to_epub", lambda tool, src, dst: make_epub(dst))
    run(capsys, "convert", str(mobi), "--trash-original")
    assert trashed == [str(mobi)]


def test_convert_dry_run_and_the_real_run_agree_when_two_sources_share_a_name(tmp_path, capsys, monkeypatch):
    (tmp_path / "x.mobi").write_bytes(b"1")
    (tmp_path / "x.azw3").write_bytes(b"2")
    (tmp_path / "x.jpg").write_bytes(b"3")
    monkeypatch.setattr(cmd_files, "find_tool", lambda *a, **k: "ebook-convert")
    monkeypatch.setattr(cmd_files, "convert_to_epub", lambda tool, src, dst: make_epub(dst))
    _code, plan = run_json(capsys, "convert", str(tmp_path), "-n")
    assert sorted(r["status"] for r in plan["results"]) == ["planned", "skipped"]
    _code, real = run_json(capsys, "convert", str(tmp_path))
    assert sorted(r["status"] for r in real["results"]) == ["converted", "skipped"]
    _code, named = run_json(capsys, "convert", str(tmp_path / "x.jpg"), "-n")  # named in full, but not a book format
    assert named["results"][0]["status"] == "skipped" and "not an e-book format" in named["results"][0]["message"]


def test_set_reports_a_value_the_epub_cannot_hold(book, capsys):
    code, document = run_json(capsys, "set", book, "-s", "series_index=2")  # a number without a series
    row = document["results"][0]
    assert code == 1 and row["status"] == "failed" and row["not_stored"] == ["series_index"]
    code, document = run_json(capsys, "set", book, "-s", "series=Dune", "-s", "series_index=2")
    assert code == 0 and document["results"][0]["status"] == "changed"


def test_set_compares_values_the_way_the_book_stores_them(book, capsys):
    run_json(capsys, "set", book, "-s", "authors=Frank Herbert;Brian Herbert")
    code, document = run_json(capsys, "set", book, "-s", "authors=Frank Herbert; Brian Herbert")
    assert code == 0 and document["results"][0]["status"] == "unchanged"


@pytest.mark.parametrize("argv,message", [
    (["-s", "title=bad\x01char"], "control character"),
    (["-s", "year=²²²²"], "whole number"),
    (["-s", "year=202"], "four-digit"),
    (["-s", "title=two\nlines"], "control character"),
])
def test_set_refuses_values_no_opf_can_store(book, argv, message):
    before = open(book, "rb").read()
    with pytest.raises(CliError, match=message):
        main(["set", book, *argv])
    assert open(book, "rb").read() == before


def test_set_on_a_drm_book_is_allowed_with_a_warning(tmp_path, capsys):
    drm = make_epub(str(tmp_path / "drm.epub"), encrypted=True)
    code, out, err = run(capsys, "set", drm, "-s", "title=New", "--json")
    document = json.loads(out)
    assert code == 0 and document["results"][0]["status"] == "changed"
    assert "DRM" in document["results"][0]["message"] and any("DRM" in w for w in document["warnings"])
    assert EpubBook(drm).metadata.title == "New"


def _break_mimetype(path):
    """The mimetype entry compressed and last, as some tools write it."""
    import zipfile

    with zipfile.ZipFile(path) as src:
        items = [(i.filename, src.read(i.filename)) for i in src.infolist()]
    with zipfile.ZipFile(path, "w") as dst:
        for name, data in items:
            if name != "mimetype":
                dst.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
        dst.writestr("mimetype", b"application/epub+zip", compress_type=zipfile.ZIP_DEFLATED)


def test_validate_fix_repairs_the_mimetype_by_saving(tmp_path, capsys):
    path = make_epub(str(tmp_path / "m.epub"))
    _break_mimetype(path)
    code, document = run_json(capsys, "validate", path)
    assert code == 1 and any(i["code"] == "MIMETYPE_POSITION" and i["fixable"] for i in document["results"][0]["issues"])
    code, document = run_json(capsys, "validate", path, "--fix")
    row = document["results"][0]
    assert code == 0 and row["problem"] is False and any("MIMETYPE_POSITION" in f for f in row["fixed"])
    assert not row["issues_after"]


def test_validate_counts_warnings_on_a_drm_book_as_a_problem(tmp_path, capsys):
    drm = make_epub(str(tmp_path / "drm.epub"), encrypted=True, toc=False)
    code, document = run_json(capsys, "validate", drm)
    assert code == 1 and document["results"][0]["problem"] is True


def test_validate_fix_does_not_claim_fixes_when_the_save_fails(tmp_path, capsys, monkeypatch):
    path = make_epub(str(tmp_path / "g.epub"), language="")
    from core.epub_metadata import EpubError

    def refuse(self, *a, **k):
        raise EpubError("disk full")

    monkeypatch.setattr(EpubBook, "save", refuse)
    code, document = run_json(capsys, "validate", path, "--fix")
    row = document["results"][0]
    assert code == 1 and row["problem"] is True and row["fixed"] == [] and "not saved" in row["message"]


def test_redact_gets_an_image_size_reader_for_the_cover_step():
    import argparse

    from epubcli import cmd_redact

    env = cmd_redact.build_env(argparse.Namespace(trash_dir=None))
    assert env.image_size is not None


def test_rename_defaults_come_from_the_saved_settings(book, capsys):
    from gui import app_settings

    run_json(capsys, "set", book, "-s", "series=Dune", "-s", "series_index=4")
    app_settings.save_rename_zero_pad(True, 3)
    _code, document = run_json(capsys, "rename", book, "-p", "%series% %series_index%", "-n")
    assert document["results"][0]["new_path"].endswith("Dune 004.epub")
    _code, document = run_json(capsys, "rename", book, "-p", "%series% %series_index%", "--zero-pad", "0", "-n")
    assert document["results"][0]["new_path"].endswith("Dune 4.epub")
