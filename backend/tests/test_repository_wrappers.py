"""The repository calls the service tests replace: which function or table each one reaches,
with which parameters, and what an empty answer becomes.

A parameter name must match the database function exactly, and only a live call would
otherwise notice. `verify_live.py` covers what the database then does with them.
"""

from datetime import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from postgrest.exceptions import APIError

from app.modules.equipment import repository as equipment
from app.modules.events import repository as events
from app.modules.events.repository import list_edit_history as list_event_edit_history
from app.modules.venues import repository as venues
from app.modules.venues.repository import list_active_bookings

EVENT_ID = "e0000000-0000-4000-8000-000000000001"
VENUE_ID = "b0000000-0000-4000-8000-000000000001"
ACTOR_ID = "a0000000-0000-4000-8000-000000000001"
AT = "2031-05-01T02:00:00+00:00"


def _database(monkeypatch, module, data=None, response="default") -> MagicMock:
    """An admin client whose query steps all return one inspectable builder."""
    builder = MagicMock()
    for step in ("select", "eq", "in_", "order", "update", "delete"):
        getattr(builder, step).return_value = builder
    builder.execute.return_value = SimpleNamespace(data=data) if response == "default" else response
    client = MagicMock(builder=builder)
    client.table.return_value = builder
    client.rpc.return_value = builder
    monkeypatch.setattr(module, "get_supabase_admin_client", lambda: client)
    return client


def test_the_health_check_answers(client):
    assert client.get("/health").json() == {"status": "ok"}


class TestEquipmentReads:
    def test_no_ids_asked_for_means_no_query(self, monkeypatch):
        client = _database(monkeypatch, equipment, [])

        assert equipment.list_equipment([]) == []
        assert equipment.list_catalogue([]) == []
        assert equipment._commitments(client.builder, None, None, []) == []
        client.builder.execute.assert_not_called()

    def test_equipment_ids_are_deduplicated_and_sorted(self, monkeypatch):
        client = _database(monkeypatch, equipment, [])

        equipment.list_equipment(["b", "a", "b"])

        client.builder.in_.assert_called_once_with("id", ["a", "b"])

    def test_the_catalogue_is_narrowed_to_the_ids_asked_for(self, monkeypatch):
        client = _database(monkeypatch, equipment, [{"id": "a"}])

        assert equipment.list_catalogue(["a"]) == [{"id": "a"}]
        assert client.builder.in_.call_args_list[-1].args == ("id", ["a"])

    @pytest.mark.parametrize(
        ("embed", "name"),
        [({"name": "Projector"}, "Projector"), ([{"name": "Speaker"}], "Speaker"), ([], ""), (None, "")],
        ids=["object", "list", "empty list", "missing"],
    )
    def test_maintenance_reads_the_equipment_name_from_any_embed_shape(self, monkeypatch, embed, name):
        _database(monkeypatch, equipment, [{
            "id": "m1", "equipment_id": "a", "start_at": AT, "end_at": AT, "reason": "Service", "equipment": embed,
        }])

        [row] = equipment.list_maintenance()

        assert (row.id, row.equipment_name, row.reason) == ("m1", name, "Service")

    def test_submitting_lines_calls_the_function_and_returns_its_outcome(self, monkeypatch):
        client = _database(monkeypatch, equipment, [{"outcome": "ok", "lines": [{"id": "l1"}]}])

        assert equipment.submit_request(EVENT_ID, ACTOR_ID, [{"quantity": 1}]) == ("ok", [{"id": "l1"}])
        client.rpc.assert_called_once_with(
            "submit_equipment_request", {"p_event_id": EVENT_ID, "p_actor_id": ACTOR_ID, "p_items": [{"quantity": 1}]},
        )

    def test_an_empty_answer_has_no_outcome(self, monkeypatch):
        _database(monkeypatch, equipment, None)

        assert equipment.submit_request(EVENT_ID, ACTOR_ID, []) == ("", [])


