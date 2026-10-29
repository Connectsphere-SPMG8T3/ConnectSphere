"""Story 37: the thin repository wrappers around the change-decision and re-review
functions send what the database expects and read back what it answers. The
functions themselves are checked by supabase/verification/change_request_decision_checks.sql."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.modules.equipment import repository as equipment_repository
from app.modules.events import repository as events_repository
from app.modules.venues import repository as venues_repository
from app.modules.venues.schemas import Period

START = datetime(2031, 4, 21, 6, tzinfo=timezone.utc)
END = datetime(2031, 4, 21, 8, tzinfo=timezone.utc)


@pytest.fixture()
def client(monkeypatch):
    client = MagicMock()
    query = MagicMock()
    for method in ("select", "eq", "in_", "order", "limit"):
        getattr(query, method).return_value = query
    client.table.return_value = query
    client.query = query
    for module in (equipment_repository, events_repository, venues_repository):
        monkeypatch.setattr(module, "get_supabase_admin_client", lambda: client)
    return client


def answer(client, data):
    client.rpc.return_value.execute.return_value = MagicMock(data=data)
    client.query.execute.return_value = MagicMock(data=data)


class TestEventDecisions:
    def test_approval_sends_every_argument(self, client):
        answer(client, {"outcome": "ok", "event": {"id": "e1"}})

        result = events_repository.approve_event_change(
            "e1", "c1", 3, ["planning"], {"name": "x"}, {"s1": {"label": "y"}}, "o",
            history_reason="r", officer_message="f", attendee_message=None,
            booking_plans=[{"booking_id": "b1"}], staff_again_message="again")

        assert result == {"outcome": "ok", "event": {"id": "e1"}}
        client.rpc.assert_called_with("approve_event_change", {
            "p_event_id": "e1", "p_actor_id": "c1", "p_expected_version": 3, "p_from_statuses": ["planning"],
            "p_event_values": {"name": "x"}, "p_space_values": {"s1": {"label": "y"}}, "p_organiser_message": "o",
            "p_history_reason": "r", "p_officer_message": "f", "p_attendee_message": None,
            "p_bookings": [{"booking_id": "b1"}], "p_staff_again_message": "again",
        })

    def test_rejection_sends_every_argument(self, client):
        answer(client, {"outcome": "ok"})

        assert events_repository.reject_event_change("e1", "c1", "No", ["planning"], "o") == {"outcome": "ok"}
        client.rpc.assert_called_with("reject_event_change", {
            "p_event_id": "e1", "p_actor_id": "c1", "p_reason": "No", "p_from_statuses": ["planning"],
            "p_organiser_message": "o",
        })


class TestSends:
    def test_a_booking_send_calls_its_function(self, client):
        answer(client, {"outcome": "ok"})

        assert venues_repository.send_booking_for_re_review("b1", "c1", "n", "m") == {"outcome": "ok"}
        client.rpc.assert_called_with("send_booking_for_re_review", {
            "p_booking_id": "b1", "p_actor_id": "c1", "p_note": "n", "p_staff_message": "m"})

    def test_a_line_send_calls_its_function(self, client):
        answer(client, {"outcome": "ok"})

        assert equipment_repository.send_line_for_re_review("l1", "c1", None, "m") == {"outcome": "ok"}
        client.rpc.assert_called_with("send_equipment_line_for_re_review", {
            "p_line_id": "l1", "p_actor_id": "c1", "p_note": None, "p_staff_message": "m"})


class TestVenueReads:
    def test_the_bookings_a_change_may_touch_are_the_occupying_ones(self, client):
        answer(client, [{"id": "b1"}])

        assert venues_repository.list_change_bookings("e1") == [{"id": "b1"}]
        client.query.in_.assert_called_with("status", ["held", "approved", "re_review"])
        answer(client, None)
        assert venues_repository.list_change_bookings("e1") == []

    def test_a_block_is_named_before_an_earlier_booking(self, client):
        answer(client, [
            {"kind": "booking", "event_name": "Launch", "block_reason": None,
             "occupied_period": "[\"2031-04-21 05:00:00+00\",\"2031-04-21 06:00:00+00\")"},
            {"kind": "block", "event_name": None, "block_reason": "maintenance",
             "occupied_period": "[\"2031-04-21 07:00:00+00\",\"2031-04-21 08:00:00+00\")"},
        ])

        clash = venues_repository.first_conflict(Period(starts_at=START, ends_at=END), "v1", "b1")

        assert clash == {"kind": "block", "event_name": None, "block_reason": "maintenance"}
        args = client.rpc.call_args.args[1]
        assert (args["p_venue_id"], args["p_exclude_booking_id"]) == ("v1", "b1")

    def test_a_free_window_has_no_clash(self, client):
        answer(client, [])

        assert venues_repository.first_conflict(Period(starts_at=START, ends_at=END), "v1", "b1") is None

    def test_the_last_move_reads_both_windows(self, client):
        answer(client, [{"old_period": "[\"2031-04-21 02:00:00+00\",\"2031-04-21 04:00:00+00\")",
                         "new_period": "[\"2031-04-21 06:00:00+00\",\"2031-04-21 08:00:00+00\")"}])

        move = venues_repository.get_last_move("b1")

        assert move["old_period"].starts_at == datetime(2031, 4, 21, 2, tzinfo=timezone.utc)
        assert move["new_period"].ends_at == END
        client.query.eq.assert_any_call("action", "moved_by_change")

    def test_a_booking_never_moved_has_no_last_move(self, client):
        answer(client, [])

        assert venues_repository.get_last_move("b1") is None


class TestEquipmentFreeQuantity:
    def test_the_lines_own_reservation_is_left_out(self, client):
        client.query.execute.return_value = MagicMock(data=[{"id": "r1"}])
        client.rpc.return_value.execute.return_value = MagicMock(data=[{"free_quantity": 5}])

        assert equipment_repository.line_free_quantity("l1", "p1", START, END) == 5
        client.rpc.assert_called_with("equipment_availability", {
            "p_equipment_ids": ["p1"], "p_start_at": START.isoformat(), "p_end_at": END.isoformat(),
            "p_exclude_reservation_id": "r1"})

    def test_a_line_without_a_reservation_counts_everything(self, client):
        client.query.execute.return_value = MagicMock(data=[])
        client.rpc.return_value.execute.return_value = MagicMock(data=[])

        assert equipment_repository.line_free_quantity("l1", "p1", START, END) == 0
        assert client.rpc.call_args.args[1]["p_exclude_reservation_id"] is None
