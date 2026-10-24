"""Story 32: the organiser requests changes to their event, through the HTTP API with
the repository mocked. The RPC's own guards are checked against the real database by
supabase/verification/event_change_request_checks.sql."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.modules.events import repository
from tests.conftest import make_table_mock

ORGANISER_ID = "a0000000-0000-4000-8000-000000000001"
COORDINATOR_ID = "a0000000-0000-4000-8000-000000000002"
EVENT_ID = "e0000000-0000-4000-8000-000000000321"
SPACE_ID = "f0000000-0000-4000-8000-000000000321"
REQUEST_ID = "c0000000-0000-4000-8000-000000000321"
MISSING_EVENT_ID = "e0000000-0000-4000-8000-0000000003ff"
OTHER_ORGANISER_ID = "a0000000-0000-4000-8000-000000000003"
REASON = "Our sponsor wants a longer programme"


def space_row():
    return {
        "id": SPACE_ID, "event_id": EVENT_ID, "label": "Main hall", "expected_pax": 80,
        "layout_preference": "theatre", "facilities_required": ["projector"],
        "starts_at": None, "ends_at": None, "version": 1, "is_primary": True,
    }


def event_row(status="planning", coordinator_id=COORDINATOR_ID):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": EVENT_ID, "organiser_id": ORGANISER_ID, "coordinator_id": coordinator_id,
        "status": status, "event_timezone": "Asia/Singapore", "name": "Partner Summit",
        "purpose": "Quarterly partner meeting", "description": None,
        "starts_at": "2026-11-12T10:00:00+08:00", "ends_at": "2026-11-12T12:00:00+08:00",
        "expected_attendance": 80, "layout_preference": "theatre", "facilities_required": ["projector"],
        "accessibility_needs": None, "preliminary_equipment_needs": None,
        "registration_enabled": False, "registration_capacity": None,
        "registration_opens_at": None, "registration_closes_at": None,
        "re_registration_allowed": True, "waitlist_enabled": True,
        "technical_readiness": "not_required", "submitted_at": now, "version": 3,
        "created_at": now, "updated_at": now, "spaces": [space_row()],
    }


@pytest.fixture()
def events(monkeypatch):
    """An in-memory events table plus a fake request_event_change that answers like
    the RPC: ok with the new request, or an outcome code."""
    store = {EVENT_ID: event_row()}
    calls = []
    outcome = {"value": "ok"}

    def get_event(event_id):
        return deepcopy(store.get(event_id))

    def request_event_change(event_id, actor_id, reason, changes, significant, from_statuses,
                             expected_version, coordinator_message, lead_message):
        calls.append({
            "event_id": event_id, "actor_id": actor_id, "reason": reason, "changes": changes,
            "significant": significant, "from_statuses": from_statuses,
            "expected_version": expected_version, "coordinator_message": coordinator_message,
            "lead_message": lead_message,
        })
        if outcome["value"] != "ok":
            return {"outcome": outcome["value"], "request": None}
        return {"outcome": "ok", "request": {
            "id": REQUEST_ID, "kind": "change", "status": "open", "reason": reason,
            "changes": changes, "significant": significant,
            "requested_by": {"id": actor_id, "full_name": "Test event_organiser"},
            "requested_at": "2026-10-24T09:00:00+00:00",
        }}

    monkeypatch.setattr(repository, "get_event", get_event)
    monkeypatch.setattr(repository, "request_event_change", request_event_change)
    return {"store": store, "calls": calls, "outcome": outcome}


@pytest.fixture()
def act_as(authenticate_as):
    def _act_as(role="event_organiser", user_id=ORGANISER_ID):
        return authenticate_as(role, user_id=user_id)
    return _act_as


def request_change(client, auth_headers, *, event=None, spaces=None, reason=REASON, version=3,
                   event_id=EVENT_ID):
    body = {"reason": reason, "version": version, "event": event or {}, "spaces": spaces or []}
    return client.post(f"/api/v1/events/{event_id}/change-request", json=body, headers=auth_headers)


class TestRequestChange:
    def test_owner_records_an_open_change_request_with_the_before_and_after(
            self, client, auth_headers, act_as, events):
        act_as()

        response = request_change(client, auth_headers, event={"description": "Two keynotes and a panel"})

        assert response.status_code == 201
        assert response.json() == {
            "id": REQUEST_ID, "kind": "change", "status": "open", "reason": REASON,
            "changes": {
                "event": [{"field": "description", "before": None, "after": "Two keynotes and a panel"}],
                "spaces": [],
            },
            "significant": False,
            "requested_by": {"id": ORGANISER_ID, "full_name": "Test event_organiser"},
            "requested_at": "2026-10-24T09:00:00Z",
        }
        [call] = events["calls"]
        assert call["event_id"] == EVENT_ID
        assert call["actor_id"] == ORGANISER_ID
        assert call["expected_version"] == 3

    @pytest.mark.parametrize("status", ["submitted", "under_review", "planning", "safety_review",
                                        "confirmed", "preparation"])
    def test_every_status_after_submission_but_returned_accepts_a_request(
            self, client, auth_headers, act_as, events, status):
        events["store"][EVENT_ID]["status"] = status
        act_as()

        response = request_change(client, auth_headers, event={"description": "Updated"})

        assert response.status_code == 201

    def test_the_rpc_rechecks_only_the_accepted_statuses(self, client, auth_headers, act_as, events):
        act_as()

        request_change(client, auth_headers, event={"description": "Updated"})

        [call] = events["calls"]
        assert set(call["from_statuses"]) == {"submitted", "under_review", "planning", "safety_review",
                                              "confirmed", "preparation"}

    def test_the_reason_is_trimmed(self, client, auth_headers, act_as, events):
        act_as()

        request_change(client, auth_headers, event={"description": "Updated"}, reason=f"  {REASON}  ")

        assert events["calls"][0]["reason"] == REASON


class TestRefusedRequests:
    @pytest.mark.parametrize("status", ["rejected", "cancelled", "completed"])
    def test_a_closed_event_records_no_request(self, client, auth_headers, act_as, events, status):
        """AC4 [LC-R1]: refused, and nothing is recorded or changed."""
        events["store"][EVENT_ID]["status"] = status
        act_as()

        response = request_change(client, auth_headers, event={"description": "Updated"})

        assert response.status_code == 409
        assert response.json()["detail"] == f"Changes can't be requested for an event that is {status}."
        assert events["calls"] == []
        assert events["store"][EVENT_ID]["description"] is None

    def test_a_draft_is_edited_directly(self, client, auth_headers, act_as, events):
        events["store"][EVENT_ID]["status"] = "draft"
        act_as()

        response = request_change(client, auth_headers, event={"description": "Updated"})

        assert response.status_code == 409
        assert response.json()["detail"] == "A draft can be edited directly."
        assert events["calls"] == []

    def test_a_returned_request_is_amended_and_resubmitted(self, client, auth_headers, act_as, events):
        events["store"][EVENT_ID]["status"] = "returned"
        act_as()

        response = request_change(client, auth_headers, event={"description": "Updated"})

        assert response.status_code == 409
        assert response.json()["detail"] == "Edit and resubmit the returned request instead."
        assert events["calls"] == []

    def test_an_event_that_has_started_is_refused(self, client, auth_headers, act_as, events):
        """CR-R15: like a cancellation (CR-R10), it runs to completed once started."""
        started = datetime.now(timezone.utc) - timedelta(minutes=5)
        events["store"][EVENT_ID].update(status="preparation", starts_at=started.isoformat(),
                                         ends_at=(started + timedelta(hours=2)).isoformat())
        act_as()

        response = request_change(client, auth_headers, event={"description": "Updated"})

        assert response.status_code == 409
        assert response.json()["detail"] == "This event has already started, so changes can't be requested."
        assert events["calls"] == []

    def test_another_organisers_event_is_not_found(self, client, auth_headers, act_as, events):
        act_as(user_id=OTHER_ORGANISER_ID)

        response = request_change(client, auth_headers, event={"description": "Updated"})

        assert response.status_code == 404
        assert events["calls"] == []

    def test_a_missing_event_is_not_found(self, client, auth_headers, act_as, events):
        act_as()

        response = request_change(client, auth_headers, event={"description": "Updated"},
                                  event_id=MISSING_EVENT_ID)

        assert response.status_code == 404

    @pytest.mark.parametrize("role", ["event_coordinator", "event_coordinator_lead", "venue_staff",
                                      "tech_support", "safety_officer", "attendee"])
    def test_other_roles_are_forbidden(self, client, auth_headers, act_as, events, role):
        act_as(role, user_id=COORDINATOR_ID)

        response = request_change(client, auth_headers, event={"description": "Updated"})

        assert response.status_code == 403
        assert events["calls"] == []

    def test_the_owner_acting_as_another_role_is_forbidden(self, client, auth_headers, monkeypatch, events):
        """SCRUM-76: the owner's account also holds coordinator and is acting as it."""
        profile = {"id": ORGANISER_ID, "email": "multi@connectsphere.dev", "full_name": "Multi Role",
                   "role": "event_organiser", "organisation_name": None, "department": None,
                   "phone_number": None}
        anon = MagicMock()
        anon.auth.get_claims.return_value = {"claims": {
            "sub": ORGANISER_ID, "aud": "authenticated", "email": profile["email"],
            "session_id": "22222222-2222-2222-2222-222222222222"}}
        monkeypatch.setattr("app.core.security.get_supabase_anon_client", lambda: anon)
        monkeypatch.setattr("app.core.security.get_supabase_admin_client",
                            lambda: make_table_mock(profile, session_active_role={"role": "event_coordinator"}))

        response = request_change(client, auth_headers, event={"description": "Updated"})

        assert response.status_code == 403
        assert events["calls"] == []

    @pytest.mark.parametrize("reason", ["", "   ", "x" * 1001, None])
    def test_a_missing_blank_or_overlong_reason_is_rejected(self, client, auth_headers, act_as, events, reason):
        act_as()

        response = request_change(client, auth_headers, event={"description": "Updated"}, reason=reason)

        assert response.status_code == 422
        assert events["calls"] == []

    def test_a_blank_reason_says_a_reason_for_the_change_is_needed(self, client, auth_headers, act_as, events):
        act_as()

        response = request_change(client, auth_headers, event={"description": "Updated"}, reason="  ")

        assert "A reason for the change is required." in response.text


