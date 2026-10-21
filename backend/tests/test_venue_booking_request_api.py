"""SCRUM-19 venue booking request, through the HTTP API with the repositories mocked.

The refusals themselves (overlap, block, one venue per event, lifecycle) are
decided by `public.request_venue_booking` and proven against the real database
in `supabase/verification/venue_booking_request_checks.sql`. Here the fake
returns each of the function's outcome codes, and the tests pin down what the
API makes of them.
"""

from copy import deepcopy
from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace

import pytest
from postgrest.exceptions import APIError

from app.modules.events import repository as events_repository
from app.modules.events import service as events_service
from app.modules.venues import repository as venues_repository
from app.modules.venues import service as venues_service
from app.modules.venues.schemas import Facility, LayoutOption, VenueLayout
from tests.test_venues_api import make_venue_profile

COORDINATOR_ID = "a0000000-0000-4000-8000-000000000002"
OTHER_COORDINATOR_ID = "a0000000-0000-4000-8000-000000000009"
ORGANISER_ID = "a0000000-0000-4000-8000-000000000001"
EVENT_ID = "e0000000-0000-4000-8000-000000000202"
VENUE_ID = "b0000000-0000-4000-8000-000000000006"
BOOKING_ID = "d0000000-0000-4000-8000-000000000999"
SPACE_ID = "f0000000-0000-4000-8000-000000000001"
URL = "/api/v1/venue-bookings"


def event_row(status="planning", coordinator_id=COORDINATOR_ID):
    now = datetime.now(timezone.utc).isoformat()
    starts = datetime.now(timezone.utc) + timedelta(days=30)
    return {
        "id": EVENT_ID, "organiser_id": ORGANISER_ID, "coordinator_id": coordinator_id,
        "status": status, "event_timezone": "Asia/Singapore", "name": "Partner Summit",
        "purpose": "Quarterly partner meeting", "description": None,
        "starts_at": starts.isoformat(), "ends_at": (starts + timedelta(hours=3)).isoformat(),
        "expected_attendance": 40, "layout_preference": "classroom", "facilities_required": ["projector"],
        "accessibility_needs": None, "preliminary_equipment_needs": None,
        "registration_enabled": False, "registration_capacity": None,
        "registration_opens_at": None, "registration_closes_at": None,
        "technical_readiness": "not_required", "submitted_at": now, "version": 4,
        "created_at": now, "updated_at": now,
    }


@pytest.fixture(autouse=True)
def a_venue_that_suits_the_event(monkeypatch):
    """SCRUM-18 BR-R3: a request is checked for suitability first, so the venue
    is read. This one suits `event_row`'s default (classroom, projector, any
    hour); a test that needs another venue patches `get_venue` itself."""
    venue = make_venue_profile(
        VENUE_ID, "Innovation Lab", facilities=[Facility.projector], opens_at=time(0, 0), closes_at=time(23, 59, 59),
        layouts=[LayoutOption(layout=VenueLayout.classroom, capacity_for_layout=None)],
    )
    monkeypatch.setattr(venues_repository, "get_venue", lambda venue_id: venue)


@pytest.fixture()
def booking(monkeypatch):
    """An in-memory event; `request_booking` records each call and answers with
    `state["outcome"]`, the way the database function answers."""
    state = {"event": event_row(), "outcome": "ok", "calls": []}

    def request_booking(event_id, venue_id, actor_id, note, *, notify_message):
        state["calls"].append({"event_id": event_id, "venue_id": venue_id, "actor_id": actor_id,
                               "note": note, "notify_message": notify_message})
        booking_id = BOOKING_ID if state["outcome"] == "ok" else None
        return {"outcome": state["outcome"], "booking_id": booking_id}

    monkeypatch.setattr(venues_repository, "list_booking_statuses", lambda event_ids: [])
    monkeypatch.setattr(events_repository, "get_event",
                        lambda event_id: deepcopy(state["event"]) if event_id == EVENT_ID else None)
    monkeypatch.setattr(venues_repository, "request_booking", request_booking)
    return state


def post(client, auth_headers, **body):
    payload = {"event_id": EVENT_ID, "venue_id": VENUE_ID, **body}
    return client.post(URL, json=payload, headers=auth_headers)


def post_for_space(client, auth_headers, space_id=SPACE_ID, **body):
    payload = {"event_space_request_id": space_id, "venue_id": VENUE_ID, **body}
    return client.post(URL, json=payload, headers=auth_headers)


