from types import SimpleNamespace
from app.modules.events import repository


def test_update_event_reads_the_updated_row_from_a_list_response(monkeypatch):
    updated_row = {"id": "event-1", "name": "Updated workshop", "version": 2}

    class UpdateQuery:
        def update(self, values):
            self.values = values
            return self

        def eq(self, field, value):
            return self

        def select(self, columns):
            return self

        def execute(self):
            return SimpleNamespace(data=[updated_row])

    class AdminClient:
        def table(self, name):
            return UpdateQuery()

    client = AdminClient()
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: client)

    result = repository.update_event("event-1", {"name": "Updated workshop"}, 1)

    assert result == updated_row


class TableQuery:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def select(self, columns):
        self.calls.append(("select", columns))
        return self

    def eq(self, field, value):
        self.calls.append(("eq", field, value))
        return self

    def order(self, field, **kwargs):
        self.calls.append(("order", field, kwargs))
        return self

    def maybe_single(self):
        self.calls.append(("maybe_single",))
        return self

    def insert(self, values):
        self.calls.append(("insert", values))
        return self

    def update(self, values):
        self.calls.append(("update", values))
        return self

    def delete(self):
        self.calls.append(("delete",))
        return self

    def execute(self):
        return self.response


class TableClient:
    def __init__(self, response):
        self.response = response
        self.queries = []

    def table(self, name):
        query = TableQuery(self.response)
        query.calls.append(("table", name))
        self.queries.append(query)
        return query


def test_event_space_repository_crud_covers_empty_and_singleton_responses(monkeypatch):
    space = {"id": "space-1", "event_id": "event-1", "label": "Main venue", "version": 1}
    client = TableClient(SimpleNamespace(data=[space]))
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: client)

    assert repository.list_event_spaces("event-1") == [space]
    assert client.queries[-1].calls[0] == ("table", "event_space_requests")
    assert ("eq", "event_id", "event-1") in client.queries[-1].calls

    client.response = SimpleNamespace(data=None)
    assert repository.list_event_spaces("event-1") == []

    client.response = SimpleNamespace(data=[space])
    assert repository.create_space("event-1", {"label": "Main venue"}) == space
    assert ("insert", {"label": "Main venue", "event_id": "event-1"}) in client.queries[-1].calls

    client.response = SimpleNamespace(data=space)
    assert repository.create_space("event-1", {"label": "Main venue"}) == space

    client.response = SimpleNamespace(data=[space])
    assert repository.update_space("space-1", {"label": "Updated"}, 1) == space
    assert ("update", {"label": "Updated", "version": 2}) in client.queries[-1].calls
    assert ("eq", "version", 1) in client.queries[-1].calls

    client.response = SimpleNamespace(data=space)
    assert repository.update_space("space-1", {"label": "Updated"}, 1) == space
    client.response = SimpleNamespace(data=[])
    assert repository.update_space("space-1", {"label": "Updated"}, 1) is None
    client.response = None
    assert repository.update_space("space-1", {"label": "Updated"}, 1) is None

    client.response = SimpleNamespace(data=[space])
    assert repository.delete_space("space-1", 1) is True
    assert ("eq", "version", 1) in client.queries[-1].calls
    client.response = SimpleNamespace(data=[])
    assert repository.delete_space("space-1", 1) is False
    client.response = None
    assert repository.delete_space("space-1", 1) is False

    client.response = SimpleNamespace(data=space)
    assert repository.get_space("space-1") == space
    assert ("maybe_single",) in client.queries[-1].calls
    client.response = None
    assert repository.get_space("space-1") is None


