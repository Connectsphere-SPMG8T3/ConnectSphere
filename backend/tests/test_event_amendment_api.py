"""SCRUM-33 return for amendment and resubmission, through the HTTP API with the repository mocked."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.modules.events import repository
from tests.conftest import make_table_mock

ORGANISER_ID = "a0000000-0000-4000-8000-000000000001"
OTHER_ORGANISER_ID = "a0000000-0000-4000-8000-000000000008"
COORDINATOR_ID = "a0000000-0000-4000-8000-000000000002"
OTHER_COORDINATOR_ID = "a0000000-0000-4000-8000-000000000009"
EVENT_ID = "e0000000-0000-4000-8000-000000000201"
ALL_STATUSES = ["draft", "submitted", "under_review", "returned", "planning",
                "confirmed", "rejected", "cancelled", "completed"]
OPEN_AMENDMENT = {"id": "a1", "message": "Please confirm the attendance",
                  "flagged_fields": ["expected_attendance"], "returned_at": "2026-09-24T03:00:00+00:00"}


def same_amendment(body_amendment, expected=OPEN_AMENDMENT):
    """The API writes `returned_at` as `...Z`; compare the instant, not its spelling."""
    assert {k: v for k, v in body_amendment.items() if k != "returned_at"} ==         {k: v for k, v in expected.items() if k != "returned_at"}
    assert datetime.fromisoformat(body_amendment["returned_at"].replace("Z", "+00:00")) ==         datetime.fromisoformat(expected["returned_at"])
    return True


def event_row(status="under_review"):
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
        "technical_readiness": "not_required", "submitted_at": now, "version": 3,
        "created_at": now, "updated_at": now,
    }


@pytest.fixture()
def events(monkeypatch):
    """An in-memory events table, an open-amendment slot, and fakes with the RPCs' guards."""
    state = {"store": {EVENT_ID: event_row()}, "amendment": None, "calls": [], "updates": []}

    def get_event(event_id):
        return deepcopy(state["store"].get(event_id))

    def _move(event_id, from_statuses, to_status, expected_version):
        row = state["store"].get(event_id)
        if row is None or row["version"] != expected_version or row["status"] not in from_statuses:
            return None
        row.update(status=to_status, version=row["version"] + 1)
        return deepcopy(row)

    def return_event(event_id, actor_id, from_statuses, to_status, expected_version, *,
                     message, flagged_fields, notify_message):
        state["calls"].append({"rpc": "return", "actor_id": actor_id, "from_statuses": from_statuses,
                               "to_status": to_status, "expected_version": expected_version,
                               "message": message, "flagged_fields": flagged_fields,
                               "notify_message": notify_message})
        moved = _move(event_id, from_statuses, to_status, expected_version)
        if moved:
            state["amendment"] = {"id": "a1", "message": message, "flagged_fields": flagged_fields,
                                  "returned_at": "2026-09-24T03:00:00+00:00"}
        return moved

    def resubmit_event(event_id, actor_id, from_statuses, to_status, expected_version, *, note, notify_message):
        state["calls"].append({"rpc": "resubmit", "actor_id": actor_id, "from_statuses": from_statuses,
                               "to_status": to_status, "expected_version": expected_version,
                               "note": note, "notify_message": notify_message})
        moved = _move(event_id, from_statuses, to_status, expected_version)
        if moved:
            state["amendment"] = None
        return moved

    def update_event(event_id, values, version):
        state["updates"].append(values)
        row = state["store"][event_id]
        if row["version"] != version:
            return None
        row.update(values, version=version + 1)
        return deepcopy(row)

    monkeypatch.setattr(repository, "get_event", get_event)
    monkeypatch.setattr(repository, "return_event", return_event)
    monkeypatch.setattr(repository, "resubmit_event", resubmit_event)
    monkeypatch.setattr(repository, "update_event", update_event)
    monkeypatch.setattr(repository, "get_open_amendment", lambda event_id: deepcopy(state["amendment"]))
    return state


@pytest.fixture()
def act_as(authenticate_as):
    def _act_as(role, user_id):
        return authenticate_as(role, user_id=user_id)
    return _act_as


def returned(events):
    events["store"][EVENT_ID]["status"] = "returned"
    events["amendment"] = deepcopy(OPEN_AMENDMENT)


def return_request(client, auth_headers, message="Please confirm the attendance",
                   flagged_fields=("expected_attendance",), event_id=EVENT_ID):
    return client.post(f"/api/v1/events/{event_id}/return",
                       json={"message": message, "flagged_fields": list(flagged_fields)}, headers=auth_headers)


