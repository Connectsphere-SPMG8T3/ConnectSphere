"""SCRUM-54: end, shorten or remove a venue block early (AC2, AC4, AC5, AC7, AC9) — input rules, outcomes, role gate.

What changing a block does to the row, its history, search and requests, and
which bookings it frees, is decided by `public.change_venue_block` and
`public.restorable_block_bookings` under the venue lock, and proven against the
real database in `supabase/verification/venue_block_change_checks.sql`. Here the
fakes answer with each outcome code, and the tests pin down what the API makes
of them and who may call it.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.modules.events import repository as events_repository
from app.modules.venues import repository
from app.modules.venues.schemas import Editor, Period, RestorableBooking, VenueBlock
from tests.test_venues_api import HALL_A_ID

BLOCK_ID = "f0000000-0000-4000-8000-000000000541"
URL = f"/api/v1/venues/{HALL_A_ID}/blocks/{BLOCK_ID}/change"
EVENT_ID = "e0000000-0000-4000-8000-000000000541"
BOOKING_ID = "d0000000-0000-4000-8000-000000000541"
STAFF_ID = "a0000000-0000-4000-8000-000000000003"
NOW = datetime.now(timezone.utc)
START = NOW - timedelta(hours=2)
END = NOW + timedelta(days=2)
NEW_END = NOW + timedelta(days=1)


def _block(**changes) -> VenueBlock:
    fields = {"id": BLOCK_ID, "period": Period(starts_at=START, ends_at=NOW), "reason": "maintenance",
              "notes": "Aircon", "status": "ended_early", "original_period": Period(starts_at=START, ends_at=END),
              "created_by": Editor(id=STAFF_ID, full_name="Vera Staff"), "created_at": START - timedelta(days=1),
              "changed_by": Editor(id=STAFF_ID, full_name="Vera Staff"), "changed_at": NOW,
              "change_note": "Fixed early"}
    return VenueBlock(**{**fields, **changes})


def _restorable(pending=False) -> RestorableBooking:
    return RestorableBooking(booking_id=BOOKING_ID, event_id=EVENT_ID, status="approved",
                             period=Period(starts_at=NOW + timedelta(hours=3), ends_at=NOW + timedelta(hours=6)),
                             has_pending_replacement=pending)


@pytest.fixture()
def changes(monkeypatch):
    state = {"outcome": "ok", "rpc": [], "block": _block(), "restorable": [], "restorable_calls": []}
    monkeypatch.setattr(events_repository, "list_event_names", lambda ids: {EVENT_ID: "Gala"})

    def _rpc(venue_id, block_id, actor_id, **kwargs):
        state["rpc"].append({"venue_id": venue_id, "block_id": block_id, "actor_id": actor_id, **kwargs})
        return {"outcome": state["outcome"]}

    def _restorable_for(block_id):
        state["restorable_calls"].append(block_id)
        return state["restorable"]

    monkeypatch.setattr(repository, "change_venue_block", _rpc)
    monkeypatch.setattr(repository, "get_block", lambda block_id: state["block"] if block_id == BLOCK_ID else None)
    monkeypatch.setattr(repository, "list_restorable_block_bookings", _restorable_for)
    return state


def _messages(response) -> str:
    detail = response.json()["detail"]
    return detail if isinstance(detail, str) else " ".join(error["msg"] for error in detail)


class TestActions:
    """AC2: end now, shorten, or remove one that hasn't started, with an optional note."""

    def test_end_now_calls_the_database_with_no_new_end(self, client, auth_headers, authenticate_as, changes):
        actor = authenticate_as("venue_staff")
        response = client.post(URL, json={"action": "end_now"}, headers=auth_headers)
        assert response.status_code == 200
        assert changes["rpc"] == [{"venue_id": HALL_A_ID, "block_id": BLOCK_ID, "actor_id": actor["id"],
                                   "action": "end_now", "ends_at": None, "note": None}]

    def test_the_response_is_the_changed_block_with_who_and_when(self, client, auth_headers, authenticate_as,
                                                                  changes):
        authenticate_as("venue_staff")
        body = client.post(URL, json={"action": "end_now"}, headers=auth_headers).json()
        block = body["block"]
        assert block["id"] == BLOCK_ID and block["status"] == "ended_early"
        assert block["original_period"]["ends_at"] is not None
        assert block["created_by"] == {"id": STAFF_ID, "full_name": "Vera Staff"}
        assert block["changed_by"]["full_name"] == "Vera Staff" and block["change_note"] == "Fixed early"

    def test_shorten_sends_the_new_end(self, client, auth_headers, authenticate_as, changes):
        authenticate_as("venue_staff")
        response = client.post(URL, json={"action": "shorten", "ends_at": NEW_END.isoformat(), "note": "Early"},
                               headers=auth_headers)
        assert response.status_code == 200
        [call] = changes["rpc"]
        assert call["action"] == "shorten" and call["ends_at"] == NEW_END and call["note"] == "Early"

    def test_remove_calls_the_database(self, client, auth_headers, authenticate_as, changes):
        authenticate_as("venue_staff")
        changes["block"] = _block(status="removed")
        response = client.post(URL, json={"action": "remove"}, headers=auth_headers)
        assert response.status_code == 200 and response.json()["block"]["status"] == "removed"
        assert changes["rpc"][0]["action"] == "remove"

    def test_a_new_end_sent_with_end_now_or_remove_is_ignored(self, client, auth_headers, authenticate_as, changes):
        authenticate_as("venue_staff")
        client.post(URL, json={"action": "remove", "ends_at": NEW_END.isoformat()}, headers=auth_headers)
        assert changes["rpc"][0]["ends_at"] is None


