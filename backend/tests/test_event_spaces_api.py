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
                "label", "expected_pax", "layout_preference", "facilities_required", "starts_at", "ends_at"
            )}),
            "is_primary": False,
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
    assert response.json()["is_primary"] is False
    assert response.json()["starts_at"] is None
    assert response.json()["ends_at"] is None
    assert created_values["starts_at"] is None
    assert created_values["ends_at"] is None


def test_organiser_cannot_set_primary_space_on_create(
    client, auth_headers, authenticate_as, monkeypatch
):
    authenticate_as("event_organiser", user_id=ORGANISER_ID)
    monkeypatch.setattr(
        repository,
        "get_event",
        lambda event_id: pytest.fail("invalid payload must be rejected before loading the event"),
    )

    response = client.post(
        f"/api/v1/events/{EVENT_ID}/spaces",
        json={
            "label": "Afternoon breakout",
            "expected_pax": 40,
            "layout_preference": "classroom",
            "is_primary": True,
        },
        headers=auth_headers,
    )

    assert response.status_code == 422


def test_space_request_rejects_window_outside_event_period(
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
            "starts_at": "2026-10-20T08:00:00+08:00",
            "ends_at": "2026-10-20T12:00:00+08:00",
            "facilities_required": ["projector"],
        },
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert "within the event's overall schedule" in str(response.json())


