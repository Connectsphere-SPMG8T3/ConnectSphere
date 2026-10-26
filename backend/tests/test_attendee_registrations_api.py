"""Story 56 attendee registered-events API behaviour."""

import pytest

from app.modules.registrations import repository


def test_attendee_reads_only_their_registered_events(client, authenticate_as, auth_headers, monkeypatch):
    attendee = authenticate_as("attendee")
    registrations = [
        {
            "id": "r0000000-0000-4000-8000-000000000056",
            "status": "registered",
            "registered_at": "2031-05-01T01:00:00Z",
            "event": {
                "id": "e0000000-0000-4000-8000-000000000056",
                "name": "Community Design Forum",
                "description": "A regional design gathering.",
                "starts_at": "2031-05-01T09:00:00Z",
                "ends_at": "2031-05-01T12:00:00Z",
                "event_timezone": "Asia/Singapore",
                "status": "confirmed",
                "withdrawal_closes_at": "2031-05-01T01:30:00Z",
                "event_space_requests": [
                    {
                        "is_primary": True,
                        "venue_bookings": [{
                            "status": "approved",
                            "venue": {
                                "id": "a0000000-0000-4000-8000-000000000056",
                                "name": "Central Hall",
                                "location": "Downtown",
                                "capacity": 100,
                            },
                        }],
                    },
                    {
                        "is_primary": False,
                        "venue_bookings": [{
                            "status": "approved",
                            "venue": {
                                "id": "a0000000-0000-4000-8000-000000000057",
                                "name": "Workshop Room",
                                "location": "Downtown",
                                "capacity": 40,
                            },
                        }],
                    },
                ],
            },
        },
        {
            "id": "r0000000-0000-4000-8000-000000000058",
            "status": "waitlisted",
            "registered_at": "2031-05-02T01:00:00Z",
            "event": {
                "id": "e0000000-0000-4000-8000-000000000058",
                "name": "Design in Practice",
                "description": None,
                "starts_at": "2031-05-02T09:00:00Z",
                "ends_at": "2031-05-02T12:00:00Z",
                "event_timezone": "Asia/Singapore",
                "status": "confirmed",
                "event_space_requests": [
                    {
                        "is_primary": False,
                        "venue_bookings": [{
                            "status": "approved",
                            "venue": {
                                "id": "a0000000-0000-4000-8000-000000000058",
                                "name": "Main Hall",
                                "location": "Downtown",
                                "capacity": 100,
                            },
                        }],
                    },
                    {
                        "is_primary": False,
                        "venue_bookings": [{
                            "status": "approved",
                            "venue": {
                                "id": "a0000000-0000-4000-8000-000000000059",
                                "name": "Studio",
                                "location": "North",
                                "capacity": 40,
                            },
                        }],
                    },
                ],
            },
        },
    ]
    received_attendee_ids = []
    monkeypatch.setattr(
        repository,
        "list_attendee_registration_rows",
        lambda attendee_id: received_attendee_ids.append(attendee_id) or registrations,
        raising=False,
    )

    response = client.get("/api/v1/registrations/me", headers=auth_headers)

    assert response.status_code == 200
    assert received_attendee_ids == [attendee["id"]]
    results = response.json()["registrations"]
    assert [item["status"] for item in results] == ["registered", "waitlisted"]
    assert results[0]["event"]["name"] == "Community Design Forum"
    assert results[0]["event"]["withdrawal_closes_at"] == "2031-05-01T01:30:00Z"
    assert [venue["name"] for venue in results[0]["event"]["venues"]] == ["Central Hall"]
    assert [venue["name"] for venue in results[1]["event"]["venues"]] == ["Main Hall", "Studio"]


def test_only_the_active_attendee_role_can_read_their_registrations(
    client, authenticate_as, auth_headers
):
    authenticate_as("event_organiser")

    response = client.get("/api/v1/registrations/me", headers=auth_headers)

    assert response.status_code == 403


def test_attendee_with_no_current_registrations_receives_an_empty_list(
    client, authenticate_as, auth_headers, monkeypatch
):
    authenticate_as("attendee")
    monkeypatch.setattr(
        repository,
        "list_attendee_registration_rows",
        lambda attendee_id: [],
        raising=False,
    )

    response = client.get("/api/v1/registrations/me", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {"registrations": []}


def test_attendee_withdraws_their_own_registration_using_the_verified_identity(
    client, authenticate_as, auth_headers, monkeypatch
):
    attendee = authenticate_as("attendee")
    registration_id = "r0000000-0000-4000-8000-000000000055"
    event_id = "e0000000-0000-4000-8000-000000000055"
    calls = []
    monkeypatch.setattr(
        repository,
        "withdraw_registration",
        lambda received_event_id, attendee_id: calls.append((received_event_id, attendee_id))
        or {"outcome": "withdrawn", "registration_id": registration_id},
        raising=False,
    )

    response = client.post(
        f"/api/v1/registrations/{event_id}/withdraw",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json() == {"registration_id": registration_id, "status": "withdrawn"}
    assert calls == [(event_id, attendee["id"])]


def test_only_the_active_attendee_role_can_withdraw_a_registration(
    client, authenticate_as, auth_headers
):
    authenticate_as("event_organiser")

    response = client.post(
        "/api/v1/registrations/e0000000-0000-4000-8000-000000000055/withdraw",
        headers=auth_headers,
    )

    assert response.status_code == 403


@pytest.mark.parametrize(
    ("outcome", "status_code", "detail"),
    [
        ("cutoff_passed", 409, "The withdrawal cutoff has passed."),
        ("event_started", 409, "The event has started."),
        ("already_withdrawn", 409, "This registration has already been withdrawn."),
        ("not_registered", 409, "No active registration found."),
        ("unavailable", 404, "Event not found."),
    ],
)
def test_withdrawal_refusals_do_not_report_success(
    client, authenticate_as, auth_headers, monkeypatch, outcome, status_code, detail
):
    authenticate_as("attendee")
    monkeypatch.setattr(
        repository,
        "withdraw_registration",
        lambda event_id, attendee_id: {"outcome": outcome},
        raising=False,
    )

    response = client.post(
        "/api/v1/registrations/e0000000-0000-4000-8000-000000000055/withdraw",
        headers=auth_headers,
    )

    assert response.status_code == status_code
    assert response.json()["detail"] == detail


def test_unexpected_withdrawal_outcome_is_not_reported_as_success(
    client, authenticate_as, auth_headers, monkeypatch
):
    authenticate_as("attendee")
    monkeypatch.setattr(
        repository,
        "withdraw_registration",
        lambda event_id, attendee_id: {"outcome": "unexpected"},
        raising=False,
    )

    with pytest.raises(RuntimeError, match="Unexpected withdrawal outcome"):
        client.post(
            "/api/v1/registrations/e0000000-0000-4000-8000-000000000055/withdraw",
            headers=auth_headers,
        )
