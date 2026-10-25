"""SCRUM-82: send authorization, readiness and coordinator event reads."""
from copy import deepcopy
from unittest.mock import MagicMock
import pytest
from app.modules.events import repository
from app.modules.venues import repository as venues_repository
from tests.test_event_review_api import event_row, EVENT_ID, COORDINATOR_ID, ORGANISER_ID
from tests.test_event_comments_api import acting_as_another_role

URL = f"/api/v1/events/{EVENT_ID}/send-for-safety-check"

@pytest.fixture()
def state(monkeypatch):
    state = {"event": event_row("planning"), "bookings": ["approved"], "calls": [], "stale": False}
    monkeypatch.setattr(repository, "get_event", lambda event_id: deepcopy(state["event"]) if event_id == EVENT_ID else None)
    monkeypatch.setattr(venues_repository, "list_booking_statuses", lambda ids: [{"event_id": EVENT_ID, "status": s} for s in state["bookings"]])
    monkeypatch.setattr(venues_repository, "get_active_booking", lambda event_id: {"id": "b1", "venue_id": "v1", "status": "approved", "venues": {"name": "Hall"}})
    def send(event_id, actor_id, from_statuses, to_status, expected_version, **messages):
        state["calls"].append((event_id, actor_id, from_statuses, to_status, expected_version, messages))
        if state["stale"]:
            return None
        state["event"].update(status=to_status, version=expected_version + 1)
        return deepcopy(state["event"])
    monkeypatch.setattr(repository, "send_to_safety_review", send, raising=False)
    return state


def test_ready_send_and_double_send(client, auth_headers, authenticate_as, state):
    authenticate_as("event_coordinator", COORDINATOR_ID)
    result = client.post(URL, headers=auth_headers)
    assert result.status_code == 200
    assert result.json()["status"] == "safety_review"
    assert state["calls"] == [(EVENT_ID, COORDINATOR_ID, ["planning"], "safety_review", 3, {
        "organiser_message": 'Your event "Partner Summit" is with the Safety Officer for its operational safety check.',
        "officer_message": '"Partner Summit" is ready for its operational safety check.'})]
    assert client.post(URL, headers=auth_headers).status_code == 409
    assert len(state["calls"]) == 1

def test_a_flagged_booking_blocks_sending(client, auth_headers, authenticate_as, state, monkeypatch):
    # SCRUM-64 / 82 AC10: the stored flag reaches the readiness check.
    authenticate_as("event_coordinator", COORDINATOR_ID)
    monkeypatch.setattr(venues_repository, "list_booking_statuses",
                        lambda ids: [{"event_id": EVENT_ID, "status": "approved", "flag": "affected"}])
    response = client.post(URL, headers=auth_headers)
    assert response.status_code == 409
    assert response.json()["detail"] == "Not ready for safety check: A venue booking is flagged Affected."
    assert not state["calls"]

@pytest.mark.parametrize("bookings,technical,missing", [
    ([], "ready", "No venue booking is approved."),
    (["approved", "held"], "pending", "A venue booking is awaiting venue staff approval. Technical status is not Ready."),
    (["re_review"], "ready", "A venue booking is under re-review."),
])
def test_missing_blocks_without_rpc(client, auth_headers, authenticate_as, state, bookings, technical, missing):
    authenticate_as("event_coordinator", COORDINATOR_ID)
    state["bookings"] = bookings
    state["event"]["technical_readiness"] = technical
    response = client.post(URL, headers=auth_headers)
    assert response.status_code == 409
    assert response.json()["detail"] == "Not ready for safety check: " + missing
    assert not state["calls"]

@pytest.mark.parametrize("status", ["submitted", "under_review", "returned", "safety_review", "confirmed", "rejected", "cancelled", "completed"])
def test_other_statuses_block(client, auth_headers, authenticate_as, state, status):
    authenticate_as("event_coordinator", COORDINATOR_ID)
    state["event"]["status"] = status
    response = client.post(URL, headers=auth_headers)
    assert response.status_code == 409
    assert response.json()["detail"] == f"Cannot send to safety an event that is {status.replace('_', ' ')}"
    assert not state["calls"]

@pytest.mark.parametrize("role", ["event_organiser", "venue_staff", "tech_support", "attendee", "event_coordinator_lead", "safety_officer"])
def test_other_roles_forbidden(client, auth_headers, authenticate_as, state, role):
    authenticate_as(role, COORDINATOR_ID)
    assert client.post(URL, headers=auth_headers).status_code == 403
    assert not state["calls"]


