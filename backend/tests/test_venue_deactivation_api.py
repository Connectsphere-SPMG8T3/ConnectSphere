"""SCRUM-64: deactivate a venue (AC1, AC3) — role gate, preview/confirm, outcomes."""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.exceptions import EventServiceUnavailableError
from app.modules.events import repository as events_repository
from app.modules.events import service as events_service
from app.modules.venues import repository
from app.modules.venues.schemas import BookingSummary, Period
from tests.test_venues_api import HALL_A_ID, make_venue_profile

URL = f"/api/v1/venues/{HALL_A_ID}/deactivate"
EVENT_ID = "e0000000-0000-4000-8000-000000000301"
BODY = {"reason": "permanently_closed", "note": None, "version": 3}


def _booking(status="approved"):
    start = datetime(2031, 5, 20, 6, tzinfo=timezone.utc)
    return BookingSummary(id="d0000000-0000-4000-8000-000000000301", event_id=EVENT_ID,
                          period=Period(starts_at=start, ends_at=start + timedelta(hours=3)), status=status)


@pytest.fixture()
def venue(monkeypatch):
    state = {"current": make_venue_profile(HALL_A_ID, "Hall A", version=3), "flaggable": [], "rpc": [],
             "outcome": {"outcome": "ok", "event_ids": []}, "returned": []}
    monkeypatch.setattr(repository, "get_venue", lambda vid: state["current"] if vid == HALL_A_ID else None)
    monkeypatch.setattr(repository, "list_upcoming_blocks", lambda vid, since: [])
    monkeypatch.setattr(repository, "list_upcoming_bookings", lambda vid, since: [])
    monkeypatch.setattr(repository, "list_flaggable_bookings", lambda vid, now: state["flaggable"])
    monkeypatch.setattr(events_repository, "list_event_names", lambda ids: {EVENT_ID: "Gala"})

    def _rpc(venue_id, actor_id, expected_version, **kwargs):
        state["rpc"].append({"venue_id": venue_id, "actor_id": actor_id, "version": expected_version, **kwargs})
        return state["outcome"]

    monkeypatch.setattr(repository, "deactivate_venue", _rpc)
    monkeypatch.setattr(events_service, "return_to_planning",
                        lambda event_id, **kw: state["returned"].append((event_id, kw)))
    return state


