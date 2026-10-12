"""CR-98 event-space request CRUD with event-level requirements."""

from copy import deepcopy
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.modules.events import repository, service
from app.modules.events.service import _validate_submission

EVENT_ID = "e0000000-0000-4000-8000-000000000201"
ORGANISER_ID = "a0000000-0000-4000-8000-000000000001"
SPACE_ID = "f0000000-0000-4000-8000-000000000001"


def event_row(status="draft"):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": EVENT_ID,
        "organiser_id": ORGANISER_ID,
        "coordinator_id": None,
        "status": status,
        "name": "Partner Summit",
        "event_timezone": "Asia/Singapore",
        "purpose": None,
        "description": None,
        "starts_at": "2026-10-20T09:00:00+08:00",
        "ends_at": "2026-10-20T18:00:00+08:00",
        "expected_attendance": 100,
        "layout_preference": "theatre",
        "facilities_required": [],
        "accessibility_needs": None,
        "preliminary_equipment_needs": None,
        "registration_enabled": False,
        "registration_capacity": None,
        "registration_opens_at": None,
        "registration_closes_at": None,
        "technical_readiness": "not_required",
        "submitted_at": None,
        "version": 1,
        "created_at": now,
        "updated_at": now,
    }


def test_organiser_can_create_a_space_request_with_pax_and_layout(
    client, auth_headers, authenticate_as, monkeypatch
):
    authenticate_as("event_organiser", user_id=ORGANISER_ID)
    monkeypatch.setattr(repository, "get_event", lambda event_id: event_row())
    created_values = {}

    def create_space(event_id, values):
        created_values.update(values)
        return {
            "id": SPACE_ID,
            "event_id": event_id,
            **deepcopy({key: values[key] for key in (
                "label", "expected_pax", "layout_preference", "facilities_required"
            )}),
            "version": 1,
        }

    monkeypatch.setattr(
        repository,
        "create_space",
        create_space,
    )

    response = client.post(
        f"/api/v1/events/{EVENT_ID}/spaces",
        json={
            "label": "Afternoon breakout",
            "expected_pax": 40,
            "layout_preference": "classroom",
            "facilities_required": ["projector"],
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert response.json()["label"] == "Afternoon breakout"
    assert response.json()["expected_pax"] == 40
    assert response.json()["layout_preference"] == "classroom"
    assert response.json()["facilities_required"] == ["projector"]
    assert "starts_at" not in response.json()
    assert "ends_at" not in response.json()
    assert created_values["starts_at"] == event_row()["starts_at"]
    assert created_values["ends_at"] == event_row()["ends_at"]


def test_space_request_rejects_space_level_schedule_fields(
    client, auth_headers, authenticate_as, monkeypatch
):
    authenticate_as("event_organiser", user_id=ORGANISER_ID)
    monkeypatch.setattr(repository, "get_event", lambda event_id: event_row())

    def unexpected_create(*args, **kwargs):
        raise AssertionError("repository write should not happen for an invalid payload")

    monkeypatch.setattr(repository, "create_space", unexpected_create)

    response = client.post(
        f"/api/v1/events/{EVENT_ID}/spaces",
        json={
            "label": "Afternoon breakout",
            "expected_pax": 40,
            "layout_preference": "classroom",
            "starts_at": "2026-10-20T10:00:00+08:00",
            "ends_at": "2026-10-20T12:00:00+08:00",
            "facilities_required": ["projector"],
        },
        headers=auth_headers,
    )

    assert response.status_code == 422


def test_organiser_can_update_a_space_request_without_internal_row_fields(
    client, auth_headers, authenticate_as, monkeypatch
):
    authenticate_as("event_organiser", user_id=ORGANISER_ID)
    monkeypatch.setattr(repository, "get_event", lambda event_id: event_row())
    current_space = {
        "id": SPACE_ID,
        "event_id": EVENT_ID,
        "label": "Afternoon breakout",
        "expected_pax": 40,
        "layout_preference": "classroom",
        "facilities_required": ["projector"],
        "version": 1,
    }
    monkeypatch.setattr(repository, "get_space", lambda space_id: current_space)
    monkeypatch.setattr(
        repository,
        "update_space",
        lambda space_id, values, version: {
            **current_space,
            **values,
            "version": version + 1,
        },
    )

    response = client.patch(
        f"/api/v1/events/{EVENT_ID}/spaces/{SPACE_ID}",
        json={"label": "Updated breakout"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["label"] == "Updated breakout"
    assert response.json()["version"] == 2


@pytest.mark.parametrize(
    "payload",
    [
        {"label": "   ", "expected_pax": 10, "layout_preference": "classroom"},
        {"label": "Room", "expected_pax": 0, "layout_preference": "classroom"},
        {"label": "Room", "expected_pax": 10},
        {"label": 42, "expected_pax": 10, "layout_preference": "classroom"},
    ],
)
def test_space_create_rejects_invalid_required_fields(
    client, auth_headers, authenticate_as, payload
):
    authenticate_as("event_organiser", user_id=ORGANISER_ID)

    response = client.post(
        f"/api/v1/events/{EVENT_ID}/spaces",
        json=payload,
        headers=auth_headers,
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"label": "   "},
        {"label": None},
        {"expected_pax": None},
        {"layout_preference": None},
        {"facilities_required": None},
    ],
)
def test_space_update_rejects_blank_or_null_labels(
    client, auth_headers, authenticate_as, monkeypatch, payload
):
    authenticate_as("event_organiser", user_id=ORGANISER_ID)
    space = {
        "id": SPACE_ID,
        "event_id": EVENT_ID,
        "label": "Existing room",
        "expected_pax": 10,
        "layout_preference": "classroom",
        "facilities_required": [],
        "version": 1,
    }
    monkeypatch.setattr(repository, "get_space", lambda space_id: space)
    monkeypatch.setattr(repository, "get_event", lambda event_id: event_row())

    response = client.patch(
        f"/api/v1/events/{EVENT_ID}/spaces/{SPACE_ID}",
        json=payload,
        headers=auth_headers,
    )

    assert response.status_code == 422


def test_space_create_and_edit_are_limited_to_draft_or_returned_events(
    client, auth_headers, authenticate_as, monkeypatch
):
    authenticate_as("event_organiser", user_id=ORGANISER_ID)
    monkeypatch.setattr(repository, "get_event", lambda event_id: event_row("under_review"))
    create_response = client.post(
        f"/api/v1/events/{EVENT_ID}/spaces",
        json={"label": "Room", "expected_pax": 10, "layout_preference": "classroom"},
        headers=auth_headers,
    )
    assert create_response.status_code == 409

    space = {"id": SPACE_ID, "event_id": EVENT_ID, "label": "Room", "version": 1}
    monkeypatch.setattr(repository, "get_space", lambda space_id: space)
    update_response = client.patch(
        f"/api/v1/events/{EVENT_ID}/spaces/{SPACE_ID}",
        json={"label": "Updated"},
        headers=auth_headers,
    )
    assert update_response.status_code == 409


def test_space_update_and_delete_report_lost_version_races(
    client, auth_headers, authenticate_as, monkeypatch
):
    authenticate_as("event_organiser", user_id=ORGANISER_ID)
    space = {
        "id": SPACE_ID,
        "event_id": EVENT_ID,
        "label": "Room",
        "expected_pax": 10,
        "layout_preference": "classroom",
        "facilities_required": [],
        "version": 1,
    }
    monkeypatch.setattr(repository, "get_space", lambda space_id: space)
    monkeypatch.setattr(repository, "get_event", lambda event_id: event_row())
    monkeypatch.setattr(repository, "update_space", lambda *args: None)
    update_response = client.patch(
        f"/api/v1/events/{EVENT_ID}/spaces/{SPACE_ID}",
        json={"label": "Updated"},
        headers=auth_headers,
    )
    assert update_response.status_code == 409

    monkeypatch.setattr(repository, "delete_space", lambda *args: False)
    delete_response = client.delete(
        f"/api/v1/events/{EVENT_ID}/spaces/{SPACE_ID}",
        headers=auth_headers,
    )
    assert delete_response.status_code == 409


def test_space_update_reports_not_found_when_space_is_missing(
    client, auth_headers, authenticate_as, monkeypatch
):
    authenticate_as("event_organiser", user_id=ORGANISER_ID)
    monkeypatch.setattr(repository, "get_space", lambda space_id: None)

    response = client.patch(
        f"/api/v1/events/{EVENT_ID}/spaces/{SPACE_ID}",
        json={"label": "Updated"},
        headers=auth_headers,
    )

    assert response.status_code == 404


def test_organiser_can_delete_a_space_request(
    client, auth_headers, authenticate_as, monkeypatch
):
    authenticate_as("event_organiser", user_id=ORGANISER_ID)
    monkeypatch.setattr(repository, "get_space", lambda space_id: {
        "id": SPACE_ID, "event_id": EVENT_ID, "label": "Room", "version": 1,
    })
    monkeypatch.setattr(repository, "get_event", lambda event_id: event_row())
    deleted = []
    monkeypatch.setattr(repository, "delete_space", lambda space_id, version: deleted.append((space_id, version)) or True)

    response = client.delete(
        f"/api/v1/events/{EVENT_ID}/spaces/{SPACE_ID}",
        headers=auth_headers,
    )

    assert response.status_code == 204
    assert deleted == [(SPACE_ID, 1)]


def test_space_submission_requires_label_pax_and_layout_but_not_event_level_venue_fields():
    starts_at = datetime.now(timezone.utc).replace(microsecond=0) + __import__("datetime").timedelta(days=2)
    event = {
        "purpose": "Planning",
        "starts_at": starts_at.isoformat(),
        "ends_at": (starts_at + __import__("datetime").timedelta(hours=2)).isoformat(),
        "event_timezone": "Asia/Singapore",
        "spaces": [{"label": None, "expected_pax": None, "layout_preference": None}],
    }

    with pytest.raises(HTTPException) as error:
        _validate_submission(event)

    assert {tuple(item["loc"]) for item in error.value.detail} == {
        ("body", "spaces", 0, "label"),
        ("body", "spaces", 0, "expected_pax"),
        ("body", "spaces", 0, "layout_preference"),
    }

    event["spaces"] = [{"label": "Main venue", "expected_pax": 10, "layout_preference": "classroom"}]
    _validate_submission(event)


def test_assigned_coordinator_can_read_a_space_and_missing_space_is_not_found(monkeypatch):
    coordinator_id = "a0000000-0000-4000-8000-000000000002"
    space = {"id": SPACE_ID, "event_id": EVENT_ID, "label": "Main venue"}
    event = event_row("planning")
    event["coordinator_id"] = coordinator_id
    monkeypatch.setattr(repository, "get_space", lambda space_id: space)
    monkeypatch.setattr(repository, "get_event", lambda event_id: event)

    assert service.assigned_space(SPACE_ID, coordinator_id) == (event, space)

    monkeypatch.setattr(repository, "get_space", lambda space_id: None)
    with pytest.raises(service.EventNotFoundError):
        service.assigned_space(SPACE_ID, coordinator_id)


def test_coordinator_event_read_includes_all_active_space_bookings(monkeypatch):
    coordinator_id = "a0000000-0000-4000-8000-000000000002"
    event = event_row("under_review")
    event["coordinator_id"] = coordinator_id
    event["spaces"] = [{"id": SPACE_ID, "event_id": EVENT_ID, "label": "Main venue"}]
    bookings = [
        {
            "id": "booking-1", "event_id": EVENT_ID, "event_space_request_id": SPACE_ID,
            "venue_id": "venue-1", "venue_name": "Innovation Lab", "status": "held",
        },
        {
            "id": "booking-2", "event_id": EVENT_ID, "event_space_request_id": "space-2",
            "venue_id": "venue-2", "venue_name": "Heritage Hall", "status": "approved",
        },
    ]
    monkeypatch.setattr(repository, "get_event", lambda event_id: event)
    monkeypatch.setattr(service.venues_service, "active_booking_for_event", lambda event_id: None)
    monkeypatch.setattr(service.venues_service, "active_bookings_for_event", lambda event_id: bookings)

    response = service.read(EVENT_ID, coordinator_id, "event_coordinator")

    assert [booking.model_dump() for booking in response.venue_bookings] == [
        {**{key: value for key, value in booking.items() if key != "event_id"}, "expires_at": None}
        for booking in bookings
    ]
