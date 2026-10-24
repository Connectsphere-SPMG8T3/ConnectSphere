"""verify_live.py's cleanup touches only its own run's throwaway rows, or rows an earlier
run left behind long ago, so two runs at once (two developers, or the API and browser
suites) can't delete each other's rows mid-run. Without live database access."""

import re

import pytest

from scripts import verify_live

RUN_ID = "20261024164600"
OTHER_RUN_ID = "20261024165000"


@pytest.fixture()
def sql(monkeypatch):
    """Every statement the cleanup sends, instead of running it."""
    sent = []

    def db_query(statement):
        sent.append(statement)
        return []

    monkeypatch.setattr(verify_live, "db_query", db_query)
    return sent


def deletes(statements):
    return [s for s in statements if s.lstrip().lower().startswith("delete")]


def run_all_cleanups(run_id):
    verify_live.delete_throwaway_accounts(run_id)
    verify_live.delete_throwaway_bookings(run_id)
    verify_live.delete_throwaway_venues(run_id)
    verify_live.delete_live_check_lines(run_id)


def test_every_delete_is_limited_to_this_run_or_long_left_over_rows(sql):
    run_all_cleanups(RUN_ID)

    assert deletes(sql), "the cleanup sent no deletes"
    for statement in deletes(sql):
        assert RUN_ID in statement, f"not limited to this run: {statement}"
        assert f"interval '{verify_live.STALE_AFTER}'" in statement, f"no age limit on other runs' rows: {statement}"


def test_no_delete_matches_every_live_check_row_regardless_of_run(sql):
    run_all_cleanups(RUN_ID)

    unguarded = re.compile(r"like '(live-check[^']*)%'\s*(\)|$|returning)", re.IGNORECASE)
    for statement in deletes(sql):
        for match in unguarded.finditer(statement):
            assert RUN_ID in match.group(1), f"bare prefix match outside the age limit: {statement}"


def test_the_age_limit_is_longer_than_a_run():
    hours = int(verify_live.STALE_AFTER.split()[0])
    assert verify_live.STALE_AFTER.endswith("hours") and hours >= 6


def test_a_runs_venue_blocks_carry_its_id(sql):
    ctx = verify_live.Context("http://api", client=None, run_id=RUN_ID)

    assert RUN_ID in verify_live.block_note(ctx)
    assert verify_live.block_note(ctx) != verify_live.block_note(
        verify_live.Context("http://api", client=None, run_id=OTHER_RUN_ID))
