"""CR-111: GET /events/{id} gives the organiser each venue on their event (AC1 to AC4, AC6, AC7)."""
from copy import deepcopy
from types import SimpleNamespace

from app.modules.events import repository
from app.modules.venues import repository as venues_repository
from tests.test_event_review_api import COORDINATOR_ID, EVENT_ID, ORGANISER_ID, event_row

OTHER_ORGANISER_ID = "00000000-0000-4000-8000-0000000000ff"


def booking_row(booking_id="b-1", status="approved", **extra):
    return {
        "id": booking_id, "event_id": EVENT_ID, "event_space_request_id": None, "venue_id": "v-1",
        "status": status, "expires_at": None, "flag": None, "flag_reason": None,
        "replaces_booking_id": None, "needs_re_review_reason": None,
        "venues": {"name": "Marina Hall", "location": "1 Bayfront Ave"}, **extra,
    }


def read(client, auth_headers, authenticate_as, monkeypatch, row, bookings, role="event_organiser", user_id=ORGANISER_ID):
    monkeypatch.setattr(repository, "get_event", lambda event_id: deepcopy(row))
    monkeypatch.setattr(venues_repository, "list_active_bookings", lambda event_id: deepcopy(bookings))
    monkeypatch.setattr(repository, "get_open_reassignment_request", lambda event_id: None)
    monkeypatch.setattr(venues_repository, "get_active_booking", lambda event_id: deepcopy(bookings[0]) if bookings else None)
    authenticate_as(role, user_id=user_id)
    return client.get(f"/api/v1/events/{EVENT_ID}", headers=auth_headers)


def test_the_organiser_sees_a_venue_with_location_window_and_status(client, auth_headers, authenticate_as, monkeypatch):
    response = read(client, auth_headers, authenticate_as, monkeypatch, event_row("confirmed"), [booking_row()])

    assert response.status_code == 200
    venue = response.json()["organiser_venues"][0]
    assert venue["venue_name"] == "Marina Hall"
    assert venue["location"] == "1 Bayfront Ave"
    assert venue["status"] == "approved"
    assert venue["starts_at"].startswith("2026-11-12T10:00:00")


def test_an_affected_venue_is_visible_while_the_event_is_back_in_planning(client, auth_headers, authenticate_as, monkeypatch):
    # SCRUM-64 returns the event to Planning when its venue is deactivated; AC3 still has to show it.
    affected = booking_row(flag="affected", flag_reason="Venue unavailable: roof repairs")

    response = read(client, auth_headers, authenticate_as, monkeypatch, event_row("planning"), [affected])

    venue = response.json()["organiser_venues"][0]
    assert venue["status"] == "affected"
    assert "no longer available" in venue["next_action"]


def test_no_internal_detail_reaches_the_organiser(client, auth_headers, authenticate_as, monkeypatch):
    bookings = [booking_row(flag="affected", flag_reason="secret flag reason", replaces_booking_id="b-0",
                            needs_re_review_reason="secret re-review reason")]

    response = read(client, auth_headers, authenticate_as, monkeypatch, event_row("planning"), bookings)

    assert "secret" not in response.text


def test_an_event_still_under_review_lists_no_venues(client, auth_headers, authenticate_as, monkeypatch):
    response = read(client, auth_headers, authenticate_as, monkeypatch, event_row("under_review"), [booking_row()])

    assert response.json()["organiser_venues"] == []


def test_another_organiser_gets_404(client, auth_headers, authenticate_as, monkeypatch):
    response = read(client, auth_headers, authenticate_as, monkeypatch, event_row("confirmed"), [booking_row()],
                    user_id=OTHER_ORGANISER_ID)

    assert response.status_code == 404
    assert "Marina Hall" not in response.text


def test_the_coordinator_read_does_not_carry_the_organiser_list(client, auth_headers, authenticate_as, monkeypatch):
    response = read(client, auth_headers, authenticate_as, monkeypatch, event_row("under_review"), [booking_row()],
                    role="event_coordinator", user_id=COORDINATOR_ID)

    assert response.status_code == 200
    assert response.json()["organiser_venues"] == []