def resubmit_request(client, auth_headers, note="Attendance is now 40", **edits):
    return client.post(f"/api/v1/events/{EVENT_ID}/resubmit",
                       json={"resubmission_note": note, **edits}, headers=auth_headers)


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


class TestReturn:
    def test_the_assigned_coordinator_returns_an_under_review_request(self, client, auth_headers, act_as, events):
        act_as("event_coordinator", COORDINATOR_ID)

        response = return_request(client, auth_headers, message="  Please confirm the attendance  ")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "returned"
        assert body["amendment"]["message"] == "Please confirm the attendance"
        assert body["amendment"]["flagged_fields"] == ["expected_attendance"]
        [call] = events["calls"]
        assert call["actor_id"] == COORDINATOR_ID
        assert call["from_statuses"] == ["under_review"]
        assert call["to_status"] == "returned"
        assert call["expected_version"] == 3
        assert call["message"] == "Please confirm the attendance"
        assert call["notify_message"] == 'Your event "Partner Summit" was returned for amendment: Please confirm the attendance'

    def test_no_fields_need_flagging(self, client, auth_headers, act_as, events):
        act_as("event_coordinator", COORDINATOR_ID)

        response = return_request(client, auth_headers, flagged_fields=())

        assert response.status_code == 200
        assert events["calls"][0]["flagged_fields"] == []

    def test_a_field_flagged_twice_is_sent_once_in_order(self, client, auth_headers, act_as, events):
        act_as("event_coordinator", COORDINATOR_ID)

        return_request(client, auth_headers, flagged_fields=("starts_at", "expected_attendance", "starts_at"))

        assert events["calls"][0]["flagged_fields"] == ["starts_at", "expected_attendance"]

    def test_an_unknown_field_is_refused(self, client, auth_headers, act_as, events):
        act_as("event_coordinator", COORDINATOR_ID)

        assert return_request(client, auth_headers, flagged_fields=("venue_id",)).status_code == 422
        assert events["calls"] == []

    @pytest.mark.parametrize("message", ["", "   ", "\n\t "])
    def test_a_blank_message_is_refused(self, client, auth_headers, act_as, events, message):
        act_as("event_coordinator", COORDINATOR_ID)

        assert return_request(client, auth_headers, message=message).status_code == 422
        assert events["calls"] == []

    def test_a_missing_message_is_refused(self, client, auth_headers, act_as, events):
        act_as("event_coordinator", COORDINATOR_ID)

        response = client.post(f"/api/v1/events/{EVENT_ID}/return", json={}, headers=auth_headers)

        assert response.status_code == 422
        assert events["calls"] == []

    def test_the_message_is_capped_at_1000_characters(self, client, auth_headers, act_as, events):
        act_as("event_coordinator", COORDINATOR_ID)

        assert return_request(client, auth_headers, message="x" * 1001).status_code == 422
        assert return_request(client, auth_headers, message="x" * 1000).status_code == 200

    @pytest.mark.parametrize("status", [s for s in ALL_STATUSES if s not in ("under_review", "draft")])
    def test_return_is_blocked_unless_under_review(self, client, auth_headers, act_as, events, status):
        events["store"][EVENT_ID]["status"] = status
        act_as("event_coordinator", COORDINATOR_ID)

        response = return_request(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == f"Cannot return an event that is {status.replace('_', ' ')}"
        assert events["calls"] == []

    def test_a_draft_is_not_found(self, client, auth_headers, act_as, events):
        events["store"][EVENT_ID]["status"] = "draft"
        act_as("event_coordinator", COORDINATOR_ID)

        assert return_request(client, auth_headers).status_code == 404

    def test_a_coordinator_who_is_not_assigned_is_forbidden(self, client, auth_headers, act_as, events):
        act_as("event_coordinator", OTHER_COORDINATOR_ID)

        assert return_request(client, auth_headers).status_code == 403
        assert events["calls"] == []

    @pytest.mark.parametrize("role", ["event_organiser", "venue_staff", "tech_support", "attendee"])
    def test_other_roles_are_forbidden(self, client, auth_headers, act_as, events, role):
        act_as(role, COORDINATOR_ID)

        assert return_request(client, auth_headers).status_code == 403
        assert events["calls"] == []

    def test_a_coordinator_acting_as_venue_staff_is_forbidden(self, client, auth_headers, monkeypatch, events):
        acting_as_another_role(monkeypatch, COORDINATOR_ID, holds="event_coordinator", acts_as="venue_staff")

        assert return_request(client, auth_headers).status_code == 403
        assert events["calls"] == []

    def test_a_lost_race_is_a_conflict(self, client, auth_headers, act_as, events, monkeypatch):
        monkeypatch.setattr(repository, "return_event", lambda *args, **kwargs: None)
        act_as("event_coordinator", COORDINATOR_ID)

        response = return_request(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == "This event was updated by someone else. Reload."

    @pytest.mark.parametrize("action", ["approve", "reject"])
    def test_a_returned_request_cannot_be_decided(self, client, auth_headers, act_as, events, action):
        """AC7: the decision waits for the organiser's resubmission."""
        returned(events)
        act_as("event_coordinator", COORDINATOR_ID)

        response = client.post(f"/api/v1/events/{EVENT_ID}/{action}", json={"reason": "No venue"}, headers=auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == f"Cannot {action} an event that is returned"


class TestResubmit:
    def test_the_owner_resubmits_with_edits_to_the_same_coordinator(self, client, auth_headers, act_as, events):
        returned(events)
        act_as("event_organiser", ORGANISER_ID)

        response = resubmit_request(client, auth_headers, note="  Attendance is now 40  ", expected_attendance=40)

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "under_review"
        assert body["coordinator_id"] == COORDINATOR_ID
        assert body["expected_attendance"] == 40
        assert body["amendment"] is None
        assert events["updates"] == [{"expected_attendance": 40}]
        [call] = events["calls"]
        assert call["actor_id"] == ORGANISER_ID
        assert call["from_statuses"] == ["returned"]
        assert call["to_status"] == "under_review"
        assert call["expected_version"] == 4  # the edit bumped it from 3
        assert call["note"] == "Attendance is now 40"
        assert call["notify_message"] == '"Partner Summit" was amended and resubmitted: Attendance is now 40'

    def test_an_emptied_optional_field_is_cleared_on_resubmit(self, client, auth_headers, act_as, events):
        """AC3 "edits any field": clearing a field is an edit. The SPA sends null for
        it, and the API must apply that rather than keep the old value."""
        returned(events)
        events["store"][EVENT_ID]["preliminary_equipment_needs"] = "Two projectors"
        act_as("event_organiser", ORGANISER_ID)

        response = resubmit_request(client, auth_headers, preliminary_equipment_needs=None)

        assert response.status_code == 200
        assert events["updates"] == [{"preliminary_equipment_needs": None}]
        assert response.json()["preliminary_equipment_needs"] is None

    def test_resubmitting_without_edits_skips_the_update(self, client, auth_headers, act_as, events):
        returned(events)
        act_as("event_organiser", ORGANISER_ID)

        response = resubmit_request(client, auth_headers)

        assert response.status_code == 200
        assert events["updates"] == []
        assert events["calls"][0]["expected_version"] == 3

    @pytest.mark.parametrize("note", ["", "   "])
    def test_a_blank_note_is_refused(self, client, auth_headers, act_as, events, note):
        returned(events)
        act_as("event_organiser", ORGANISER_ID)

        assert resubmit_request(client, auth_headers, note=note).status_code == 422
        assert events["calls"] == []

    def test_a_missing_note_is_refused(self, client, auth_headers, act_as, events):
        returned(events)
        act_as("event_organiser", ORGANISER_ID)

        response = client.post(f"/api/v1/events/{EVENT_ID}/resubmit", json={"expected_attendance": 40}, headers=auth_headers)

        assert response.status_code == 422
        assert events["updates"] == []

    def test_the_note_is_capped_at_1000_characters(self, client, auth_headers, act_as, events):
        returned(events)
        act_as("event_organiser", ORGANISER_ID)

        assert resubmit_request(client, auth_headers, note="x" * 1001).status_code == 422

    def test_edits_that_break_submission_rules_are_refused_before_anything_changes(self, client, auth_headers, act_as, events):
        returned(events)
        act_as("event_organiser", ORGANISER_ID)

        response = resubmit_request(client, auth_headers, purpose="")

        assert response.status_code == 422
        assert events["updates"] == []
        assert events["calls"] == []

    def test_an_event_date_that_has_passed_while_returned_is_refused(self, client, auth_headers, act_as, events):
        """Review focus: the organiser took too long; the request must not go back with a past date."""
        returned(events)
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        events["store"][EVENT_ID].update(starts_at=yesterday.isoformat(),
                                         ends_at=(yesterday + timedelta(hours=2)).isoformat())
        act_as("event_organiser", ORGANISER_ID)

        response = resubmit_request(client, auth_headers)

        assert response.status_code == 422
        assert any(error["msg"] == "Event date must be after today." for error in response.json()["detail"])
        assert events["store"][EVENT_ID]["status"] == "returned"

    def test_edits_saved_but_a_lost_race_is_a_conflict_and_stays_returned(self, client, auth_headers, act_as, events, monkeypatch):
        """Review focus: the PATCH lands, the RPC finds the version moved."""
        returned(events)
        monkeypatch.setattr(repository, "resubmit_event", lambda *args, **kwargs: None)
        act_as("event_organiser", ORGANISER_ID)

        response = resubmit_request(client, auth_headers, expected_attendance=40)

        assert response.status_code == 409
        assert events["store"][EVENT_ID]["status"] == "returned"
        assert events["store"][EVENT_ID]["expected_attendance"] == 40

    @pytest.mark.parametrize("status", [s for s in ALL_STATUSES if s != "returned"])
    def test_resubmit_is_blocked_unless_returned(self, client, auth_headers, act_as, events, status):
        events["store"][EVENT_ID]["status"] = status
        act_as("event_organiser", ORGANISER_ID)

        response = resubmit_request(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == f"Cannot resubmit an event that is {status.replace('_', ' ')}"
        assert events["calls"] == []

    def test_another_organiser_gets_not_found(self, client, auth_headers, act_as, events):
        returned(events)
        act_as("event_organiser", OTHER_ORGANISER_ID)

        assert resubmit_request(client, auth_headers).status_code == 404
        assert events["calls"] == []

    @pytest.mark.parametrize("role", ["event_coordinator", "venue_staff", "tech_support", "attendee"])
    def test_other_roles_are_forbidden(self, client, auth_headers, act_as, events, role):
        returned(events)
        act_as(role, ORGANISER_ID)

        assert resubmit_request(client, auth_headers).status_code == 403
        assert events["calls"] == []

    def test_an_organiser_acting_as_attendee_is_forbidden(self, client, auth_headers, monkeypatch, events):
        returned(events)
        acting_as_another_role(monkeypatch, ORGANISER_ID, holds="event_organiser", acts_as="attendee")

        assert resubmit_request(client, auth_headers).status_code == 403


class TestAmendmentOnResponses:
    def test_reading_a_returned_request_includes_its_open_amendment(self, client, auth_headers, act_as, events):
        returned(events)
        act_as("event_organiser", ORGANISER_ID)

        body = client.get(f"/api/v1/events/{EVENT_ID}", headers=auth_headers).json()

        assert same_amendment(body["amendment"])

    def test_the_assigned_coordinator_reads_the_same_amendment(self, client, auth_headers, act_as, events):
        returned(events)
        act_as("event_coordinator", COORDINATOR_ID)

        body = client.get(f"/api/v1/events/{EVENT_ID}", headers=auth_headers).json()

        assert body["amendment"]["message"] == OPEN_AMENDMENT["message"]

    def test_a_request_that_is_not_returned_has_no_amendment(self, client, auth_headers, act_as, events):
        events["amendment"] = deepcopy(OPEN_AMENDMENT)  # stale row must not leak onto another status
        act_as("event_organiser", ORGANISER_ID)

        body = client.get(f"/api/v1/events/{EVENT_ID}", headers=auth_headers).json()

        assert body["amendment"] is None

    def test_a_returned_request_with_no_amendment_row_reads_as_null(self, client, auth_headers, act_as, events):
        """Review focus: returned before this migration, or set by SQL."""
        events["store"][EVENT_ID]["status"] = "returned"
        act_as("event_organiser", ORGANISER_ID)

        response = client.get(f"/api/v1/events/{EVENT_ID}", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["amendment"] is None

    def test_a_stored_flag_the_api_no_longer_knows_still_reads(self, client, auth_headers, act_as, events):
        """Only the request validates flag names. A stored name that has since left
        EventField must not turn every read of the returned event into a 500."""
        returned(events)
        events["amendment"]["flagged_fields"] = ["expected_attendance", "venue_notes"]
        act_as("event_organiser", ORGANISER_ID)

        response = client.get(f"/api/v1/events/{EVENT_ID}", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["amendment"]["flagged_fields"] == ["expected_attendance", "venue_notes"]

    def test_saving_changes_on_a_returned_request_keeps_the_amendment(self, client, auth_headers, act_as, events):
        """Review focus: the PATCH response feeds the form; losing `amendment` would drop the banner."""
        returned(events)
        act_as("event_organiser", ORGANISER_ID)

        response = client.patch(f"/api/v1/events/{EVENT_ID}", json={"expected_attendance": 40}, headers=auth_headers)

        assert response.status_code == 200
        assert same_amendment(response.json()["amendment"])
