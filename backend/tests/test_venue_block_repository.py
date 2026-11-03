"""SCRUM-51 venue block reads and the create call, at the Supabase client seam.

The API tests fake these functions; here a recording fake client checks what
each one asks PostgREST for and how it shapes the rows. The trigger's flags,
links and notices are proved against the live project in `scripts/verify_live.py`.
"""

from datetime import datetime, timedelta, timezone

from app.modules.venues import repository
from app.modules.venues.schemas import Period
from tests.test_venue_booking_decision_repository import FakeClient

VENUE_ID = "b0000000-0000-4000-8000-000000000001"
BLOCK_ID = "f0000000-0000-4000-8000-000000000511"
FUTURE = '["2031-05-20 09:00:00+00","2031-05-20 12:00:00+00")'
PAST = '["2020-05-20 09:00:00+00","2020-05-20 12:00:00+00")'
PERIOD = Period(starts_at=datetime(2031, 5, 20, 8, tzinfo=timezone.utc),
                ends_at=datetime(2031, 5, 20, 16, tzinfo=timezone.utc))


def _conflict(kind="booking", status="approved", period=FUTURE, booking_id="d1"):
    return {"venue_id": VENUE_ID, "kind": kind, "booking_id": booking_id if kind == "booking" else None,
            "event_id": "e1" if kind == "booking" else None, "event_name": "Gala",
            "booking_status": status if kind == "booking" else None,
            "block_reason": "maintenance" if kind == "block" else None, "occupied_period": period}


def test_list_block_conflicts_asks_the_shared_check_and_keeps_held_and_approved_future_bookings(monkeypatch):
    client = FakeClient([
        _conflict(status="approved", booking_id="d1"),
        _conflict(status="held", booking_id="d2"),
        _conflict(status="re_review", booking_id="d3"),
        _conflict(kind="block"),
        _conflict(status="approved", period=PAST, booking_id="d4"),
    ])
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: client)

    rows = repository.list_block_conflicts(VENUE_ID, PERIOD)

    assert client.rpcs == [("venue_conflicts", {"p_period": "[2031-05-20T08:00:00+00:00,2031-05-20T16:00:00+00:00)",
                                                "p_venue_id": VENUE_ID})]
    assert [(r.booking_id, r.status) for r in rows] == [("d1", "approved"), ("d2", "held")]
    assert rows[0].period.starts_at == datetime(2031, 5, 20, 9, tzinfo=timezone.utc)


def test_list_block_conflicts_with_nothing_in_the_way_is_empty(monkeypatch):
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: FakeClient(None))
    assert repository.list_block_conflicts(VENUE_ID, PERIOD) == []


def test_create_venue_block_sends_every_argument_and_returns_the_outcome(monkeypatch):
    client = FakeClient([{"outcome": "ok", "block_id": BLOCK_ID}])
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: client)
    after = {"block": {"reason": "safety"}}

    result = repository.create_venue_block(VENUE_ID, "a1", period=PERIOD, reason="safety", notes="Cracked beam",
                                           history_after=after)

    assert result == {"outcome": "ok", "block_id": BLOCK_ID}
    assert client.rpcs == [("create_venue_block", {
        "p_venue_id": VENUE_ID, "p_actor_id": "a1",
        "p_starts_at": "2031-05-20T08:00:00+00:00", "p_ends_at": "2031-05-20T16:00:00+00:00",
        "p_reason": "safety", "p_notes": "Cracked beam", "p_history_after": after,
    })]


def test_create_venue_block_refusal_has_no_block_id(monkeypatch):
    monkeypatch.setattr(repository, "get_supabase_admin_client",
                        lambda: FakeClient([{"outcome": "ended", "block_id": None}]))
    result = repository.create_venue_block(VENUE_ID, "a1", period=PERIOD, reason="other", notes="x",
                                           history_after={})
    assert result == {"outcome": "ended", "block_id": None}


def test_list_block_bookings_reads_the_links_soonest_first_and_drops_bookings_no_longer_open(monkeypatch):
    later = '["2031-05-21 09:00:00+00","2031-05-21 12:00:00+00")'
    client = FakeClient([
        {"booking": {"id": "d2", "event_id": "e2", "status": "held", "occupied_period": later}},
        {"booking": {"id": "d1", "event_id": "e1", "status": "approved", "occupied_period": FUTURE}},
        {"booking": {"id": "d3", "event_id": "e3", "status": "released", "occupied_period": FUTURE}},
        {"booking": None},
    ])
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: client)

    rows = repository.list_block_bookings(BLOCK_ID)

    assert client.tables == ["venue_block_bookings"]
    assert ("eq", ("block_id", BLOCK_ID), {}) in client.query.calls
    assert [r.booking_id for r in rows] == ["d1", "d2"]
    assert rows[0].period.ends_at - rows[0].period.starts_at == timedelta(hours=3)


# --- SCRUM-54: changing a block, reading it back, and what it freed -------------

