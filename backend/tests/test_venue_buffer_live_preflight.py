"""CR-100 live checks distinguish an undeployed schema from a failed test."""
import subprocess

import pytest

from scripts import verify_live as live


@pytest.mark.parametrize("present", [False, True])
def test_buffer_sql_waits_for_all_four_columns(monkeypatch, present):
    calls = []
    monkeypatch.setattr(live, "DB_SCRIPTS", [("venue_buffer_checks.sql", "TC-VENUE-092")])

    def query(*args):
        calls.append(args)
        if args[0] == "-f":
            return subprocess.CompletedProcess(args, 0, '{"rows":[{"result":"VENUE BUFFER CHECKS PASSED"}]}', "")
        return subprocess.CompletedProcess(args, 0, '{"rows":[{"present":' + str(present).lower() + '}]}', "")

    monkeypatch.setattr(live, "_supabase_query", query)
    [result] = live.run_db_checks(None)
    assert result.status == ("pass" if present else "blocked")
    assert len(calls) == (2 if present else 1)
    if not present:
        assert "not deployed" in result.detail


def test_failed_preflight_records_failure_instead_of_aborting_the_run(monkeypatch):
    monkeypatch.setattr(live, "DB_SCRIPTS", [("venue_buffer_checks.sql", "TC-VENUE-092")])
    monkeypatch.setattr(live, "_supabase_query", lambda *args: subprocess.CompletedProcess(
        args, 1, "", "ERROR: connection refused"))
    [result] = live.run_db_checks(None)
    assert result.status == "fail"
    assert "connection refused" in result.detail
