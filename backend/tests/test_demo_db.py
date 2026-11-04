"""demo_db.py's backup, wipe and restore SQL for the live-demo swap, without live
database access: the statements are inspected, not run."""

import json
import os
import time

import pytest

from scripts import demo_db


def write_backup(directory, tables, age_seconds=0):
    directory.mkdir(parents=True, exist_ok=True)
    for table, rows in tables.items():
        (directory / f"{table}.json").write_text(json.dumps(rows))
    counts = directory / "_counts.json"
    counts.write_text(json.dumps({table: len(rows) for table, rows in tables.items()}))
    stamp = time.time() - age_seconds
    os.utime(counts, (stamp, stamp))
    return directory


def test_wipe_never_touches_reference_tables():
    sql = demo_db.wipe_sql(["public.events", "public.notification_types", "public.notifications"])
    assert "public.notification_types" not in sql
    assert "public.events" in sql and "public.notifications" in sql


def test_wipe_deletes_auth_users_after_public_tables():
    sql = demo_db.wipe_sql(["public.events"])
    assert "delete from auth.users" in sql
    assert sql.index("public.events") < sql.index("delete from auth.users")


def test_restore_sql_turns_triggers_off_before_any_insert(tmp_path):
    backup = write_backup(tmp_path / "b", {"public.events": [{"id": "e1", "name": "x"}]})
    sql = demo_db.restore_sql(backup, ["public.events"], {})
    assert "session_replication_role = replica" in sql
    assert sql.index("session_replication_role = replica") < sql.index("insert into")
    assert sql.index("delete from auth.users") < sql.index("insert into")


def test_restore_round_trips_quotes_and_dollar_signs(tmp_path):
    row = {"id": "c1", "body": "can't $$ $tag$ x"}
    backup = write_backup(tmp_path / "b", {"public.event_comments": [row]})
    sql = demo_db.restore_sql(backup, ["public.event_comments"], {})
    tag = sql.split("json_populate_recordset(null::public.event_comments, ")[1].split("$", 2)[1]
    literal = sql.split(f"${tag}$")[1]
    assert json.loads(literal) == [row]


def test_restore_leaves_out_generated_columns(tmp_path):
    backup = write_backup(tmp_path / "b", {"auth.users": [{"id": "u1", "email": "a@b", "confirmed_at": None}]})
    sql = demo_db.restore_sql(backup, [], {"auth.users": {"confirmed_at"}})
    insert = sql[sql.index("insert into auth.users"):]
    assert "confirmed_at" not in insert.split("from json_populate_recordset")[0]
    assert '"email"' in insert


def test_restore_skips_empty_tables(tmp_path):
    backup = write_backup(tmp_path / "b", {"public.events": []})
    assert "insert into public.events" not in demo_db.restore_sql(backup, ["public.events"], {})


def test_compare_counts_reports_each_mismatch():
    assert demo_db.compare_counts({"public.events": 59}, {"public.events": 58}) == [
        "public.events: expected 59, found 58"
    ]
    assert demo_db.compare_counts({"public.events": 59}, {"public.events": 59}) == []


def test_swap_refuses_backup_without_counts(tmp_path):
    with pytest.raises(SystemExit, match="no _counts.json"):
        demo_db.require_fresh_backup(tmp_path)


def test_swap_refuses_backup_older_than_an_hour(tmp_path):
    backup = write_backup(tmp_path / "b", {"public.events": []}, age_seconds=3601)
    with pytest.raises(SystemExit, match="older than an hour"):
        demo_db.require_fresh_backup(backup)
    demo_db.require_fresh_backup(write_backup(tmp_path / "c", {"public.events": []}))


FK_EVENT = ("public.event_status_history", ["event_id"], "public.events", ["id"])


def test_check_backup_passes_a_complete_consistent_backup(tmp_path):
    backup = write_backup(tmp_path / "b", {"public.events": [{"id": "e1"}],
                                           "public.event_status_history": [{"id": "h1", "event_id": "e1"}]})
    assert demo_db.check_backup(backup, [FK_EVENT]) == []


def test_check_backup_finds_a_row_whose_parent_is_missing(tmp_path):
    """Tables are read one by one, so a write mid-backup can leave a child without its parent."""
    backup = write_backup(tmp_path / "b", {"public.events": [{"id": "e1"}],
                                           "public.event_status_history": [{"id": "h1", "event_id": "e2"}]})
    assert demo_db.check_backup(backup, [FK_EVENT]) == [
        "public.event_status_history: 1 row(s) point at a missing public.events"]


def test_check_backup_ignores_null_references(tmp_path):
    backup = write_backup(tmp_path / "b", {"public.events": [],
                                           "public.event_status_history": [{"id": "h1", "event_id": None}]})
    assert demo_db.check_backup(backup, [FK_EVENT]) == []


def test_check_backup_reports_a_missing_or_short_file(tmp_path):
    backup = write_backup(tmp_path / "b", {"public.events": [{"id": "e1"}], "public.venues": [{"id": "v1"}]})
    (backup / "public.venues.json").unlink()
    (backup / "public.events.json").write_text("[]")
    assert demo_db.check_backup(backup, []) == [
        "public.events: file has 0 rows, _counts.json says 1",
        "public.venues: no backup file",
    ]