class TestRequest:
    def test_a_space_request_can_hold_a_venue_independently(self, client, auth_headers, authenticate_as, booking, monkeypatch):
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)
        calls = []
        checked = []
        monkeypatch.setattr(
            events_service,
            "assigned_space",
            lambda space_id, coordinator_id: checked.append((space_id, coordinator_id))
            or (deepcopy(booking["event"]), {"id": space_id}),
        )

        def request_booking_for_space(space_id, venue_id, actor_id, note, *, notify_message):
            calls.append((space_id, venue_id, actor_id, note, notify_message))
            return {"outcome": "ok", "booking_id": BOOKING_ID}

        monkeypatch.setattr(venues_repository, "request_booking_for_space", request_booking_for_space)

        response = post_for_space(client, auth_headers, note="Breakout room")

        assert response.status_code == 201
        assert response.json()["event_space_request_id"] == SPACE_ID
        assert checked == [(SPACE_ID, COORDINATOR_ID)]
        assert calls == [
            (SPACE_ID, VENUE_ID, COORDINATOR_ID, "Breakout room", 'A venue booking was requested for "Partner Summit".')
        ]

    # CR-97 AC10 / BR-R16: the database refuses a venue too small for the space
    # (event_space_checks.sql); the API says how far short it falls.
    @pytest.mark.parametrize("layout,seats", [("classroom", 60), ("theatre", 80)])
    def test_a_venue_too_small_for_the_space_is_refused_with_its_capacity(
        self, client, auth_headers, authenticate_as, booking, monkeypatch, layout, seats
    ):
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)
        space = {"id": SPACE_ID, "event_id": EVENT_ID, "label": "Breakout room",
                 "expected_pax": 90, "layout_preference": layout}
        monkeypatch.setattr(events_service, "assigned_space",
                            lambda space_id, coordinator_id: (deepcopy(booking["event"]), space))
        monkeypatch.setattr(venues_repository, "request_booking_for_space",
                            lambda *args, **kwargs: {"outcome": "over_capacity", "booking_id": None})
        monkeypatch.setattr(venues_repository, "get_venue", lambda venue_id: make_venue_profile(
            VENUE_ID, "Innovation Lab", capacity=80,
            layouts=[LayoutOption(layout="classroom", capacity_for_layout=60)]))

        response = post_for_space(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == f"Innovation Lab seats {seats}; this space needs 90."

    # CR-97: an event-only request (the pre-CR-98 shape) books the event's first
    # space, so it gets the same per-space rules as a space request.
    def test_an_event_only_request_books_the_events_first_space(
        self, client, auth_headers, authenticate_as, booking, monkeypatch
    ):
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)
        booking["event"]["spaces"] = [
            {"id": SPACE_ID, "event_id": EVENT_ID, "label": "Main space", "expected_pax": 40, "layout_preference": "classroom"},
            {"id": "f0000000-0000-4000-8000-000000000002", "event_id": EVENT_ID, "label": "Breakout room",
             "expected_pax": 10, "layout_preference": None},
        ]
        space_calls = []

        def request_booking_for_space(space_id, venue_id, actor_id, note, *, notify_message):
            space_calls.append((space_id, venue_id, actor_id, note))
            return {"outcome": "ok", "booking_id": BOOKING_ID}

        monkeypatch.setattr(venues_repository, "request_booking_for_space", request_booking_for_space)

        response = post(client, auth_headers, note="Main room")

        assert response.status_code == 201
        assert response.json()["event_space_request_id"] == SPACE_ID
        assert space_calls == [(SPACE_ID, VENUE_ID, COORDINATOR_ID, "Main room")]
        assert booking["calls"] == []

    def test_the_assigned_coordinator_holds_a_venue_and_venue_staff_are_told(
        self, client, auth_headers, authenticate_as, booking
    ):
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        response = post(client, auth_headers, note="  Need early access at 13:00  ")

        assert response.status_code == 201
        assert response.json() == {
            "id": BOOKING_ID, "event_id": EVENT_ID, "venue_id": VENUE_ID,
            "event_space_request_id": None,
            "status": "held", "note": "Need early access at 13:00",
        }
        [sent] = booking["calls"]
        # The period is never the client's to choose: the function takes it
        # from the event, so the API passes ids, the caller and the note only.
        assert sent == {
            "event_id": EVENT_ID, "venue_id": VENUE_ID, "actor_id": COORDINATOR_ID,
            "note": "Need early access at 13:00",
            "notify_message": 'A venue booking was requested for "Partner Summit".',
        }

    @pytest.mark.parametrize(
        ("outcome", "status_code", "detail"),
        [
            # AC2, BR-R2 (QA-6, QA-10): first come, first served, no override.
            ("held_by_other", 409, "Venue already held for this time by another event."),
            # AC2, §6.14.
            ("blocked", 409, "Venue blocked for this time."),
            # SCRUM-64 AC2: an inactive venue takes no new requests.
            ("venue_inactive", 409, "This venue is inactive."),
            # AC4, BR-R1 (QA-116, QA-135).
            ("already_booked", 409, "This event already has a venue booking."),
            # AC5, BR-R6 (QA-22).
            ("returned", 409, "Requirements are still being amended."),
            ("no_period", 409, "This event has no start and end time to hold a venue for."),
            ("venue_not_found", 404, "Venue not found."),
        ],
    )
    def test_a_refusal_from_the_database_is_answered_with_its_message(
        self, client, auth_headers, authenticate_as, booking, outcome, status_code, detail
    ):
        booking["outcome"] = outcome
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        response = post(client, auth_headers)

        assert response.status_code == status_code
        assert response.json()["detail"] == detail

    # SCRUM-21 AC2: the refusal names what is in the way, as the database
    # function reports it (booking_conflict_checks.sql): the other event's name
    # and its occupied window, or the block's reason. Nothing else about it.
    @pytest.mark.parametrize(
        ("outcome", "conflict", "expected"),
        [
            ("held_by_other",
             {"kind": "booking", "event_name": "Alumni Night", "block_reason": None,
              "starts_at": "2031-04-07T01:30:00+00:00", "ends_at": "2031-04-07T04:45:00+00:00"},
             {"kind": "booking", "event_name": "Alumni Night", "block_reason": None,
              "starts_at": "2031-04-07T01:30:00Z", "ends_at": "2031-04-07T04:45:00Z"}),
            ("blocked",
             {"kind": "block", "event_name": None, "block_reason": "maintenance",
              "starts_at": "2031-04-08T02:00:00+00:00", "ends_at": "2031-04-08T04:00:00+00:00"},
             {"kind": "block", "event_name": None, "block_reason": "maintenance",
              "starts_at": "2031-04-08T02:00:00Z", "ends_at": "2031-04-08T04:00:00Z"}),
        ],
    )
    @pytest.mark.parametrize("path", ["event", "space"])
    def test_a_conflict_refusal_names_what_is_in_the_way(
        self, client, auth_headers, authenticate_as, booking, monkeypatch, outcome, conflict, expected, path
    ):
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)
        answer = {"outcome": outcome, "booking_id": None, "conflict": conflict}
        monkeypatch.setattr(venues_repository, "request_booking", lambda *args, **kwargs: answer)
        monkeypatch.setattr(venues_repository, "request_booking_for_space", lambda *args, **kwargs: answer)
        monkeypatch.setattr(events_service, "assigned_space",
                            lambda space_id, coordinator_id: (deepcopy(booking["event"]), {"id": space_id}))

        response = post(client, auth_headers) if path == "event" else post_for_space(client, auth_headers)

        assert response.status_code == 409
        assert response.json() == {"detail": venues_service.BOOKING_REFUSALS[outcome], "conflict": expected}

    def test_a_refusal_with_nothing_in_the_way_carries_no_conflict(
        self, client, auth_headers, authenticate_as, booking
    ):
        # A lost race whose winner is already gone (Q13), or any other refusal.
        booking["outcome"] = "held_by_other"
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        response = post(client, auth_headers)

        assert response.status_code == 409
        assert response.json() == {"detail": "Venue already held for this time by another event."}

    @pytest.mark.parametrize("status", ["under_review", "confirmed", "rejected"])
    def test_an_event_outside_planning_is_refused_naming_its_status(
        self, client, auth_headers, authenticate_as, booking, status
    ):
        # AC5, BR-R6: only a planning event can hold a venue.
        booking["event"]["status"] = status
        booking["outcome"] = "not_planning"
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        response = post(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == (
            f"Cannot request a venue for an event that is {status.replace('_', ' ')}."
        )

    @pytest.mark.parametrize(("outcome", "status_code"), [("not_assigned", 403), ("event_not_found", 404)])
    def test_a_change_between_the_api_check_and_the_hold_still_refuses(
        self, client, auth_headers, authenticate_as, booking, outcome, status_code
    ):
        # The event was reassigned or removed after the API read it; the
        # function re-checks under its lock and the API reports what it found.
        booking["outcome"] = outcome
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        assert post(client, auth_headers).status_code == status_code


class TestWhoMayRequest:
    def test_a_coordinator_who_is_not_assigned_is_forbidden(self, client, auth_headers, authenticate_as, booking):
        # AC6: role alone isn't enough; it has to be this event's coordinator.
        booking["event"]["coordinator_id"] = OTHER_COORDINATOR_ID
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        response = post(client, auth_headers)

        assert response.status_code == 403
        assert booking["calls"] == []

    @pytest.mark.parametrize("event_id", [EVENT_ID, "e0000000-0000-4000-8000-0000000000ff"])
    def test_a_draft_or_missing_event_is_not_found(self, client, auth_headers, authenticate_as, booking, event_id):
        # Drafts are private to their organiser (DR-R2), so they look missing.
        booking["event"]["status"] = "draft"
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        response = client.post(URL, json={"event_id": event_id, "venue_id": VENUE_ID}, headers=auth_headers)

        assert response.status_code == 404
        assert booking["calls"] == []

    @pytest.mark.parametrize("role", ["event_organiser", "venue_staff", "tech_support", "attendee"])
    def test_every_other_role_is_forbidden(self, client, auth_headers, authenticate_as, booking, role):
        authenticate_as(role, user_id=COORDINATOR_ID)

        assert post(client, auth_headers).status_code == 403
        assert booking["calls"] == []

    def test_a_coordinator_acting_as_venue_staff_is_forbidden(self, client, auth_headers, monkeypatch, booking):
        # AC6, SCRUM-76: the seeded coordinator also holds venue_staff. Acting
        # as venue staff, they can't request a venue even for their own event.
        from tests.test_event_comments_api import acting_as_another_role

        acting_as_another_role(monkeypatch, COORDINATOR_ID, holds="event_coordinator", acts_as="venue_staff")

        assert post(client, auth_headers).status_code == 403
        assert booking["calls"] == []

    def test_an_unauthenticated_request_is_refused(self, client, booking):
        assert client.post(URL, json={"event_id": EVENT_ID, "venue_id": VENUE_ID}).status_code == 401



def test_space_booking_repository_calls_the_space_rpc_with_its_parameters(monkeypatch):
    calls = []

    class Rpc:
        def execute(self):
            return SimpleNamespace(data=[{"outcome": "ok", "booking_id": BOOKING_ID}])

    class AdminClient:
        def rpc(self, name, params):
            calls.append((name, params))
            return Rpc()

    monkeypatch.setattr(venues_repository, "get_supabase_admin_client", lambda: AdminClient())

    result = venues_repository.request_booking_for_space(
        SPACE_ID, VENUE_ID, COORDINATOR_ID, "Breakout room", notify_message="requested",
    )

    assert result == {"outcome": "ok", "booking_id": BOOKING_ID}
    assert calls == [("request_venue_booking_for_space", {
        "p_event_space_request_id": SPACE_ID,
        "p_venue_id": VENUE_ID,
        "p_actor_id": COORDINATOR_ID,
        "p_note": "Breakout room",
        "p_notify_message": "requested",
    })]


def test_list_active_bookings_reads_rows_and_returns_empty_on_schema_read_failure(monkeypatch):
    rows = [{
        "id": BOOKING_ID,
        "event_id": EVENT_ID,
        "event_space_request_id": SPACE_ID,
        "venue_id": VENUE_ID,
        "status": "held",
    }]

    class Query:
        def __init__(self, response=None, error=None):
            self.response = response
            self.error = error
            self.calls = []

        def select(self, value):
            self.calls.append(("select", value))
            return self

        def eq(self, field, value):
            self.calls.append(("eq", field, value))
            return self

        def in_(self, field, values):
            self.calls.append(("in", field, values))
            return self

        def order(self, field):
            self.calls.append(("order", field))
            return self

        def execute(self):
            if self.error:
                raise self.error
            return self.response

    class AdminClient:
        def __init__(self, query):
            self.query = query

        def table(self, name):
            assert name == "venue_bookings"
            return self.query

    query = Query(SimpleNamespace(data=rows))
    monkeypatch.setattr(venues_repository, "get_supabase_admin_client", lambda: AdminClient(query))
    assert venues_repository.list_active_bookings(EVENT_ID) == rows
    assert ("eq", "event_id", EVENT_ID) in query.calls
    assert ("order", "created_at") in query.calls

    query.response = SimpleNamespace(data=None)
    assert venues_repository.list_active_bookings(EVENT_ID) == []

    failed_query = Query(error=APIError({"code": "PGRST204", "message": "column not available during rollout"}))
    monkeypatch.setattr(venues_repository, "get_supabase_admin_client", lambda: AdminClient(failed_query))
    assert venues_repository.list_active_bookings(EVENT_ID) == []

    failed_query = Query(error=RuntimeError("database unavailable"))
    monkeypatch.setattr(venues_repository, "get_supabase_admin_client", lambda: AdminClient(failed_query))
    with pytest.raises(RuntimeError, match="database unavailable"):
        venues_repository.list_active_bookings(EVENT_ID)


def test_active_bookings_for_event_maps_each_space_booking(monkeypatch):
    row = {
        "id": BOOKING_ID,
        "event_id": EVENT_ID,
        "event_space_request_id": SPACE_ID,
        "venue_id": VENUE_ID,
        "status": "held",
        "venues": {"name": "Innovation Lab"},
    }
    monkeypatch.setattr(venues_repository, "list_active_bookings", lambda event_id: [row] if event_id == EVENT_ID else [])

    assert venues_service.active_bookings_for_event(EVENT_ID) == [{
        "id": BOOKING_ID,
        "event_id": EVENT_ID,
        "event_space_request_id": SPACE_ID,
        "venue_id": VENUE_ID,
        "venue_name": "Innovation Lab",
        "status": "held",
        "expires_at": None,
        "flag": None,
        "flag_reason": None,
        "replaces_booking_id": None,
    }]


def test_an_affected_booking_and_its_replacement_are_both_listed(monkeypatch):
    # CR-95 AC4: the coordinator sees the affected booking and the replacement
    # asked for beside it, for the same space.
    affected = {
        "id": AFFECTED_BOOKING_ID, "event_id": EVENT_ID, "event_space_request_id": SPACE_ID, "venue_id": VENUE_ID,
        "status": "approved", "venues": {"name": "Seminar Room 1"}, "flag": "affected",
        "flag_reason": "Venue unavailable: Maintenance", "replaces_booking_id": None,
    }
    replacement_row = {
        "id": BOOKING_ID, "event_id": EVENT_ID, "event_space_request_id": SPACE_ID, "venue_id": VENUE_ID,
        "status": "held", "venues": {"name": "Innovation Lab"}, "flag": None, "flag_reason": None,
        "replaces_booking_id": AFFECTED_BOOKING_ID,
    }
    monkeypatch.setattr(venues_repository, "list_active_bookings", lambda event_id: [affected, replacement_row])

    shown = venues_service.active_bookings_for_event(EVENT_ID)

    assert [(b["id"], b["flag"], b["replaces_booking_id"]) for b in shown] == [
        (AFFECTED_BOOKING_ID, "affected", None),
        (BOOKING_ID, None, AFFECTED_BOOKING_ID),
    ]
    assert shown[0]["flag_reason"] == "Venue unavailable: Maintenance"


def test_the_events_single_booking_summary_carries_the_flag(monkeypatch):
    row = {
        "id": AFFECTED_BOOKING_ID, "event_space_request_id": None, "venue_id": VENUE_ID, "status": "approved",
        "expires_at": None, "venues": {"name": "Seminar Room 1"}, "flag": "affected",
        "flag_reason": "Venue unavailable: Maintenance", "replaces_booking_id": None,
    }
    monkeypatch.setattr(venues_repository, "get_active_booking", lambda event_id: row)

    summary = venues_service.active_booking_for_event(EVENT_ID)

    assert (summary["flag"], summary["flag_reason"], summary["replaces_booking_id"]) == (
        "affected", "Venue unavailable: Maintenance", None)

class TestRequestBody:
    def test_the_note_is_optional(self, client, auth_headers, authenticate_as, booking):
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        response = post(client, auth_headers)

        assert response.status_code == 201
        assert response.json()["note"] is None
        assert booking["calls"][0]["note"] is None

    def test_a_blank_note_is_stored_as_no_note(self, client, auth_headers, authenticate_as, booking):
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        assert post(client, auth_headers, note="   ").status_code == 201
        assert booking["calls"][0]["note"] is None

    def test_a_note_is_capped_at_1000_characters(self, client, auth_headers, authenticate_as, booking):
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        assert post(client, auth_headers, note="x" * 1000).status_code == 201
        assert post(client, auth_headers, note="x" * 1001).status_code == 422
        assert len(booking["calls"]) == 1

    @pytest.mark.parametrize("missing", ["event_id", "venue_id"])
    def test_the_event_and_venue_are_required(self, client, auth_headers, authenticate_as, booking, missing):
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)
        payload = {"event_id": EVENT_ID, "venue_id": VENUE_ID}
        del payload[missing]

        assert client.post(URL, json=payload, headers=auth_headers).status_code == 422
        assert booking["calls"] == []

    def test_a_client_supplied_period_is_ignored(self, client, auth_headers, authenticate_as, booking):
        # The hold always covers the event's own period (§6.12); nothing in the
        # body can widen or move it.
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        response = post(client, auth_headers, starts_at="2026-01-01T00:00:00+08:00", ends_at="2027-01-01T00:00:00+08:00")

        assert response.status_code == 201
        assert set(booking["calls"][0]) == {"event_id", "venue_id", "actor_id", "note", "notify_message"}


