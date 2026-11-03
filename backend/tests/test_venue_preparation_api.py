"""SCRUM-109 venue preparation progress through the HTTP API."""

from copy import deepcopy

import pytest

from app.modules.venues import repository

BOOKING_ID = "e0000000-0000-4000-8000-000000000301"
PREPARATION_URL = f"/api/v1/venue-bookings/{BOOKING_ID}/preparation"
STAFF_ID = "a0000000-0000-4000-8000-000000000004"
OTHER_ROLES = [
    "event_organiser",
    "event_coordinator",
    "event_coordinator_lead",
    "tech_support",
    "safety_officer",
    "attendee",
]


@pytest.fixture()
def preparation(monkeypatch):
    state = {"row": {"outcome": "ok", "stage": "in_progress", "note": "Doors checked",
                     "updated_at": "2026-11-03T08:00:00+00:00", "event_status": "preparation"},
             "calls": []}

    def set_preparation(*args):
        state["calls"].append(args)
        return deepcopy(state["row"])

    monkeypatch.setattr(repository, "set_venue_preparation", set_preparation)
    return state


class TestVenuePreparation:
    def test_staff_can_update_a_booking_with_an_internal_note(
        self, client, auth_headers, authenticate_as, preparation
    ):
        authenticate_as("venue_staff", user_id=STAFF_ID)

        response = client.put(
            PREPARATION_URL,
            headers=auth_headers,
            json={"stage": "in_progress", "note": "  Doors checked  "},
        )

        assert response.status_code == 200
        assert response.json()["stage"] == "in_progress"
        assert response.json()["note"] == "Doors checked"
        assert preparation["calls"] == [(BOOKING_ID, STAFF_ID, "in_progress", "Doors checked")]

    @pytest.mark.parametrize("stage", ["not_started", "in_preparation", "in_progress", "completed"])
    def test_all_preparation_stages_are_valid(
        self, client, auth_headers, authenticate_as, preparation, stage
    ):
        authenticate_as("venue_staff", user_id=STAFF_ID)

        assert client.put(PREPARATION_URL, headers=auth_headers, json={"stage": stage}).status_code == 200

    def test_locked_event_is_rejected(self, client, auth_headers, authenticate_as, preparation):
        authenticate_as("venue_staff", user_id=STAFF_ID)
        preparation["row"] = {"outcome": "not_confirmed", "event_status": "planning"}

        response = client.put(PREPARATION_URL, headers=auth_headers, json={"stage": "completed"})

        assert response.status_code == 409
        assert "confirmed" in response.json()["detail"].lower()

    @pytest.mark.parametrize("role", OTHER_ROLES)
    def test_every_other_active_role_is_forbidden(
        self, client, auth_headers, authenticate_as, preparation, role
    ):
        authenticate_as(role)

        response = client.put(PREPARATION_URL, headers=auth_headers, json={"stage": "completed"})

        assert response.status_code == 403
        assert preparation["calls"] == []

    def test_invalid_stage_is_rejected_before_the_repository(
        self, client, auth_headers, authenticate_as, preparation
    ):
        authenticate_as("venue_staff", user_id=STAFF_ID)

        response = client.put(PREPARATION_URL, headers=auth_headers, json={"stage": "ready"})

        assert response.status_code == 422
        assert preparation["calls"] == []
