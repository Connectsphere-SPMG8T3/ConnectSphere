"""SCRUM-45 equipment request lines, through the HTTP API with the repositories mocked."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.modules.equipment import repository
from app.modules.events import repository as events_repository
from tests.conftest import make_table_mock

COORDINATOR_ID = "a0000000-0000-4000-8000-000000000002"
OTHER_COORDINATOR_ID = "a0000000-0000-4000-8000-000000000009"
TECH_ID = "a0000000-0000-4000-8000-000000000004"
EVENT_ID = "e0000000-0000-4000-8000-000000000202"
PROJECTOR_ID = "b0000000-0000-4000-8000-000000000001"
MIC_ID = "b0000000-0000-4000-8000-000000000002"
RETIRED_ID = "b0000000-0000-4000-8000-000000000003"
UNKNOWN_ID = "b0000000-0000-4000-8000-0000000000ff"
NOT_PLANNING = ["safety_review", "submitted", "under_review", "confirmed", "rejected", "cancelled", "completed"]
SUBMIT_URL = "/api/v1/equipment/requests"
EVENT_URL = f"/api/v1/equipment/requests/event/{EVENT_ID}"
PENDING_URL = "/api/v1/equipment/requests/pending"
QUEUE_URL = "/api/v1/equipment/requests"
CATALOGUE_URL = "/api/v1/equipment/catalogue"

CATALOGUE = [
    {"id": PROJECTOR_ID, "name": "Projector", "equipment_type": "AV", "total_quantity": 20, "status": "active"},
    {"id": MIC_ID, "name": "Wireless microphone", "equipment_type": "Audio", "total_quantity": 8, "status": "maintenance"},
    {"id": RETIRED_ID, "name": "Overhead projector", "equipment_type": "AV", "total_quantity": 2, "status": "retired"},
]


def event_row(status="planning", coordinator_id=COORDINATOR_ID, event_id=EVENT_ID, name="Year-End Dinner"):
    now = datetime.now(timezone.utc).isoformat()
    starts = datetime.now(timezone.utc) + timedelta(days=30)
    return {
        "id": event_id, "organiser_id": "a0000000-0000-4000-8000-000000000001",
        "coordinator_id": coordinator_id, "status": status, "event_timezone": "Asia/Singapore",
        "name": name, "purpose": "Dinner", "description": None,
        "starts_at": starts.isoformat(), "ends_at": (starts + timedelta(hours=3)).isoformat(),
        "expected_attendance": 80, "layout_preference": "banquet", "facilities_required": [],
        "accessibility_needs": None, "preliminary_equipment_needs": "Projector and mics",
        "registration_enabled": False, "registration_capacity": None,
        "registration_opens_at": None, "registration_closes_at": None,
        "technical_readiness": "pending", "submitted_at": now, "version": 4,
        "created_at": now, "updated_at": now,
    }


@pytest.fixture()
def store(monkeypatch):
    """In-memory events, catalogue and request lines; `submit_request` mimics the
    database function: re-checks the event, then writes the whole batch or nothing."""
    state = {"events": {EVENT_ID: event_row()}, "lines": [], "calls": [], "outcome": None}

    def list_catalogue(equipment_ids=None):
        rows = [row for row in CATALOGUE if row["status"] != "retired"]
        if equipment_ids is not None:
            wanted = {str(i) for i in equipment_ids}
            rows = [row for row in rows if row["id"] in wanted]
        return deepcopy(rows)

    def submit_request(event_id, actor_id, items):
        state["calls"].append({"event_id": event_id, "actor_id": actor_id, "items": deepcopy(items)})
        if state["outcome"]:
            return state["outcome"], []
        submission_id = f"5{len(state['calls']):07d}-0000-4000-8000-000000000000"
        written = []
        for item in items:
            row = {
                "id": f"9{len(state['lines']):07d}-0000-4000-8000-000000000000",
                "submission_id": submission_id, "event_id": event_id,
                "equipment_id": item["equipment_id"], "quantity": item["quantity"],
                "technical_requirements": item["technical_requirements"], "status": "pending",
                "requested_by": actor_id, "created_at": "2026-10-06T02:00:00+00:00",
            }
            state["lines"].append(row)
            written.append(deepcopy(row))
        return "ok", written

    names = {row["id"]: row["name"] for row in CATALOGUE}
    types = {row["id"]: row["equipment_type"] for row in CATALOGUE}

    def _embedded(row):
        event = state["events"].get(row["event_id"], {})
        return {
            **deepcopy(row),
            "equipment": {"name": names[row["equipment_id"]], "equipment_type": types[row["equipment_id"]]},
            "requester": {"id": row["requested_by"], "full_name": "Marcus Lim"},
            "event": {"name": event.get("name"), "starts_at": event.get("starts_at"), "status": event.get("status")},
        }

    def list_event_requests(event_id):
        return [_embedded(row) for row in state["lines"] if row["event_id"] == event_id]

    def list_requests(statuses=None):
        state["queue_statuses"] = statuses
        return [_embedded(row) for row in state["lines"] if statuses is None or row["status"] in statuses]

    monkeypatch.setattr(events_repository, "get_event", lambda event_id: deepcopy(state["events"].get(event_id)))
    monkeypatch.setattr(repository, "list_catalogue", list_catalogue)
    monkeypatch.setattr(repository, "submit_request", submit_request)
    monkeypatch.setattr(repository, "list_event_requests", list_event_requests)
    monkeypatch.setattr(repository, "list_requests", list_requests)
    monkeypatch.setattr(repository, "get_event_technical", lambda event_id: None)
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


def item(equipment_id=PROJECTOR_ID, quantity=4, technical_requirements=None):
    body = {"equipment_id": equipment_id, "quantity": quantity}
    if technical_requirements is not None:
        body["technical_requirements"] = technical_requirements
    return body


def submit(client, auth_headers, items=None, event_id=EVENT_ID):
    payload = {"event_id": event_id, "items": [item()] if items is None else items}
    return client.post(SUBMIT_URL, json=payload, headers=auth_headers)


class TestCatalogue:
    @pytest.mark.parametrize("role", ["event_coordinator", "tech_support"])
    def test_coordinators_and_tech_support_read_the_catalogue(self, client, auth_headers, act_as, store, role):
        act_as(role, COORDINATOR_ID)

        response = client.get(CATALOGUE_URL, headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["items"] == [
            {"equipment_id": PROJECTOR_ID, "name": "Projector", "equipment_type": "AV", "total_quantity": 20},
            {"equipment_id": MIC_ID, "name": "Wireless microphone", "equipment_type": "Audio", "total_quantity": 8},
        ]

    @pytest.mark.parametrize("role", ["event_organiser", "venue_staff", "attendee"])
    def test_other_roles_cannot_read_it(self, client, auth_headers, act_as, store, role):
        act_as(role, COORDINATOR_ID)

        assert client.get(CATALOGUE_URL, headers=auth_headers).status_code == 403


class TestSubmit:
    def test_the_assigned_coordinator_submits_lines_that_become_pending(self, client, auth_headers, act_as, store):
        act_as("event_coordinator", COORDINATOR_ID)

        response = submit(client, auth_headers, [
            item(PROJECTOR_ID, 4, "  1080p, HDMI to the lectern  "),
            item(MIC_ID, 2),
        ])

        assert response.status_code == 201
        lines = response.json()["lines"]
        assert [(l["equipment_name"], l["quantity"], l["status"]) for l in lines] == [
            ("Projector", 4, "pending"), ("Wireless microphone", 2, "pending"),
        ]
        assert lines[0]["technical_requirements"] == "1080p, HDMI to the lectern"
        assert lines[1]["technical_requirements"] is None
        assert lines[0]["submission_id"] == lines[1]["submission_id"]
        [call] = store["calls"]
        assert call["actor_id"] == COORDINATOR_ID
        assert call["event_id"] == EVENT_ID

    def test_the_whole_batch_goes_to_the_database_in_one_call(self, client, auth_headers, act_as, store):
        act_as("event_coordinator", COORDINATOR_ID)

        submit(client, auth_headers, [item(PROJECTOR_ID, 1), item(MIC_ID, 1)])

        assert len(store["calls"]) == 1
        assert len(store["calls"][0]["items"]) == 2

    def test_technical_requirements_of_1000_characters_are_kept(self, client, auth_headers, act_as, store):
        act_as("event_coordinator", COORDINATOR_ID)

        response = submit(client, auth_headers, [item(technical_requirements="x" * 1000)])

        assert response.status_code == 201
        assert len(response.json()["lines"][0]["technical_requirements"]) == 1000

    def test_technical_requirements_over_1000_characters_are_refused(self, client, auth_headers, act_as, store):
        act_as("event_coordinator", COORDINATOR_ID)

        assert submit(client, auth_headers, [item(technical_requirements="x" * 1001)]).status_code == 422
        assert store["calls"] == []

    @pytest.mark.parametrize("text", ["", "   ", "\n\t"])
    def test_blank_technical_requirements_are_stored_as_none(self, client, auth_headers, act_as, store, text):
        act_as("event_coordinator", COORDINATOR_ID)

        response = submit(client, auth_headers, [item(technical_requirements=text)])

        assert response.status_code == 201
        assert store["calls"][0]["items"][0]["technical_requirements"] is None

    @pytest.mark.parametrize("quantity", [0, -1, 2.5, "2", None, True])
    def test_quantity_must_be_a_whole_number_of_at_least_one(self, client, auth_headers, act_as, store, quantity):
        act_as("event_coordinator", COORDINATOR_ID)

        assert submit(client, auth_headers, [item(quantity=quantity)]).status_code == 422
        assert store["calls"] == []

    def test_a_quantity_of_one_is_accepted(self, client, auth_headers, act_as, store):
        act_as("event_coordinator", COORDINATOR_ID)

        assert submit(client, auth_headers, [item(quantity=1)]).status_code == 201

    def test_a_submission_needs_at_least_one_item(self, client, auth_headers, act_as, store):
        act_as("event_coordinator", COORDINATOR_ID)

        assert submit(client, auth_headers, []).status_code == 422
        assert store["calls"] == []

    def test_a_quantity_above_total_inventory_is_still_accepted(self, client, auth_headers, act_as, store):
        """EQ-R1: the warning is the client's; the request still goes through."""
        act_as("event_coordinator", COORDINATOR_ID)

        response = submit(client, auth_headers, [item(PROJECTOR_ID, 21)])

        assert response.status_code == 201
        assert response.json()["lines"][0]["quantity"] == 21

    def test_the_same_item_twice_in_one_submission_is_refused(self, client, auth_headers, act_as, store):
        act_as("event_coordinator", COORDINATOR_ID)

        response = submit(client, auth_headers, [item(PROJECTOR_ID, 1), item(PROJECTOR_ID, 2)])

        assert response.status_code == 422
        assert store["calls"] == []

    def test_more_than_50_items_are_refused(self, client, auth_headers, act_as, store):
        act_as("event_coordinator", COORDINATOR_ID)

        items = [item(f"b0000000-0000-4000-8000-{n:012d}", 1) for n in range(51)]

        assert submit(client, auth_headers, items).status_code == 422

    @pytest.mark.parametrize("equipment_id", [UNKNOWN_ID, RETIRED_ID])
    def test_an_item_outside_the_catalogue_refuses_the_whole_batch(self, client, auth_headers, act_as, store, equipment_id):
        act_as("event_coordinator", COORDINATOR_ID)

        response = submit(client, auth_headers, [item(PROJECTOR_ID, 1), item(equipment_id, 1)])

        assert response.status_code == 422
        assert store["calls"] == []
        assert store["lines"] == []

    def test_the_database_refusing_an_item_writes_nothing(self, client, auth_headers, act_as, store):
        """An item retired between the API's check and the insert."""
        act_as("event_coordinator", COORDINATOR_ID)
        store["outcome"] = "unknown_equipment"

        response = submit(client, auth_headers)

        assert response.status_code == 422
        assert store["lines"] == []


