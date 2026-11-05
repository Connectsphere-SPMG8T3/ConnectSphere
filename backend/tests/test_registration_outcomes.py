"""Feature 18: what an attendee, organiser or coordinator is told about a registration.

Pins the counts, the fields shown and the identifiers passed to the database functions,
which the API tests mock away. `test_registration_public_directory.py` covers availability.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.modules.registrations import service

EVENT_ID = "e0000000-0000-4000-8000-000000000001"
ATTENDEE_ID = "a0000000-0000-4000-8000-000000000001"
REGISTRATION_ID = "c0000000-0000-4000-8000-000000000001"
STARTS_AT = "2031-05-01T02:00:00+00:00"
ENDS_AT = "2031-05-01T06:00:00+00:00"
EXPIRES_AT = "2031-04-01T02:00:00+00:00"
PUBLIC_ROW = {
    "id": EVENT_ID, "name": "Open Day", "description": "Campus tour", "starts_at": STARTS_AT, "ends_at": ENDS_AT,
    "event_timezone": "Asia/Singapore", "status": "confirmed", "registration_enabled": False,
    "waitlist_enabled": False, "event_space_requests": [],
}


def _future(hours: int = 1) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def _record(monkeypatch, name: str, result):
    """Replaces a repository function with one that keeps the arguments it was given."""
    calls = []
    monkeypatch.setattr(service.repository, name, lambda *args: calls.append(args) or result)
    return calls


def _attendee_row(status: str, **fields) -> dict:
    return {"id": REGISTRATION_ID, "status": status, "attendee": {"full_name": "Sam Lee"}, **fields}


class TestPublicEvent:
    def test_the_detail_shows_the_events_own_fields_and_counts(self, monkeypatch):
        rows = _record(monkeypatch, "get_public_event_row", PUBLIC_ROW)
        registered = _record(monkeypatch, "registered_count", 7)
        occupied = _record(monkeypatch, "registration_occupied_count", 9)

        event = service.public_event(EVENT_ID)

        assert rows == registered == occupied == [(EVENT_ID,)]
        assert event.description == "Campus tour"
        assert event.starts_at == datetime.fromisoformat(STARTS_AT)
        assert event.ends_at == datetime.fromisoformat(ENDS_AT)
        assert event.registered_count == 7
        assert event.waitlist_enabled is False

    def test_the_registered_count_is_for_that_event(self, monkeypatch):
        calls = _record(monkeypatch, "registered_count", 3)

        assert service.registered_count(EVENT_ID) == 3
        assert calls == [(EVENT_ID,)]


class TestManagedRegistrations:
    def _report(self, monkeypatch, rows, event=None):
        event_calls = _record(monkeypatch, "get_registration_event_row", event or {"registration_capacity": 10})
        row_calls = _record(monkeypatch, "list_event_registration_rows", rows)
        report = service.managed_event_registrations(EVENT_ID, "event_organiser")
        assert event_calls == row_calls == [(EVENT_ID,)]
        return report

    def test_every_active_invitation_holds_a_place(self, monkeypatch):
        report = self._report(monkeypatch, [
            _attendee_row("registered"),
            _attendee_row("invited", invitation_expires_at=_future()),
            _attendee_row("invited", invitation_expires_at=_future(2)),
        ])

        assert report.registered_count == 1
        assert report.remaining_places == 7

    def test_an_expired_invitation_or_one_with_no_expiry_holds_no_place(self, monkeypatch):
        report = self._report(monkeypatch, [
            _attendee_row("invited", invitation_expires_at=_future(-1)),
            _attendee_row("invited"),
        ])

        assert report.remaining_places == 10

    def test_a_waitlisted_row_with_an_old_expiry_counts_as_waitlisted_only(self, monkeypatch):
        report = self._report(monkeypatch, [_attendee_row("waitlisted", invitation_expires_at=_future())])

        assert report.waitlist_count == 1
        assert report.remaining_places == 10

    def test_an_event_without_a_capacity_has_no_remaining_places(self, monkeypatch):
        report = self._report(monkeypatch, [_attendee_row("registered")], {"registration_capacity": None})

        assert report.effective_capacity is None
        assert report.remaining_places is None

    def test_an_invitation_expiry_may_already_be_a_datetime(self, monkeypatch):
        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        report = self._report(monkeypatch, [_attendee_row("invited", invitation_expires_at=expires)])

        assert report.remaining_places == 9

    def test_a_missing_event_is_not_found(self, monkeypatch):
        _record(monkeypatch, "get_registration_event_row", None)

        with pytest.raises(HTTPException) as error:
            service.managed_event_registrations(EVENT_ID, "event_organiser")

        assert (error.value.status_code, error.value.detail) == (404, "Event not found.")


class TestAttendeeRegistrations:
    def test_a_registration_shows_the_events_description_and_its_invitation_expiry(self, monkeypatch):
        event = {key: PUBLIC_ROW[key] for key in ("id", "name", "description", "starts_at", "ends_at",
                                                  "event_timezone", "status", "event_space_requests")}
        _record(monkeypatch, "list_attendee_registration_rows", [{
            "id": REGISTRATION_ID, "status": "invited", "registered_at": STARTS_AT,
            "invitation_expires_at": EXPIRES_AT, "event": event,
        }])

        [registration] = service.attendee_registrations(ATTENDEE_ID).registrations

        assert registration.event.description == "Campus tour"
        assert registration.invitation_expires_at == datetime.fromisoformat(EXPIRES_AT)


class TestRegisterAttendee:
    @pytest.mark.parametrize("outcome", ["already_waitlisted", "invited"])
    def test_a_queued_attendee_gets_their_status_and_invitation_expiry(self, monkeypatch, outcome):
        calls = _record(monkeypatch, "register_for_event", {
            "outcome": outcome, "registration_id": REGISTRATION_ID, "invitation_expires_at": EXPIRES_AT,
        })

        result = service.register_attendee(EVENT_ID, ATTENDEE_ID)

        assert calls == [(EVENT_ID, ATTENDEE_ID)]
        assert result.status == outcome
        assert result.invitation_expires_at == datetime.fromisoformat(EXPIRES_AT)

    def test_an_unknown_outcome_is_an_error_not_a_success(self, monkeypatch):
        _record(monkeypatch, "register_for_event", {"outcome": "surprise"})

        with pytest.raises(RuntimeError, match="surprise"):
            service.register_attendee(EVENT_ID, ATTENDEE_ID)


class TestAcceptInvitation:
    def test_the_attendees_own_invitation_is_the_one_accepted(self, monkeypatch):
        calls = _record(monkeypatch, "accept_waitlist_invitation", {
            "outcome": "registered", "registration_id": REGISTRATION_ID,
        })

        assert service.accept_invitation(REGISTRATION_ID, ATTENDEE_ID).status == "registered"
        assert calls == [(REGISTRATION_ID, ATTENDEE_ID)]

    @pytest.mark.parametrize(
        ("outcome", "status_code", "detail"),
        [
            ("not_found", 404, "Invitation not found."),
            ("not_invited", 409, "This registration has no active invitation."),
        ],
    )
    def test_a_refusal_is_reported(self, monkeypatch, outcome, status_code, detail):
        _record(monkeypatch, "accept_waitlist_invitation", {"outcome": outcome})

        with pytest.raises(HTTPException) as error:
            service.accept_invitation(REGISTRATION_ID, ATTENDEE_ID)

        assert (error.value.status_code, error.value.detail) == (status_code, detail)

    def test_an_unknown_outcome_is_an_error_not_a_success(self, monkeypatch):
        _record(monkeypatch, "accept_waitlist_invitation", {"outcome": "surprise"})

        with pytest.raises(RuntimeError, match="surprise"):
            service.accept_invitation(REGISTRATION_ID, ATTENDEE_ID)


class TestLeaveWaitlist:
    def test_leaving_removes_the_attendees_own_entry(self, monkeypatch):
        calls = _record(monkeypatch, "leave_waitlist", {"outcome": "removed"})

        assert service.leave_waitlist(REGISTRATION_ID, ATTENDEE_ID) is None
        assert calls == [(REGISTRATION_ID, ATTENDEE_ID)]

    def test_an_entry_no_longer_active_is_not_found(self, monkeypatch):
        _record(monkeypatch, "leave_waitlist", {"outcome": "not_active"})

        with pytest.raises(HTTPException) as error:
            service.leave_waitlist(REGISTRATION_ID, ATTENDEE_ID)

        assert error.value.status_code == 404

    def test_an_unknown_outcome_is_an_error_not_a_success(self, monkeypatch):
        _record(monkeypatch, "leave_waitlist", {"outcome": "surprise"})

        with pytest.raises(RuntimeError, match="surprise"):
            service.leave_waitlist(REGISTRATION_ID, ATTENDEE_ID)
