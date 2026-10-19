"""verify_live.db_query reads the Supabase CLI's JSON in either of its two shapes.

Under an agent the CLI wraps rows as `{"rows": [...], "boundary": ...}`; in a plain
terminal it prints a bare list, and prints `[]` for a delete that removed nothing.
The script used to look only for the first `{`, so the second shape crashed the
run before any check started (found while running CR-101's live checks).
"""

import subprocess

import pytest

from scripts import verify_live


def returns(monkeypatch, stdout: str, returncode: int = 0, stderr: str = ""):
    monkeypatch.setattr(
        verify_live,
        "_supabase_query",
        lambda *args: subprocess.CompletedProcess(args, returncode, stdout, stderr),
    )


def test_reads_the_wrapped_object_form(monkeypatch):
    returns(monkeypatch, 'Initialising\n{"boundary": "b", "rows": [{"x": 1}], "warning": "w"}\n')
    assert verify_live.db_query("select 1") == [{"x": 1}]


def test_reads_a_bare_list(monkeypatch):
    returns(monkeypatch, '[\n  {"x": 1},\n  {"x": 2}\n]\n')
    assert verify_live.db_query("select 1") == [{"x": 1}, {"x": 2}]


def test_an_empty_result_is_an_empty_list_not_a_crash(monkeypatch):
    returns(monkeypatch, "[]\n")
    assert verify_live.db_query("delete from auth.users where false returning email") == []


def test_trailing_cli_notices_are_ignored(monkeypatch):
    returns(monkeypatch, '[{"x": 1}]\nA new version of Supabase CLI is available: v9\n')
    assert verify_live.db_query("select 1") == [{"x": 1}]


def test_an_object_with_no_rows_is_empty(monkeypatch):
    returns(monkeypatch, '{"boundary": "b"}')
    assert verify_live.db_query("select 1") == []


def test_output_with_no_json_is_a_clear_failure(monkeypatch):
    returns(monkeypatch, "Initialising login role...\n")
    with pytest.raises(verify_live.CheckFailed, match="no JSON"):
        verify_live.db_query("select 1")


def test_a_failed_query_still_reports_the_cli_error(monkeypatch):
    returns(monkeypatch, "", returncode=1, stderr="Error: not logged in")
    with pytest.raises(verify_live.CheckFailed, match="database query failed"):
        verify_live.db_query("select 1")


def test_supabase_cli_output_is_decoded_as_utf8(monkeypatch):
    options = {}

    def run(*args, **kwargs):
        options.update(kwargs)
        return subprocess.CompletedProcess(args, 0, "[]", "")

    monkeypatch.setattr(verify_live.subprocess, "run", run)

    verify_live._supabase_query("select 1")

    assert options["encoding"] == "utf-8"


def test_failed_rows_reads_the_bare_list_form():
    assert verify_live._failed_rows('[{"check": "grants", "ok": true}, {"check": "rls", "ok": false}]') == ["rls"]


def test_failed_rows_reads_the_wrapped_form_and_a_script_that_only_prints_a_result():
    assert verify_live._failed_rows('{"rows": [{"check": "a", "ok": false}]}') == ["a"]
    assert verify_live._failed_rows('[{"result": "CR-101 LEAD ASSIGNMENT CHECKS PASSED"}]') == []