class TestWhoAndWhen:
    def test_a_coordinator_not_assigned_to_the_event_is_forbidden(self, client, auth_headers, act_as, store):
        act_as("event_coordinator", OTHER_COORDINATOR_ID)

        response = submit(client, auth_headers)

        assert response.status_code == 403
        assert store["calls"] == []

    def test_an_unassigned_event_is_forbidden(self, client, auth_headers, act_as, store):
        store["events"][EVENT_ID]["coordinator_id"] = None
        act_as("event_coordinator", COORDINATOR_ID)

        assert submit(client, auth_headers).status_code == 403

    def test_a_missing_event_is_not_found(self, client, auth_headers, act_as, store):
        act_as("event_coordinator", COORDINATOR_ID)

        response = submit(client, auth_headers, event_id="e0000000-0000-4000-8000-0000000000ff")

        assert response.status_code == 404

    def test_a_draft_is_not_found(self, client, auth_headers, act_as, store):
        store["events"][EVENT_ID]["status"] = "draft"
        act_as("event_coordinator", COORDINATOR_ID)

        assert submit(client, auth_headers).status_code == 404

    def test_a_returned_event_says_why(self, client, auth_headers, act_as, store):
        store["events"][EVENT_ID]["status"] = "returned"
        act_as("event_coordinator", COORDINATOR_ID)

        response = submit(client, auth_headers)

        assert response.status_code == 409
        assert "returned for amendment" in response.json()["detail"]
        assert store["calls"] == []

    @pytest.mark.parametrize("status", NOT_PLANNING)
    def test_only_a_planning_event_takes_requests(self, client, auth_headers, act_as, store, status):
        store["events"][EVENT_ID]["status"] = status
        act_as("event_coordinator", COORDINATOR_ID)

        response = submit(client, auth_headers)

        assert response.status_code == 409
        assert "planning" in response.json()["detail"]
        assert store["calls"] == []

    @pytest.mark.parametrize(("outcome", "code"), [
        ("not_planning", 409), ("returned", 409), ("not_assigned", 403), ("event_not_found", 404),
    ])
    def test_the_database_recheck_under_the_lock_is_honoured(self, client, auth_headers, act_as, store, outcome, code):
        """The event changed between the API's check and the function's lock."""
        act_as("event_coordinator", COORDINATOR_ID)
        store["outcome"] = outcome

        assert submit(client, auth_headers).status_code == code

    @pytest.mark.parametrize("role", ["event_organiser", "venue_staff", "tech_support", "attendee"])
    def test_other_roles_cannot_submit(self, client, auth_headers, act_as, store, role):
        act_as(role, COORDINATOR_ID)

        assert submit(client, auth_headers).status_code == 403
        assert store["calls"] == []

    def test_holding_coordinator_but_acting_as_tech_support_cannot_submit(self, client, auth_headers, monkeypatch, store):
        acting_as_another_role(monkeypatch, COORDINATOR_ID, holds="event_coordinator", acts_as="tech_support")

        assert submit(client, auth_headers).status_code == 403
        assert store["calls"] == []


