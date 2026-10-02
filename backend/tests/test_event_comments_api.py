"""SCRUM-61 event comments, through the HTTP API with the repository mocked."""

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
OPEN_STATUSES = ["submitted", "under_review", "returned", "planning", "confirmed"]
CLOSED_STATUSES = ["rejected", "cancelled", "completed"]
URL = f"/api/v1/events/{EVENT_ID}/comments"


def event_row(status="under_review", coordinator_id=COORDINATOR_ID):
    now = datetime.now(timezone.utc).isoformat()
    starts = datetime.now(timezone.utc) + timedelta(days=30)
    return {
        "id": EVENT_ID, "organiser_id": ORGANISER_ID, "coordinator_id": coordinator_id,
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
def thread(monkeypatch):
    """An in-memory event and comment list; `add_comment` mimics the function's guard."""
    state = {"event": event_row(), "comments": [], "calls": [], "refuse": False}

    def add_comment(event_id, author_id, body, *, notify_message):
        state["calls"].append({"event_id": event_id, "author_id": author_id, "body": body,
                               "notify_message": notify_message})
        if state["refuse"] or state["event"]["status"] not in OPEN_STATUSES:
            return None
        row = {"id": f"c{len(state['comments']) + 1}", "event_id": event_id, "author_id": author_id,
               "body": body, "created_at": "2026-10-02T03:00:00+00:00"}
        state["comments"].append(row)
        return deepcopy(row)

    def list_comments(event_id):
        names = {ORGANISER_ID: "Olivia Tan", COORDINATOR_ID: "Marcus Lim"}
        return [{**row, "author": {"id": row["author_id"], "full_name": names[row["author_id"]]}}
                for row in deepcopy(state["comments"])]

    monkeypatch.setattr(repository, "get_event", lambda event_id: deepcopy(state["event"]) if event_id == EVENT_ID else None)
    monkeypatch.setattr(repository, "add_comment", add_comment)
    monkeypatch.setattr(repository, "list_comments", list_comments)
    return state


@pytest.fixture()
def act_as(authenticate_as):
    def _act_as(role, user_id):
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


def post(client, auth_headers, body="Can we recce the hall on Friday?"):
    return client.post(URL, json={"body": body}, headers=auth_headers)


def call(client, method, auth_headers):
    if method == "post":
        return client.post(URL, json={"body": "hi"}, headers=auth_headers)
    return client.get(URL, headers=auth_headers)


class TestPost:
    def test_the_owning_organiser_posts_and_the_coordinator_is_told(self, client, auth_headers, act_as, thread):
        act_as("event_organiser", ORGANISER_ID)

        response = post(client, auth_headers, body="  Can we recce the hall on Friday?  ")

        assert response.status_code == 201
        body = response.json()
        assert body["body"] == "Can we recce the hall on Friday?"
        assert body["author"] == {"id": ORGANISER_ID, "full_name": "Olivia Tan", "role": "event_organiser"}
        assert body["created_at"]
        [sent] = thread["calls"]
        assert sent["author_id"] == ORGANISER_ID
        assert sent["notify_message"] == 'The organiser commented on "Partner Summit".'

    def test_the_assigned_coordinator_posts_and_the_organiser_is_told(self, client, auth_headers, act_as, thread):
        act_as("event_coordinator", COORDINATOR_ID)

        response = post(client, auth_headers, body="Booked for 3pm.")

        assert response.status_code == 201
        assert response.json()["author"]["role"] == "event_coordinator"
        assert thread["calls"][0]["notify_message"] == 'Your coordinator commented on "Partner Summit".'

    @pytest.mark.parametrize("status", OPEN_STATUSES)
    def test_every_open_status_accepts_a_comment(self, client, auth_headers, act_as, thread, status):
        thread["event"]["status"] = status
        act_as("event_organiser", ORGANISER_ID)

        assert post(client, auth_headers).status_code == 201

    @pytest.mark.parametrize("body", ["", "   ", "\n\t "])
    def test_a_blank_comment_is_refused(self, client, auth_headers, act_as, thread, body):
        act_as("event_organiser", ORGANISER_ID)

        assert post(client, auth_headers, body=body).status_code == 422
        assert thread["calls"] == []

    def test_a_missing_body_is_refused(self, client, auth_headers, act_as, thread):
        act_as("event_organiser", ORGANISER_ID)

        assert client.post(URL, json={}, headers=auth_headers).status_code == 422
        assert thread["calls"] == []

    def test_a_comment_is_capped_at_1000_characters(self, client, auth_headers, act_as, thread):
        act_as("event_organiser", ORGANISER_ID)

        assert post(client, auth_headers, body="x" * 1001).status_code == 422
        assert post(client, auth_headers, body="x" * 1000).status_code == 201

    @pytest.mark.parametrize("status", CLOSED_STATUSES)
    def test_a_closed_event_refuses_new_comments(self, client, auth_headers, act_as, thread, status):
        thread["event"]["status"] = status
        act_as("event_coordinator", COORDINATOR_ID)

        response = post(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == f"Comments are closed for a {status} event."
        assert thread["calls"] == []

    def test_a_draft_refuses_comments_for_its_organiser(self, client, auth_headers, act_as, thread):
        thread["event"]["status"] = "draft"
        act_as("event_organiser", ORGANISER_ID)

        response = post(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == "Comments open once the request is submitted."

    def test_a_comment_racing_a_close_is_a_conflict(self, client, auth_headers, act_as, thread):
        thread["refuse"] = True  # the event closed after the service read it
        act_as("event_organiser", ORGANISER_ID)

        response = post(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == "Comments are closed for this event. Reload."

    def test_an_unassigned_event_still_takes_the_organisers_comment(self, client, auth_headers, act_as, thread):
        thread["event"]["coordinator_id"] = None
        act_as("event_organiser", ORGANISER_ID)

        assert post(client, auth_headers).status_code == 201


class TestRead:
    def test_both_parties_read_the_thread_oldest_first(self, client, auth_headers, act_as, thread):
        act_as("event_organiser", ORGANISER_ID)
        post(client, auth_headers, body="First")
        act_as("event_coordinator", COORDINATOR_ID)
        post(client, auth_headers, body="Second")

        for role, user_id in (("event_organiser", ORGANISER_ID), ("event_coordinator", COORDINATOR_ID)):
            act_as(role, user_id)
            response = client.get(URL, headers=auth_headers)
            assert response.status_code == 200
            comments = response.json()["comments"]
            assert [c["body"] for c in comments] == ["First", "Second"]
            assert [c["author"]["role"] for c in comments] == ["event_organiser", "event_coordinator"]

    @pytest.mark.parametrize("status", CLOSED_STATUSES)
    def test_a_closed_events_thread_stays_readable(self, client, auth_headers, act_as, thread, status):
        thread["event"]["status"] = status
        act_as("event_coordinator", COORDINATOR_ID)

        assert client.get(URL, headers=auth_headers).status_code == 200

    def test_a_draft_has_an_empty_thread_for_its_organiser(self, client, auth_headers, act_as, thread):
        thread["event"]["status"] = "draft"
        act_as("event_organiser", ORGANISER_ID)

        response = client.get(URL, headers=auth_headers)

        assert response.status_code == 200
        assert response.json() == {"comments": []}

    def test_a_deleted_authors_comment_keeps_its_place(self, client, auth_headers, act_as, thread, monkeypatch):
        monkeypatch.setattr(repository, "list_comments", lambda event_id: [
            {"id": "c1", "body": "Old note", "created_at": "2026-10-02T03:00:00+00:00", "author_id": None, "author": None}])
        act_as("event_organiser", ORGANISER_ID)

        [comment] = client.get(URL, headers=auth_headers).json()["comments"]

        assert comment["author"] is None
        assert comment["body"] == "Old note"

    def test_a_former_coordinators_comment_has_no_role(self, client, auth_headers, act_as, thread):
        act_as("event_coordinator", COORDINATOR_ID)
        post(client, auth_headers, body="Handing over")
        thread["event"]["coordinator_id"] = OTHER_COORDINATOR_ID
        act_as("event_organiser", ORGANISER_ID)

        [comment] = client.get(URL, headers=auth_headers).json()["comments"]

        assert comment["author"]["role"] is None


class TestAccess:
    @pytest.mark.parametrize("method", ["get", "post"])
    def test_another_organiser_gets_not_found(self, client, auth_headers, act_as, thread, method):
        act_as("event_organiser", OTHER_ORGANISER_ID)

        assert call(client, method, auth_headers).status_code == 404
        assert thread["calls"] == []

    @pytest.mark.parametrize("method", ["get", "post"])
    def test_a_coordinator_who_is_not_assigned_is_forbidden(self, client, auth_headers, act_as, thread, method):
        act_as("event_coordinator", OTHER_COORDINATOR_ID)

        assert call(client, method, auth_headers).status_code == 403
        assert thread["calls"] == []

    @pytest.mark.parametrize("method", ["get", "post"])
    def test_every_coordinator_gets_not_found_on_a_draft(self, client, auth_headers, act_as, thread, method):
        thread["event"]["status"] = "draft"
        act_as("event_coordinator", COORDINATOR_ID)

        assert call(client, method, auth_headers).status_code == 404

    @pytest.mark.parametrize("role", ["venue_staff", "tech_support", "attendee"])
    @pytest.mark.parametrize("method", ["get", "post"])
    def test_other_roles_are_forbidden(self, client, auth_headers, act_as, thread, role, method):
        act_as(role, "a0000000-0000-4000-8000-000000000003")

        assert call(client, method, auth_headers).status_code == 403
        assert thread["calls"] == []

    @pytest.mark.parametrize("method", ["get", "post"])
    def test_a_coordinator_acting_as_venue_staff_is_forbidden(self, client, auth_headers, monkeypatch, thread, method):
        acting_as_another_role(monkeypatch, COORDINATOR_ID, holds="event_coordinator", acts_as="venue_staff")

        assert call(client, method, auth_headers).status_code == 403
        assert thread["calls"] == []

    @pytest.mark.parametrize("method", ["get", "post"])
    def test_an_organiser_acting_as_attendee_is_forbidden(self, client, auth_headers, monkeypatch, thread, method):
        acting_as_another_role(monkeypatch, ORGANISER_ID, holds="event_organiser", acts_as="attendee")

        assert call(client, method, auth_headers).status_code == 403
        assert thread["calls"] == []