class TestEventWrites:
    def test_a_lost_update_is_none(self, monkeypatch):
        _database(monkeypatch, events, [])

        assert events.update_event(EVENT_ID, {"name": "New"}, 1) is None

    def test_an_edit_calls_the_function_and_returns_the_event_shape(self, monkeypatch):
        client = _database(monkeypatch, events, [{"id": EVENT_ID, "name": "New"}])
        monkeypatch.setattr(events, "_with_spaces", lambda row: row)

        row = events.edit_event(EVENT_ID, ACTOR_ID, {"name": "New"}, 3, ["planning"])

        client.rpc.assert_called_once_with("edit_event", {
            "p_event_id": EVENT_ID, "p_actor_id": ACTOR_ID, "p_values": {"name": "New"},
            "p_expected_version": 3, "p_from_statuses": ["planning"],
        })
        assert (row["id"], row["name"], row["status"]) == (EVENT_ID, "New", None)

    @pytest.mark.parametrize("response", [None, SimpleNamespace(data=[])], ids=["no response", "no rows"])
    def test_an_edit_that_lost_the_race_is_none(self, monkeypatch, response):
        _database(monkeypatch, events, response=response)

        assert events.edit_event(EVENT_ID, ACTOR_ID, {}, 3, []) is None

    def test_deleting_targets_that_event(self, monkeypatch):
        client = _database(monkeypatch, events)

        events.delete_event(EVENT_ID)

        client.table.assert_called_once_with("events")
        client.builder.eq.assert_called_once_with("id", EVENT_ID)
        client.builder.execute.assert_called_once_with()

    def test_a_transition_passes_every_parameter(self, monkeypatch):
        client = _database(monkeypatch, events, [{"id": EVENT_ID}])

        row = events.transition_event(EVENT_ID, ACTOR_ID, ["draft"], "submitted", 2, "Why", "kind", "Told")

        assert row == {"id": EVENT_ID}
        client.rpc.assert_called_once_with("transition_event", {
            "p_event_id": EVENT_ID, "p_actor_id": ACTOR_ID, "p_from_statuses": ["draft"], "p_to_status": "submitted",
            "p_expected_version": 2, "p_reason": "Why", "p_notify_type": "kind", "p_notify_message": "Told",
        })

    def test_a_transition_that_lost_the_race_is_none(self, monkeypatch):
        _database(monkeypatch, events, response=None)

        assert events.transition_event(EVENT_ID, ACTOR_ID, [], "submitted", 2) is None

    def test_assigning_passes_every_parameter(self, monkeypatch):
        client = _database(monkeypatch, events, [{"id": EVENT_ID}])

        assert events.assign_event(
            EVENT_ID, ACTOR_ID, "coordinator", from_statuses=["submitted"], to_status="under_review", reason="Why",
            notify_assigned="You", notify_organiser="Them",
        ) == {"id": EVENT_ID}
        client.rpc.assert_called_once_with("assign_event", {
            "p_event_id": EVENT_ID, "p_lead_id": ACTOR_ID, "p_coordinator_id": "coordinator",
            "p_from_statuses": ["submitted"], "p_to_status": "under_review", "p_reason": "Why",
            "p_notify_assigned": "You", "p_notify_organiser": "Them",
        })

    def test_setting_the_primary_space_returns_its_outcome(self, monkeypatch):
        client = _database(monkeypatch, events, "ok")

        assert events.set_primary_space(EVENT_ID, "space", ACTOR_ID) == "ok"
        client.rpc.assert_called_once_with(
            "set_primary_space", {"p_event_id": EVENT_ID, "p_space_id": "space", "p_actor_id": ACTOR_ID},
        )


