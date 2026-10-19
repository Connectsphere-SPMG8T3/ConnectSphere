"""SCRUM-51: block a venue (AC1, AC5, AC6, AC8, AC9) — input rules, preview/confirm, outcomes, role gate.

The flagging, linking and notices happen in the database trigger (CR-95,
SCRUM-51 AC5, AC10-AC13); those are proved by the live checks, not here.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.modules.events import repository as events_repository
from app.modules.venues import repository
from app.modules.venues.schemas import BlockAffectedBooking, Period
from tests.test_venues_api import HALL_A_ID, make_venue_profile

URL = f"/api/v1/venues/{HALL_A_ID}/blocks"
EVENT_ID = "e0000000-0000-4000-8000-000000000511"
BOOKING_ID = "d0000000-0000-4000-8000-000000000511"
BLOCK_ID = "f0000000-0000-4000-8000-000000000511"
START = datetime(2031, 5, 20, 1, tzinfo=timezone.utc)
END = START + timedelta(hours=8)
BODY = {"starts_at": START.isoformat(), "ends_at": END.isoformat(), "reason": "maintenance", "detail": None}


def _affected(status="approved"):
    return BlockAffectedBooking(booking_id=BOOKING_ID, event_id=EVENT_ID, status=status,
                                period=Period(starts_at=START + timedelta(hours=1), ends_at=START + timedelta(hours=3)))


@pytest.fixture()
def blocks(monkeypatch):
    state = {"venue": make_venue_profile(HALL_A_ID, "Hall A"), "conflicts": [], "linked": [], "rpc": [],
             "conflict_calls": [], "outcome": {"outcome": "ok", "block_id": BLOCK_ID}}
    monkeypatch.setattr(repository, "get_venue", lambda vid: state["venue"] if vid == HALL_A_ID else None)
    monkeypatch.setattr(events_repository, "list_event_names", lambda ids: {EVENT_ID: "Gala"})

    def _conflicts(venue_id, period):
        state["conflict_calls"].append((venue_id, period))
        return state["conflicts"]

    def _rpc(venue_id, actor_id, **kwargs):
        state["rpc"].append({"venue_id": venue_id, "actor_id": actor_id, **kwargs})
        return state["outcome"]

    monkeypatch.setattr(repository, "list_block_conflicts", _conflicts)
    monkeypatch.setattr(repository, "create_venue_block", _rpc)
    monkeypatch.setattr(repository, "list_block_bookings", lambda block_id: state["linked"])
    return state


def _messages(response) -> str:
    return " ".join(error["msg"] for error in response.json()["detail"])


class TestInputRules:
    """AC1: invalid or incomplete input is refused with a message naming the problem."""

    def test_a_valid_block_with_no_bookings_saves_straight_away(self, client, auth_headers, authenticate_as, blocks):
        actor = authenticate_as("venue_staff")
        response = client.post(URL, json=BODY, headers=auth_headers)
        body = response.json()
        assert response.status_code == 200 and body["saved"] is True
        assert body["block"] == {"id": BLOCK_ID, "period": {"starts_at": START.isoformat().replace("+00:00", "Z"),
                                                            "ends_at": END.isoformat().replace("+00:00", "Z")},
                                 "reason": "maintenance", "notes": None}
        [call] = blocks["rpc"]
        assert call["actor_id"] == actor["id"] and call["reason"] == "maintenance" and call["notes"] is None
        assert call["period"] == Period(starts_at=START, ends_at=END)

    @pytest.mark.parametrize("reason", ["maintenance", "equipment_failure", "renovation", "safety",
                                        "internal_activity"])
    def test_every_listed_category_is_accepted(self, client, auth_headers, authenticate_as, blocks, reason):
        authenticate_as("venue_staff")
        assert client.post(URL, json={**BODY, "reason": reason}, headers=auth_headers).json()["saved"] is True

    def test_end_before_start_is_refused(self, client, auth_headers, authenticate_as, blocks):
        authenticate_as("venue_staff")
        response = client.post(URL, json={**BODY, "starts_at": END.isoformat(), "ends_at": START.isoformat()},
                               headers=auth_headers)
        assert response.status_code == 422 and "End must be after start." in _messages(response)
        assert blocks["rpc"] == []

    def test_end_equal_to_start_is_refused(self, client, auth_headers, authenticate_as, blocks):
        authenticate_as("venue_staff")
        response = client.post(URL, json={**BODY, "ends_at": START.isoformat()}, headers=auth_headers)
        assert response.status_code == 422 and "End must be after start." in _messages(response)

    def test_end_in_the_past_is_refused(self, client, auth_headers, authenticate_as, blocks):
        authenticate_as("venue_staff")
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        response = client.post(URL, json={**BODY, "starts_at": (past - timedelta(hours=2)).isoformat(),
                                          "ends_at": past.isoformat()}, headers=auth_headers)
        assert response.status_code == 422 and "End must be in the future." in _messages(response)

    def test_a_start_in_the_past_is_accepted_for_an_emergency_block(self, client, auth_headers, authenticate_as,
                                                                     blocks):
        authenticate_as("venue_staff")
        now = datetime.now(timezone.utc)
        response = client.post(URL, json={**BODY, "starts_at": (now - timedelta(hours=1)).isoformat(),
                                          "ends_at": (now + timedelta(hours=4)).isoformat()}, headers=auth_headers)
        assert response.status_code == 200 and response.json()["saved"] is True

    def test_a_time_without_an_offset_is_refused(self, client, auth_headers, authenticate_as, blocks):
        authenticate_as("venue_staff")
        response = client.post(URL, json={**BODY, "starts_at": "2031-05-20T09:00:00"}, headers=auth_headers)
        assert response.status_code == 422 and "timezone" in _messages(response)

    @pytest.mark.parametrize("missing", ["starts_at", "ends_at", "reason"])
    def test_a_missing_field_is_refused(self, client, auth_headers, authenticate_as, blocks, missing):
        authenticate_as("venue_staff")
        body = {k: v for k, v in BODY.items() if k != missing}
        response = client.post(URL, json=body, headers=auth_headers)
        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"][-1] == missing

    @pytest.mark.parametrize("reason", ["", "flood", None])
    def test_an_empty_or_unknown_reason_is_refused(self, client, auth_headers, authenticate_as, blocks, reason):
        authenticate_as("venue_staff")
        response = client.post(URL, json={**BODY, "reason": reason}, headers=auth_headers)
        assert response.status_code == 422 and response.json()["detail"][0]["loc"][-1] == "reason"

    @pytest.mark.parametrize("detail", [None, "", "   "])
    def test_other_requires_a_detail(self, client, auth_headers, authenticate_as, blocks, detail):
        authenticate_as("venue_staff")
        response = client.post(URL, json={**BODY, "reason": "other", "detail": detail}, headers=auth_headers)
        assert response.status_code == 422
        assert "A detail is required when the reason is Other." in _messages(response)
        assert blocks["rpc"] == []

    def test_other_with_a_detail_is_saved_trimmed(self, client, auth_headers, authenticate_as, blocks):
        authenticate_as("venue_staff")
        response = client.post(URL, json={**BODY, "reason": "other", "detail": "  Film shoot  "}, headers=auth_headers)
        assert response.json()["saved"] is True and blocks["rpc"][0]["notes"] == "Film shoot"

    def test_a_blank_detail_is_stored_as_none(self, client, auth_headers, authenticate_as, blocks):
        authenticate_as("venue_staff")
        client.post(URL, json={**BODY, "detail": "   "}, headers=auth_headers)
        assert blocks["rpc"][0]["notes"] is None

    def test_a_detail_of_1000_characters_is_accepted(self, client, auth_headers, authenticate_as, blocks):
        authenticate_as("venue_staff")
        response = client.post(URL, json={**BODY, "detail": "x" * 1000}, headers=auth_headers)
        assert response.status_code == 200

    def test_a_detail_over_1000_characters_is_refused(self, client, auth_headers, authenticate_as, blocks):
        authenticate_as("venue_staff")
        response = client.post(URL, json={**BODY, "detail": "x" * 1001}, headers=auth_headers)
        assert response.status_code == 422
        assert "The detail can be at most 1000 characters." in _messages(response)


class TestPreviewAndSave:
    """AC5/AC6 (CAL-R1): overlapping bookings are listed before saving, and after."""

    def test_overlapping_bookings_without_confirm_preview_and_write_nothing(
        self, client, auth_headers, authenticate_as, blocks
    ):
        authenticate_as("venue_staff")
        blocks["conflicts"] = [_affected("held")]
        response = client.post(URL, json=BODY, headers=auth_headers)
        body = response.json()
        assert response.status_code == 200 and body["saved"] is False and body["block"] is None
        [row] = body["affected"]
        assert row["event_name"] == "Gala" and row["status"] == "held"
        assert row["block_reason"] == "Maintenance"
        assert blocks["rpc"] == []

    def test_the_preview_asks_the_shared_conflict_check_for_this_venue_and_period(
        self, client, auth_headers, authenticate_as, blocks
    ):
        # AC7: the block code names no overlap of its own.
        authenticate_as("venue_staff")
        client.post(URL, json=BODY, headers=auth_headers)
        assert blocks["conflict_calls"] == [(HALL_A_ID, Period(starts_at=START, ends_at=END))]

    def test_confirm_saves_and_returns_the_bookings_linked_to_the_block(
        self, client, auth_headers, authenticate_as, blocks
    ):
        authenticate_as("venue_staff")
        blocks["conflicts"] = [_affected("held")]
        blocks["linked"] = [_affected("approved")]
        response = client.post(URL, json={**BODY, "reason": "equipment_failure", "confirm": True},
                               headers=auth_headers)
        body = response.json()
        assert body["saved"] is True and body["block"]["id"] == BLOCK_ID
        [row] = body["affected"]
        assert row == {"booking_id": BOOKING_ID, "event_id": EVENT_ID, "event_name": "Gala", "status": "approved",
                       "period": row["period"], "block_reason": "Equipment failure"}

    def test_the_history_row_records_period_reason_and_detail(self, client, auth_headers, authenticate_as, blocks):
        # AC9: who and when are the actor and the row's own time, set in the database.
        authenticate_as("venue_staff")
        client.post(URL, json={**BODY, "detail": "Aircon"}, headers=auth_headers)
        assert blocks["rpc"][0]["history_after"] == {
            "block": {"starts_at": START.isoformat(), "ends_at": END.isoformat(),
                      "reason": "maintenance", "notes": "Aircon"}
        }

    def test_unknown_venue_is_404_and_nothing_is_written(self, client, auth_headers, authenticate_as, blocks):
        authenticate_as("venue_staff")
        response = client.post("/api/v1/venues/b0000000-0000-4000-8000-0000000000ff/blocks",
                               json=BODY, headers=auth_headers)
        assert response.status_code == 404 and blocks["rpc"] == []

    @pytest.mark.parametrize(("outcome", "status", "detail"), [
        ("venue_not_found", 404, "Venue not found."),
        ("invalid_period", 422, "End must be after start."),
        ("ended", 422, "End must be in the future."),
        ("detail_too_long", 422, "The detail can be at most 1000 characters."),
        ("invalid_detail", 422, "A detail is required when the reason is Other."),
    ])
    def test_database_refusals_map_to_errors(self, client, auth_headers, authenticate_as, blocks,
                                             outcome, status, detail):
        authenticate_as("venue_staff")
        blocks["outcome"] = {"outcome": outcome, "block_id": None}
        response = client.post(URL, json=BODY, headers=auth_headers)
        assert response.status_code == status and response.json()["detail"] == detail


class TestAccess:
    """AC8: only users acting as Venue Staff (a pool, AUTH-R5) can block a venue."""

    @pytest.mark.parametrize("role", ["event_coordinator", "event_organiser", "tech_support",
                                      "safety_officer", "event_coordinator_lead", "attendee"])
    def test_every_other_role_is_forbidden(self, client, auth_headers, authenticate_as, blocks, role):
        authenticate_as(role)
        assert client.post(URL, json=BODY, headers=auth_headers).status_code == 403
        assert blocks["rpc"] == [] and blocks["conflict_calls"] == []

    def test_a_venue_staff_holder_acting_as_coordinator_is_forbidden(self, client, auth_headers, monkeypatch,
                                                                       blocks):
        from tests.test_event_comments_api import acting_as_another_role

        acting_as_another_role(monkeypatch, "a0000000-0000-4000-8000-000000000002",
                               holds="venue_staff", acts_as="event_coordinator")
        assert client.post(URL, json=BODY, headers=auth_headers).status_code == 403
        assert blocks["rpc"] == []

    def test_an_unauthenticated_request_is_refused(self, client, blocks):
        assert client.post(URL, json=BODY).status_code == 401