def test_an_organiser_acting_as_another_role_is_refused(client, auth_headers, authenticate_as, monkeypatch):
    # Active role, not held roles: a user acting as an attendee gets 403 even if they also organise.
    response = read(client, auth_headers, authenticate_as, monkeypatch, event_row("confirmed"), [booking_row()],
                    role="attendee")

    assert response.status_code == 403


def test_the_repository_reads_the_venue_location(monkeypatch):
    selected = []

    class Query:
        def table(self, name): return self
        def select(self, columns):
            selected.append(columns)
            return self
        def eq(self, field, value): return self
        def in_(self, field, values): return self
        def order(self, field): return self
        def execute(self): return SimpleNamespace(data=[])

    monkeypatch.setattr(venues_repository, "get_supabase_admin_client", lambda: Query())

    venues_repository.list_active_bookings(EVENT_ID)

    assert "venues!venue_bookings_venue_id_fkey(name, location)" in selected[0]


def test_the_coordinator_is_unassigned_until_one_is_assigned_then_named(client, auth_headers, authenticate_as, monkeypatch):
    unassigned = {**event_row("planning", coordinator_id=None), "coordinator": None}
    assigned = {**event_row("planning"), "coordinator": {"id": COORDINATOR_ID, "full_name": "Marcus Lim"}}
    reassigned = {**event_row("planning"), "coordinator": {"id": "other", "full_name": "Priya Nair"}}

    bodies = [read(client, auth_headers, authenticate_as, monkeypatch, row, []).json()
              for row in (unassigned, assigned, reassigned)]

    assert bodies[0]["coordinator"] is None and bodies[0]["coordinator_id"] is None
    assert bodies[1]["coordinator"]["full_name"] == "Marcus Lim"
    assert bodies[2]["coordinator"]["full_name"] == "Priya Nair"


# AC5 (CR-109 AC4): each venue's preparation stage, once the event is Confirmed, never the note.
def preparation(stage, note="secret staff preparation note"):
    return {"stage": stage, "note": note, "updated_at": "2026-11-10T09:00:00+08:00",
            "updater": {"full_name": "Venue Staff Member"}}


def test_each_venue_shows_its_preparation_stage_once_the_event_is_in_preparation(
        client, auth_headers, authenticate_as, monkeypatch):
    bookings = [booking_row("b-1", preparation=preparation("in_progress")), booking_row("b-2")]

    response = read(client, auth_headers, authenticate_as, monkeypatch, event_row("preparation"), bookings)

    assert response.status_code == 200
    assert [v["preparation_stage"] for v in response.json()["organiser_venues"]] == ["in_progress", "not_started"]


def test_a_confirmed_event_with_nothing_recorded_shows_not_started(client, auth_headers, authenticate_as, monkeypatch):
    response = read(client, auth_headers, authenticate_as, monkeypatch, event_row("confirmed"), [booking_row()])

    assert response.json()["organiser_venues"][0]["preparation_stage"] == "not_started"


def test_the_preparation_note_and_who_saved_it_never_reach_the_organiser(
        client, auth_headers, authenticate_as, monkeypatch):
    bookings = [booking_row(preparation=preparation("completed"))]

    response = read(client, auth_headers, authenticate_as, monkeypatch, event_row("preparation"), bookings)

    assert response.json()["organiser_venues"][0]["preparation_stage"] == "completed"
    assert "secret staff preparation note" not in response.text
    assert "Venue Staff Member" not in response.text


def test_no_preparation_stage_while_the_event_is_back_in_planning(client, auth_headers, authenticate_as, monkeypatch):
    # CR-109 AC7: progress is kept when the event returns to Planning, but it isn't shown until confirmed again.
    bookings = [booking_row(preparation=preparation("completed"))]

    response = read(client, auth_headers, authenticate_as, monkeypatch, event_row("planning"), bookings)

    assert response.json()["organiser_venues"][0]["preparation_stage"] is None