def test_event_responses_attach_space_requests_to_full_event_rows(monkeypatch):
    event = {"id": "event-1", "status": "draft", "name": "Summit"}
    space = {"id": "space-1", "event_id": "event-1", "label": "Main venue"}
    monkeypatch.setattr(repository, "list_event_spaces", lambda event_id: [space])

    assert repository._with_spaces(None) is None
    assert repository._with_spaces({"id": "partial"}) == {"id": "partial"}
    assert repository._with_spaces(event) == {**event, "spaces": [space]}

    client = TableClient(SimpleNamespace(data=[event]))
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: client)
    assert repository.list_events("organiser-1") == [{**event, "spaces": [space]}]
    assert ("eq", "organiser_id", "organiser-1") in client.queries[-1].calls

    client.response = SimpleNamespace(data=event)
    assert repository.get_event("event-1") == {**event, "spaces": [space]}
    assert ("maybe_single",) in client.queries[-1].calls
    client.response = None
    assert repository.get_event("event-1") is None

    client.response = SimpleNamespace(data=[event])
    assert repository.create_event("organiser-1", {"name": "Summit"}) == {**event, "spaces": [space]}
    assert ("insert", {"name": "Summit", "organiser_id": "organiser-1", "status": "draft"}) in client.queries[-1].calls
    client.response = SimpleNamespace(data=event)
    assert repository.create_event("organiser-1", {"name": "Summit"}) == {**event, "spaces": [space]}


def test_update_event_enriches_a_full_event_row_with_its_spaces(monkeypatch):
    event = {"id": "event-1", "status": "draft", "name": "Summit", "version": 2}
    space = {"id": "space-1", "event_id": "event-1", "label": "Main venue"}
    client = TableClient(SimpleNamespace(data=[event]))
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: client)
    monkeypatch.setattr(repository, "list_event_spaces", lambda event_id: [space])

    assert repository.update_event("event-1", {"name": "Summit"}, 1) == {**event, "spaces": [space]}

def test_status_history_puts_the_creation_entry_last_when_timestamps_tie(monkeypatch):
    """A creation row (no from_status) and a later row can share a timestamp,
    e.g. seeded events whose created_at and submitted_at are both now(); newest
    first must still end with the creation row."""
    orders = []

    class HistoryQuery:
        def select(self, columns):
            return self

        def eq(self, field, value):
            return self

        def order(self, column, *, desc=False, nullsfirst=None):
            orders.append((column, desc, nullsfirst))
            return self

        def execute(self):
            return SimpleNamespace(data=[])

    class AdminClient:
        def table(self, name):
            return HistoryQuery()

    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: AdminClient())

    repository.list_status_history("event-1")

    assert orders == [("at", True, None), ("from_status", True, False)]


def test_assignment_history_reads_the_event_s_rows_with_both_coordinators_named(monkeypatch):
    seen = {}

    class Query:
        def select(self, columns):
            seen["columns"] = columns
            return self

        def eq(self, field, value):
            seen["eq"] = (field, value)
            return self

        def order(self, column, *, desc=False):
            seen["order"] = (column, desc)
            return self

        def execute(self):
            return SimpleNamespace(data=[{"id": "a1"}])

    class AdminClient:
        def table(self, name):
            seen["table"] = name
            return Query()

    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: AdminClient())

    assert repository.list_assignment_history("event-1") == [{"id": "a1"}]
    assert seen["table"] == "event_assignment_history"
    assert seen["eq"] == ("event_id", "event-1") and seen["order"] == ("at", True)
    for embedded in ("actor:", "from_coordinator:", "to_coordinator:"):
        assert embedded in seen["columns"]


class RpcClient:
    """Records the RPC name and parameters; answers with the rows given."""

    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows)


def test_return_event_calls_the_return_function_with_every_parameter(monkeypatch):
    client = RpcClient([{"id": "event-1", "status": "returned"}])
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: client)

    row = repository.return_event(
        "event-1", "coordinator-1", ["under_review"], "returned", 3,
        message="Confirm attendance", flagged_fields=["expected_attendance"], notify_message="msg",
    )

    assert row == {"id": "event-1", "status": "returned"}
    assert client.calls == [("return_event_for_amendment", {
        "p_event_id": "event-1", "p_actor_id": "coordinator-1", "p_from_statuses": ["under_review"],
        "p_to_status": "returned", "p_expected_version": 3, "p_message": "Confirm attendance",
        "p_flagged_fields": ["expected_attendance"], "p_notify_message": "msg",
    })]


