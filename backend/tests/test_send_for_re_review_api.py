"""Story 37 AC6, Q20: the assigned coordinator sends a booking or an equipment line an
approved change marked Needs re-review to venue staff or technical support, through
the HTTP API with the repositories mocked. The RPCs' own guards are checked against
the real database by supabase/verification/change_request_decision_checks.sql."""

import pytest

from app.modules.equipment import repository as equipment_repository
from app.modules.events import service as events_service
from app.modules.venues import repository as venues_repository

COORDINATOR_ID = "a0000000-0000-4000-8000-000000000002"
EVENT_ID = "e0000000-0000-4000-8000-000000000372"
BOOKING_ID = "d0000000-0000-4000-8000-000000000372"
LINE_ID = "c0000000-0000-4000-8000-000000000372"
NOTE = "The event now runs in the afternoon"


@pytest.fixture()
def sends(monkeypatch):
    """Fake RPCs that answer like the database, and the reads the messages need."""
    calls = []
    outcome = {"value": "ok"}

    def send_booking(booking_id, actor_id, note, staff_message):
        calls.append({"kind": "booking", "id": booking_id, "actor_id": actor_id, "note": note,
                      "staff_message": staff_message})
        return {"outcome": outcome["value"]}

    def send_line(line_id, actor_id, note, staff_message):
        calls.append({"kind": "line", "id": line_id, "actor_id": actor_id, "note": note,
                      "staff_message": staff_message})
        return {"outcome": outcome["value"]}

    monkeypatch.setattr(venues_repository, "get_booking", lambda booking_id: {
        "id": booking_id, "event_id": EVENT_ID, "venue_name": "Grand Ballroom"} if booking_id == BOOKING_ID else None)
    monkeypatch.setattr(venues_repository, "send_booking_for_re_review", send_booking)
    monkeypatch.setattr(equipment_repository, "get_line", lambda line_id: {
        "id": line_id, "event_id": EVENT_ID, "status": "reserved"} if line_id == LINE_ID else None)
    monkeypatch.setattr(equipment_repository, "send_line_for_re_review", send_line)
    monkeypatch.setattr(events_service, "names_by_id", lambda ids: {EVENT_ID: "Partner Summit"})
    return {"calls": calls, "outcome": outcome}


def send_booking(client, auth_headers, booking_id=BOOKING_ID, body=None):
    return client.post(f"/api/v1/venue-bookings/{booking_id}/send-for-re-review", json=body or {},
                       headers=auth_headers)


def send_line(client, auth_headers, line_id=LINE_ID, body=None):
    return client.post(f"/api/v1/equipment/requests/{line_id}/send-for-re-review", json=body or {},
                       headers=auth_headers)


class TestSendBooking:
    def test_the_coordinator_sends_it_with_a_note(self, client, auth_headers, authenticate_as, sends):
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        response = send_booking(client, auth_headers, body={"note": f"  {NOTE}  "})

        assert response.status_code == 204
        assert sends["calls"] == [{
            "kind": "booking", "id": BOOKING_ID, "actor_id": COORDINATOR_ID, "note": NOTE,
            "staff_message": f'"Partner Summit" changed: Grand Ballroom needs re-review. Note: {NOTE}',
        }]

    def test_the_note_is_optional(self, client, auth_headers, authenticate_as, sends):
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        send_booking(client, auth_headers, body={"note": "   "})

        assert sends["calls"][0]["note"] is None
        assert sends["calls"][0]["staff_message"] == '"Partner Summit" changed: Grand Ballroom needs re-review.'

    def test_an_overlong_note_is_rejected(self, client, auth_headers, authenticate_as, sends):
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        response = send_booking(client, auth_headers, body={"note": "x" * 1001})

        assert response.status_code == 422
        assert sends["calls"] == []

    def test_an_unknown_booking_is_not_found(self, client, auth_headers, authenticate_as, sends):
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        response = send_booking(client, auth_headers, booking_id="d0000000-0000-4000-8000-0000000003ff")

        assert response.status_code == 404
        assert sends["calls"] == []

    @pytest.mark.parametrize(("outcome", "status_code", "detail"), [
        ("not_found", 404, "Booking not found."),
        ("not_assigned", 403, None),
        ("status_changed", 409, "Arrangements can be sent for re-review only while the event is in Planning."),
        ("not_marked", 409, "This booking doesn't need re-review."),
    ])
    def test_the_rpc_decides_under_its_lock(self, client, auth_headers, authenticate_as, sends, outcome,
                                            status_code, detail):
        sends["outcome"]["value"] = outcome
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        response = send_booking(client, auth_headers)

        assert response.status_code == status_code
        if detail:
            assert response.json()["detail"] == detail