class TestInputRules:
    def test_shorten_without_a_new_end_is_refused(self, client, auth_headers, authenticate_as, changes):
        authenticate_as("venue_staff")
        response = client.post(URL, json={"action": "shorten"}, headers=auth_headers)
        assert response.status_code == 422 and "A new end is required to shorten a block." in _messages(response)
        assert changes["rpc"] == []

    def test_a_new_end_without_an_offset_is_refused(self, client, auth_headers, authenticate_as, changes):
        authenticate_as("venue_staff")
        response = client.post(URL, json={"action": "shorten", "ends_at": "2031-05-20T09:00:00"},
                               headers=auth_headers)
        assert response.status_code == 422 and "timezone" in _messages(response)

    def test_a_new_end_in_the_past_is_refused(self, client, auth_headers, authenticate_as, changes):
        authenticate_as("venue_staff")
        past = NOW - timedelta(minutes=1)
        response = client.post(URL, json={"action": "shorten", "ends_at": past.isoformat()}, headers=auth_headers)
        assert response.status_code == 422
        assert "The new end must be in the future. To end the block now, choose End now." in _messages(response)
        assert changes["rpc"] == []

    @pytest.mark.parametrize("action", ["", "extend", None])
    def test_an_unknown_action_is_refused(self, client, auth_headers, authenticate_as, changes, action):
        authenticate_as("venue_staff")
        response = client.post(URL, json={"action": action}, headers=auth_headers)
        assert response.status_code == 422 and response.json()["detail"][0]["loc"][-1] == "action"

    def test_a_note_of_1000_characters_is_accepted(self, client, auth_headers, authenticate_as, changes):
        authenticate_as("venue_staff")
        response = client.post(URL, json={"action": "end_now", "note": "n" * 1000}, headers=auth_headers)
        assert response.status_code == 200 and len(changes["rpc"][0]["note"]) == 1000

    def test_a_note_over_1000_characters_is_refused(self, client, auth_headers, authenticate_as, changes):
        authenticate_as("venue_staff")
        response = client.post(URL, json={"action": "end_now", "note": "n" * 1001}, headers=auth_headers)
        assert response.status_code == 422 and "The note can be at most 1000 characters." in _messages(response)
        assert changes["rpc"] == []

    @pytest.mark.parametrize("note,stored", [("  Fixed  ", "Fixed"), ("   ", None), (None, None)])
    def test_the_note_is_trimmed_and_a_blank_one_is_none(self, client, auth_headers, authenticate_as, changes,
                                                          note, stored):
        authenticate_as("venue_staff")
        client.post(URL, json={"action": "end_now", "note": note}, headers=auth_headers)
        assert changes["rpc"][0]["note"] == stored


class TestRefusals:
    """AC2: a block can't be lengthened, and one that has ended (or was removed) can't be changed."""

    @pytest.mark.parametrize(
        "outcome,status,message",
        [
            ("ended", 409, "This block has already ended, so it can't be changed."),
            ("removed", 409, "This block was removed, so it can't be changed."),
            ("not_started", 409, "This block hasn't started yet. Remove it instead."),
            ("already_started", 409, "Only a block that hasn't started can be removed. End it now instead."),
            ("end_not_before_current", 422,
             "The new end must be earlier than the current end. To block for longer, add a new block."),
            ("end_not_after_start", 422, "The new end must be after the block's start."),
            ("end_in_past", 422, "The new end must be in the future. To end the block now, choose End now."),
            ("note_too_long", 422, "The note can be at most 1000 characters."),
        ],
    )
    def test_each_database_refusal_says_why(self, client, auth_headers, authenticate_as, changes, outcome, status,
                                            message):
        authenticate_as("venue_staff")
        changes["outcome"] = outcome
        response = client.post(URL, json={"action": "end_now"}, headers=auth_headers)
        assert response.status_code == status and response.json()["detail"] == message
        assert changes["restorable_calls"] == []

    def test_an_unknown_venue_is_404(self, client, auth_headers, authenticate_as, changes):
        authenticate_as("venue_staff")
        changes["outcome"] = "venue_not_found"
        response = client.post(URL, json={"action": "end_now"}, headers=auth_headers)
        assert response.status_code == 404 and response.json()["detail"] == "Venue not found."

    def test_an_unknown_block_or_one_on_another_venue_is_404(self, client, auth_headers, authenticate_as, changes):
        authenticate_as("venue_staff")
        changes["outcome"] = "block_not_found"
        response = client.post(URL, json={"action": "end_now"}, headers=auth_headers)
        assert response.status_code == 404 and response.json()["detail"] == "Block not found."

    def test_a_block_gone_by_the_time_it_is_read_back_is_404(self, client, auth_headers, authenticate_as, changes):
        authenticate_as("venue_staff")
        changes["block"] = None
        response = client.post(URL, json={"action": "end_now"}, headers=auth_headers)
        assert response.status_code == 404 and response.json()["detail"] == "Block not found."

    def test_a_malformed_block_id_is_422(self, client, auth_headers, authenticate_as, changes):
        authenticate_as("venue_staff")
        response = client.post(f"/api/v1/venues/{HALL_A_ID}/blocks/not-a-uuid/change", json={"action": "end_now"},
                               headers=auth_headers)
        assert response.status_code == 422 and changes["rpc"] == []


