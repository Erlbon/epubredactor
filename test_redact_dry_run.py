"""`redact -n` (redactor_common 2026-11-05-01): only the steps marked dry_run_safe run, in memory; nothing on disk
changes (no save, no trash folder, no History entry, no rename log) and the report says DRY RUN. Plus a pin on WHICH
steps are dry_run_safe, so adding one to that list is a deliberate edit."""

import json
import os
import socket

from core import history
from core.redact_steps import Lookups, run_catalogue
from epubcli import cmd_redact
from epubcli.main import main
from gui import app_settings
from test_redact_steps import make_epub

# Every step except the two that rename or move the finished file. The guard only reads; the rest change the
# in-memory working copy and read files, the local databases and the web (see core/redact_steps.py).
DRY_RUN_SAFE = {
    "guard", "validate_fix", "dedupe_manifest_ids", "rebuild_manifest", "repair_navigation", "remove_page_headers",
    "generate_toc", "strip_description_html", "language", "path_tags", "scan_isbn", "scan_publisher", "scan_year",
    "scan_series", "metadata_lookup", "clean_authors", "cover",
}
NOT_SAFE = {"rename", "move_into_folders"}


def test_which_steps_may_run_in_a_dry_run_is_pinned():
    steps = run_catalogue("%title%", "%authors%/%title%")
    assert {s.key for s in steps if s.dry_run_safe} == DRY_RUN_SAFE
    assert {s.key for s in steps if not s.dry_run_safe} == NOT_SAFE


def _snapshot(folder):
    """Every file and folder under `folder`: relative path -> (bytes, mtime_ns), folders -> None."""
    seen = {}
    for root, dirs, files in os.walk(folder):
        for name in dirs:
            seen[os.path.relpath(os.path.join(root, name), folder)] = None
        for name in files:
            path = os.path.join(root, name)
            with open(path, "rb") as f:
                seen[os.path.relpath(path, folder)] = (f.read(), os.stat(path).st_mtime_ns)
    return seen


def test_redact_dry_run_with_every_step_on_changes_nothing_on_disk_and_lists_the_changes(tmp_path, capsys, monkeypatch):
    # No test may reach the internet: any socket connect fails, and the lookups are fakes that record the call.
    def no_network(*_args, **_kwargs):
        raise AssertionError("a dry-run test tried to reach the network")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    asked = []

    def fake(name, answer):
        def call(*args):
            asked.append(name)
            return answer
        return call

    lookups = Lookups(
        google_by_isbn=fake("google_by_isbn", []), google_by_title=fake("google_by_title", []),
        openlibrary_by_isbn=fake("openlibrary_by_isbn", []), openlibrary_by_title=fake("openlibrary_by_title", []),
        local_by_isbn=fake("local_by_isbn", []), local_by_title=fake("local_by_title", []),
        isfdb_by_isbn=fake("isfdb_by_isbn", []), isfdb_by_title=fake("isfdb_by_title", []),
        cover_by_isbn=fake("cover_by_isbn", None), cover_by_id=fake("cover_by_id", None),
        download_google_cover=fake("download_google_cover", None),
    )
    real_build_env = cmd_redact.build_env

    def build_env(args):
        env = real_build_env(args)
        env.lookups = lookups
        return env

    monkeypatch.setattr(cmd_redact, "build_env", build_env)

    # History on, so a real run would journal the save: a dry run must not.
    app_settings.save_history_enabled(True)
    library = tmp_path / "library"
    library.mkdir()
    app_settings.save_library_root(str(library))
    books = library / "Frank Herbert"
    books.mkdir()
    # A book with something for most steps to do: duplicate manifest ids, a broken guide reference, a missing
    # manifest file, HTML in the description, no language, no table of contents, no cover.
    path = make_epub(
        str(books / "dune.epub"), title="Dune", authors=("Herbert, Frank",), language="",
        description="&lt;p&gt;Hello &lt;b&gt;world&lt;/b&gt;&lt;/p&gt;", toc=False, cover=False,
        dup_ids=True, bad_guide=True, missing_item=True,
    )
    make_epub(str(books / "clean.epub"), title="Children of Dune", authors=("Frank Herbert",), publisher="Ace")
    trash = tmp_path / "trash"
    before = _snapshot(library)

    steps = [r["step"] for r in json.loads(_run(capsys, "redact", "--list-steps", "--json"))["results"]]
    argv = ["redact", "-n", str(library), "--trash-dir", str(trash), "--json"]
    for step in steps:
        argv += ["--enable", step]
    document = json.loads(_run(capsys, *argv))

    assert _snapshot(library) == before  # same files and folders, same bytes, same mtimes
    assert not trash.exists()
    assert not os.path.exists(history.get_journal().path)
    assert document["dry_run"] is True and document["failed"] == 0 and document["files"] == 2
    rows = {os.path.basename(r["path"]): r for r in document["results"]}
    assert rows["dune.epub"]["applied"], rows["dune.epub"]  # what a real run would change
    assert any("Rename by pattern" in note and "Move into folders" in note for note in document["run_notes"])
    assert "google_by_title" in asked  # the lookup step did run (against the fakes)
    assert path == str(books / "dune.epub") and os.path.isfile(path)


def test_redact_dry_run_text_report_says_dry_run(tmp_path, capsys, monkeypatch):
    path = make_epub(str(tmp_path / "html.epub"), title="Marked", authors=("A",), description="&lt;p&gt;Hi&lt;/p&gt;")
    before = open(path, "rb").read()
    out = _run(capsys, "redact", "--dry-run", path, "--disable", "metadata_lookup", "--disable", "cover")
    assert "DRY RUN" in out and open(path, "rb").read() == before


def _run(capsys, *argv):
    main(list(argv))
    return capsys.readouterr().out
