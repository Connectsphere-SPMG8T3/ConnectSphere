"""SCRUM-24: the equipment repository's database calls, with the Supabase client captured.

The API tests replace these functions, so this pins what each one sends (function
name and parameters, or table and filters) and how it reads the answer. What the
database does with them is checked by supabase/verification/equipment_reservation_checks.sql.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.modules.equipment import repository
from app.modules.equipment.repository import AvailabilityRow

START = datetime(2033, 3, 1, 1, tzinfo=timezone.utc)
END = datetime(2033, 3, 1, 4, tzinfo=timezone.utc)


@pytest.fixture()
def client(monkeypatch):
    client = MagicMock()
    query = MagicMock()
    for method in ("select", "eq", "in_", "order", "limit"):
        getattr(query, method).return_value = query
    client.table.return_value = query
    client.query = query
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: client)
    return client


def answer(client, data):
    client.rpc.return_value.execute.return_value = MagicMock(data=data)
    client.query.execute.return_value = MagicMock(data=data)


class TestAvailability:
    def test_sends_the_ids_and_window_and_reads_each_row(self, client):
        answer(client, [{"equipment_id": "x", "total_quantity": 5, "outage_quantity": 1,
                         "reserved_quantity": 2, "free_quantity": 2}])

        rows = repository.availability(["y", "x", "x"], START, END)

        assert rows == [AvailabilityRow("x", 5, 1, 2, 2)]
        client.rpc.assert_called_once_with("equipment_availability", {
            "p_equipment_ids": ["x", "y"], "p_start_at": START.isoformat(), "p_end_at": END.isoformat(),
        })

    def test_no_ids_asks_nothing(self, client):
        assert repository.availability([], START, END) == []
        client.rpc.assert_not_called()


class TestStaffActions:
    def test_reserve_reads_outcome_free_count_and_left_ready(self, client):
        answer(client, [{"outcome": "insufficient", "free_quantity": 1, "left_ready": False}])

        assert repository.reserve_line("l1", "t1") == ("insufficient", 1, False)
        client.rpc.assert_called_once_with("reserve_equipment_line", {"p_line_id": "l1", "p_actor_id": "t1"})

    def test_an_empty_answer_is_no_outcome(self, client):
        answer(client, [])

        assert repository.reserve_line("l1", "t1") == ("", None, False)

    def test_not_available_sends_the_reason(self, client):
        answer(client, [{"outcome": "ok", "left_ready": True}])

        assert repository.mark_not_available("l1", "t1", "Broken") == ("ok", True)
        client.rpc.assert_called_once_with(
            "mark_equipment_line_not_available", {"p_line_id": "l1", "p_actor_id": "t1", "p_reason": "Broken"})

    def test_a_note_reads_the_scalar_outcome(self, client):
        answer(client, "ok")

        assert repository.set_note("l1", "t1", None) == "ok"
        client.rpc.assert_called_once_with(
            "set_equipment_line_note", {"p_line_id": "l1", "p_actor_id": "t1", "p_note": None})

    def test_a_null_answer_is_no_outcome(self, client):
        answer(client, None)

        assert repository.set_note("l1", "t1", "x") == ""

    def test_exit_confirmation_sends_the_tick(self, client):
        answer(client, [{"outcome": "ok", "left_ready": False}])

        assert repository.set_exit_confirmation("e1", "t1", True) == ("ok", False)
        client.rpc.assert_called_once_with(
            "set_exit_confirmation", {"p_event_id": "e1", "p_actor_id": "t1", "p_confirmed": True})

    def test_recheck_reads_the_flagged_count(self, client):
        answer(client, [{"outcome": "ok", "flagged": 2, "left_ready": True}])

        assert repository.recheck_event("e1", None) == ("ok", 2, True)
        client.rpc.assert_called_once_with("recheck_event_reservations", {"p_event_id": "e1", "p_actor_id": None})

    def test_recheck_without_a_count_is_zero(self, client):
        answer(client, [{"outcome": "no_schedule", "flagged": None, "left_ready": False}])

        assert repository.recheck_event("e1", None) == ("no_schedule", 0, False)


class TestReads:
    def test_get_line_reads_one_line_or_none(self, client):
        answer(client, [{"id": "l1", "event_id": "e1", "status": "pending"}])
        assert repository.get_line("l1") == {"id": "l1", "event_id": "e1", "status": "pending"}
        client.table.assert_called_with("equipment_requests")
        client.query.eq.assert_called_with("id", "l1")

        answer(client, [])
        assert repository.get_line("l1") is None

    def test_get_event_technical_names_the_coordinator_and_confirmer(self, client):
        answer(client, [{"id": "e1"}])

        assert repository.get_event_technical("e1") == {"id": "e1"}
        client.table.assert_called_with("events")
        columns = client.query.select.call_args.args[0]
        assert "events_exit_confirmed_by_fkey" in columns and "events_coordinator_id_fkey" in columns

        answer(client, None)
        assert repository.get_event_technical("e1") is None

    def test_history_is_the_events_newest_first(self, client):
        answer(client, [{"id": "h1"}])

        assert repository.list_technical_history("e1") == [{"id": "h1"}]
        client.table.assert_called_with("event_technical_history")
        client.query.eq.assert_called_with("event_id", "e1")
        client.query.order.assert_called_with("created_at", desc=True)

        answer(client, None)
        assert repository.list_technical_history("e1") == []

    def test_line_statuses_for_the_events(self, client):
        answer(client, [{"event_id": "e1", "status": "reserved"}])

        assert repository.list_line_statuses(["e2", "e1"]) == [{"event_id": "e1", "status": "reserved"}]
        client.query.in_.assert_called_with("event_id", ["e1", "e2"])

        answer(client, None)
        assert repository.list_line_statuses(["e1"]) == []

    def test_line_statuses_for_no_events_asks_nothing(self, client):
        assert repository.list_line_statuses([]) == []
        client.table.assert_not_called()

    def test_the_request_list_filters_by_status_only_when_asked(self, client):
        answer(client, [{"id": "l1"}])

        assert repository.list_requests(["pending", "re_review"]) == [{"id": "l1"}]
        client.query.in_.assert_called_with("status", ["pending", "re_review"])

        client.query.in_.reset_mock()
        answer(client, None)
        assert repository.list_requests() == []
        client.query.in_.assert_not_called()

    def test_lines_carry_notes_reason_and_equipment_type(self):
        assert "equipment_type" in repository.REQUEST_LINE_SELECT
        assert "technical_notes" in repository.REQUEST_LINE_SELECT
        assert "not_available_reason" in repository.REQUEST_LINE_SELECT