def test_space_request_requires_both_schedule_bounds_or_neither(
    client, auth_headers, authenticate_as, monkeypatch
):
    authenticate_as("event_organiser", user_id=ORGANISER_ID)
    monkeypatch.setattr(repository, "get_event", lambda event_id: event_row())
    monkeypatch.setattr(repository, "create_space", lambda *args: pytest.fail("invalid window must not be stored"))

    response = client.post(
        f"/api/v1/events/{EVENT_ID}/spaces",
        json={
            "label": "Afternoon breakout",
            "expected_pax": 40,
            "layout_preference": "classroom",
            "starts_at": "2026-10-20T13:00:00+08:00",
        },
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert "starts_at and ends_at must be provided together" in str(response.json())


@pytest.mark.parametrize(
    ("starts_at", "ends_at", "message"),
    [
        ("2026-10-20T13:00:00", "2026-10-20T16:00:00+08:00", "timezone offset"),
        ("2026-10-20T16:00:00+08:00", "2026-10-20T13:00:00+08:00", "end time must be after"),
    ],
)
def test_space_request_rejects_naive_or_inverted_windows(
    starts_at, ends_at, message, client, auth_headers, authenticate_as, monkeypatch
):
    authenticate_as("event_organiser", user_id=ORGANISER_ID)
    monkeypatch.setattr(repository, "get_event", lambda event_id: event_row())
    monkeypatch.setattr(repository, "create_space", lambda *args: pytest.fail("invalid window must not be stored"))

    response = client.post(
        f"/api/v1/events/{EVENT_ID}/spaces",
        json={
            "label": "Afternoon breakout",
            "expected_pax": 40,
            "layout_preference": "classroom",
            "starts_at": starts_at,
            "ends_at": ends_at,
        },
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert message in str(response.json()).lower()


def test_space_window_requires_an_event_schedule(
    client, auth_headers, authenticate_as, monkeypatch
):
    authenticate_as("event_organiser", user_id=ORGANISER_ID)
    parent = event_row()
    parent["starts_at"] = None
    parent["ends_at"] = None
    monkeypatch.setattr(repository, "get_event", lambda event_id: parent)
    monkeypatch.setattr(repository, "create_space", lambda *args: pytest.fail("window without event bounds must not be stored"))

    response = client.post(
        f"/api/v1/events/{EVENT_ID}/spaces",
        json={
            "label": "Afternoon breakout",
            "expected_pax": 40,
            "layout_preference": "classroom",
            "starts_at": "2026-10-20T13:00:00+08:00",
            "ends_at": "2026-10-20T16:00:00+08:00",
        },
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert "requires the event's overall schedule" in str(response.json())


def test_organiser_can_create_a_space_with_its_own_window_within_the_event(
    client, auth_headers, authenticate_as, monkeypatch
):
    authenticate_as("event_organiser", user_id=ORGANISER_ID)
    parent = event_row()
    monkeypatch.setattr(repository, "get_event", lambda event_id: parent)
    created = {}

    def create_space(event_id, values):
        created.update(values)
        return {"id": SPACE_ID, "event_id": event_id, **values, "version": 1}

    monkeypatch.setattr(repository, "create_space", create_space)
    window = {
        "starts_at": "2026-10-20T13:00:00+08:00",
        "ends_at": "2026-10-20T16:00:00+08:00",
    }

    response = client.post(
        f"/api/v1/events/{EVENT_ID}/spaces",
        json={
            "label": "Afternoon breakout",
            "expected_pax": 40,
            "layout_preference": "classroom",
            **window,
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert created["starts_at"] == window["starts_at"]
    assert created["ends_at"] == window["ends_at"]
    assert response.json()["starts_at"] == window["starts_at"]
    assert response.json()["ends_at"] == window["ends_at"]


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
        "is_primary": False,
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
    assert response.json()["is_primary"] is False
    assert response.json()["version"] == 2


def test_organiser_can_set_and_clear_a_space_schedule(monkeypatch, client, auth_headers, authenticate_as):
    authenticate_as("event_organiser", user_id=ORGANISER_ID)
    monkeypatch.setattr(repository, "get_event", lambda event_id: event_row("returned"))
    space = {
        "id": SPACE_ID,
        "event_id": EVENT_ID,
        "label": "Afternoon breakout",
        "expected_pax": 40,
        "layout_preference": "classroom",
        "facilities_required": [],
        "starts_at": None,
        "ends_at": None,
        "version": 1,
    }
    monkeypatch.setattr(repository, "get_space", lambda space_id: space)
    writes = []

    def update_space(space_id, values, version):
        writes.append(values)
        return {**space, **values, "version": version + 1}

    monkeypatch.setattr(repository, "update_space", update_space)
    window = {"starts_at": "2026-10-20T13:00:00+08:00", "ends_at": "2026-10-20T16:00:00+08:00"}

    response = client.patch(f"/api/v1/events/{EVENT_ID}/spaces/{SPACE_ID}", json=window, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["starts_at"] == window["starts_at"]
    assert response.json()["ends_at"] == window["ends_at"]

    space.update(window, version=2)
    cleared = client.patch(
        f"/api/v1/events/{EVENT_ID}/spaces/{SPACE_ID}",
        json={"starts_at": None, "ends_at": None, "version": 2},
        headers=auth_headers,
    )
    assert cleared.status_code == 200
    assert cleared.json()["starts_at"] is None
    assert cleared.json()["ends_at"] is None
    assert writes == [window, {"starts_at": None, "ends_at": None}]


def test_event_schedule_cannot_be_shrunk_past_an_explicit_space_window(
    client, auth_headers, authenticate_as, monkeypatch
):
    authenticate_as("event_organiser", user_id=ORGANISER_ID)
    event = event_row()
    event["spaces"] = [{
        "id": SPACE_ID,
        "event_id": EVENT_ID,
        "label": "Afternoon breakout",
        "expected_pax": 40,
        "layout_preference": "classroom",
        "facilities_required": [],
        "starts_at": "2026-10-20T13:00:00+08:00",
        "ends_at": "2026-10-20T16:00:00+08:00",
        "version": 1,
    }]
    monkeypatch.setattr(repository, "get_event", lambda event_id: event)
    monkeypatch.setattr(repository, "update_event", lambda *args: pytest.fail("invalid event period must not be saved"))

    response = client.patch(
        f"/api/v1/events/{EVENT_ID}",
        json={"ends_at": "2026-10-20T14:00:00+08:00"},
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert "within the event's overall schedule" in str(response.json())


def test_submission_rejects_a_space_window_outside_the_event_period(
    client, auth_headers, authenticate_as, monkeypatch
):
    authenticate_as("event_organiser", user_id=ORGANISER_ID)
    event = event_row()
    event.update({"purpose": "Plan the summit"})
    event["spaces"] = [{
        "id": SPACE_ID,
        "event_id": EVENT_ID,
        "label": "Afternoon breakout",
        "expected_pax": 40,
        "layout_preference": "classroom",
        "facilities_required": [],
        "starts_at": "2026-10-20T13:00:00+08:00",
        "ends_at": "2026-10-20T19:00:00+08:00",
        "version": 1,
    }]
    monkeypatch.setattr(repository, "get_event", lambda event_id: event)
    monkeypatch.setattr(repository, "transition_event", lambda *args, **kwargs: pytest.fail("invalid event must not submit"))

    response = client.post(f"/api/v1/events/{EVENT_ID}/submit", headers=auth_headers)

    assert response.status_code == 422
    assert "within the event's overall schedule" in str(response.json())


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


def test_space_submission_requires_attendance_and_space_fields_but_not_event_level_layout():
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
        ("body", "expected_attendance"),
        ("body", "spaces", 0, "label"),
        ("body", "spaces", 0, "expected_pax"),
        ("body", "spaces", 0, "layout_preference"),
    }

    event["spaces"] = [{"label": "Main venue", "expected_pax": 10, "layout_preference": "classroom"}]
    with pytest.raises(HTTPException) as error:
        _validate_submission(event)
    assert {tuple(item["loc"]) for item in error.value.detail} == {("body", "expected_attendance")}

    event["expected_attendance"] = 10
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
        {**{key: value for key, value in booking.items() if key != "event_id"}, "expires_at": None,
         "flag": None, "flag_reason": None, "replaces_booking_id": None}
        for booking in bookings
    ]


@pytest.mark.parametrize("flag", ["affected", "safety_rejected"])
def test_an_organiser_does_not_see_a_bookings_flag_or_what_it_replaces(monkeypatch, flag):
    # CR-95: the flag and the replacement link are the coordinator's follow-up.
    # An organiser sees a confirmed event's venues, not what is wrong with them
    # (CR-111 gives them their own view).
    organiser_id = "a0000000-0000-4000-8000-000000000001"
    event = event_row("confirmed")
    event["organiser_id"] = organiser_id
    booking = {
        "id": "booking-1", "event_id": EVENT_ID, "event_space_request_id": None, "venue_id": "venue-1",
        "venue_name": "Innovation Lab", "status": "approved", "flag": flag,
        "flag_reason": "Venue unavailable: Maintenance", "replaces_booking_id": "booking-0",
    }
    monkeypatch.setattr(repository, "get_event", lambda event_id: event)
    monkeypatch.setattr(service.venues_service, "active_booking_for_event", lambda event_id: dict(booking))
    monkeypatch.setattr(service.venues_service, "active_bookings_for_event", lambda event_id: [dict(booking)])

    response = service.read(EVENT_ID, organiser_id, "event_organiser")

    for shown in [response.venue_booking, *response.venue_bookings]:
        assert (shown.flag, shown.flag_reason, shown.replaces_booking_id) == (None, None, None)
        assert shown.status == "approved"

    response = service.read(EVENT_ID, event['coordinator_id'], 'event_coordinator')
    for shown in [response.venue_booking, *response.venue_bookings]:
        assert (shown.flag, shown.flag_reason) == (flag, booking['flag_reason'])
