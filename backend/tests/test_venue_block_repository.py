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