def test_resubmit_event_calls_the_resubmit_function_with_every_parameter(monkeypatch):
    client = RpcClient([{"id": "event-1", "status": "under_review"}])
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: client)

    row = repository.resubmit_event(
        "event-1", "organiser-1", ["returned"], "under_review", 4, note="Now 40", notify_message="msg",
    )

    assert row == {"id": "event-1", "status": "under_review"}
    assert client.calls == [("resubmit_event", {
        "p_event_id": "event-1", "p_actor_id": "organiser-1", "p_from_statuses": ["returned"],
        "p_to_status": "under_review", "p_expected_version": 4, "p_note": "Now 40", "p_notify_message": "msg",
    })]


def test_a_stale_return_or_resubmit_comes_back_as_none(monkeypatch):
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: RpcClient([]))

    assert repository.return_event("e", "c", ["under_review"], "returned", 1,
                                   message="m", flagged_fields=[], notify_message="n") is None
    assert repository.resubmit_event("e", "o", ["returned"], "under_review", 1, note="n", notify_message="n") is None


def test_get_open_amendment_reads_only_the_unresubmitted_row(monkeypatch):
    filters = []
    open_row = {"id": "a1", "message": "Confirm attendance", "flagged_fields": ["expected_attendance"],
                "returned_at": "2026-09-24T03:00:00+00:00"}

    class AmendmentQuery:
        def select(self, columns):
            filters.append(("select", columns))
            return self

        def eq(self, field, value):
            filters.append(("eq", field, value))
            return self

        def is_(self, field, value):
            filters.append(("is", field, value))
            return self

        def maybe_single(self):
            return self

        def execute(self):
            return SimpleNamespace(data=open_row)

    class AdminClient:
        def table(self, name):
            filters.append(("table", name))
            return AmendmentQuery()

    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: AdminClient())

    assert repository.get_open_amendment("event-1") == open_row
    assert filters == [
        ("table", "amendment_requests"),
        ("select", "id, message, flagged_fields, returned_at"),
        ("eq", "event_id", "event-1"),
        ("is", "resubmitted_at", "null"),
    ]


def test_get_open_amendment_is_none_when_nothing_is_open(monkeypatch):
    """supabase-py returns no response object at all for maybe_single() with no row."""

    class EmptyQuery:
        def select(self, columns): return self
        def eq(self, field, value): return self
        def is_(self, field, value): return self
        def maybe_single(self): return self
        def execute(self): return None

    class AdminClient:
        def table(self, name): return EmptyQuery()

    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: AdminClient())

    assert repository.get_open_amendment("event-1") is None


def test_list_comments_reads_oldest_first_with_the_author_embedded(monkeypatch):
    calls = {}

    class CommentQuery:
        def select(self, columns):
            calls["columns"] = columns
            return self

        def eq(self, field, value):
            calls["eq"] = (field, value)
            return self

        def order(self, column, *, desc=False):
            calls["order"] = (column, desc)
            return self

        def execute(self):
            return SimpleNamespace(data=[{"id": "c1"}])

    class AdminClient:
        def table(self, name):
            calls["table"] = name
            return CommentQuery()

    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: AdminClient())

    assert repository.list_comments("event-1") == [{"id": "c1"}]
    assert calls["table"] == "event_comments"
    assert "author:profiles!event_comments_author_id_fkey(id, full_name)" in calls["columns"]
    assert calls["eq"] == ("event_id", "event-1")
    assert calls["order"] == ("created_at", False)


def test_add_comment_calls_the_function_and_returns_its_row(monkeypatch):
    sent = {}

    class Rpc:
        def execute(self):
            return SimpleNamespace(data=[{"id": "c1", "body": "Hi"}])

    class AdminClient:
        def rpc(self, name, params):
            sent["name"], sent["params"] = name, params
            return Rpc()

    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: AdminClient())

    row = repository.add_comment("event-1", "user-1", "Hi", notify_message="msg")

    assert row == {"id": "c1", "body": "Hi"}
    assert sent == {"name": "add_event_comment", "params": {
        "p_event_id": "event-1", "p_author_id": "user-1", "p_body": "Hi", "p_notify_message": "msg"}}


