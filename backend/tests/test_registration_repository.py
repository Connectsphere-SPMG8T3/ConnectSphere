from types import SimpleNamespace
from unittest.mock import Mock

from app.modules.registrations import repository


def _client_with_query():
    client = Mock()
    query = Mock()
    client.table.return_value = query
    query.select.return_value = query
    query.in_.return_value = query
    query.order.return_value = query
    query.eq.return_value = query
    query.maybe_single.return_value = query
    query.execute.return_value = SimpleNamespace(data=[])
    return client, query


def test_list_public_event_rows_returns_rows_and_orders_by_start(monkeypatch):
    client, query = _client_with_query()
    rows = [{"id": "event-1"}]
    query.execute.return_value = SimpleNamespace(data=rows)
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: client)

    assert repository.list_public_event_rows() == rows
    client.table.assert_called_once_with("events")
    query.in_.assert_called_once_with("status", ["confirmed", "preparation"])
    query.order.assert_called_once_with("starts_at")


def test_list_public_event_rows_returns_empty_list_for_null_data(monkeypatch):
    client, query = _client_with_query()
    query.execute.return_value = SimpleNamespace(data=None)
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: client)

    assert repository.list_public_event_rows() == []


def test_get_public_event_row_returns_matching_row(monkeypatch):
    client, query = _client_with_query()
    row = {"id": "event-1"}
    query.execute.return_value = SimpleNamespace(data=row)
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: client)

    assert repository.get_public_event_row("event-1") == row
    query.eq.assert_called_once_with("id", "event-1")
    query.maybe_single.assert_called_once_with()


def test_get_public_event_row_returns_none_for_missing_response(monkeypatch):
    client, query = _client_with_query()
    query.execute.return_value = None
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: client)

    assert repository.get_public_event_row("missing") is None


def test_registered_count_defaults_to_zero(monkeypatch):
    client, query = _client_with_query()
    query.execute.return_value = SimpleNamespace(count=None)
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: client)

    assert repository.registered_count("event-1") == 0
    client.table.assert_called_once_with("event_registrations")
    query.eq.assert_any_call("event_id", "event-1")
    query.eq.assert_any_call("status", "registered")


def test_registered_count_returns_exact_count(monkeypatch):
    client, query = _client_with_query()
    query.execute.return_value = SimpleNamespace(count=7)
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: client)

    assert repository.registered_count("event-1") == 7


def test_register_for_event_returns_rpc_result(monkeypatch):
    client = Mock()
    client.rpc.return_value.execute.return_value = SimpleNamespace(data={"outcome": "registered"})
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: client)

    assert repository.register_for_event("event-1", "attendee-1") == {"outcome": "registered"}
    client.rpc.assert_called_once_with(
        "register_for_event",
        {"p_event_id": "event-1", "p_attendee_id": "attendee-1"},
    )


def test_list_attendee_registration_rows_scopes_to_attendee_and_active_statuses(monkeypatch):
    client, query = _client_with_query()
    rows = [{"id": "registration-1", "status": "registered"}]
    query.execute.return_value = SimpleNamespace(data=rows)
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: client)

    result = repository.list_attendee_registration_rows("attendee-1")

    assert result == rows
    client.table.assert_called_once_with("event_registrations")
    query.eq.assert_called_once_with("attendee_id", "attendee-1")
    query.in_.assert_called_once_with("status", ["registered", "waitlisted"])
    query.order.assert_called_once_with("registered_at", desc=True)
