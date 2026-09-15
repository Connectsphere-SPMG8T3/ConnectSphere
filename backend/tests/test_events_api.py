from datetime import datetime, timedelta, timezone
from copy import deepcopy

import pytest

from app.modules.events import repository

SGT = timezone(timedelta(hours=8))
EVENT_ID = "e0000000-0000-4000-8000-000000000001"
OTHER_EVENT_ID = "e0000000-0000-4000-8000-000000000002"


DRAFT = {
    "name": "Regional Planning Workshop",
}


COMPLETE_REQUEST = {
    "name": "Regional Planning Workshop",
    "purpose": "Coordinate the regional planning workshop.",
    "description": "A full-day workshop for regional planning teams.",
    "starts_at": "2026-10-10T14:00:00+08:00",
    "ends_at": "2026-10-10T17:00:00+08:00",
    "expected_attendance": 150,
    "layout_preference": "theatre",
    "facilities_required": ["projector"],
    "accessibility_needs": "Step-free access required.",
    "preliminary_equipment_needs": "Wireless microphones.",
    "registration_enabled": False,
}


@pytest.fixture(autouse=True)
def mock_event_repository(monkeypatch, request):
    now = datetime.now(timezone.utc).isoformat()
    submitted = "submitted_event" in request.node.name or "already_submitted" in request.node.name

    def event_row(event_id, organiser_id, status="draft"):
        row = {
            "id": event_id,
            "organiser_id": organiser_id,
            "coordinator_id": None,
            "status": "under_review" if submitted else status,
            "name": "Regional Planning Workshop",
            "purpose": None,
            "description": None,
            "starts_at": None,
            "ends_at": None,
            "expected_attendance": None,
            "layout_preference": None,
            "facilities_required": [],
            "accessibility_needs": None,
            "preliminary_equipment_needs": None,
            "registration_enabled": False,
            "registration_capacity": None,
            "registration_opens_at": None,
            "registration_closes_at": None,
            "technical_readiness": "not_required",
            "submitted_at": now if submitted else None,
            "version": 1,
            "created_at": now,
            "updated_at": now,
        }
        if "valid_draft_can_be_submitted_without_coordinator_assignment" in request.node.name:
            row.update(COMPLETE_REQUEST)
        return row

    store = {
        EVENT_ID: event_row(EVENT_ID, "11111111-1111-1111-1111-111111111111"),
        OTHER_EVENT_ID: event_row(OTHER_EVENT_ID, "33333333-3333-3333-3333-333333333333"),
    }

    def list_events(organiser_id):
        return [deepcopy(row) for row in store.values() if row["organiser_id"] == organiser_id]

    def get_event(event_id):
        return deepcopy(store.get(event_id))

    def create_event(organiser_id, values):
        row = event_row("new-event", organiser_id)
        row.update(values)
        store[row["id"]] = row
        return deepcopy(row)

    def update_event(event_id, values, version):
        row = store.get(event_id)
        if row is None or row["version"] != version:
            return None
        row.update(values)
        row["version"] += 1
        return deepcopy(row)

    def delete_event(event_id):
        store.pop(event_id, None)

    def submit_event(event_id, version, submitted_at):
        row = store.get(event_id)
        if row is None or row["version"] != version:
            return None
        row.update(status="under_review", submitted_at=submitted_at.isoformat(), version=version + 1)
        return deepcopy(row)

    monkeypatch.setattr(repository, "list_events", list_events)
    monkeypatch.setattr(repository, "get_event", get_event)
    monkeypatch.setattr(repository, "create_event", create_event)
    monkeypatch.setattr(repository, "update_event", update_event)
    monkeypatch.setattr(repository, "delete_event", delete_event)
    monkeypatch.setattr(repository, "submit_event", submit_event)