class TestEventShowsItsBooking:
    """The coordinator's event page shows the venue the event holds, so the
    request has somewhere to land and a second request isn't offered."""

    @pytest.fixture()
    def held(self, monkeypatch, booking):
        row = {"id": BOOKING_ID, "venue_id": VENUE_ID, "status": "held",
               "expires_at": "2026-11-01T04:00:00+00:00", "venues": {"name": "Innovation Lab"}}
        monkeypatch.setattr(venues_repository, "get_active_booking",
                            lambda event_id: deepcopy(row) if event_id == EVENT_ID else None)
        return row

    def test_the_assigned_coordinator_sees_the_held_venue(self, client, auth_headers, authenticate_as, held):
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        response = client.get(f"/api/v1/events/{EVENT_ID}", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["venue_booking"] == {
            "id": BOOKING_ID, "event_space_request_id": None, "venue_id": VENUE_ID,
            "venue_name": "Innovation Lab", "status": "held",
            # CR-99 AC3: the coordinator sees when the hold runs out.
            "expires_at": "2026-11-01T04:00:00Z",
            "flag": None, "flag_reason": None, "replaces_booking_id": None,
        }

    def test_an_expired_hold_is_shown_so_the_venue_can_be_requested_again(
        self, client, auth_headers, authenticate_as, monkeypatch, booking
    ):
        # CR-99 AC7: with nothing active, the event shows its expired hold
        # rather than looking as if no venue had ever been requested.
        row = {
            "id": BOOKING_ID,
            "event_space_request_id": SPACE_ID,
            "venue_id": VENUE_ID,
            "status": "expired",
            "expires_at": "2026-10-01T04:00:00+00:00",
            "venues": {"name": "Innovation Lab"},
        }
        monkeypatch.setattr(venues_repository, "get_active_booking", lambda event_id: deepcopy(row))
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        response = client.get(f"/api/v1/events/{EVENT_ID}", headers=auth_headers)

        assert response.json()["venue_booking"]["status"] == "expired"
        assert response.json()["venue_booking"]["expires_at"] == "2026-10-01T04:00:00Z"
        assert response.json()["venue_booking"]["event_space_request_id"] == SPACE_ID

    def test_each_space_shows_its_occupying_booking_or_else_its_latest_expired_hold(
        self, client, auth_headers, authenticate_as, monkeypatch, booking
    ):
        # CR-97 AC5 with CR-99 AC3/AC7: each space card needs its own hold's
        # expiry, and an expired hold's explanation, on a multi-space event.
        other, third = "f0000000-0000-4000-8000-000000000002", "f0000000-0000-4000-8000-000000000003"

        def row(booking_id, space_id, status, expires_at):
            return {"id": booking_id, "event_id": EVENT_ID, "event_space_request_id": space_id, "venue_id": VENUE_ID,
                    "status": status, "expires_at": expires_at, "venues": {"name": "Innovation Lab"}}

        rows = [  # oldest first, as the query orders them
            row("b1", SPACE_ID, "held", "2026-11-01T04:00:00+00:00"),
            row("b2", other, "expired", "2026-10-01T04:00:00+00:00"),
            row("b3", third, "expired", "2026-10-02T04:00:00+00:00"),
            row("b4", third, "approved", None),
            row("b5", SPACE_ID, "expired", "2026-10-03T04:00:00+00:00"),  # an occupying booking still wins
        ]
        monkeypatch.setattr(venues_repository, "list_active_bookings", lambda event_id: deepcopy(rows))
        monkeypatch.setattr(venues_repository, "get_active_booking", lambda event_id: None)
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        response = client.get(f"/api/v1/events/{EVENT_ID}", headers=auth_headers)

        shown = {(b["event_space_request_id"], b["id"], b["status"], b["expires_at"]) for b in response.json()["venue_bookings"]}
        assert shown == {
            (SPACE_ID, "b1", "held", "2026-11-01T04:00:00Z"),
            (other, "b2", "expired", "2026-10-01T04:00:00Z"),
            (third, "b4", "approved", None),
        }

    def test_an_expired_space_hold_keeps_its_space_id(self, monkeypatch):
        row = {
            "id": BOOKING_ID,
            "event_space_request_id": SPACE_ID,
            "venue_id": VENUE_ID,
            "status": "expired",
            "expires_at": "2026-10-01T04:00:00+00:00",
            "venues": {"name": "Innovation Lab"},
        }
        calls = []

        class Query:
            def select(self, columns):
                calls.append(("select", columns))
                return self

            def eq(self, field, value):
                return self

            def in_(self, field, values):
                return self

            def order(self, field, *, desc=False):
                return self

            def execute(self):
                return SimpleNamespace(data=[row])

        class AdminClient:
            def table(self, name):
                assert name == "venue_bookings"
                return Query()

        monkeypatch.setattr(venues_repository, "get_supabase_admin_client", lambda: AdminClient())

        assert venues_repository.get_active_booking(EVENT_ID) == row
        assert "event_space_request_id" in calls[0][1]

    def test_an_event_without_a_venue_says_so(self, client, auth_headers, authenticate_as, monkeypatch, booking):
        monkeypatch.setattr(venues_repository, "get_active_booking", lambda event_id: None)
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        response = client.get(f"/api/v1/events/{EVENT_ID}", headers=auth_headers)

        assert response.json()["venue_booking"] is None

    def test_the_organiser_does_not_see_booking_state(self, client, auth_headers, authenticate_as, held, booking):
        # AUTH-R2 (QA-51): booking state is internal planning detail.
        booking["event"]["organiser_id"] = ORGANISER_ID
        authenticate_as("event_organiser", user_id=ORGANISER_ID)

        response = client.get(f"/api/v1/events/{EVENT_ID}", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["venue_booking"] is None


# CR-95 AC4, AC7: a replacement for an affected booking. The overlap, link and
# one-at-a-time rules are the database's (venue_replacement_checks.sql); here
# the fakes pin the API's own part: who may ask, which bookings it will try to
# replace, and that a Confirmed or Safety-review event goes back to planning
# first, since the database function only accepts a planning event.
AFFECTED_BOOKING_ID = "d0000000-0000-4000-8000-000000000a01"


@pytest.fixture()
def replacement(monkeypatch, booking):
    """Records the order of the calls and answers `get_replaceable_booking` and the request from `state`."""
    state = {
        "order": [],
        "returned": [],
        "requests": [],
        "outcome": "ok",
        "return_error": None,
        "replaceable": {
            "id": AFFECTED_BOOKING_ID, "event_id": EVENT_ID, "event_space_request_id": None,
            "status": "approved", "flag": "affected",
        },
    }

    def request_booking(event_id, venue_id, actor_id, note, *, notify_message, replaces_booking_id=None):
        state["order"].append("request")
        state["requests"].append({"event_id": event_id, "replaces_booking_id": replaces_booking_id})
        return {"outcome": state["outcome"], "booking_id": BOOKING_ID if state["outcome"] == "ok" else None}

    def request_booking_for_space(space_id, venue_id, actor_id, note, *, notify_message, replaces_booking_id=None):
        state["order"].append("request")
        state["requests"].append({"space_id": space_id, "replaces_booking_id": replaces_booking_id})
        return {"outcome": state["outcome"], "booking_id": BOOKING_ID if state["outcome"] == "ok" else None}

    def return_to_planning(event_id, *, reason_code, message=None, actor_id=None):
        state["order"].append("return")
        if state["return_error"]:
            raise state["return_error"]
        state["returned"].append((event_id, reason_code))

    monkeypatch.setattr(venues_repository, "get_replaceable_booking", lambda booking_id: state["replaceable"]
                        if state["replaceable"] and booking_id == AFFECTED_BOOKING_ID else None)
    monkeypatch.setattr(venues_repository, "request_booking", request_booking)
    monkeypatch.setattr(venues_repository, "request_booking_for_space", request_booking_for_space)
    monkeypatch.setattr(events_service, "return_to_planning", return_to_planning)
    state["event"] = booking["event"]
    state["booking"] = booking
    return state


class TestReplacement:
    def test_a_replacement_on_a_planning_event_is_requested_and_linked(
        self, client, auth_headers, authenticate_as, replacement
    ):
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        response = post(client, auth_headers, replaces_booking_id=AFFECTED_BOOKING_ID)

        assert response.status_code == 201
        assert replacement["requests"] == [{"event_id": EVENT_ID, "replaces_booking_id": AFFECTED_BOOKING_ID}]
        assert replacement["order"] == ["request"]

    @pytest.mark.parametrize("status", ["confirmed", "safety_review"])
    def test_a_confirmed_or_safety_review_event_returns_to_planning_before_the_request(
        self, client, auth_headers, authenticate_as, replacement, status
    ):
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)
        replacement["event"]["status"] = status

        response = post(client, auth_headers, replaces_booking_id=AFFECTED_BOOKING_ID)

        assert response.status_code == 201
        assert replacement["returned"] == [(EVENT_ID, "arrangement_flagged")]
        assert replacement["order"] == ["return", "request"]

    def test_a_replacement_for_a_space_links_that_spaces_booking(
        self, client, auth_headers, authenticate_as, replacement, monkeypatch
    ):
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)
        replacement["replaceable"]["event_space_request_id"] = SPACE_ID
        monkeypatch.setattr(events_service, "assigned_space",
                            lambda space_id, coordinator_id: (deepcopy(replacement["event"]), {"id": space_id}))

        response = post_for_space(client, auth_headers, replaces_booking_id=AFFECTED_BOOKING_ID)

        assert response.status_code == 201
        assert replacement["requests"] == [{"space_id": SPACE_ID, "replaces_booking_id": AFFECTED_BOOKING_ID}]

    @pytest.mark.parametrize(
        "override",
        [
            {"flag": None},
            {"flag": "unsuitable"},
            {"status": "released"},
            {"event_id": "e0000000-0000-4000-8000-000000000999"},
            {"event_space_request_id": "f0000000-0000-4000-8000-0000000000ff"},
        ],
    )
    def test_only_the_events_own_affected_live_booking_can_be_replaced(
        self, client, auth_headers, authenticate_as, replacement, override
    ):
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)
        replacement["event"]["status"] = "confirmed"
        replacement["replaceable"].update(override)

        response = post(client, auth_headers, replaces_booking_id=AFFECTED_BOOKING_ID)

        assert response.status_code == 409
        assert "replacement" in response.json()["detail"].lower()
        # Nothing was changed on the way to refusing: the event stays confirmed.
        assert replacement["order"] == []

    def test_an_unknown_booking_is_a_404_and_changes_nothing(
        self, client, auth_headers, authenticate_as, replacement
    ):
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)
        replacement["event"]["status"] = "confirmed"

        response = post(client, auth_headers, replaces_booking_id="d0000000-0000-4000-8000-000000000bad")

        assert response.status_code == 404
        assert replacement["order"] == []

    def test_a_failed_return_to_planning_requests_nothing(
        self, client, auth_headers, authenticate_as, replacement
    ):
        from app.core.exceptions import EventServiceUnavailableError

        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)
        replacement["event"]["status"] = "confirmed"
        replacement["return_error"] = EventServiceUnavailableError()

        response = post(client, auth_headers, replaces_booking_id=AFFECTED_BOOKING_ID)

        assert response.status_code == 503
        assert replacement["requests"] == []

    def test_the_database_refusing_the_link_is_a_409(self, client, auth_headers, authenticate_as, replacement):
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)
        replacement["outcome"] = "replaced_booking_invalid"

        response = post(client, auth_headers, replaces_booking_id=AFFECTED_BOOKING_ID)

        assert response.status_code == 409

    def test_a_request_without_the_link_never_returns_the_event_to_planning(
        self, client, auth_headers, authenticate_as, replacement
    ):
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)
        replacement["event"]["status"] = "confirmed"
        replacement["outcome"] = "not_planning"

        response = post(client, auth_headers)

        assert response.status_code == 409
        assert replacement["returned"] == []

    def test_only_this_events_coordinator_may_ask(self, client, auth_headers, authenticate_as, replacement):
        authenticate_as("event_coordinator", user_id=OTHER_COORDINATOR_ID)
        replacement["event"]["status"] = "confirmed"

        response = post(client, auth_headers, replaces_booking_id=AFFECTED_BOOKING_ID)

        assert response.status_code == 403
        assert replacement["order"] == []

    @pytest.mark.parametrize("role", ["venue_staff", "event_organiser", "attendee", "tech_support"])
    def test_acting_as_any_other_role_is_forbidden(self, client, auth_headers, authenticate_as, replacement, role):
        authenticate_as(role, user_id=COORDINATOR_ID)

        response = post(client, auth_headers, replaces_booking_id=AFFECTED_BOOKING_ID)

        assert response.status_code == 403
        assert replacement["order"] == []


