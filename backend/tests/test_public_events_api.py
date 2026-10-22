"""Public event discovery and registration behaviour for Story 43."""

from app.modules.registrations.schemas import RegistrationResult


def test_public_event_directory_is_accessible_without_authentication(client, monkeypatch):
    monkeypatch.setattr("app.modules.registrations.service.public_directory", lambda: [])
    response = client.get("/api/v1/public/events")

    assert response.status_code == 200


def test_public_event_directory_returns_only_attendee_facing_fields(client, monkeypatch):
    event = {
        "id": "e0000000-0000-4000-8000-000000000043",
        "name": "Community Design Forum",
        "description": "A regional design gathering.",
        "starts_at": "2031-05-01T09:00:00+08:00",
        "ends_at": "2031-05-01T12:00:00+08:00",
        "event_timezone": "Asia/Singapore",
        "status": "confirmed",
        "availability": "open",
        "effective_capacity": 80,
        "registered_count": 12,
        "waitlist_enabled": True,
        "venues": [{
            "id": "a0000000-0000-4000-8000-000000000043",
            "name": "Central Hall",
            "location": "Downtown",
            "capacity": 100,
        }],
        "organiser_id": "internal-only",
        "preliminary_equipment_needs": "Internal technician note",
    }
    monkeypatch.setattr("app.modules.registrations.service.public_directory", lambda: [event])

    response = client.get("/api/v1/public/events")

    assert response.status_code == 200
    result = response.json()["events"][0]
    assert result["id"] == event["id"]
    assert result["name"] == event["name"]
    assert "organiser_id" not in result
    assert "preliminary_equipment_needs" not in result


def test_registration_requires_the_active_attendee_role(client, authenticate_as):
    organiser = authenticate_as("event_organiser")

    response = client.post(
        "/api/v1/public/events/e0000000-0000-4000-8000-000000000043/registrations",
        headers={"Authorization": "Bearer fake-access-token"},
    )

    assert organiser["role"] == "event_organiser"
    assert response.status_code == 403


def test_public_event_detail_is_accessible_without_authentication(client, monkeypatch):
    event_id = "e0000000-0000-4000-8000-000000000043"
    monkeypatch.setattr(
        "app.modules.registrations.service.public_event",
        lambda requested_id: {
            "id": requested_id,
            "name": "Community Design Forum",
            "event_timezone": "Asia/Singapore",
            "status": "preparation",
            "availability": "not_open",
            "registered_count": 0,
            "waitlist_enabled": True,
            "venues": [],
        },
    )

    response = client.get(f"/api/v1/public/events/{event_id}")

    assert response.status_code == 200
    assert response.json()["status"] == "preparation"


def test_attendee_registration_returns_immediate_confirmation(client, authenticate_as, monkeypatch):
    attendee = authenticate_as("attendee")
    monkeypatch.setattr(
        "app.modules.registrations.service.register_attendee",
        lambda event_id, attendee_id: RegistrationResult(
            registration_id="r0000000-0000-4000-8000-000000000043",
            status="registered",
            registered_at="2031-05-01T01:00:00Z",
        ),
    )

    response = client.post(
        "/api/v1/public/events/e0000000-0000-4000-8000-000000000043/registrations",
        headers={"Authorization": "Bearer fake-access-token"},
    )

    assert attendee["role"] == "attendee"
    assert response.status_code == 201
    assert response.json()["status"] == "registered"


def test_duplicate_attendee_registration_returns_ok(client, authenticate_as, monkeypatch):
    authenticate_as("attendee")
    monkeypatch.setattr(
        "app.modules.registrations.service.register_attendee",
        lambda event_id, attendee_id: RegistrationResult(
            registration_id="r0000000-0000-4000-8000-000000000043",
            status="already_registered",
            registered_at="2031-05-01T01:00:00Z",
        ),
    )

    response = client.post(
        "/api/v1/public/events/e0000000-0000-4000-8000-000000000043/registrations",
        headers={"Authorization": "Bearer fake-access-token"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "already_registered"