class TestCoordinatorSeesTheLines:
    def test_the_assigned_coordinator_sees_the_events_lines(self, client, auth_headers, act_as, store):
        act_as("event_coordinator", COORDINATOR_ID)
        submit(client, auth_headers, [item(PROJECTOR_ID, 4, "HDMI"), item(MIC_ID, 2)])

        response = client.get(EVENT_URL, headers=auth_headers)

        assert response.status_code == 200
        lines = response.json()["lines"]
        assert [(l["equipment_name"], l["quantity"], l["status"], l["technical_requirements"]) for l in lines] == [
            ("Projector", 4, "pending", "HDMI"), ("Wireless microphone", 2, "pending", None),
        ]
        assert lines[0]["requested_by"] == {"id": COORDINATOR_ID, "full_name": "Marcus Lim"}

    def test_another_coordinator_is_forbidden(self, client, auth_headers, act_as, store):
        act_as("event_coordinator", OTHER_COORDINATOR_ID)

        assert client.get(EVENT_URL, headers=auth_headers).status_code == 403

    @pytest.mark.parametrize("role", ["event_organiser", "venue_staff", "tech_support", "attendee"])
    def test_other_roles_cannot_read_an_events_lines_here(self, client, auth_headers, act_as, store, role):
        act_as(role, COORDINATOR_ID)

        assert client.get(EVENT_URL, headers=auth_headers).status_code == 403