class TestEventDrafts:
    def test_organiser_can_save_a_draft_with_only_a_name(
        self, client, auth_headers, authenticate_as, monkeypatch
    ):
        organiser = authenticate_as("event_organiser")

        response = client.post("/api/v1/events", json=DRAFT, headers=auth_headers)

        assert response.status_code == 201
        body = response.json()
        assert body["id"]
        assert body["organiser_id"] == organiser["id"]
        assert body["name"] == DRAFT["name"]
        assert body["status"] == "draft"

    @pytest.mark.parametrize(
        "payload",
        [
            {"name": ""},
            {"name": "ab"},
            {"name": "x" * 151},
        ],
    )
    def test_draft_name_must_be_between_three_and_150_characters(
        self, client, auth_headers, authenticate_as, payload
    ):
        authenticate_as("event_organiser")

        response = client.post("/api/v1/events", json=payload, headers=auth_headers)

        assert response.status_code == 422

    def test_only_organisers_can_create_events(self, client, auth_headers, authenticate_as):
        authenticate_as("event_coordinator")

        response = client.post("/api/v1/events", json=DRAFT, headers=auth_headers)

        assert response.status_code == 403

    def test_organiser_can_list_only_their_own_events(
        self, client, auth_headers, authenticate_as
    ):
        authenticate_as("event_organiser")

        response = client.get("/api/v1/events", headers=auth_headers)

        assert response.status_code == 200
        assert all(event["organiser_id"] == "11111111-1111-1111-1111-111111111111" for event in response.json())

    def test_organiser_can_read_their_event(self, client, auth_headers, authenticate_as):
        authenticate_as("event_organiser")

        response = client.get(f"/api/v1/events/{EVENT_ID}", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["id"] == EVENT_ID

    def test_an_organiser_cannot_read_another_organisers_event(
        self, client, auth_headers, authenticate_as
    ):
        authenticate_as("event_organiser", user_id="22222222-2222-2222-2222-222222222222")

        response = client.get(f"/api/v1/events/{OTHER_EVENT_ID}", headers=auth_headers)

        assert response.status_code == 404

    def test_draft_can_be_updated_by_its_owner(self, client, auth_headers, authenticate_as):
        authenticate_as("event_organiser")

        response = client.patch(
            f"/api/v1/events/{EVENT_ID}",
            json={"name": "Updated Workshop"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Updated Workshop"
        assert response.json()["status"] == "draft"

    def test_submitted_event_cannot_be_edited_directly(
        self, client, auth_headers, authenticate_as
    ):
        authenticate_as("event_organiser")

        response = client.patch(
            f"/api/v1/events/{EVENT_ID}",
            json={"name": "Changed after submission"},
            headers=auth_headers,
        )

        assert response.status_code == 409

    def test_submitted_event_cannot_be_discarded(self, client, auth_headers, authenticate_as):
        authenticate_as("event_organiser")

        response = client.delete(f"/api/v1/events/{EVENT_ID}", headers=auth_headers)

        assert response.status_code == 409


class TestEventSubmission:
    def test_valid_draft_can_be_submitted_without_coordinator_assignment(
        self, client, auth_headers, authenticate_as
    ):
        authenticate_as("event_organiser")

        response = client.post(f"/api/v1/events/{EVENT_ID}/submit", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == EVENT_ID
        assert body["status"] == "under_review"

    def test_submission_returns_all_missing_required_field_errors(
        self, client, auth_headers, authenticate_as
    ):
        authenticate_as("event_organiser")

        response = client.post(
            f"/api/v1/events/{EVENT_ID}/submit",
            headers=auth_headers,
        )

        assert response.status_code == 422
        detail = response.json()["detail"]
        fields = {error["loc"][-1] for error in detail}
        assert {"purpose", "starts_at", "ends_at", "expected_attendance", "layout_preference"}.issubset(fields)

    def test_submission_rejects_an_end_time_at_or_before_the_start_time(
        self, client, auth_headers, authenticate_as
    ):
        authenticate_as("event_organiser")

        response = client.post(
            f"/api/v1/events/{EVENT_ID}/submit",
            json={**COMPLETE_REQUEST, "ends_at": "2026-10-10T14:00:00+08:00"},
            headers=auth_headers,
        )

        assert response.status_code == 422
        assert "End time must be after start time." in str(response.json())

    def test_submission_rejects_a_start_time_in_the_past(
        self, client, auth_headers, authenticate_as
    ):
        authenticate_as("event_organiser")

        response = client.post(
            f"/api/v1/events/{EVENT_ID}/submit",
            json={**COMPLETE_REQUEST, "starts_at": "2020-10-10T14:00:00+08:00"},
            headers=auth_headers,
        )

        assert response.status_code == 422

    def test_submission_accepts_an_event_one_day_from_now(
        self, client, auth_headers, authenticate_as, monkeypatch
    ):
        authenticate_as("event_organiser")
        tomorrow = datetime.now(SGT) + timedelta(days=1)
        starts_at = tomorrow.replace(hour=14, minute=0, second=0, microsecond=0)
        ends_at = starts_at + timedelta(hours=3)

        response = client.post(
            f"/api/v1/events/{EVENT_ID}/submit",
            json={
                **COMPLETE_REQUEST,
                "starts_at": starts_at.isoformat(),
                "ends_at": ends_at.isoformat(),
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["status"] == "under_review"

    def test_submitting_an_already_submitted_event_returns_conflict(
        self, client, auth_headers, authenticate_as
    ):
        authenticate_as("event_organiser")

        response = client.post(f"/api/v1/events/{EVENT_ID}/submit", headers=auth_headers)

        assert response.status_code == 409

    def test_registration_settings_are_required_and_validated_when_enabled(
        self, client, auth_headers, authenticate_as
    ):
        authenticate_as("event_organiser")

        response = client.post(
            f"/api/v1/events/{EVENT_ID}/submit",
            json={
                **COMPLETE_REQUEST,
                "registration_enabled": True,
                "registration_capacity": 0,
            },
            headers=auth_headers,
        )

        assert response.status_code == 422
