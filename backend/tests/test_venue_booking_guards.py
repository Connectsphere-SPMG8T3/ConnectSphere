"""Features 10 and 12-14: what a booking request checks, and the window a move is judged on.

Traces to SCRUM-18, SCRUM-19, SCRUM-21 AC4 and SCRUM-36. Pins the arguments and fallbacks
the booking API tests mock away.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.modules.venues import repository, service
from app.modules.venues.schemas import VenueBookingCreate, VenueSearchCriteria
from app.modules.venues.service import event_booking_history

START = datetime(2031, 5, 1, 9, tzinfo=timezone.utc)
END = START + timedelta(hours=3)
EVENT_ID = str(uuid4())
VENUE_ID = str(uuid4())
BOOKING_ID = str(uuid4())
COORDINATOR_ID = str(uuid4())


class TestMoveClash:
    def _clash(self, monkeypatch, found):
        seen = []
        monkeypatch.setattr(repository, "first_conflict", lambda *args: seen.append(args) or found)
        return service.move_clash(BOOKING_ID, VENUE_ID, 30, 45, START, END), seen

    def test_the_window_includes_setup_and_turnaround_and_leaves_the_booking_out(self, monkeypatch):
        result, seen = self._clash(monkeypatch, None)

        assert result is None
        [(occupied, venue_id, booking_id)] = seen
        assert occupied.starts_at == START - timedelta(minutes=30)
        assert occupied.ends_at == END + timedelta(minutes=45)
        assert (venue_id, booking_id) == (VENUE_ID, BOOKING_ID)

    def test_a_block_is_named_by_its_reason(self, monkeypatch):
        reason = next(iter(service.BLOCK_REASON_LABELS))
        result, _ = self._clash(monkeypatch, {"kind": "block", "block_reason": reason})

        assert result == f"a venue block ({service.BLOCK_REASON_LABELS[reason]})"

    def test_a_reason_with_no_label_is_shown_as_stored(self, monkeypatch):
        result, _ = self._clash(monkeypatch, {"kind": "block", "block_reason": "new_reason"})

        assert result == "a venue block (new_reason)"

    def test_a_booking_is_named_by_its_event(self, monkeypatch):
        result, _ = self._clash(monkeypatch, {"kind": "booking", "event_name": "Open Day"})

        assert result == '"Open Day"'

    def test_a_booking_whose_event_is_hidden_reads_as_another_event(self, monkeypatch):
        result, _ = self._clash(monkeypatch, {"kind": "booking", "event_name": None})

        assert result == '"another event"'


class TestRequestBooking:
    @pytest.fixture()
    def request_flow(self, monkeypatch):
        calls = {"venues": [], "event": {"id": EVENT_ID, "name": "Open Day", "status": "planning"}}
        monkeypatch.setattr(
            service.events_service, "assigned_event", lambda event_id, coordinator_id: calls["event"],
        )
        monkeypatch.setattr(repository, "list_booking_statuses", lambda ids: [])
        monkeypatch.setattr(repository, "get_venue", lambda venue_id: calls["venues"].append(venue_id) or "venue")
        monkeypatch.setattr(service, "_require_suitable", lambda *args: None)
        monkeypatch.setattr(service, "_requirements_from", lambda event, space: None)
        monkeypatch.setattr(service, "_prepare_replacement", lambda *args: None)
        monkeypatch.setattr(
            repository, "request_booking", lambda *args, **kwargs: {"outcome": "held", "booking_id": BOOKING_ID},
        )
        return calls

    def test_suitability_is_read_for_the_venue_requested(self, request_flow):
        service.request_booking(VenueBookingCreate(event_id=EVENT_ID, venue_id=VENUE_ID), COORDINATOR_ID)

        assert request_flow["venues"] == [VENUE_ID]

    def test_a_replacement_from_a_confirmed_event_is_still_checked_for_suitability(self, request_flow):
        request_flow["event"]["status"] = "confirmed"

        service.request_booking(
            VenueBookingCreate(event_id=EVENT_ID, venue_id=VENUE_ID, replaces_booking_id=str(uuid4())), COORDINATOR_ID,
        )

        assert request_flow["venues"] == [VENUE_ID]

    def test_an_ordinary_request_from_a_confirmed_event_is_left_to_the_database(self, request_flow):
        request_flow["event"]["status"] = "confirmed"

        service.request_booking(VenueBookingCreate(event_id=EVENT_ID, venue_id=VENUE_ID), COORDINATOR_ID)

        assert request_flow["venues"] == []


class TestApproveBooking:
    @pytest.mark.parametrize(
        ("from_status", "label"),
        [("re_review", "under re-review"), ("some_new_status", "some new status")],
    )
    def test_a_booking_that_is_not_held_says_what_it_is(self, monkeypatch, from_status, label):
        monkeypatch.setattr(repository, "get_booking", lambda booking_id: {"event_id": EVENT_ID, "status": "held"})
        monkeypatch.setattr(service.events_service, "names_by_id", lambda ids: {})
        monkeypatch.setattr(
            repository, "approve_booking",
            lambda *args, **kwargs: {"outcome": "not_held", "from_status": from_status},
        )

        with pytest.raises(service.BookingDecisionConflictError) as error:
            service.approve_booking(BOOKING_ID, COORDINATOR_ID)

        assert error.value.detail == f"Only a held booking can be approved. This one is {label}."


class TestRequestFields:
    def test_a_blank_search_location_means_no_location(self):
        assert VenueSearchCriteria(location="   ").location is None

    @pytest.mark.parametrize("note", [None, "   "], ids=["none", "blank"])
    def test_no_note_or_a_blank_one_is_stored_as_none(self, note):
        assert VenueBookingCreate(event_id=EVENT_ID, venue_id=VENUE_ID, note=note).note is None


class TestEventBookingHistory:
    """conftest.py stubs `service.event_booking_history`; the import above is the real one."""

    def test_the_history_is_read_for_that_event(self, monkeypatch):
        reads = []
        monkeypatch.setattr(repository, "list_event_booking_history", lambda event_id: reads.append(event_id) or ["row"])

        assert event_booking_history(EVENT_ID) == ["row"]
        assert reads == [EVENT_ID]