BLOCK_ROW = {
    "id": BLOCK_ID, "venue_id": VENUE_ID, "blocked_period": FUTURE, "reason": "maintenance", "notes": "Aircon",
    "created_at": "2031-05-01T02:00:00+00:00", "original_period": None, "changed_at": None, "change_note": None,
    "removed_at": None, "creator": {"id": "a1", "full_name": "Vera Staff"}, "changer": None,
}


def test_change_venue_block_sends_every_argument_and_returns_the_outcome(monkeypatch):
    client = FakeClient([{"outcome": "ok"}])
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: client)
    new_end = datetime(2031, 5, 20, 10, tzinfo=timezone.utc)

    result = repository.change_venue_block(VENUE_ID, BLOCK_ID, "a1", action="shorten", ends_at=new_end, note="Done")

    assert result == {"outcome": "ok"}
    assert client.rpcs == [("change_venue_block", {
        "p_venue_id": VENUE_ID, "p_block_id": BLOCK_ID, "p_actor_id": "a1", "p_action": "shorten",
        "p_new_ends_at": "2031-05-20T10:00:00+00:00", "p_note": "Done",
    })]


def test_change_venue_block_without_a_new_end_sends_null(monkeypatch):
    client = FakeClient([{"outcome": "ended"}])
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: client)

    assert repository.change_venue_block(VENUE_ID, BLOCK_ID, "a1", action="end_now", ends_at=None,
                                         note=None) == {"outcome": "ended"}
    assert client.rpcs[0][1]["p_new_ends_at"] is None


def test_get_block_names_who_set_it_and_an_unchanged_block_is_active(monkeypatch):
    client = FakeClient([BLOCK_ROW])
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: client)

    block = repository.get_block(BLOCK_ID)

    assert client.tables == ["venue_blocks"]
    [select] = [args[0] for name, args, _ in client.query.calls if name == "select"]
    # Two foreign keys to profiles (created_by, changed_by): an unnamed embed is PGRST201.
    assert "creator:profiles!venue_blocks_created_by_fkey(id, full_name)" in select
    assert "changer:profiles!venue_blocks_changed_by_fkey(id, full_name)" in select
    assert block.status == "active" and block.original_period is None
    assert block.created_by.full_name == "Vera Staff" and block.changed_by is None
    assert block.created_at == datetime(2031, 5, 1, 2, tzinfo=timezone.utc)


def test_get_block_reads_an_ended_early_block_with_its_original_period(monkeypatch):
    row = {**BLOCK_ROW, "original_period": '["2031-05-20 09:00:00+00","2031-05-21 09:00:00+00")',
           "changed_at": "2031-05-20T10:00:00+00:00", "change_note": "Fixed", "changer": [{"id": "a2",
                                                                                            "full_name": None}]}
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: FakeClient([row]))

    block = repository.get_block(BLOCK_ID)

    assert block.status == "ended_early"
    assert block.original_period.ends_at == datetime(2031, 5, 21, 9, tzinfo=timezone.utc)
    assert block.changed_by.id == "a2" and block.change_note == "Fixed"


def test_get_block_reads_a_removed_block(monkeypatch):
    row = {**BLOCK_ROW, "original_period": FUTURE, "removed_at": "2031-05-19T10:00:00+00:00"}
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: FakeClient([row]))
    assert repository.get_block(BLOCK_ID).status == "removed"


def test_get_block_that_does_not_exist_is_none(monkeypatch):
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: FakeClient([]))
    assert repository.get_block(BLOCK_ID) is None


def test_list_restorable_block_bookings_asks_the_database_for_this_block(monkeypatch):
    client = FakeClient([{"booking_id": "d1", "event_id": "e1", "status": "approved", "occupied_period": FUTURE,
                          "has_pending_replacement": True}])
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: client)

    [booking] = repository.list_restorable_block_bookings(BLOCK_ID)

    assert client.rpcs == [("restorable_block_bookings", {"p_block_id": BLOCK_ID})]
    assert (booking.booking_id, booking.status, booking.has_pending_replacement) == ("d1", "approved", True)
    assert booking.period.starts_at == datetime(2031, 5, 20, 9, tzinfo=timezone.utc)


def test_list_restorable_block_bookings_with_none_is_empty(monkeypatch):
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: FakeClient(None))
    assert repository.list_restorable_block_bookings(BLOCK_ID) == []


def test_list_upcoming_blocks_leaves_out_removed_blocks_and_names_who_set_them(monkeypatch):
    removed = {**BLOCK_ROW, "id": "gone", "removed_at": "2031-05-19T10:00:00+00:00"}
    client = FakeClient([BLOCK_ROW, removed])
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: client)

    blocks = repository.list_upcoming_blocks(VENUE_ID, datetime(2031, 5, 1, tzinfo=timezone.utc))

    assert [b.id for b in blocks] == [BLOCK_ID]
    assert blocks[0].created_by.full_name == "Vera Staff"
