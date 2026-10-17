"""The venues module's per-event reads, which other modules call (coordinator
dashboard, safety review). Each must ask the repository about the
event it was given; the API tests that use them answer the same rows whatever
id arrives, so they can't tell."""

from app.modules.venues import repository, service

EVENT_ID = "e0000000-0000-4000-8000-000000000301"
OTHER_EVENT_ID = "e0000000-0000-4000-8000-000000000302"
VENUE_ID = "b0000000-0000-4000-8000-000000000001"


def test_booking_statuses_are_read_for_the_events_given(monkeypatch):
    asked = []

    def _statuses(event_ids):
        asked.append(list(event_ids))
        return [{"event_id": EVENT_ID, "status": "held"}, {"event_id": EVENT_ID, "status": "approved"}]

    monkeypatch.setattr(repository, "list_booking_statuses", _statuses)

    assert service.booking_statuses_by_event([EVENT_ID, OTHER_EVENT_ID]) == {EVENT_ID: ["held", "approved"]}
    assert asked == [[EVENT_ID, OTHER_EVENT_ID]]


def test_bookings_with_venues_are_read_for_the_event_given(monkeypatch):
    row = {"id": "d1", "venue_id": VENUE_ID, "status": "approved",
           "venues": {"name": "Hall A", "capacity": 150, "venue_layouts": [{"layout": "theatre"}]}}
    monkeypatch.setattr(repository, "list_event_bookings_with_venues", lambda event_id: [row] if event_id == EVENT_ID else [])

    [item] = service.event_bookings_with_venues(EVENT_ID)

    assert item["venue_name"] == "Hall A"
    assert item["layouts"] == ["theatre"]

