"""Story 112: the assigned coordinator edits an event's ordinary details, through the HTTP API with the repository mocked."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.modules.events import repository
from tests.conftest import make_table_mock

ORGANISER_ID = "a0000000-0000-4000-8000-000000000001"
COORDINATOR_ID = "a0000000-0000-4000-8000-000000000002"
OTHER_COORDINATOR_ID = "a0000000-0000-4000-8000-000000000009"
EVENT_ID = "e0000000-0000-4000-8000-000000000301"
EDITABLE_STATUSES = ["under_review", "planning", "safety_review", "confirmed", "preparation"]
READ_ONLY_STATUSES = ["returned", "rejected", "cancelled", "completed"]
STALE = "This event was updated by someone else. Reload."
SIGNIFICANT_MESSAGE = "Significant changes go through a change request."


def event_row(status="planning"):
    now = datetime.now(timezone.utc).isoformat()
    starts = datetime.now(timezone.utc) + timedelta(days=30)
    return {
        "id": EVENT_ID, "organiser_id": ORGANISER_ID, "coordinator_id": COORDINATOR_ID,
        "status": status, "event_timezone": "Asia/Singapore", "name": "Partner Summit",
        "purpose": "Quarterly partner meeting", "description": None,
        "starts_at": starts.isoformat(), "ends_at": (starts + timedelta(hours=2)).isoformat(),
        "expected_attendance": 12, "layout_preference": "boardroom", "facilities_required": [],
        "accessibility_needs": None, "preliminary_equipment_needs": None,
        "registration_enabled": False, "registration_capacity": None,
        "registration_opens_at": None, "registration_closes_at": None,
        "technical_readiness": "not_required", "submitted_at": now, "version": 4,
        "created_at": now, "updated_at": now,
    }


@pytest.fixture()
def events(monkeypatch):
    """An in-memory events table whose `edit_event` has the RPC's guards (version, status)."""
    state = {"store": {EVENT_ID: event_row()}, "edits": []}

    def get_event(event_id):
        return deepcopy(state["store"].get(event_id))

    def edit_event(event_id, actor_id, values, version, from_statuses):
        state["edits"].append({"actor_id": actor_id, "values": values, "version": version,
                               "from_statuses": from_statuses})
        row = state["store"].get(event_id)
        if row is None or row["version"] != version or row["status"] not in from_statuses:
            return None
        row.update(values, version=version + 1)
        return deepcopy(row)

    monkeypatch.setattr(repository, "get_event", get_event)
    monkeypatch.setattr(repository, "edit_event", edit_event)
    monkeypatch.setattr(repository, "get_open_amendment", lambda event_id: None)
    return state


@pytest.fixture()
def act_as(authenticate_as):
    def _act_as(role, user_id=COORDINATOR_ID):
        return authenticate_as(role, user_id=user_id)
    return _act_as


def acting_as_another_role(monkeypatch, user_id, holds, acts_as):
    """SCRUM-76: an account that holds `holds` but whose session acts as `acts_as`."""
    profile = {"id": user_id, "email": "someone@connectsphere.dev", "full_name": "Someone",
               "role": holds, "organisation_name": None, "department": None, "phone_number": None}
    anon_client = MagicMock()
    anon_client.auth.get_claims.return_value = {"claims": {
        "sub": user_id, "aud": "authenticated", "email": profile["email"],
        "session_id": "33333333-3333-3333-3333-333333333333",
    }}
    monkeypatch.setattr("app.core.security.get_supabase_anon_client", lambda: anon_client)
    monkeypatch.setattr("app.core.security.get_supabase_admin_client",
                        lambda: make_table_mock(profile, session_active_role={"role": acts_as}))


def edit(client, auth_headers, event_id=EVENT_ID, version=4, **fields):
    return client.patch(f"/api/v1/events/{event_id}/details",
                        json={"version": version, **fields}, headers=auth_headers)


def messages(response):
    return [error["msg"] for error in response.json()["detail"]]