def test_add_comment_is_none_when_the_function_refuses(monkeypatch):
    class Rpc:
        def execute(self):
            return SimpleNamespace(data=[])

    class AdminClient:
        def rpc(self, name, params):
            return Rpc()

    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: AdminClient())

    assert repository.add_comment("event-1", "user-1", "Hi", notify_message="msg") is None


def test_send_to_safety_review_passes_both_messages(monkeypatch):
    """SCRUM-82 wrapper RPC contract."""
    client = RpcClient([{"id": "e", "status": "safety_review"}])
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: client)
    assert repository.send_to_safety_review("e", "c", ["planning"], "safety_review", 3,
        organiser_message="o", officer_message="s") == {"id": "e", "status": "safety_review"}
    assert client.calls == [("send_event_to_safety_review", {
        "p_event_id": "e", "p_actor_id": "c", "p_from_statuses": ["planning"],
        "p_to_status": "safety_review", "p_expected_version": 3,
        "p_organiser_message": "o", "p_officer_message": "s"})]
    client.rows = []
    assert repository.send_to_safety_review("e", "c", ["planning"], "safety_review", 3,
        organiser_message="o", officer_message="s") is None


def test_list_recent_safety_decisions_reads_the_window_and_flattens_names(monkeypatch):
    """CR-103 AC7: every decision since the cut-off, newest first, with event and decider names."""
    from datetime import datetime, timezone
    calls = []
    rows = [
        {"id": "d1", "event_id": "e1", "decision": "approved", "comment": "ok", "decided_at": "2026-10-09T01:00:00Z",
         "event": {"name": "Dinner"}, "decider": {"full_name": "Hafiz Ismail"}},
        {"id": "d2", "event_id": "e2", "decision": "withdrawn", "comment": None, "decided_at": "2026-10-08T01:00:00Z",
         "event": None, "decider": None},
    ]

    class Query:
        def __getattr__(self, name):
            def record(*args, **kwargs):
                calls.append((name, args, kwargs))
                return self
            return record

        def execute(self):
            return SimpleNamespace(data=rows)

    class AdminClient:
        def table(self, name):
            calls.append(("table", (name,), {}))
            return Query()

    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: AdminClient())
    since = datetime(2026, 9, 9, tzinfo=timezone.utc)
    assert repository.list_recent_safety_decisions(since) == [
        {"id": "d1", "event_id": "e1", "event_name": "Dinner", "decision": "approved", "comment": "ok",
         "decided_at": "2026-10-09T01:00:00Z", "decided_by_name": "Hafiz Ismail"},
        {"id": "d2", "event_id": "e2", "event_name": "", "decision": "withdrawn", "comment": None,
         "decided_at": "2026-10-08T01:00:00Z", "decided_by_name": None},
    ]
    assert ("table", ("event_safety_decisions",), {}) in calls
    assert ("gte", ("decided_at", "2026-09-09T00:00:00+00:00"), {}) in calls
    assert ("order", ("decided_at",), {"desc": True}) in calls


def test_planning_context_reads_what_venue_staff_judge_a_booking_by(monkeypatch):
    """SCRUM-38 AC1: the booking request shows the event's status and
    accessibility needs beside its attendance, layout and facilities."""
    selects = []

    class ContextQuery:
        def select(self, columns):
            selects.append(columns)
            return self

        def in_(self, field, values):
            self.ids = values
            return self

        def execute(self):
            return SimpleNamespace(data=[{"id": "e1", "status": "planning", "accessibility_needs": "Ramp"}])

    class AdminClient:
        def table(self, name):
            assert name == "events"
            return ContextQuery()

    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: AdminClient())

    rows = repository.list_planning_context(["e1", None, "e1"])

    assert rows == [{"id": "e1", "status": "planning", "accessibility_needs": "Ramp"}]
    for column in ("status", "accessibility_needs", "expected_attendance", "layout_preference", "facilities_required"):
        assert column in selects[0]
    assert repository.list_planning_context([]) == []