class TestReplacementRepository:
    """CR-95 AC4: the link reaches the database function only when one is asked for."""

    @pytest.fixture()
    def rpc_calls(self, monkeypatch):
        calls = []

        class Rpc:
            def execute(self):
                return SimpleNamespace(data=[{"outcome": "ok", "booking_id": BOOKING_ID}])

        class AdminClient:
            def rpc(self, name, params):
                calls.append((name, params))
                return Rpc()

        monkeypatch.setattr(venues_repository, "get_supabase_admin_client", lambda: AdminClient())
        return calls

    def test_an_event_request_sends_the_replaced_booking_only_when_given(self, rpc_calls):
        venues_repository.request_booking(EVENT_ID, VENUE_ID, COORDINATOR_ID, None, notify_message="m")
        venues_repository.request_booking(
            EVENT_ID, VENUE_ID, COORDINATOR_ID, None, notify_message="m", replaces_booking_id=AFFECTED_BOOKING_ID,
        )

        assert "p_replaces_booking_id" not in rpc_calls[0][1]
        assert rpc_calls[1] == ("request_venue_booking", {
            "p_event_id": EVENT_ID, "p_venue_id": VENUE_ID, "p_actor_id": COORDINATOR_ID, "p_note": None,
            "p_notify_message": "m", "p_replaces_booking_id": AFFECTED_BOOKING_ID,
        })

    def test_a_space_request_sends_the_replaced_booking_when_given(self, rpc_calls):
        venues_repository.request_booking_for_space(
            SPACE_ID, VENUE_ID, COORDINATOR_ID, None, notify_message="m", replaces_booking_id=AFFECTED_BOOKING_ID,
        )

        assert rpc_calls[0][1]["p_replaces_booking_id"] == AFFECTED_BOOKING_ID

    def test_the_replaceable_booking_is_read_by_id_and_may_be_absent(self, monkeypatch):
        row = {"id": AFFECTED_BOOKING_ID, "event_id": EVENT_ID, "event_space_request_id": None,
               "status": "approved", "flag": "affected"}
        seen = []

        class Query:
            def __init__(self, data):
                self.data = data

            def select(self, columns):
                seen.append(("select", columns))
                return self

            def eq(self, field, value):
                seen.append(("eq", field, value))
                return self

            def limit(self, count):
                return self

            def execute(self):
                return SimpleNamespace(data=self.data)

        class AdminClient:
            def __init__(self, data):
                self.data = data

            def table(self, name):
                assert name == "venue_bookings"
                return Query(self.data)

        monkeypatch.setattr(venues_repository, "get_supabase_admin_client", lambda: AdminClient([row]))
        assert venues_repository.get_replaceable_booking(AFFECTED_BOOKING_ID) == row
        assert ("eq", "id", AFFECTED_BOOKING_ID) in seen

        monkeypatch.setattr(venues_repository, "get_supabase_admin_client", lambda: AdminClient([]))
        assert venues_repository.get_replaceable_booking(AFFECTED_BOOKING_ID) is None