class TestEditOrdinaryFields:
    @pytest.mark.parametrize("status", EDITABLE_STATUSES)
    def test_the_assigned_coordinator_edits_in_every_allowed_status(self, client, auth_headers, act_as, events, status):
        """AC1: saved, and the status does not move."""
        events["store"][EVENT_ID]["status"] = status
        act_as("event_coordinator")

        response = edit(client, auth_headers, description="Agreed with the organiser")

        assert response.status_code == 200
        assert response.json()["description"] == "Agreed with the organiser"
        assert response.json()["status"] == status
        assert events["store"][EVENT_ID]["status"] == status

    def test_all_four_ordinary_fields_save_through_the_recorded_edit(self, client, auth_headers, act_as, events):
        """AC1, AC5: the save goes through edit_event, so the history records old and new."""
        act_as("event_coordinator")

        response = edit(client, auth_headers, name="  Partner Summit 2027  ", purpose="Annual meeting",
                        description="Updated", accessibility_needs="Step-free access")

        assert response.status_code == 200
        [call] = events["edits"]
        assert call["actor_id"] == COORDINATOR_ID
        assert call["version"] == 4
        assert call["from_statuses"] == EDITABLE_STATUSES
        assert call["values"] == {"name": "Partner Summit 2027", "purpose": "Annual meeting",
                                  "description": "Updated", "accessibility_needs": "Step-free access"}
        assert response.json()["version"] == 5

    def test_the_version_is_not_saved_as_a_field(self, client, auth_headers, act_as, events):
        act_as("event_coordinator")

        edit(client, auth_headers, description="x")

        assert "version" not in events["edits"][0]["values"]

    def test_accessibility_notes_and_description_can_be_cleared(self, client, auth_headers, act_as, events):
        events["store"][EVENT_ID].update(description="Old", accessibility_needs="Old")
        act_as("event_coordinator")

        response = edit(client, auth_headers, description=None, accessibility_needs=None)

        assert response.status_code == 200
        assert events["edits"][0]["values"] == {"description": None, "accessibility_needs": None}

    def test_an_edit_with_no_fields_is_refused(self, client, auth_headers, act_as, events):
        act_as("event_coordinator")

        response = edit(client, auth_headers)

        assert response.status_code == 422
        assert events["edits"] == []


class TestSignificantAndOtherFields:
    @pytest.mark.parametrize("field,value", [
        ("starts_at", "2030-01-01T09:00:00+08:00"), ("ends_at", "2030-01-01T11:00:00+08:00"),
        ("event_timezone", "Asia/Tokyo"), ("expected_attendance", 99),
        ("layout_preference", "theatre"), ("facilities_required", ["projector"]),
        ("preliminary_equipment_needs", "Two microphones"),
    ])
    @pytest.mark.parametrize("status", EDITABLE_STATUSES)
    def test_a_significant_field_is_refused_at_every_status(self, client, auth_headers, act_as, events,
                                                            status, field, value):
        """AC2."""
        events["store"][EVENT_ID]["status"] = status
        act_as("event_coordinator")

        response = edit(client, auth_headers, **{field: value})

        assert response.status_code == 422
        assert messages(response) == [SIGNIFICANT_MESSAGE]
        assert response.json()["detail"][0]["loc"] == ["body", field]
        assert events["edits"] == []

    def test_a_significant_field_alongside_an_ordinary_one_saves_nothing(self, client, auth_headers, act_as, events):
        act_as("event_coordinator")

        response = edit(client, auth_headers, name="Renamed event", starts_at="2030-01-01T09:00:00+08:00")

        assert response.status_code == 422
        assert events["edits"] == []

    @pytest.mark.parametrize("field,value", [
        ("registration_enabled", True), ("registration_capacity", 50), ("waitlist_enabled", False),
        ("coordinator_id", "a0000000-0000-4000-8000-000000000009"), ("status", "confirmed"),
    ])
    def test_a_field_outside_the_ordinary_four_is_refused(self, client, auth_headers, act_as, events, field, value):
        act_as("event_coordinator")

        response = edit(client, auth_headers, **{field: value})

        assert response.status_code == 422
        assert messages(response) == ["That field can't be edited here."]
        assert events["edits"] == []

    def test_every_refused_field_is_listed_together(self, client, auth_headers, act_as, events):
        act_as("event_coordinator")

        response = edit(client, auth_headers, starts_at="2030-01-01T09:00:00+08:00", registration_enabled=True)

        assert response.status_code == 422
        assert sorted(error["loc"][-1] for error in response.json()["detail"]) == ["registration_enabled", "starts_at"]


class TestValidation:
    def test_every_field_error_is_returned_together(self, client, auth_headers, act_as, events):
        """AC3."""
        act_as("event_coordinator")

        response = edit(client, auth_headers, name="ab", purpose="x" * 501, description="y" * 5001)

        assert response.status_code == 422
        assert sorted(error["loc"][-1] for error in response.json()["detail"]) == ["description", "name", "purpose"]
        assert events["edits"] == []

    @pytest.mark.parametrize("name,ok", [("abc", True), ("a" * 150, True), ("ab", False), ("a" * 151, False)])
    def test_the_name_length_bounds_match_creation(self, client, auth_headers, act_as, events, name, ok):
        act_as("event_coordinator")

        assert (edit(client, auth_headers, name=name).status_code == 200) is ok

    @pytest.mark.parametrize("length,ok", [(500, True), (501, False)])
    def test_the_purpose_length_bound_matches_creation(self, client, auth_headers, act_as, events, length, ok):
        act_as("event_coordinator")

        assert (edit(client, auth_headers, purpose="p" * length).status_code == 200) is ok

    @pytest.mark.parametrize("length,ok", [(5000, True), (5001, False)])
    def test_the_description_length_bound_matches_creation(self, client, auth_headers, act_as, events, length, ok):
        act_as("event_coordinator")

        assert (edit(client, auth_headers, description="d" * length).status_code == 200) is ok

    @pytest.mark.parametrize("field", ["name", "purpose"])
    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_name_and_purpose_stay_required_once_submitted(self, client, auth_headers, act_as, events, field, value):
        """A submitted request must keep what submission required (8)."""
        act_as("event_coordinator")

        response = edit(client, auth_headers, **{field: value})

        assert response.status_code == 422
        assert events["edits"] == []

    @pytest.mark.parametrize("version", [None, 0, "x"])
    def test_a_missing_or_invalid_version_is_refused(self, client, auth_headers, act_as, events, version):
        act_as("event_coordinator")

        response = client.patch(f"/api/v1/events/{EVENT_ID}/details",
                                json={"version": version, "description": "x"}, headers=auth_headers)

        assert response.status_code == 422
        assert events["edits"] == []


