"""SCRUM-38 venue booking reads and the reject call, at the Supabase client seam.

The API tests fake these functions; here a recording fake client checks what
each one asks PostgREST for and how it shapes the rows it gets back. The real
queries run against the live project in `supabase/verification/` and
`scripts/verify_live.py`.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

from app.modules.venues import repository


class FakeQuery:
    """Chains like a PostgREST builder, records every call, returns `data`."""

    def __init__(self, data):
        self.data = data
        self.calls = []

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return self
        return record

    def execute(self):
        return SimpleNamespace(data=self.data)


class FakeClient:
    def __init__(self, data):
        self.query = FakeQuery(data)
        self.tables = []
        self.rpcs = []

    def table(self, name):
        self.tables.append(name)
        return self.query

    def rpc(self, name, params):
        self.rpcs.append((name, params))
        return self.query


def use(monkeypatch, data):
    client = FakeClient(data)
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: client)
    return client


BOOKING_ROW = {
    "id": "d1", "event_id": "e1", "venue_id": "v1",
    "occupied_period": '["2031-03-10 06:00:00+00","2031-03-10 09:00:00+00")',
    "status": "rejected", "request_note": "Early access", "created_at": "2031-02-01T00:00:00+00:00",
    "decision_reason": "Capacity exceeded", "suggestion_note": "Try Heritage Hall",
    "decided_at": "2031-03-01T02:00:00+00:00",
    "venue": {"name": "Innovation Lab"}, "requester": [{"full_name": "Marcus Lim"}], "decider": None,
}


def test_get_booking_shapes_the_row_and_names_every_embed(monkeypatch):
    client = use(monkeypatch, [BOOKING_ROW])

    booking = repository.get_booking("d1")

    assert client.tables == ["venue_bookings"]
    [select] = [args[0] for name, args, _ in client.query.calls if name == "select"]
    # Two foreign keys each to venues and profiles: an unnamed embed is PGRST201.
    for constraint in ("venue_bookings_venue_id_fkey", "venue_bookings_requested_by_fkey",
                       "venue_bookings_decided_by_fkey"):
        assert constraint in select
    assert ("eq", ("id", "d1"), {}) in client.query.calls
    assert booking["venue_name"] == "Innovation Lab"
    assert booking["requested_by_name"] == "Marcus Lim"  # an embed PostgREST returned as a list
    assert booking["decided_by_name"] is None
    assert booking["period"].starts_at == datetime(2031, 3, 10, 6, tzinfo=timezone.utc)
    assert booking["requested_at"] == datetime(2031, 2, 1, tzinfo=timezone.utc)
    assert booking["decided_at"] == datetime(2031, 3, 1, 2, tzinfo=timezone.utc)
    assert booking["decision_reason"] == "Capacity exceeded"
    assert booking["suggestion_note"] == "Try Heritage Hall"


def test_get_booking_of_an_undecided_booking_has_no_decision_time(monkeypatch):
    use(monkeypatch, [{**BOOKING_ROW, "status": "held", "decided_at": None, "requester": []}])

    booking = repository.get_booking("d1")

    assert booking["decided_at"] is None
    assert booking["requested_by_name"] is None


def test_get_booking_of_a_missing_booking_is_none(monkeypatch):
    use(monkeypatch, [])

    assert repository.get_booking("nope") is None


def test_list_booking_history_reads_cr99s_table_oldest_first(monkeypatch):
    client = use(monkeypatch, [
        {"action": "expiry_changed", "from_status": "held", "to_status": "held", "reason": None,
         "suggestion_note": None, "created_at": "2031-02-02T00:00:00+00:00", "actor": None},
        {"action": "rejected", "from_status": "held", "to_status": "rejected", "reason": "Capacity exceeded",
         "suggestion_note": "Try Heritage Hall", "created_at": "2031-03-01T02:00:00+00:00",
         "actor": {"full_name": "Venue Staff"}},
    ])

    history = repository.list_booking_history("d1")

    assert client.tables == ["venue_booking_history"]
    assert ("eq", ("booking_id", "d1"), {}) in client.query.calls
    assert ("order", ("created_at",), {}) in client.query.calls
    assert history == [
        {"action": "expiry_changed", "from_status": "held", "to_status": "held", "actor_name": None,
         "reason": None, "suggestion": None, "at": datetime(2031, 2, 2, tzinfo=timezone.utc)},
        {"action": "rejected", "from_status": "held", "to_status": "rejected", "actor_name": "Venue Staff",
         "reason": "Capacity exceeded", "suggestion": "Try Heritage Hall",
         "at": datetime(2031, 3, 1, 2, tzinfo=timezone.utc)},
    ]


def test_reject_booking_calls_the_database_function_with_every_argument(monkeypatch):
    client = use(monkeypatch, [{"outcome": "ok", "event_id": "e1", "from_status": "held"}])

    result = repository.reject_booking("d1", "u1", "Capacity exceeded", None, notify_message="Rejected.")

    assert client.rpcs == [("reject_venue_booking", {
        "p_booking_id": "d1", "p_actor_id": "u1", "p_reason": "Capacity exceeded",
        "p_suggestion": None, "p_notify_message": "Rejected.",
    })]
    assert result == {"outcome": "ok", "event_id": "e1", "from_status": "held"}


def test_list_rejected_bookings_reads_only_this_events_rejections_newest_first(monkeypatch):
    client = use(monkeypatch, [
        {"id": "d2", "venue_id": "v2", "decision_reason": "Closed", "suggestion_note": None,
         "decided_at": "2031-03-02T00:00:00+00:00", "venue": {"name": "Heritage Hall"}},
        {"id": "d1", "venue_id": "v1", "decision_reason": None, "suggestion_note": None,
         "decided_at": None, "venue": None},
    ])

    rejected = repository.list_rejected_bookings("e1")

    assert ("eq", ("event_id", "e1"), {}) in client.query.calls
    assert ("eq", ("status", "rejected"), {}) in client.query.calls
    assert ("order", ("decided_at",), {"desc": True}) in client.query.calls
    assert rejected == [
        {"id": "d2", "venue_id": "v2", "venue_name": "Heritage Hall", "reason": "Closed", "suggestion": None,
         "decided_at": datetime(2031, 3, 2, tzinfo=timezone.utc)},
        # Rejected before SCRUM-38 recorded reasons: still listed, with nothing to say.
        {"id": "d1", "venue_id": "v1", "venue_name": None, "reason": None, "suggestion": None, "decided_at": None},
    ]