class TestEventReads:
    def test_no_ids_means_no_query(self, monkeypatch):
        client = _database(monkeypatch, events, [])

        assert events.list_event_names([None]) == {}
        assert events.list_spaces_by_ids([]) == []
        client.builder.execute.assert_not_called()

    def test_spaces_are_read_by_id_skipping_blanks(self, monkeypatch):
        client = _database(monkeypatch, events, [{"id": "s1"}])

        assert events.list_spaces_by_ids(["s2", None, "s1"]) == [{"id": "s1"}]
        client.table.assert_called_once_with("event_space_requests")
        client.builder.in_.assert_called_once_with("id", ["s1", "s2"])

    def test_history_is_for_that_event_newest_first(self, monkeypatch):
        client = _database(monkeypatch, events, [{"id": "h1"}])

        assert list_event_edit_history(EVENT_ID) == [{"id": "h1"}]
        client.builder.eq.assert_called_once_with("event_id", EVENT_ID)
        client.builder.order.assert_called_once_with("at", desc=True)


class TestVenueWrites:
    FIELDS = dict(
        name="Hall", location="Campus", capacity=100, opens_at=time(8), closes_at="22:00", description=None,
        accessibility_features=[], layouts=[], facilities=[], before={"a": 1}, after={"a": 2},
        notifications=[], flags=[],
    )

    def test_an_edit_sends_times_as_text_and_returns_what_it_flagged(self, monkeypatch):
        client = _database(monkeypatch, venues, {"flagged_event_ids": [EVENT_ID]})
        monkeypatch.setattr(venues, "get_venue", lambda venue_id: "saved")

        assert venues.update_venue(VENUE_ID, ACTOR_ID, 2, **self.FIELDS) == ("saved", [EVENT_ID])
        name, params = client.rpc.call_args.args
        assert name == "update_venue"
        assert (params["p_venue_id"], params["p_actor_id"], params["p_expected_version"]) == (VENUE_ID, ACTOR_ID, 2)
        assert (params["p_opens_at"], params["p_closes_at"]) == ("08:00:00", "22:00")
        assert (params["p_before"], params["p_after"]) == ({"a": 1}, {"a": 2})

    def test_an_edit_that_lost_the_race_is_none(self, monkeypatch):
        _database(monkeypatch, venues, None)

        assert venues.update_venue(VENUE_ID, ACTOR_ID, 2, **self.FIELDS) is None

    def test_deactivating_returns_its_outcome_and_event_ids_as_text(self, monkeypatch):
        client = _database(monkeypatch, venues, [{"outcome": "ok", "event_ids": [1, 2]}])

        result = venues.deactivate_venue(
            VENUE_ID, ACTOR_ID, 2, reason="renovation", note=None, before={}, after={},
            flag_reason="Closed", message="Told",
        )

        assert result == {"outcome": "ok", "event_ids": ["1", "2"]}
        assert client.rpc.call_args.args[1] == {
            "p_venue_id": VENUE_ID, "p_actor_id": ACTOR_ID, "p_expected_version": 2, "p_reason": "renovation",
            "p_note": None, "p_before": {}, "p_after": {}, "p_flag_reason": "Closed", "p_message": "Told",
        }

    def test_reactivating_returns_its_outcome(self, monkeypatch):
        client = _database(monkeypatch, venues, "ok")

        assert venues.reactivate_venue(VENUE_ID, ACTOR_ID, 2, before={}, after={}) == "ok"
        client.rpc.assert_called_once_with("reactivate_venue", {
            "p_venue_id": VENUE_ID, "p_actor_id": ACTOR_ID, "p_expected_version": 2, "p_before": {}, "p_after": {},
        })

    def test_recording_preparation_returns_the_functions_row(self, monkeypatch):
        client = _database(monkeypatch, venues, [{"outcome": "ok"}])

        assert venues.set_venue_preparation("booking", ACTOR_ID, "in_progress", "Note") == {"outcome": "ok"}
        client.rpc.assert_called_once_with("set_venue_preparation", {
            "p_booking_id": "booking", "p_actor_id": ACTOR_ID, "p_stage": "in_progress", "p_note": "Note",
        })


