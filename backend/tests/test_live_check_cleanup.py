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
    verify_live.cleanup_throwaway_data(run_id)
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


def test_throwaway_events_are_deleted_before_attendee_accounts(sql):
    verify_live.cleanup_throwaway_data(RUN_ID)

    statements = [statement.lower() for statement in sql]
    event_delete = next(i for i, statement in enumerate(statements)
                        if statement.startswith("delete from public.events"))
    account_delete = next(i for i, statement in enumerate(statements)
                          if statement.startswith("delete from auth.users"))
    assert event_delete < account_delete


def like_patterns(statement, table):
    """The `like` patterns a delete on `table` uses for rows of any age, as regular
    expressions. Patterns limited to long-left-over rows don't count: a run's own
    fresh rows must be deleted the same day."""
    if not re.search(rf"delete from {re.escape(table)}\b", statement):
        return []
    return [re.compile("^" + re.escape(p).replace("%", ".*").replace("_", ".") + "$")
            for p in re.findall(r"like '([^']*)'(?! and created_at)", statement.split(" where ", 1)[1])]


@pytest.mark.parametrize("table, name", [
    ("public.events", f"live-check {RUN_ID} 84-001"),
    ("public.venues", f"live-check venue {RUN_ID} B001"),
    ("public.venues", f"live-check {RUN_ID} 076"),  # CR-94's venues use the event prefix
    ("public.equipment", f"live-check equipment {RUN_ID} EQR-003"),
    ("public.venue_blocks", f"live-check {RUN_ID}"),
    ("auth.users", f"live-check+{RUN_ID}-SIGNUP001@connectsphere.dev"),
])
def test_each_name_a_run_gives_its_rows_is_deleted_by_that_run(sql, table, name):
    run_all_cleanups(RUN_ID)

    patterns = [p for s in deletes(sql) for p in like_patterns(s, table)]
    assert any(p.match(name) for p in patterns), f"no {table} delete matches {name!r}"
