from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.modules.registrations import service
from app.modules.registrations.schemas import RegistrationAvailability


NOW = datetime(2031, 5, 1, 1, 0, tzinfo=timezone.utc)


def test_availability_uses_open_and_close_instants_as_inclusive_boundaries():
    row = {
        "registration_enabled": True,
        "registration_opens_at": "2031-05-01T09:00:00+08:00",
        "registration_closes_at": "2031-05-01T09:00:00+08:00",
    }

    assert service._availability(row, 0, 10, NOW) is RegistrationAvailability.closed

    row["registration_closes_at"] = "2031-05-01T10:00:00+08:00"
    assert service._availability(row, 0, 10, NOW) is RegistrationAvailability.open

    row["registration_opens_at"] = "2031-05-01T09:00:01+08:00"
    assert service._availability(row, 0, 10, NOW) is RegistrationAvailability.not_open


def test_public_directory_limits_venue_and_capacity_to_primary_space(monkeypatch):
    row = {
        "id": "e0000000-0000-4000-8000-000000000043",
        "name": "Community Design Forum",
        "event_timezone": "Asia/Singapore",
        "status": "confirmed",
        "registration_enabled": True,
        "registration_capacity": 80,
        "registration_opens_at": "2031-05-01T08:00:00+08:00",
        "registration_closes_at": "2031-05-01T20:00:00+08:00",
        "waitlist_enabled": True,
        "event_space_requests": [
            {
                "is_primary": True,
                "venue_bookings": [{"status": "approved", "venue": {
                    "id": "a0000000-0000-4000-8000-000000000043",
                    "name": "Central Hall", "location": "Downtown", "capacity": 100,
                }}],
            },
            {
                "is_primary": False,
                "venue_bookings": [{"status": "approved", "venue": {
                    "id": "a0000000-0000-4000-8000-000000000044",
                    "name": "Small Room", "location": "Uptown", "capacity": 20,
                }}],
            },
        ],
    }
    monkeypatch.setattr(service.repository, "list_public_event_rows", lambda: [row])
    monkeypatch.setattr(service.repository, "registered_count", lambda event_id: 9)

    [event] = service.public_directory()

    assert [venue.name for venue in event.venues] == ["Central Hall"]
    assert event.effective_capacity == 80
    assert event.registered_count == 9


@pytest.mark.parametrize(
    ("row", "registered", "capacity", "expected"),
    [
        ({"registration_enabled": False}, 0, 10, RegistrationAvailability.not_open),
        ({"registration_enabled": True, "registration_opens_at": None}, 0, 10, RegistrationAvailability.not_open),
        (
            {
                "registration_enabled": True,
                "registration_opens_at": "2031-05-01T08:00:00+08:00",
                "registration_closes_at": None,
            },
            0,
            None,
            RegistrationAvailability.open,
        ),
        (
            {
                "registration_enabled": True,
                "registration_opens_at": "2031-05-01T08:00:00+08:00",
            },
            10,
            10,
            RegistrationAvailability.full,
        ),
    ],
)
def test_availability_handles_disabled_missing_unlimited_and_full(row, registered, capacity, expected):
    assert service._availability(row, registered, capacity, NOW) is expected


def test_public_directory_uses_all_confirmed_venues_when_no_primary_is_set(monkeypatch):
    row = {
        "id": "e0000000-0000-4000-8000-000000000043",
        "name": "Community Design Forum",
        "event_timezone": "Asia/Singapore",
        "status": "confirmed",
        "registration_enabled": False,
        "event_space_requests": [
            {
                "is_primary": False,
                "venue_bookings": [
                    {"status": "held", "venue": {
                        "id": "a0000000-0000-4000-8000-000000000045",
                        "name": "Held Hall", "location": "West", "capacity": 5,
                    }},
                    {"status": "approved", "venue": {
                        "id": "a0000000-0000-4000-8000-000000000046",
                        "name": "Approved Hall", "location": "East", "capacity": 40,
                    }},
                    {"status": "approved", "venue": None},
                ],
            },
            {
                "is_primary": False,
                "venue_bookings": [{"status": "approved", "venue": {
                    "id": "a0000000-0000-4000-8000-000000000047",
                    "name": "Second Hall", "location": "North", "capacity": 60,
                }}],
            },
        ],
    }
    monkeypatch.setattr(service.repository, "list_public_event_rows", lambda: [row])
    monkeypatch.setattr(service.repository, "registered_count", lambda event_id: 0)

    [event] = service.public_directory()

    assert [venue.name for venue in event.venues] == ["Approved Hall", "Second Hall"]
    assert event.effective_capacity == 40
    assert event.waitlist_enabled is True


def test_public_directory_without_spaces_has_no_venue_capacity(monkeypatch):
    row = {
        "id": "e0000000-0000-4000-8000-000000000043",
        "name": "Community Design Forum",
        "event_timezone": "Asia/Singapore",
        "status": "preparation",
        "registration_enabled": False,
        "event_space_requests": None,
    }
    monkeypatch.setattr(service.repository, "list_public_event_rows", lambda: [row])
    monkeypatch.setattr(service.repository, "registered_count", lambda event_id: 0)

    [event] = service.public_directory()

    assert event.venues == []
    assert event.effective_capacity is None


def test_public_event_raises_not_found_when_repository_has_no_row(monkeypatch):
    monkeypatch.setattr(service.repository, "get_public_event_row", lambda event_id: None)

    with pytest.raises(HTTPException) as error:
        service.public_event("missing")

    assert error.value.status_code == 404
    assert error.value.detail == "Event not found."


def test_public_event_returns_the_public_detail(monkeypatch):
    row = {
        "id": "e0000000-0000-4000-8000-000000000043",
        "name": "Community Design Forum",
        "event_timezone": "Asia/Singapore",
        "status": "preparation",
        "registration_enabled": False,
    }
    monkeypatch.setattr(service.repository, "get_public_event_row", lambda event_id: row)
    monkeypatch.setattr(service.repository, "registered_count", lambda event_id: 0)

    event = service.public_event(row["id"])

    assert event.id == row["id"]
    assert event.status == "preparation"


@pytest.mark.parametrize(
    ("outcome", "status_code", "detail"),
    [
        ("unavailable", 404, "Event not found."),
        ("not_open", 409, "Registration is not open yet."),
        ("closed", 409, "Registration is closed."),
        ("full", 409, "Event is full."),
        ("reregistration_disabled", 409, "Re-registration is not allowed for this event."),
    ],
)
def test_register_attendee_maps_registration_refusals(monkeypatch, outcome, status_code, detail):
    monkeypatch.setattr(
        service.repository,
        "register_for_event",
        lambda event_id, attendee_id: {"outcome": outcome},
    )

    with pytest.raises(HTTPException) as error:
        service.register_attendee("event-1", "attendee-1")

    assert error.value.status_code == status_code
    assert error.value.detail == detail


@pytest.mark.parametrize(
    ("outcome", "expected_status"),
    [("registered", "registered"), ("already_registered", "already_registered")],
)
def test_register_attendee_returns_registration_result(monkeypatch, outcome, expected_status):
    monkeypatch.setattr(
        service.repository,
        "register_for_event",
        lambda event_id, attendee_id: {
            "outcome": outcome,
            "registration_id": "registration-1",
            "registered_at": "2031-05-01T01:00:00Z",
        },
    )

    result = service.register_attendee("event-1", "attendee-1")

    assert result.registration_id == "registration-1"
    assert result.registered_at == NOW
    assert result.status == expected_status