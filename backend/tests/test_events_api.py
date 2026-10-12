from datetime import datetime, time, timedelta, timezone
from copy import deepcopy

import pytest

from app.modules.events import repository

SGT = timezone(timedelta(hours=8))
EVENT_ID = "e0000000-0000-4000-8000-000000000001"
OTHER_EVENT_ID = "e0000000-0000-4000-8000-000000000002"
# Submission requires an event date after today, so fixture dates are relative.
EVENT_DAY = (datetime.now(SGT) + timedelta(days=30)).date()


def sgt_at(day, hour, minute=0, second=0):
    return datetime.combine(day, time(hour, minute, second), tzinfo=SGT).isoformat()


DRAFT = {
    "name": "Regional Planning Workshop",
}


COMPLETE_REQUEST = {
    "name": "Regional Planning Workshop",
    "purpose": "Coordinate the regional planning workshop.",
    "description": "A full-day workshop for regional planning teams.",
    "starts_at": sgt_at(EVENT_DAY, 14),
    "ends_at": sgt_at(EVENT_DAY, 17),
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
            "event_timezone": "Asia/Singapore",
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
        if request.node.name == "test_organiser_can_list_only_their_own_events":
            row["spaces"] = [
                {
                    "id": "f0000000-0000-4000-8000-000000000001",
                    "event_id": event_id,
                    "label": "Main space",
                    "expected_pax": None,
                    "layout_preference": None,
                    "facilities_required": [],
                    "starts_at": None,
                    "ends_at": None,
                    "version": 1,
                }
            ]
        if "valid_draft_can_be_submitted_without_coordinator_assignment" in request.node.name:
            row.update(COMPLETE_REQUEST)
        if event_id == EVENT_ID and (
            "clone" in request.node.name or "independent_draft" in request.node.name
        ):
            row.update(
                COMPLETE_REQUEST,
                status="confirmed",
                coordinator_id="44444444-4444-4444-4444-444444444444",
                starts_at=sgt_at(EVENT_DAY, 14),
                ends_at=sgt_at(EVENT_DAY, 17),
                submitted_at=now,
            )
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
        row = event_row("e0000000-0000-4000-8000-000000000003", organiser_id)
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

    transition_calls = []

    def transition_event(event_id, actor_id, from_statuses, to_status, expected_version,
                         reason=None, notify_type=None, notify_message=None):
        transition_calls.append({
            "event_id": event_id, "actor_id": actor_id, "from_statuses": from_statuses,
            "to_status": to_status, "expected_version": expected_version,
            "reason": reason, "notify_type": notify_type, "notify_message": notify_message,
        })
        row = store.get(event_id)
        if row is None or row["version"] != expected_version or row["status"] not in from_statuses:
            return None
        row.update(status=to_status, submitted_at=now, version=expected_version + 1)
        return deepcopy(row)

    from app.modules.venues import repository as venues_repository
    monkeypatch.setattr(venues_repository, "get_active_booking", lambda event_id: None)
    monkeypatch.setattr(repository, "list_events", list_events)
    monkeypatch.setattr(repository, "get_event", get_event)
    monkeypatch.setattr(repository, "create_event", create_event)
    monkeypatch.setattr(repository, "update_event", update_event)
    monkeypatch.setattr(repository, "delete_event", delete_event)
    monkeypatch.setattr(repository, "transition_event", transition_event)
    return {"transition_calls": transition_calls}


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

    def test_event_timezone_must_be_a_valid_iana_timezone(self, client, auth_headers, authenticate_as):
        authenticate_as("event_organiser")

        response = client.post(
            "/api/v1/events",
            json={"name": "Planning workshop", "event_timezone": "Not/A_Timezone"},
            headers=auth_headers,
        )

        assert response.status_code == 422

    def test_organiser_can_list_only_their_own_events(
        self, client, auth_headers, authenticate_as
    ):
        authenticate_as("event_organiser")

        response = client.get("/api/v1/events", headers=auth_headers)

        assert response.status_code == 200
        assert all(event["organiser_id"] == "11111111-1111-1111-1111-111111111111" for event in response.json())

    def test_organiser_can_create_an_independent_draft_from_their_event(
        self, client, auth_headers, authenticate_as
    ):
        authenticate_as("event_organiser")

        response = client.post(f"/api/v1/events/{EVENT_ID}/clone", headers=auth_headers)

        assert response.status_code == 201
        body = response.json()
        assert body["id"] != EVENT_ID
        assert body["organiser_id"] == "11111111-1111-1111-1111-111111111111"
        assert body["status"] == "draft"
        assert body["name"] == "Regional Planning Workshop"
        assert body["purpose"] == "Coordinate the regional planning workshop."
        assert body["expected_attendance"] == 150
        assert body["starts_at"] is None
        assert body["ends_at"] is None
        assert body["coordinator_id"] is None
        assert body["submitted_at"] is None

    def test_cloned_draft_can_be_edited_and_submitted_without_changing_source(
        self, client, auth_headers, authenticate_as
    ):
        authenticate_as("event_organiser")

        clone_response = client.post(f"/api/v1/events/{EVENT_ID}/clone", headers=auth_headers)
        cloned_id = clone_response.json()["id"]

        update_response = client.patch(
            f"/api/v1/events/{cloned_id}",
            json={**COMPLETE_REQUEST, "name": "Updated recurring workshop"},
            headers=auth_headers,
        )
        submit_response = client.post(f"/api/v1/events/{cloned_id}/submit", headers=auth_headers)
        source_response = client.get(f"/api/v1/events/{EVENT_ID}", headers=auth_headers)

        assert update_response.status_code == 200
        assert submit_response.status_code == 200
        assert submit_response.json()["status"] == "under_review"
        assert source_response.json()["id"] == EVENT_ID
        assert source_response.json()["name"] == "Regional Planning Workshop"
        assert source_response.json()["status"] == "confirmed"

    def test_organiser_cannot_clone_another_organisers_event(
        self, client, auth_headers, authenticate_as
    ):
        authenticate_as("event_organiser", user_id="22222222-2222-2222-2222-222222222222")

        response = client.post(f"/api/v1/events/{EVENT_ID}/clone", headers=auth_headers)

        assert response.status_code == 404

    def test_organiser_cannot_clone_a_missing_event(
        self, client, auth_headers, authenticate_as
    ):
        authenticate_as("event_organiser")

        response = client.post(
            "/api/v1/events/00000000-0000-4000-8000-000000000099/clone",
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_non_organiser_cannot_clone_an_event(
        self, client, auth_headers, authenticate_as
    ):
        authenticate_as("event_coordinator")

        response = client.post(f"/api/v1/events/{EVENT_ID}/clone", headers=auth_headers)

        assert response.status_code == 403

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
    def test_submission_uses_the_event_timezone_for_local_date_validation(
        self, client, auth_headers, authenticate_as
    ):
        authenticate_as("event_organiser")
        tomorrow_in_bangkok = datetime.now(timezone(timedelta(hours=7))) + timedelta(days=1)
        starts_at = tomorrow_in_bangkok.replace(hour=14, minute=0, second=0, microsecond=0)
        ends_at = starts_at + timedelta(hours=3)

        response = client.post(
            f"/api/v1/events/{EVENT_ID}/submit",
            json={
                **COMPLETE_REQUEST,
                "event_timezone": "Asia/Bangkok",
                "starts_at": starts_at.isoformat(),
                "ends_at": ends_at.isoformat(),
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["event_timezone"] == "Asia/Bangkok"

    def test_valid_draft_can_be_submitted_without_coordinator_assignment(
        self, client, auth_headers, authenticate_as
    ):
        authenticate_as("event_organiser")

        response = client.post(f"/api/v1/events/{EVENT_ID}/submit", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == EVENT_ID
        assert body["status"] == "under_review"

    def test_valid_draft_can_be_submitted_without_coordinator_assignment_through_transition_event(
        self, client, auth_headers, authenticate_as, mock_event_repository
    ):
        """Submission writes event_status_history (draft -> under_review) with the
        organiser as actor, so it must go through transition_event, the one path
        that records history."""
        organiser = authenticate_as("event_organiser")

        response = client.post(f"/api/v1/events/{EVENT_ID}/submit", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["submitted_at"]
        assert mock_event_repository["transition_calls"] == [{
            "event_id": EVENT_ID, "actor_id": organiser["id"], "from_statuses": ["draft"],
            "to_status": "under_review", "expected_version": 1,
            "reason": None, "notify_type": None, "notify_message": None,
        }]

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
            json={**COMPLETE_REQUEST, "ends_at": sgt_at(EVENT_DAY, 14)},
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

    def test_submission_rejects_a_future_time_on_today_date(
        self, client, auth_headers, authenticate_as
    ):
        authenticate_as("event_organiser")
        today = datetime.now(SGT).date()
        starts_at = datetime.combine(today, time(23, 59), tzinfo=SGT)
        ends_at = starts_at + timedelta(hours=1)

        response = client.post(
            f"/api/v1/events/{EVENT_ID}/submit",
            json={
                **COMPLETE_REQUEST,
                "starts_at": starts_at.isoformat(),
                "ends_at": ends_at.isoformat(),
            },
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

    def test_registration_closing_datetime_must_follow_opening_datetime(
        self, client, auth_headers, authenticate_as
    ):
        authenticate_as("event_organiser")

        response = client.post(
            f"/api/v1/events/{EVENT_ID}/submit",
            json={
                **COMPLETE_REQUEST,
                "registration_enabled": True,
                "registration_capacity": 50,
                "registration_opens_at": sgt_at(EVENT_DAY - timedelta(days=10), 9),
                "registration_closes_at": sgt_at(EVENT_DAY - timedelta(days=10), 8),
            },
            headers=auth_headers,
        )

        assert response.status_code == 422
        assert "Registration closing time must be after opening time." in str(response.json())

    def test_registration_closing_date_must_be_after_today(
        self, client, auth_headers, authenticate_as
    ):
        authenticate_as("event_organiser")
        today = datetime.now(SGT).date()

        response = client.post(
            f"/api/v1/events/{EVENT_ID}/submit",
            json={
                **COMPLETE_REQUEST,
                "registration_enabled": True,
                "registration_capacity": 50,
                "registration_opens_at": f"{today + timedelta(days=1)}T09:00:00+08:00",
                "registration_closes_at": f"{today}T18:00:00+08:00",
            },
            headers=auth_headers,
        )

        assert response.status_code == 422
        assert "Registration closing date must be after today." in str(response.json())

    def test_registration_closing_datetime_cannot_be_after_event_end(
        self, client, auth_headers, authenticate_as
    ):
        authenticate_as("event_organiser")

        response = client.post(
            f"/api/v1/events/{EVENT_ID}/submit",
            json={
                **COMPLETE_REQUEST,
                "registration_enabled": True,
                "registration_capacity": 50,
                "registration_opens_at": sgt_at(EVENT_DAY - timedelta(days=1), 9),
                "registration_closes_at": sgt_at(EVENT_DAY, 18, 0, 1),
            },
            headers=auth_headers,
        )

        assert response.status_code == 422
        assert "Registration closing time cannot be after the event end time." in str(response.json())

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