@pytest.mark.parametrize("flag", ["affected", "safety_rejected"])
@pytest.mark.parametrize("for_space", [False, True])
def test_a_flagged_booking_can_be_replaced(client, auth_headers, authenticate_as, replacement, monkeypatch, flag, for_space):
    replacement["replaceable"]["flag"] = flag
    authenticate_as("event_coordinator", user_id=COORDINATOR_ID)
    if for_space:
        replacement["replaceable"]["event_space_request_id"] = SPACE_ID
        monkeypatch.setattr(events_service, "assigned_space", lambda *a: (deepcopy(replacement["event"]), {"id": SPACE_ID}))
    response = (post_for_space if for_space else post)(client, auth_headers, replaces_booking_id=AFFECTED_BOOKING_ID)
    assert response.status_code == 201
    assert replacement["returned"] == []


@pytest.mark.parametrize("flag", [None, "conflict", "unsuitable"])
def test_other_flags_are_not_replaceable(client, auth_headers, authenticate_as, replacement, flag):
    replacement["replaceable"]["flag"] = flag
    authenticate_as("event_coordinator", user_id=COORDINATOR_ID)
    response = post(client, auth_headers, replaces_booking_id=AFFECTED_BOOKING_ID)
    assert response.status_code == 409
    assert response.json()["detail"] == "That booking is not waiting for a replacement."
    assert replacement["order"] == []
