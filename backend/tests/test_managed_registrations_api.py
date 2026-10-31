"""SCRUM-35 event-manager registration reports."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.modules.events import repository as events_repository
from app.modules.events import service as events_service
from app.modules.registrations import repository as registrations_repository

USER_ID = "11111111-1111-1111-1111-111111111111"
EVENT_ID = "35000000-0000-4000-8000-000000000035"


def _registration(status: str, suffix: int, *, expires_at: str | None = None) -> dict:
    return {
        "id": f"35000000-0000-4000-8000-{suffix:012d}",
        "status": status,
        "registered_at": "2031-05-01T01:00:00Z",
        "invitation_expires_at": expires_at,
        "attendee": {
            "id": f"35000000-0000-4000-8000-{suffix + 100:012d}",
            "full_name": f"Attendee {suffix}",
            "email": f"attendee-{suffix}@example.test",
            "phone_number": f"+65 8000 {suffix:04d}",
        },
    }


def _configure_report(monkeypatch, *, owner_id: str, coordinator_id: str) -> list[dict]:
    now = datetime.now(timezone.utc)
    registrations = [
        _registration("registered", 1),
        _registration("registered", 2),
        _registration("invited", 3, expires_at=(now + timedelta(hours=1)).isoformat()),
        _registration("invited", 4, expires_at=(now - timedelta(hours=1)).isoformat()),
        _registration("waitlisted", 5),
        _registration("waitlisted", 6),
        _registration("withdrawn", 7),
        _registration("cancelled", 8),
        _registration("invitation_expired", 9),
        _registration("left", 10),
    ]
    event = {
        "id": EVENT_ID,
        "organiser_id": owner_id,
        "coordinator_id": coordinator_id,
        "status": "confirmed",
    }
    capacity_context = {
        "id": EVENT_ID,
        "registration_capacity": 8,
        "event_space_requests": [
            {
                "is_primary": True,
                "venue_bookings": [
                    {"status": "approved", "venue": {"id": "venue-1", "name": "Hall", "location": "City", "capacity": 6}},
                ],
            },
            {
                "is_primary": False,
                "venue_bookings": [
                    {"status": "approved", "venue": {"id": "venue-2", "name": "Room", "location": "City", "capacity": 2}},
                ],
            },
        ],
    }
    monkeypatch.setattr(events_repository, "get_event", lambda event_id: event)
    monkeypatch.setattr(registrations_repository, "get_registration_event_row", lambda event_id: capacity_context, raising=False)
    monkeypatch.setattr(
        registrations_repository,
        "list_event_registration_rows",
        lambda event_id: [
            row for row in registrations if row["status"] in {"registered", "waitlisted", "invited", "withdrawn"}
        ],
        raising=False,
    )
    return registrations


def test_assigned_coordinator_sees_registration_counts_contacts_and_only_manager_statuses(
    client, authenticate_as, auth_headers, monkeypatch
):
    authenticate_as("event_coordinator")
    _configure_report(monkeypatch, owner_id="22222222-2222-2222-2222-222222222222", coordinator_id=USER_ID)

    response = client.get(f"/api/v1/events/{EVENT_ID}/registrations", headers=auth_headers)

    assert response.status_code == 200
    report = response.json()
    assert report["effective_capacity"] == 6
    assert report["registered_count"] == 2
    assert report["waitlist_count"] == 2
    assert report["remaining_places"] == 3
    assert {row["status"] for row in report["registrations"]} == {
        "registered",
        "invited",
        "waitlisted",
        "withdrawn",
    }
    attendee = next(row for row in report["registrations"] if row["status"] == "registered")
    assert attendee["full_name"] == "Attendee 1"
    assert attendee["email"] == "attendee-1@example.test"
    assert attendee["phone_number"] == "+65 8000 0001"


def test_event_organiser_receives_the_report_without_contact_information(
    client, authenticate_as, auth_headers, monkeypatch
):
    authenticate_as("event_organiser")
    _configure_report(monkeypatch, owner_id=USER_ID, coordinator_id="22222222-2222-2222-2222-222222222222")

    response = client.get(f"/api/v1/events/{EVENT_ID}/registrations", headers=auth_headers)

    assert response.status_code == 200
    report = response.json()
    assert report["registered_count"] == 2
    assert report["remaining_places"] == 3
    attendee = next(row for row in report["registrations"] if row["status"] == "registered")
    assert attendee["full_name"] == "Attendee 1"
    assert "email" not in attendee
    assert "phone_number" not in attendee


@pytest.mark.parametrize(
    ("role", "owner_id", "coordinator_id", "expected_status"),
    [
        ("event_coordinator", "22222222-2222-2222-2222-222222222222", "33333333-3333-3333-3333-333333333333", 403),
        ("event_organiser", "22222222-2222-2222-2222-222222222222", "33333333-3333-3333-3333-333333333333", 403),
    ],
)
def test_registration_report_requires_the_event_relationship(
    client, authenticate_as, auth_headers, monkeypatch, role, owner_id, coordinator_id, expected_status
):
    authenticate_as(role)
    _configure_report(monkeypatch, owner_id=owner_id, coordinator_id=coordinator_id)

    response = client.get(f"/api/v1/events/{EVENT_ID}/registrations", headers=auth_headers)

    assert response.status_code == expected_status


def test_registration_report_returns_404_when_report_event_is_missing(
    client, authenticate_as, auth_headers, monkeypatch
):
    authenticate_as("event_organiser")
    monkeypatch.setattr(events_repository, "get_event", lambda event_id: {"organiser_id": USER_ID})
    monkeypatch.setattr(registrations_repository, "get_registration_event_row", lambda event_id: None)

    response = client.get(f"/api/v1/events/{EVENT_ID}/registrations", headers=auth_headers)

    assert response.status_code == 404


def test_managed_registration_service_rejects_other_roles():
    with pytest.raises(HTTPException) as error:
        events_service.managed_registrations(EVENT_ID, USER_ID, "attendee")

    assert error.value.status_code == 403