class TestVenueReads:
    def test_an_unreadable_range_is_an_error_not_a_guess(self):
        with pytest.raises(ValueError, match="Unrecognised range literal"):
            venues._parse_range("not a range")

    def test_a_readable_editor_is_named(self):
        editor = venues._to_editor({"profiles": {"id": ACTOR_ID, "full_name": "Vera Staff"}})

        assert (editor.id, editor.full_name) == (ACTOR_ID, "Vera Staff")

    def test_an_unreadable_editor_still_keeps_their_id(self):
        assert venues._to_editor({"profiles": None, "updated_by": ACTOR_ID}).id == ACTOR_ID

    def test_nobody_recorded_is_no_editor(self):
        assert venues._to_editor({"profiles": None}) is None

    @pytest.mark.parametrize(
        ("embedded", "expected"),
        [([{"name": "A"}], {"name": "A"}), ([], None), ("text", None)],
        ids=["list", "empty list", "not an object"],
    )
    def test_an_embed_is_read_as_one_object(self, embedded, expected):
        assert venues._embedded_relation({"key": embedded}, "key") == expected

    def test_history_is_for_that_venue_newest_first(self, monkeypatch):
        client = _database(monkeypatch, venues, [{"id": "h1"}])

        assert venues.list_edit_history(VENUE_ID) == [{"id": "h1"}]
        client.builder.eq.assert_called_once_with("venue_id", VENUE_ID)
        client.builder.order.assert_called_once_with("created_at", desc=True)

    def test_no_events_means_no_query(self, monkeypatch):
        client = _database(monkeypatch, venues, [])

        assert venues.list_booking_statuses([]) == []
        client.builder.execute.assert_not_called()

    def test_booking_statuses_are_read_for_those_events(self, monkeypatch):
        client = _database(monkeypatch, venues, [{"status": "held"}])

        assert venues.list_booking_statuses([EVENT_ID]) == [{"status": "held"}]
        client.builder.in_.assert_called_once_with("event_id", [EVENT_ID])

    def test_booking_history_names_the_venue_and_keeps_a_null_actor(self, monkeypatch):
        client = _database(monkeypatch, venues, [{
            "id": "h1", "action": "approved", "created_at": AT, "actor": None, "reason": "Fine",
            "booking": {"venue": {"name": "Hall A"}},
        }])

        [entry] = venues.list_event_booking_history(EVENT_ID)

        client.builder.eq.assert_called_once_with("booking.event_id", EVENT_ID)
        assert (entry["venue_name"], entry["actor"], entry["reason"], entry["at"]) == ("Hall A", None, "Fine", AT)

    def test_bookings_for_history_flatten_the_venue_name(self, monkeypatch):
        client = _database(monkeypatch, venues, [{"status": "held", "venues": {"name": "Hall A"}}])

        assert venues.list_event_bookings_for_history(EVENT_ID) == [{"status": "held", "venue_name": "Hall A"}]
        client.builder.eq.assert_called_once_with("event_id", EVENT_ID)

    def test_only_the_missing_column_error_falls_back_to_no_bookings(self, monkeypatch):
        """conftest.py stubs `venues.list_active_bookings`; the import above is the real one."""
        client = _database(monkeypatch, venues)
        client.builder.execute.side_effect = APIError({"code": "PGRST204", "message": "column missing"})
        assert list_active_bookings(EVENT_ID) == []

        client.builder.execute.side_effect = APIError({"code": "42501", "message": "denied"})
        with pytest.raises(APIError):
            list_active_bookings(EVENT_ID)

    def test_venue_staff_are_read_by_role(self, monkeypatch):
        client = _database(monkeypatch, venues, [{"profile_id": "a"}, {"profile_id": "b"}])

        assert venues.list_venue_staff_ids() == {"a", "b"}
        client.builder.eq.assert_called_once_with("role", "venue_staff")