class TestProposedChanges:
    def test_a_space_change_is_recorded_under_its_space_and_is_significant(
            self, client, auth_headers, act_as, events):
        act_as()

        response = request_change(client, auth_headers, spaces=[{"id": SPACE_ID, "expected_pax": 120}])

        assert response.status_code == 201
        call = events["calls"][0]
        assert call["changes"] == {"event": [], "spaces": [{
            "space_id": SPACE_ID, "label": "Main hall",
            "fields": [{"field": "expected_pax", "before": 80, "after": 120}],
        }]}
        assert call["significant"] is True

    def test_event_and_space_changes_are_recorded_together(self, client, auth_headers, act_as, events):
        act_as()

        request_change(client, auth_headers, event={"expected_attendance": 120, "name": "Partner Summit 2026"},
                       spaces=[{"id": SPACE_ID, "layout_preference": "banquet"}])

        call = events["calls"][0]
        assert call["changes"]["event"] == [
            {"field": "name", "before": "Partner Summit", "after": "Partner Summit 2026"},
            {"field": "expected_attendance", "before": 80, "after": 120},
        ]
        assert call["changes"]["spaces"][0]["fields"] == [
            {"field": "layout_preference", "before": "theatre", "after": "banquet"},
        ]
        assert call["significant"] is True

    @pytest.mark.parametrize("field, value", [
        ("name", "Partner Summit 2026"), ("purpose", "Annual partner meeting"),
        ("accessibility_needs", "Step-free access"), ("waitlist_enabled", False),
    ])
    def test_ordinary_fields_alone_are_not_significant(self, client, auth_headers, act_as, events, field, value):
        act_as()

        request_change(client, auth_headers, event={field: value})

        assert events["calls"][0]["significant"] is False

    @pytest.mark.parametrize("field, value", [
        ("expected_attendance", 120), ("layout_preference", "banquet"),
        ("facilities_required", ["projector", "microphone"]),
        ("preliminary_equipment_needs", "Two wireless microphones"),
        ("event_timezone", "Asia/Tokyo"), ("ends_at", "2026-11-12T13:00:00+08:00"),
    ])
    def test_date_time_attendance_venue_and_equipment_fields_are_significant(
            self, client, auth_headers, act_as, events, field, value):
        act_as()

        request_change(client, auth_headers, event={field: value})

        assert events["calls"][0]["significant"] is True

    def test_a_space_label_alone_is_not_significant(self, client, auth_headers, act_as, events):
        act_as()

        request_change(client, auth_headers, spaces=[{"id": SPACE_ID, "label": "Grand hall"}])

        assert events["calls"][0]["significant"] is False

    def test_values_that_only_look_different_are_not_changes(self, client, auth_headers, act_as, events):
        """Q10: facilities compare as a set, blank text is no text, times compare as instants."""
        events["store"][EVENT_ID]["facilities_required"] = ["projector", "microphone"]
        events["store"][EVENT_ID]["spaces"][0]["facilities_required"] = ["projector", "microphone"]
        act_as()

        response = request_change(
            client, auth_headers,
            event={"facilities_required": ["microphone", "projector"], "description": "   ",
                   "starts_at": "2026-11-12T02:00:00Z", "name": "Partner Summit",
                   "purpose": "Annual partner meeting"},
            spaces=[{"id": SPACE_ID, "facilities_required": ["microphone", "projector"], "label": "Main hall"}],
        )

        assert response.status_code == 201
        assert events["calls"][0]["changes"] == {"event": [
            {"field": "purpose", "before": "Quarterly partner meeting", "after": "Annual partner meeting"},
        ], "spaces": []}

    def test_a_request_that_changes_nothing_is_rejected(self, client, auth_headers, act_as, events):
        act_as()

        response = request_change(client, auth_headers, event={"name": "Partner Summit"},
                                  spaces=[{"id": SPACE_ID, "expected_pax": 80}])

        assert response.status_code == 422
        assert response.json()["detail"] == "Change at least one detail."
        assert events["calls"] == []

    def test_a_space_that_is_not_the_events_is_rejected(self, client, auth_headers, act_as, events):
        act_as()

        response = request_change(client, auth_headers,
                                  spaces=[{"id": "f0000000-0000-4000-8000-0000000003ff", "expected_pax": 120}])

        assert response.status_code == 422
        assert response.json()["detail"] == "One of the spaces is not part of this event."
        assert events["calls"] == []

    @pytest.mark.parametrize("event, spaces, field", [
        ({"starts_at": "2020-01-01T10:00:00+08:00"}, [], "starts_at"),
        ({"ends_at": "2026-11-12T09:00:00+08:00"}, [], "ends_at"),
        ({}, [{"id": SPACE_ID, "starts_at": "2026-11-12T09:00:00+08:00",
               "ends_at": "2026-11-12T11:00:00+08:00"}], "starts_at"),
    ])
    def test_a_change_that_breaks_a_submission_rule_is_rejected(self, client, auth_headers, act_as, events,
                                                                event, spaces, field):
        """CR-R19: the proposed event must pass the same rules as a submission."""
        act_as()

        response = request_change(client, auth_headers, event=event, spaces=spaces)

        assert response.status_code == 422
        assert field in {error["loc"][-1] for error in response.json()["detail"]}
        assert events["calls"] == []

    def test_a_rule_the_event_already_breaks_does_not_block_an_unrelated_change(
            self, client, auth_headers, act_as, events):
        """CR-R19: registration opened yesterday; changing the description still works."""
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        events["store"][EVENT_ID].update(registration_enabled=True, registration_capacity=80,
                                         registration_opens_at=yesterday,
                                         registration_closes_at="2026-11-11T18:00:00+08:00")
        act_as()

        response = request_change(client, auth_headers, event={"description": "Two keynotes"})

        assert response.status_code == 201

    def test_the_coordinator_is_told_what_changes_and_why(self, client, auth_headers, act_as, events):
        act_as()

        request_change(client, auth_headers, event={"expected_attendance": 120},
                       spaces=[{"id": SPACE_ID, "layout_preference": "banquet"}])

        call = events["calls"][0]
        assert call["coordinator_message"] == (
            'Test event_organiser requested changes to "Partner Summit": expected attendance, '
            f'Main hall layout. Reason: {REASON}')
        assert call["lead_message"] == 'Changes requested for unassigned event "Partner Summit".'

    def test_clearing_a_text_field_records_no_text_and_trims_new_text(self, client, auth_headers, act_as, events):
        events["store"][EVENT_ID]["accessibility_needs"] = "Step-free access"
        act_as()

        request_change(client, auth_headers, event={"accessibility_needs": "   ", "description": "  Two keynotes "})

        assert events["calls"][0]["changes"]["event"] == [
            {"field": "description", "before": None, "after": "Two keynotes"},
            {"field": "accessibility_needs", "before": "Step-free access", "after": None},
        ]

    @pytest.mark.parametrize("field", ["name", "purpose"])
    def test_a_required_field_cannot_be_cleared(self, client, auth_headers, act_as, events, field):
        act_as()

        response = request_change(client, auth_headers, event={field: "     "})

        assert response.status_code == 422
        assert field in {error["loc"][-1] for error in response.json()["detail"]}
        assert events["calls"] == []

    def test_a_space_label_cannot_be_cleared(self, client, auth_headers, act_as, events):
        act_as()

        response = request_change(client, auth_headers, spaces=[{"id": SPACE_ID, "label": "   "}])

        assert response.status_code == 422
        assert events["calls"] == []