class TestRestorableBookings:
    """AC5, AC7: the bookings this change freed are listed, named, with any pending replacement marked."""

    def test_none_freed_is_an_empty_list(self, client, auth_headers, authenticate_as, changes):
        authenticate_as("venue_staff")
        body = client.post(URL, json={"action": "end_now"}, headers=auth_headers).json()
        assert body["restorable"] == [] and changes["restorable_calls"] == [BLOCK_ID]

    def test_freed_bookings_are_named_with_the_block_reason(self, client, auth_headers, authenticate_as, changes):
        authenticate_as("venue_staff")
        changes["restorable"] = [_restorable(pending=True)]
        [booking] = client.post(URL, json={"action": "end_now"}, headers=auth_headers).json()["restorable"]
        assert booking["booking_id"] == BOOKING_ID and booking["event_name"] == "Gala"
        assert booking["block_reason"] == "Maintenance" and booking["has_pending_replacement"] is True


class TestAccess:
    """AC9: only a session acting as Venue Staff may change a block."""

    @pytest.mark.parametrize("role", ["event_coordinator", "event_organiser", "tech_support", "safety_officer",
                                      "attendee"])
    def test_every_other_role_is_forbidden(self, client, auth_headers, authenticate_as, changes, role):
        authenticate_as(role)
        assert client.post(URL, json={"action": "end_now"}, headers=auth_headers).status_code == 403
        assert changes["rpc"] == []

    def test_a_venue_staff_holder_acting_as_coordinator_is_forbidden(self, client, auth_headers, monkeypatch,
                                                                      changes):
        from tests.test_event_comments_api import acting_as_another_role

        acting_as_another_role(monkeypatch, STAFF_ID, holds="venue_staff", acts_as="event_coordinator")
        assert client.post(URL, json={"action": "end_now"}, headers=auth_headers).status_code == 403
        assert changes["rpc"] == []

    def test_an_unauthenticated_request_is_refused(self, client, changes):
        assert client.post(URL, json={"action": "end_now"}).status_code == 401


class TestWhoSeesBlockManagement:
    """AC1, AC9: who set and changed a block, and the note, are for Venue Staff. A
    coordinator reading the venue profile still sees its blocks' periods and
    reasons (SCRUM-67, QA-104), without them."""

    @pytest.fixture()
    def profile(self, monkeypatch):
        from tests.test_venues_api import make_venue_profile

        monkeypatch.setattr(repository, "get_venue", lambda vid: make_venue_profile(HALL_A_ID, "Hall A"))
        monkeypatch.setattr(repository, "list_upcoming_bookings", lambda vid, since: [])
        monkeypatch.setattr(repository, "list_upcoming_blocks", lambda vid, since: [_block(status="active")])

    def test_venue_staff_see_who_set_and_changed_it(self, client, auth_headers, authenticate_as, profile):
        authenticate_as("venue_staff")
        [block] = client.get(f"/api/v1/venues/{HALL_A_ID}", headers=auth_headers).json()["upcoming_blocks"]
        assert block["created_by"]["full_name"] == "Vera Staff" and block["change_note"] == "Fixed early"

    def test_a_coordinator_sees_the_block_without_them(self, client, auth_headers, authenticate_as, profile):
        authenticate_as("event_coordinator")
        [block] = client.get(f"/api/v1/venues/{HALL_A_ID}", headers=auth_headers).json()["upcoming_blocks"]
        assert block["reason"] == "maintenance" and block["period"]
        assert (block["created_by"], block["created_at"], block["changed_by"], block["changed_at"],
                block["change_note"], block["original_period"]) == (None, None, None, None, None, None)
