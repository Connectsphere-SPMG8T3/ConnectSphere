"""CR-97 AC9: the assigned coordinator marks one event space as the primary venue.

Through the HTTP API with the repositories mocked. Which space is primary, and
the refusals made under the event's lock, are decided by
`public.set_primary_space` and proven in `supabase/verification/event_space_checks.sql`;
the fake here answers with the same outcome codes.
"""
from copy import deepcopy

import pytest

from app.modules.events import repository
from app.modules.venues import repository as venues_repository
from tests.test_event_comments_api import acting_as_another_role
from tests.test_event_review_api import event_row, EVENT_ID, COORDINATOR_ID, ORGANISER_ID

MAIN = "f0000000-0000-4000-8000-000000000001"
BREAKOUT = "f0000000-0000-4000-8000-000000000002"


def space(space_id, label, is_primary=False):
    return {"id": space_id, "event_id": EVENT_ID, "label": label, "expected_pax": None, "layout_preference": None,
            "facilities_required": [], "starts_at": None, "ends_at": None, "version": 1, "is_primary": is_primary}


@pytest.fixture()
def state(monkeypatch):
    event = event_row("planning")
    event["spaces"] = [space(MAIN, "Main hall"), space(BREAKOUT, "Breakout room")]
    state = {"event": event, "calls": [], "outcome": "ok"}
    monkeypatch.setattr(repository, "get_event", lambda event_id: deepcopy(state["event"]) if event_id == EVENT_ID else None)
    monkeypatch.setattr(venues_repository, "list_booking_statuses", lambda ids: [])
    monkeypatch.setattr(venues_repository, "get_active_booking", lambda event_id: None)

    def set_primary_space(event_id, space_id, actor_id):
        state["calls"].append((event_id, space_id, actor_id))
        if state["outcome"] == "ok":
            for row in state["event"]["spaces"]:
                row["is_primary"] = row["id"] == space_id
        return state["outcome"]

    monkeypatch.setattr(repository, "set_primary_space", set_primary_space, raising=False)
    return state


def primaries(response):
    return [s["label"] for s in response.json()["spaces"] if s["is_primary"]]


def test_the_assigned_coordinator_makes_a_space_primary(client, auth_headers, authenticate_as, state):
    authenticate_as("event_coordinator", COORDINATOR_ID)
    response = client.put(f"/api/v1/events/{EVENT_ID}/spaces/{BREAKOUT}/primary", headers=auth_headers)
    assert response.status_code == 200
    assert primaries(response) == ["Breakout room"]
    assert state["calls"] == [(EVENT_ID, BREAKOUT, COORDINATOR_ID)]


def test_the_assigned_coordinator_clears_the_primary_space(client, auth_headers, authenticate_as, state):
    state["event"]["spaces"][0]["is_primary"] = True
    authenticate_as("event_coordinator", COORDINATOR_ID)
    response = client.delete(f"/api/v1/events/{EVENT_ID}/spaces/primary", headers=auth_headers)
    assert response.status_code == 200
    assert primaries(response) == []
    assert state["calls"] == [(EVENT_ID, None, COORDINATOR_ID)]


# The database's refusals, as the coordinator reads them. Planning only: once
# the event is with the Safety Officer its arrangements are frozen.
@pytest.mark.parametrize("outcome,code,detail", [
    ("not_planning", 409, "The primary venue can only be changed while the event is in planning."),
    ("space_not_found", 404, "Event space not found."),
    ("not_assigned", 403, None),
    ("event_not_found", 404, None),
])
def test_refusals_from_the_database(client, auth_headers, authenticate_as, state, outcome, code, detail):
    state["outcome"] = outcome
    authenticate_as("event_coordinator", COORDINATOR_ID)
    response = client.put(f"/api/v1/events/{EVENT_ID}/spaces/{MAIN}/primary", headers=auth_headers)
    assert response.status_code == code
    if detail:
        assert response.json()["detail"] == detail


# Like every coordinator action: a draft is 404 to every coordinator, a
# coordinator who isn't assigned is 403, checked before the database is asked.
@pytest.mark.parametrize("condition,code", [("draft", 404), ("missing", 404), ("unassigned", 403)])
def test_the_event_relationship_is_checked_before_the_database(client, auth_headers, authenticate_as, state, condition, code):
    if condition == "draft": state["event"]["status"] = "draft"
    if condition == "missing": state["event"] = None
    if condition == "unassigned": state["event"]["coordinator_id"] = "a0000000-0000-4000-8000-000000000009"
    authenticate_as("event_coordinator", COORDINATOR_ID)
    assert client.put(f"/api/v1/events/{EVENT_ID}/spaces/{MAIN}/primary", headers=auth_headers).status_code == code
    assert client.delete(f"/api/v1/events/{EVENT_ID}/spaces/primary", headers=auth_headers).status_code == code
    assert state["calls"] == []


@pytest.mark.parametrize("role", ["event_organiser", "venue_staff", "tech_support", "attendee",
                                  "event_coordinator_lead", "safety_officer"])
def test_other_roles_are_forbidden(client, auth_headers, authenticate_as, state, role):
    authenticate_as(role, ORGANISER_ID if role == "event_organiser" else COORDINATOR_ID)
    assert client.put(f"/api/v1/events/{EVENT_ID}/spaces/{MAIN}/primary", headers=auth_headers).status_code == 403
    assert client.delete(f"/api/v1/events/{EVENT_ID}/spaces/primary", headers=auth_headers).status_code == 403
    assert state["calls"] == []


def test_the_assigned_coordinator_acting_as_another_role_is_forbidden(client, auth_headers, monkeypatch, state):  # SCRUM-76
    acting_as_another_role(monkeypatch, COORDINATOR_ID, "event_coordinator", "venue_staff")
    assert client.put(f"/api/v1/events/{EVENT_ID}/spaces/{MAIN}/primary", headers=auth_headers).status_code == 403
    assert client.delete(f"/api/v1/events/{EVENT_ID}/spaces/primary", headers=auth_headers).status_code == 403
    assert state["calls"] == []


# Q11: an event's only space is its primary venue without anyone marking it.
def test_an_events_only_space_reads_as_primary(client, auth_headers, authenticate_as, state):
    state["event"]["spaces"] = [space(MAIN, "Main hall")]
    authenticate_as("event_organiser", ORGANISER_ID)
    response = client.get(f"/api/v1/events/{EVENT_ID}", headers=auth_headers)
    assert response.status_code == 200
    assert primaries(response) == ["Main hall"]


def test_with_several_spaces_none_is_primary_until_one_is_marked(client, auth_headers, authenticate_as, state):
    authenticate_as("event_organiser", ORGANISER_ID)
    assert primaries(client.get(f"/api/v1/events/{EVENT_ID}", headers=auth_headers)) == []