class TestSendLine:
    def test_the_coordinator_sends_it(self, client, auth_headers, authenticate_as, sends):
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        response = send_line(client, auth_headers, body={"note": NOTE})

        assert response.status_code == 204
        assert sends["calls"] == [{
            "kind": "line", "id": LINE_ID, "actor_id": COORDINATOR_ID, "note": NOTE,
            "staff_message": f'Equipment for "Partner Summit" needs re-review after an approved change. Note: {NOTE}',
        }]

    def test_an_unknown_line_is_not_found(self, client, auth_headers, authenticate_as, sends):
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        response = send_line(client, auth_headers, line_id="c0000000-0000-4000-8000-0000000003ff")

        assert response.status_code == 404
        assert sends["calls"] == []

    @pytest.mark.parametrize(("outcome", "status_code", "detail"), [
        ("not_assigned", 403, None),
        ("status_changed", 409, "Arrangements can be sent for re-review only while the event is in Planning."),
        ("not_marked", 409, "This equipment line doesn't need re-review."),
    ])
    def test_the_rpc_decides_under_its_lock(self, client, auth_headers, authenticate_as, sends, outcome,
                                            status_code, detail):
        sends["outcome"]["value"] = outcome
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        response = send_line(client, auth_headers)

        assert response.status_code == status_code
        if detail:
            assert response.json()["detail"] == detail


SENDS = [("booking", send_booking), ("line", send_line)]


class TestOnlyTheCoordinatorSends:
    """SCRUM-76: by the session's active role."""

    @pytest.mark.parametrize(("name", "send"), SENDS)
    @pytest.mark.parametrize("role", ["event_organiser", "event_coordinator_lead", "venue_staff",
                                      "tech_support", "safety_officer", "attendee"])
    def test_other_roles_are_forbidden(self, client, auth_headers, authenticate_as, sends, role, name, send):
        authenticate_as(role, user_id=COORDINATOR_ID)

        response = send(client, auth_headers)

        assert response.status_code == 403
        assert sends["calls"] == []


class TestTheCoordinatorSeesTheMarker:
    """Q20: each marked arrangement says why, so the page can offer Send for re-review."""

    def test_a_space_booking_carries_why_it_needs_re_review(self, monkeypatch):
        from app.modules.venues import service as venues_service

        monkeypatch.setattr(venues_repository, "list_active_bookings", lambda event_id: [{
            "id": BOOKING_ID, "event_id": EVENT_ID, "event_space_request_id": "s1", "venue_id": "v1",
            "status": "approved", "venues": {"name": "Grand Ballroom"}, "flag": None, "flag_reason": None,
            "replaces_booking_id": None, "needs_re_review_reason": "Date or time changed.",
        }])

        [booking] = venues_service.active_bookings_for_event(EVENT_ID)

        assert booking["needs_re_review_reason"] == "Date or time changed."

    def test_an_equipment_line_carries_why_it_needs_re_review(self, client, auth_headers, authenticate_as,
                                                              monkeypatch):
        from app.modules.equipment import service as equipment_service

        monkeypatch.setattr(events_service, "assigned_event",
                            lambda event_id, coordinator_id: {"id": EVENT_ID, "technical_readiness": "pending"})
        monkeypatch.setattr(equipment_service, "exit_confirmation", lambda event_id: None)
        monkeypatch.setattr(equipment_repository, "list_event_requests", lambda event_id: [{
            "id": LINE_ID, "submission_id": "50000000-0000-4000-8000-000000000001", "event_id": EVENT_ID,
            "equipment_id": "b0000000-0000-4000-8000-000000000003", "quantity": 8, "technical_requirements": None,
            "status": "reserved", "technical_notes": None, "not_available_reason": None,
            "needs_re_review_reason": "Event time changed; 5 free for 8.",
            "requested_by": COORDINATOR_ID, "created_at": "2026-10-06T02:00:00+00:00",
            "equipment": {"name": "PA Systems"}, "requester": {"id": COORDINATOR_ID, "full_name": "Marcus Lim"},
        }])
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        body = client.get(f"/api/v1/equipment/requests/event/{EVENT_ID}", headers=auth_headers).json()

        assert body["lines"][0]["needs_re_review_reason"] == "Event time changed; 5 free for 8."
