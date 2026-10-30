"""SCRUM-86 attendee waitlist invitation and removal API behaviour."""

from fastapi import HTTPException

from app.modules.registrations import service
from app.modules.registrations.schemas import RegistrationResult


REGISTRATION_ID = "86000000-0000-4000-8000-000000000001"


def test_attendee_accepts_their_own_invitation(
    client, authenticate_as, auth_headers, monkeypatch
):
    attendee = authenticate_as("attendee")
    calls = []

    def accept_invitation(registration_id, attendee_id):
        calls.append((registration_id, attendee_id))
        return RegistrationResult(
            registration_id=registration_id,
            status="registered",
            registered_at="2031-05-01T01:00:00Z",
        )

    monkeypatch.setattr(service, "accept_invitation", accept_invitation, raising=False)

    response = client.post(
        f"/api/v1/registrations/{REGISTRATION_ID}/accept",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "registered"
    assert calls == [(REGISTRATION_ID, attendee["id"])]


def test_attendee_cannot_accept_another_attendees_invitation(
    client, authenticate_as, auth_headers, monkeypatch
):
    attendee = authenticate_as("attendee", user_id="33333333-3333-3333-3333-333333333333")
    calls = []

    def accept_invitation(registration_id, attendee_id):
        calls.append((registration_id, attendee_id))
        raise HTTPException(status_code=404, detail="Invitation not found.")

    monkeypatch.setattr(service, "accept_invitation", accept_invitation, raising=False)

    response = client.post(
        f"/api/v1/registrations/{REGISTRATION_ID}/accept",
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Invitation not found."
    assert calls == [(REGISTRATION_ID, attendee["id"])]


def test_only_the_active_attendee_role_can_accept_an_invitation(
    client, authenticate_as, auth_headers
):
    authenticate_as("event_organiser")

    response = client.post(
        f"/api/v1/registrations/{REGISTRATION_ID}/accept",
        headers=auth_headers,
    )

    assert response.status_code == 403


def test_attendee_can_leave_their_waitlist_entry(
    client, authenticate_as, auth_headers, monkeypatch
):
    attendee = authenticate_as("attendee")
    calls = []
    monkeypatch.setattr(
        service,
        "leave_waitlist",
        lambda registration_id, attendee_id: calls.append((registration_id, attendee_id)),
        raising=False,
    )

    response = client.delete(
        f"/api/v1/registrations/{REGISTRATION_ID}",
        headers=auth_headers,
    )

    assert response.status_code == 204
    assert calls == [(REGISTRATION_ID, attendee["id"])]
