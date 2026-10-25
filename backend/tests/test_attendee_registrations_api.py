"""Story 56 attendee registered-events API behaviour."""

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
