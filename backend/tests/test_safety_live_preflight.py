"""CR-103/CR-104: safety SQL preflight outcomes, without live database access."""

import subprocess

import pytest

from scripts import verify_live


@pytest.fixture()
def safety_runner(monkeypatch):
    monkeypatch.setattr(
        verify_live, "DB_SCRIPTS", [("safety_decision_checks.sql", "TC-SDEC database")],
    )
    return verify_live


def test_missing_migration_is_blocked_without_executing_script(safety_runner, monkeypatch):
    calls = []

    def query(*args):
        calls.append(args)
        assert args[0] != "-f", "SQL verification must not run before migration application"
        return subprocess.CompletedProcess(args, 0, '{"rows":[{"migration_present":false}]}', "")

    monkeypatch.setattr(safety_runner, "_supabase_query", query)

    [result] = safety_runner.run_db_checks(None)

    assert result.status == "blocked"
    assert result.passed is False
    assert "interfaces are missing" in result.detail
    assert len(calls) == 1


def test_present_migration_executes_registered_sql(safety_runner, monkeypatch):
    calls = []

    def query(*args):
        calls.append(args)
        if args[0] == "-f":
            return subprocess.CompletedProcess(args, 0, '{"rows":[{"ok":true}]}', "")
        return subprocess.CompletedProcess(args, 0, '{"rows":[{"migration_present":true}]}', "")

    monkeypatch.setattr(safety_runner, "_supabase_query", query)

    [result] = safety_runner.run_db_checks(None)

    assert result.status == "pass"
    assert result.case_id == "safety_decision_checks.sql"
    assert len(calls) == 2
    assert calls[1] == ("-f", str(safety_runner.VERIFICATION_DIR / "safety_decision_checks.sql"))


def test_preflight_cli_error_is_failure_without_executing_script(safety_runner, monkeypatch):
    calls = []

    def query(*args):
        calls.append(args)
        assert args[0] != "-f", "SQL verification must not run after a failed preflight"
        return subprocess.CompletedProcess(args, 1, "", "ERROR: database connection refused")

    monkeypatch.setattr(safety_runner, "_supabase_query", query)

    [result] = safety_runner.run_db_checks(None)

    assert result.status == "fail"
    assert result.passed is False
    assert "database connection refused" in result.detail
    assert len(calls) == 1