class TestDeactivate:
    def test_no_bookings_saves_straight_away(self, client, auth_headers, authenticate_as, venue):
        actor = authenticate_as("venue_staff")
        response = client.post(URL, json=BODY, headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["saved"] is True
        [call] = venue["rpc"]
        assert call["actor_id"] == actor["id"] and call["version"] == 3
        assert call["reason"] == "permanently_closed"
        assert call["before"]["is_active"] is True and call["after"]["is_active"] is False
        assert call["after"]["inactive_reason"] == "permanently_closed"
        assert call["flag_reason"] == "Venue deactivated: permanently closed"

    def test_bookings_without_confirm_preview_and_write_nothing(self, client, auth_headers, authenticate_as, venue):
        authenticate_as("venue_staff")
        venue["flaggable"] = [_booking("held")]
        response = client.post(URL, json=BODY, headers=auth_headers)
        body = response.json()
        assert response.status_code == 200 and body["saved"] is False
        assert body["affected"][0]["event_name"] == "Gala" and body["affected"][0]["status"] == "held"
        assert venue["rpc"] == []

    def test_confirm_flags_and_returns_flagged_events_to_planning(self, client, auth_headers, authenticate_as, venue):
        authenticate_as("venue_staff")
        venue["flaggable"] = [_booking()]
        venue["outcome"] = {"outcome": "ok", "event_ids": [EVENT_ID]}
        response = client.post(URL, json={**BODY, "confirm": True}, headers=auth_headers)
        assert response.json()["saved"] is True
        assert venue["returned"] == [(EVENT_ID, {"reason_code": "arrangement_flagged"})]

    def test_event_service_outage_after_commit_still_reports_saved(
        self, client, auth_headers, authenticate_as, venue, monkeypatch
    ):
        authenticate_as("venue_staff")
        venue["outcome"] = {"outcome": "ok", "event_ids": [EVENT_ID]}

        def _down(event_id, **kw):
            raise EventServiceUnavailableError()

        monkeypatch.setattr(events_service, "return_to_planning", _down)
        response = client.post(URL, json={**BODY, "confirm": True}, headers=auth_headers)
        assert response.status_code == 200 and response.json()["saved"] is True

    def test_other_requires_a_note(self, client, auth_headers, authenticate_as, venue):
        authenticate_as("venue_staff")
        for note in (None, "   "):
            response = client.post(URL, json={**BODY, "reason": "other", "note": note}, headers=auth_headers)
            assert response.status_code == 422
        assert venue["rpc"] == []

    def test_note_over_500_chars_is_422(self, client, auth_headers, authenticate_as, venue):
        authenticate_as("venue_staff")
        response = client.post(URL, json={**BODY, "note": "x" * 501}, headers=auth_headers)
        assert response.status_code == 422

    def test_other_with_note_includes_it_in_the_flag_reason(self, client, auth_headers, authenticate_as, venue):
        authenticate_as("venue_staff")
        client.post(URL, json={**BODY, "reason": "other", "note": " Lease ended "}, headers=auth_headers)
        assert venue["rpc"][0]["note"] == "Lease ended"
        assert venue["rpc"][0]["flag_reason"] == "Venue deactivated: other — Lease ended"

    def test_already_inactive_is_409(self, client, auth_headers, authenticate_as, venue):
        authenticate_as("venue_staff")
        venue["current"] = make_venue_profile(HALL_A_ID, "Hall A", version=3, is_active=False,
                                              inactive_reason="permanently_closed")
        response = client.post(URL, json=BODY, headers=auth_headers)
        assert response.status_code == 409 and response.json()["detail"] == "This venue is already inactive."

    @pytest.mark.parametrize("outcome", ["already_inactive", "stale", "venue_not_found"])
    def test_rpc_refusals_map_to_errors(self, client, auth_headers, authenticate_as, venue, outcome):
        authenticate_as("venue_staff")
        venue["outcome"] = {"outcome": outcome, "event_ids": []}
        response = client.post(URL, json=BODY, headers=auth_headers)
        assert response.status_code == (404 if outcome == "venue_not_found" else 409)
        assert venue["returned"] == []

    def test_stale_version_from_client_is_409_without_rpc(self, client, auth_headers, authenticate_as, venue):
        authenticate_as("venue_staff")
        response = client.post(URL, json={**BODY, "version": 2}, headers=auth_headers)
        assert response.status_code == 409 and venue["rpc"] == []

    def test_unknown_venue_is_404(self, client, auth_headers, authenticate_as, venue):
        authenticate_as("venue_staff")
        response = client.post("/api/v1/venues/b0000000-0000-4000-8000-0000000000ff/deactivate",
                               json=BODY, headers=auth_headers)
        assert response.status_code == 404

    @pytest.mark.parametrize("role", ["event_coordinator", "event_organiser", "tech_support",
                                      "safety_officer", "event_coordinator_lead", "attendee"])
    def test_other_roles_are_forbidden(self, client, auth_headers, authenticate_as, venue, role):
        authenticate_as(role)
        assert client.post(URL, json=BODY, headers=auth_headers).status_code == 403
        assert venue["rpc"] == []


class TestReactivate:
    URL = f"/api/v1/venues/{HALL_A_ID}/reactivate"

    @pytest.fixture()
    def inactive(self, monkeypatch, venue):
        venue["current"] = make_venue_profile(HALL_A_ID, "Hall A", version=4, is_active=False,
                                              inactive_reason="long_term_renovation", inactive_note="Roof works")
        venue["re_rpc"] = []

        def _rpc(venue_id, actor_id, expected_version, **kwargs):
            venue["re_rpc"].append({"version": expected_version, **kwargs})
            return venue.get("re_outcome", "ok")

        monkeypatch.setattr(repository, "reactivate_venue", _rpc)
        return venue

    def test_venue_staff_reactivates(self, client, auth_headers, authenticate_as, inactive):
        authenticate_as("venue_staff")
        response = client.post(self.URL, json={"version": 4}, headers=auth_headers)
        assert response.status_code == 200
        [call] = inactive["re_rpc"]
        assert call["before"]["inactive_reason"] == "long_term_renovation"
        assert call["after"] == {**call["before"], "is_active": True, "inactive_reason": None, "inactive_note": None}
        assert inactive["returned"] == []

    def test_already_active_is_409(self, client, auth_headers, authenticate_as, venue, monkeypatch):
        authenticate_as("venue_staff")
        monkeypatch.setattr(repository, "reactivate_venue", lambda *a, **k: pytest.fail("must not write"))
        response = client.post(self.URL, json={"version": 3}, headers=auth_headers)
        assert response.status_code == 409 and response.json()["detail"] == "This venue is already active."

    @pytest.mark.parametrize(("outcome", "code"), [("stale", 409), ("already_active", 409), ("venue_not_found", 404)])
    def test_rpc_refusals(self, client, auth_headers, authenticate_as, inactive, outcome, code):
        authenticate_as("venue_staff")
        inactive["re_outcome"] = outcome
        assert client.post(self.URL, json={"version": 4}, headers=auth_headers).status_code == code

    def test_stale_client_version_is_409(self, client, auth_headers, authenticate_as, inactive):
        authenticate_as("venue_staff")
        assert client.post(self.URL, json={"version": 3}, headers=auth_headers).status_code == 409
        assert inactive["re_rpc"] == []

    def test_coordinator_is_forbidden(self, client, auth_headers, authenticate_as, inactive):
        authenticate_as("event_coordinator")
        assert client.post(self.URL, json={"version": 4}, headers=auth_headers).status_code == 403