class TestTechSupportQueue:
    def test_tech_support_see_pending_lines_with_their_technical_requirements(self, client, auth_headers, act_as, store):
        act_as("event_coordinator", COORDINATOR_ID)
        submit(client, auth_headers, [item(PROJECTOR_ID, 4, "HDMI to the lectern")])
        act_as("tech_support", TECH_ID)

        response = client.get(PENDING_URL, headers=auth_headers)

        assert response.status_code == 200
        [line] = response.json()["lines"]
        assert line["equipment_name"] == "Projector"
        assert line["quantity"] == 4
        assert line["status"] == "pending"
        assert line["technical_requirements"] == "HDMI to the lectern"
        assert line["event_id"] == EVENT_ID
        assert line["event_name"] == "Year-End Dinner"
        assert line["event_starts_at"]
        assert line["requested_by"] == {"id": COORDINATOR_ID, "full_name": "Marcus Lim"}

    @pytest.mark.parametrize("status", ["rejected", "cancelled", "completed"])
    def test_lines_on_a_closed_event_are_left_out(self, client, auth_headers, act_as, store, status):
        act_as("event_coordinator", COORDINATOR_ID)
        submit(client, auth_headers)
        store["events"][EVENT_ID]["status"] = status
        act_as("tech_support", TECH_ID)

        assert client.get(PENDING_URL, headers=auth_headers).json()["lines"] == []

    def test_lines_are_ordered_by_event_date_then_submission(self, client, auth_headers, act_as, store):
        later_id = "e0000000-0000-4000-8000-000000000299"
        later = event_row(event_id=later_id, name="Later Event")
        later["starts_at"] = (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()
        store["events"][later_id] = later
        act_as("event_coordinator", COORDINATOR_ID)
        submit(client, auth_headers, [item(MIC_ID, 1)], event_id=later_id)
        submit(client, auth_headers, [item(PROJECTOR_ID, 1)])
        act_as("tech_support", TECH_ID)

        names = [l["event_name"] for l in client.get(PENDING_URL, headers=auth_headers).json()["lines"]]

        assert names == ["Year-End Dinner", "Later Event"]

    @pytest.mark.parametrize("role", ["event_organiser", "event_coordinator", "venue_staff", "attendee"])
    def test_only_tech_support_see_the_queue(self, client, auth_headers, act_as, store, role):
        act_as(role, COORDINATOR_ID)

        assert client.get(PENDING_URL, headers=auth_headers).status_code == 403

    def test_holding_tech_support_but_acting_as_coordinator_cannot_see_the_queue(self, client, auth_headers, monkeypatch, store):
        acting_as_another_role(monkeypatch, TECH_ID, holds="tech_support", acts_as="event_coordinator")

        assert client.get(PENDING_URL, headers=auth_headers).status_code == 403


class TestTechSupportRequestList:
    """Every line on an open event, for tech support's requests page, whatever its
    status, so resolved lines stay available for reference (as venue staff's)."""

    def test_every_status_is_listed_with_the_equipment_type(self, client, auth_headers, act_as, store):
        act_as("event_coordinator", COORDINATOR_ID)
        submit(client, auth_headers, [item(PROJECTOR_ID, 1), item(MIC_ID, 2)])
        store["lines"][1]["status"] = "reserved"
        act_as("tech_support", TECH_ID)

        response = client.get(QUEUE_URL, headers=auth_headers)

        assert response.status_code == 200
        lines = response.json()["lines"]
        assert {(l["equipment_name"], l["equipment_type"], l["status"]) for l in lines} == {
            ("Projector", "AV", "pending"), ("Wireless microphone", "Audio", "reserved"),
        }
        assert store["queue_statuses"] is None

    def test_lines_on_a_closed_event_are_left_out(self, client, auth_headers, act_as, store):
        act_as("event_coordinator", COORDINATOR_ID)
        submit(client, auth_headers)
        store["events"][EVENT_ID]["status"] = "completed"
        act_as("tech_support", TECH_ID)

        assert client.get(QUEUE_URL, headers=auth_headers).json()["lines"] == []

    def test_lines_on_an_event_in_preparation_stay_listed(self, client, auth_headers, act_as, store):
        """D73: tech support reach the event from here to keep recording its preparation (CR-110)."""
        act_as("event_coordinator", COORDINATOR_ID)
        submit(client, auth_headers)
        store["lines"][0]["status"] = "reserved"
        store["events"][EVENT_ID]["status"] = "preparation"
        act_as("tech_support", TECH_ID)

        lines = client.get(QUEUE_URL, headers=auth_headers).json()["lines"]

        assert [line["event_id"] for line in lines] == [EVENT_ID]

    def test_the_pending_queue_asks_only_for_waiting_lines(self, client, auth_headers, act_as, store):
        act_as("tech_support", TECH_ID)

        client.get(PENDING_URL, headers=auth_headers)

        assert store["queue_statuses"] == ["pending", "re_review"]

    @pytest.mark.parametrize("role", ["event_organiser", "event_coordinator", "venue_staff", "attendee"])
    def test_only_tech_support_see_the_list(self, client, auth_headers, act_as, store, role):
        act_as(role, COORDINATOR_ID)

        assert client.get(QUEUE_URL, headers=auth_headers).status_code == 403


def test_safety_review_keeps_pending_equipment_visible(client, auth_headers, act_as, store):
    """SCRUM-82: keep the technical queue open during safety review."""
    act_as("event_coordinator", COORDINATOR_ID)
    submit(client, auth_headers, [item(PROJECTOR_ID, 1)])
    store["events"][EVENT_ID]["status"] = "safety_review"
    act_as("tech_support", TECH_ID)
    assert len(client.get(PENDING_URL, headers=auth_headers).json()["lines"]) == 1
