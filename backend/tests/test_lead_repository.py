"""CR-101 Lead reads and the reassign call, at the Supabase client seam.

The API tests fake these functions; here a recording fake client checks what
each one asks PostgREST for and how it shapes the rows it gets back. The real
queries run against the live project in `supabase/verification/` and
`scripts/verify_live.py`.
"""

from types import SimpleNamespace

from app.modules.events import repository


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
    """Answers each table with its own rows, so two-step reads can be faked."""

    def __init__(self, data_by_table=None, rpc_data=None):
        self.queries = {name: FakeQuery(data) for name, data in (data_by_table or {}).items()}
        self.rpc_query = FakeQuery(rpc_data)
        self.rpcs = []

    def table(self, name):
        return self.queries[name]

    def rpc(self, name, params):
        self.rpcs.append((name, params))
        return self.rpc_query


def use(monkeypatch, data_by_table=None, rpc_data=None):
    client = FakeClient(data_by_table, rpc_data)
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: client)
    return client


def test_list_lead_events_asks_for_the_given_statuses_with_both_profile_embeds(monkeypatch):
    client = use(monkeypatch, {"events": [{"id": "e1"}]})

    assert repository.list_lead_events(("planning", "confirmed")) == [{"id": "e1"}]

    calls = dict((name, args) for name, args, _ in client.queries["events"].calls)
    assert calls["in_"] == ("status", ["planning", "confirmed"])
    assert "events_organiser_id_fkey" in calls["select"][0] and "events_coordinator_id_fkey" in calls["select"][0]
    assert "assigned_by" in calls["select"][0]


def test_list_lead_events_is_empty_when_nothing_comes_back(monkeypatch):
    use(monkeypatch, {"events": None})
    assert repository.list_lead_events(["planning"]) == []


def test_list_lead_ids_returns_the_profile_ids_holding_the_lead_role(monkeypatch):
    client = use(monkeypatch, {"user_roles": [{"profile_id": "l1"}, {"profile_id": "l2"}]})

    assert repository.list_lead_ids() == {"l1", "l2"}
    assert ("eq", ("role", "event_coordinator_lead")) in [(n, a) for n, a, _ in client.queries["user_roles"].calls]


def test_list_coordinators_names_every_coordinator_by_name(monkeypatch):
    client = use(monkeypatch, {
        "user_roles": [{"profile_id": "c1"}, {"profile_id": "c2"}],
        "profiles": [{"id": "c1", "full_name": "Marcus Lim"}, {"id": "c2", "full_name": "Priya Nair"}],
    })

    assert [c["full_name"] for c in repository.list_coordinators()] == ["Marcus Lim", "Priya Nair"]
    assert ("in_", ("id", ["c1", "c2"])) in [(n, a) for n, a, _ in client.queries["profiles"].calls]


def test_list_coordinators_is_empty_when_nobody_holds_the_role(monkeypatch):
    use(monkeypatch, {"user_roles": [], "profiles": [{"id": "never-read"}]})
    assert repository.list_coordinators() == []


def test_get_lead_event_returns_the_row_or_none(monkeypatch):
    use(monkeypatch, {"events": {"id": "e1", "version": 2}})
    assert repository.get_lead_event("e1") == {"id": "e1", "version": 2}

    use(monkeypatch, {"events": None})
    assert repository.get_lead_event("e1") is None


def test_get_coordinator_returns_the_profile_only_when_the_coordinator_role_is_held(monkeypatch):
    use(monkeypatch, {"user_roles": {"profile_id": "c1"}, "profiles": {"id": "c1", "full_name": "Marcus Lim"}})
    assert repository.get_coordinator("c1") == {"id": "c1", "full_name": "Marcus Lim"}


def test_get_coordinator_is_none_without_the_role(monkeypatch):
    use(monkeypatch, {"user_roles": None, "profiles": {"id": "c1", "full_name": "Marcus Lim"}})
    assert repository.get_coordinator("c1") is None


def test_get_coordinator_is_none_when_the_profile_is_missing(monkeypatch):
    use(monkeypatch, {"user_roles": {"profile_id": "c1"}, "profiles": None})
    assert repository.get_coordinator("c1") is None


def test_reassign_event_calls_the_rpc_with_every_parameter_and_returns_the_row(monkeypatch):
    client = use(monkeypatch, rpc_data=[{"id": "e1", "coordinator_id": "c2"}])

    row = repository.reassign_event(
        "e1", "l1", "c2", 3, active_statuses=["planning"],
        notify_assigned="a", notify_previous="p", notify_organiser="o",
    )

    assert row == {"id": "e1", "coordinator_id": "c2"}
    assert client.rpcs == [("reassign_event", {
        "p_event_id": "e1", "p_lead_id": "l1", "p_coordinator_id": "c2", "p_expected_version": 3,
        "p_active_statuses": ["planning"],
        "p_notify_assigned": "a", "p_notify_previous": "p", "p_notify_organiser": "o",
    })]


def test_reassign_event_is_none_when_the_rpc_returns_no_row(monkeypatch):
    use(monkeypatch, rpc_data=[])
    assert repository.reassign_event(
        "e1", "l1", "c2", 3, active_statuses=[], notify_assigned="", notify_previous="",
        notify_organiser="",
    ) is None