class TestStatusAndConcurrency:
    @pytest.mark.parametrize("status", READ_ONLY_STATUSES)
    def test_returned_and_terminal_events_are_read_only(self, client, auth_headers, act_as, events, status):
        """AC6: Rejected, Cancelled and Completed are read-only; a returned request is the organiser's."""
        events["store"][EVENT_ID]["status"] = status
        act_as("event_coordinator")

        response = edit(client, auth_headers, description="x")

        assert response.status_code == 409
        assert response.json()["detail"] == "This event can't be edited in its current status."
        assert events["edits"] == []

    def test_a_stale_version_is_a_conflict(self, client, auth_headers, act_as, events):
        """AC4."""
        events["store"][EVENT_ID]["version"] = 5
        act_as("event_coordinator")

        response = edit(client, auth_headers, version=4, description="x")

        assert response.status_code == 409
        assert response.json()["detail"] == STALE
        assert events["store"][EVENT_ID]["description"] is None

    def test_a_lost_race_after_the_read_is_a_conflict(self, client, auth_headers, act_as, events, monkeypatch):
        monkeypatch.setattr(repository, "edit_event", lambda *args, **kwargs: None)
        act_as("event_coordinator")

        response = edit(client, auth_headers, description="x")

        assert response.status_code == 409
        assert response.json()["detail"] == STALE


class TestAuthorisation:
    def test_a_draft_is_not_found(self, client, auth_headers, act_as, events):
        events["store"][EVENT_ID]["status"] = "draft"
        act_as("event_coordinator")

        assert edit(client, auth_headers, description="x").status_code == 404
        assert events["edits"] == []

    def test_a_missing_event_is_not_found(self, client, auth_headers, act_as, events):
        act_as("event_coordinator")

        assert edit(client, auth_headers, event_id="e0000000-0000-4000-8000-0000000003ff",
                    description="x").status_code == 404

    def test_a_coordinator_who_is_not_assigned_is_forbidden(self, client, auth_headers, act_as, events):
        act_as("event_coordinator", OTHER_COORDINATOR_ID)

        assert edit(client, auth_headers, description="x").status_code == 403
        assert events["edits"] == []

    def test_an_unassigned_event_is_forbidden_to_a_coordinator(self, client, auth_headers, act_as, events):
        events["store"][EVENT_ID].update(status="under_review", coordinator_id=None)
        act_as("event_coordinator")

        assert edit(client, auth_headers, description="x").status_code == 403
        assert events["edits"] == []

    @pytest.mark.parametrize("role", ["event_organiser", "venue_staff", "tech_support", "attendee",
                                      "safety_officer", "event_coordinator_lead"])
    def test_other_roles_are_forbidden(self, client, auth_headers, act_as, events, role):
        act_as(role)

        assert edit(client, auth_headers, description="x").status_code == 403
        assert events["edits"] == []

    @pytest.mark.parametrize("acts_as", ["event_organiser", "venue_staff", "attendee"])
    def test_a_coordinator_acting_as_another_role_is_forbidden(self, client, auth_headers, monkeypatch, events, acts_as):
        """SCRUM-76: holding the coordinator role is not enough; the session's active role decides."""
        acting_as_another_role(monkeypatch, COORDINATOR_ID, holds="event_coordinator", acts_as=acts_as)

        assert edit(client, auth_headers, description="x").status_code == 403
        assert events["edits"] == []

    def test_the_organiser_still_edits_through_their_own_route(self, client, auth_headers, act_as, events, monkeypatch):
        """The organiser's PATCH /events/{id} is unchanged: it is not open to the coordinator."""
        act_as("event_coordinator")

        response = client.patch(f"/api/v1/events/{EVENT_ID}", json={"description": "x"}, headers=auth_headers)

        assert response.status_code == 403

    def test_an_unauthenticated_request_is_refused(self, client, events):
        response = client.patch(f"/api/v1/events/{EVENT_ID}/details", json={"version": 4, "description": "x"})

        assert response.status_code in (401, 403)