def test_active_role_denial(client, auth_headers, monkeypatch, state):
    acting_as_another_role(monkeypatch, COORDINATOR_ID, "event_coordinator", "safety_officer")
    assert client.post(URL, headers=auth_headers).status_code == 403
    assert not state["calls"]

@pytest.mark.parametrize("condition,code", [("draft",404),("missing",404),("unassigned",403),("stale",409)])
def test_failures(client, auth_headers, authenticate_as, state, condition, code):
    authenticate_as("event_coordinator", COORDINATOR_ID)
    if condition == "draft": state["event"]["status"] = "draft"
    if condition == "missing": state["event"] = None
    if condition == "unassigned": state["event"]["coordinator_id"] = None
    if condition == "stale": state["stale"] = True
    response = client.post(URL, headers=auth_headers)
    assert response.status_code == code
    if condition == "stale": assert response.json()["detail"] == "This event was updated by someone else. Reload."

@pytest.mark.parametrize("role,status,expected", [("event_coordinator","planning",True),("event_coordinator","under_review",False),("event_organiser","planning",False),("event_organiser","confirmed",False)])
def test_read_shape(client, auth_headers, authenticate_as, state, role, status, expected):
    state["event"]["status"] = status
    authenticate_as(role, COORDINATOR_ID if role == "event_coordinator" else ORGANISER_ID)
    result = client.get(f"/api/v1/events/{EVENT_ID}", headers=auth_headers).json()
    assert result["safety_readiness"] == ({"ready": True, "missing": []} if expected else None)
    assert bool(result["venue_booking"]) == (role == "event_coordinator" or status == "confirmed")


def test_coordinator_read_shows_missing_and_other_reads_do_not_query_bookings(client, auth_headers, authenticate_as, state, monkeypatch):
    state["bookings"] = ["held"]
    authenticate_as("event_coordinator", COORDINATOR_ID)
    result = client.get(f"/api/v1/events/{EVENT_ID}", headers=auth_headers).json()
    assert result["safety_readiness"] == {"ready": False, "missing": ["A venue booking is awaiting venue staff approval."]}
    def unexpected_query(ids):
        pytest.fail("Non-planning or organiser read queried safety bookings")
    monkeypatch.setattr(venues_repository, "list_booking_statuses", unexpected_query)
    state["event"]["status"] = "safety_review"
    assert client.get(f"/api/v1/events/{EVENT_ID}", headers=auth_headers).json()["safety_readiness"] is None
    state["event"]["status"] = "planning"
    authenticate_as("event_organiser", ORGANISER_ID)
    assert client.get(f"/api/v1/events/{EVENT_ID}", headers=auth_headers).json()["safety_readiness"] is None


def _space(space_id, label):
    return {"id": space_id, "event_id": EVENT_ID, "label": label, "expected_pax": None, "layout_preference": None,
            "facilities_required": [], "starts_at": None, "ends_at": None, "version": 1}


# CR-97 AC10: every event space needs its own approved booking.
def test_an_event_space_without_an_approved_booking_blocks_and_is_named(client, auth_headers, authenticate_as, state, monkeypatch):
    state["event"]["spaces"] = [_space("s1", "Main hall"), _space("s2", "Breakout room")]
    monkeypatch.setattr(venues_repository, "list_booking_statuses", lambda ids: [
        {"event_id": EVENT_ID, "event_space_request_id": "s1", "status": "approved"},
        {"event_id": EVENT_ID, "event_space_request_id": "s2", "status": "rejected"},
    ])
    authenticate_as("event_coordinator", COORDINATOR_ID)
    response = client.post(URL, headers=auth_headers)
    assert response.status_code == 409
    assert response.json()["detail"] == "Not ready for safety check: Breakout room: no approved venue booking."
    assert not state["calls"]


def test_a_booking_that_needs_re_review_blocks_sending(client, auth_headers, authenticate_as, state, monkeypatch):
    # Story 37 Q13: an approved change marked it; it counts as not ready until sent and decided.
    authenticate_as("event_coordinator", COORDINATOR_ID)
    monkeypatch.setattr(venues_repository, "list_booking_statuses",
                        lambda ids: [{"event_id": EVENT_ID, "status": "approved",
                                      "needs_re_review_since": "2026-10-25T02:00:00+00:00"}])
    response = client.post(URL, headers=auth_headers)
    assert response.status_code == 409
    assert response.json()["detail"] == "Not ready for safety check: A venue booking needs re-review."
    assert not state["calls"]
