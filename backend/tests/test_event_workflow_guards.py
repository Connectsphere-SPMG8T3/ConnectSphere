"""Features 4-7 and 19: assignment, the coordinator's dashboard, edits and change decisions.

Calls the service with its reads replaced, to pin which event each read asks about and the
branches the API tests pass over. Traces to SCRUM-12, SCRUM-72, stories 32, 37 and 112.
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.modules.events import change_impact, lifecycle, repository, service
from app.modules.events.schemas import (
    EventDetailsEdit,
    EventSpaceRequestFields,
    EventSpaceRequestUpdate,
    EventUpdateRequest,
    _required_text,
)
from tests.test_coordinator_dashboard import event_row

EVENT_ID = "e0000000-0000-4000-8000-000000000001"
SPACE_ID = "d0000000-0000-4000-8000-000000000001"
OTHER_SPACE_ID = "d0000000-0000-4000-8000-000000000002"
USER_ID = "a0000000-0000-4000-8000-000000000001"
STARTS_AT = "2031-06-10T09:00:00+08:00"
ENDS_AT = "2031-06-10T12:00:00+08:00"


def _space(space_id=SPACE_ID, **fields) -> dict:
    return {"id": space_id, "label": "Hall", "expected_pax": 50, "layout_preference": "theatre", **fields}


def _event(**fields) -> dict:
    return {
        "id": EVENT_ID, "name": "Open Day", "purpose": "Outreach", "status": "planning", "version": 4,
        "starts_at": STARTS_AT, "ends_at": ENDS_AT, "expected_attendance": 50, "layout_preference": "theatre",
        "event_timezone": "Asia/Singapore", **fields,
    }


class TestAssign:
    def _assign(self, monkeypatch, **fields):
        reads = []
        monkeypatch.setattr(
            repository, "get_lead_event", lambda event_id: reads.append(event_id) or _event(**fields),
        )
        with pytest.raises(service.EventConflictError) as error:
            service.assign(EVENT_ID, USER_ID, "new-coordinator")
        assert reads == [EVENT_ID]
        assert error.value.detail == service.ALREADY_ASSIGNED_MESSAGE

    def test_a_queued_event_that_somehow_has_a_coordinator_is_refused(self, monkeypatch):
        self._assign(monkeypatch, status="submitted", coordinator_id="someone")

    def test_an_active_event_with_no_coordinator_is_refused(self, monkeypatch):
        self._assign(monkeypatch, status="under_review", coordinator_id=None)


class TestCoordinatorDashboardReads:
    @pytest.fixture()
    def reads(self, monkeypatch):
        calls = SimpleNamespace(venue_spaces=[])
        rows = [
            event_row("e-001", "under_review"),
            event_row("e-002", "planning", spaces=[_space("s-1", label="Main hall")]),
            event_row("e-003", "rejected"),
        ]
        monkeypatch.setattr(repository, "list_coordinator_events", lambda coordinator_id, statuses: rows)

        def keep(name):
            def read(ids):
                setattr(calls, name, ids)
                return {}
            return read

        for name in ("list_latest_resubmissions", "list_open_cancellation_requests", "list_open_change_requests"):
            monkeypatch.setattr(repository, name, keep(name))
        monkeypatch.setattr(service.venues_service, "booking_statuses_by_event", lambda ids: {})
        monkeypatch.setattr(service.venues_service, "affected_event_ids", lambda ids: set())
        monkeypatch.setattr(
            service.venues_service, "booking_readiness_by_event_space",
            lambda ids: {"e-002": {"s-1": ["booking-readiness"]}},
        )
        monkeypatch.setattr(service.equipment_service, "equipment_readiness_by_event", lambda ids: {})

        def venue_readiness(bookings, affected, spaces):
            calls.venue_spaces.append(spaces)
            return service.ReadinessState.not_required

        monkeypatch.setattr(service, "SpaceReadiness", lambda label, bookings: (label, bookings))
        monkeypatch.setattr(service, "_venue_readiness", venue_readiness)
        return calls

    def test_resubmissions_are_read_for_events_under_review_only(self, reads):
        service.coordinator_dashboard(USER_ID)

        assert reads.list_latest_resubmissions == ["e-001"]

    def test_open_requests_are_read_for_every_active_event_and_not_rejected_ones(self, reads):
        service.coordinator_dashboard(USER_ID)

        assert reads.list_open_change_requests == reads.list_open_cancellation_requests == ["e-001", "e-002"]

    def test_each_space_gets_its_own_bookings(self, reads):
        service.coordinator_dashboard(USER_ID)

        assert reads.venue_spaces == [[], [("Main hall", ["booking-readiness"])]]


class TestEditDetails:
    def test_an_edit_with_nothing_in_it_says_so_at_the_form_level(self, monkeypatch):
        monkeypatch.setattr(service, "_assigned_event", lambda event_id, coordinator_id: _event())

        with pytest.raises(HTTPException) as error:
            service.edit_details(EVENT_ID, USER_ID, EventDetailsEdit(version=4))

        assert error.value.status_code == 422
        assert error.value.detail == [{"loc": ["body"], "msg": "Nothing to change.", "type": "value_error"}]


class TestApproveChange:
    @pytest.fixture()
    def decision(self, monkeypatch):
        calls = SimpleNamespace(requests=[], bookings=[], approved=[], space_values={}, event_values={})
        row = _event(spaces=[
            _space(starts_at=STARTS_AT, ends_at=ENDS_AT), _space(OTHER_SPACE_ID),
        ])
        monkeypatch.setattr(service, "_assigned_event", lambda event_id, coordinator_id: row)
        monkeypatch.setattr(service, "_refuse_deciding_change", lambda row: None)
        monkeypatch.setattr(
            repository, "get_open_change_request",
            lambda event_id: calls.requests.append(event_id) or {"changes": {"event": [], "spaces": []}},
        )
        monkeypatch.setattr(service, "_approved_values", lambda row, changes: (calls.event_values, calls.space_values))
        monkeypatch.setattr(
            service.venues_service, "change_bookings", lambda event_id: calls.bookings.append(event_id) or [],
        )
        monkeypatch.setattr(change_impact, "booking_plans", lambda *args: [])
        monkeypatch.setattr(
            repository, "approve_event_change",
            lambda *args, **kwargs: calls.approved.append(args) or {"outcome": "ok", "event": row},
        )
        monkeypatch.setattr(service, "_raise_for_change_outcome", lambda outcome: None)
        monkeypatch.setattr(service, "_to_response", lambda event: "approved")
        return calls

    def test_the_change_is_approved_for_that_event_from_the_allowed_statuses(self, decision):
        assert service.approve_change(EVENT_ID, USER_ID, 4) == "approved"

        assert decision.requests == decision.bookings == [EVENT_ID]
        assert decision.approved[0][:4] == (EVENT_ID, USER_ID, 4, lifecycle.change_requestable_from())

    def test_a_space_change_is_checked_against_the_submission_rules(self, decision):
        decision.space_values = {SPACE_ID: {"ends_at": "2031-06-10T12:30:00+08:00"}}

        with pytest.raises(service.ChangeRequestInvalidError) as error:
            service.approve_change(EVENT_ID, USER_ID, 4)

        assert error.value.detail[0]["loc"] == ["body", "spaces", 0, "ends_at"]
        assert decision.approved == []


class TestChangeImpact:
    @pytest.fixture()
    def impact(self, monkeypatch):
        calls = SimpleNamespace(requests=[], bookings=[], shortfalls=[], counts=[], changes=[])
        monkeypatch.setattr(service, "_assigned_event", lambda event_id, coordinator_id: _event())
        monkeypatch.setattr(
            repository, "get_open_change_request",
            lambda event_id: calls.requests.append(event_id) or {"changes": {"event": calls.changes}},
        )
        monkeypatch.setattr(
            service.venues_service, "change_bookings", lambda event_id: calls.bookings.append(event_id) or [],
        )
        monkeypatch.setattr(change_impact, "booking_plans", lambda *args: [])
        monkeypatch.setattr(
            service.equipment_service, "shortfalls", lambda *args: calls.shortfalls.append(args) or [],
        )
        monkeypatch.setattr(
            service.registrations_service, "registered_count", lambda event_id: calls.counts.append(event_id) or 12,
        )
        return calls

    @pytest.mark.parametrize(
        ("field", "after"),
        [("starts_at", "2031-06-10T10:00:00+08:00"), ("ends_at", "2031-06-10T13:00:00+08:00"),
         ("event_timezone", "Asia/Tokyo")],
    )
    def test_anything_that_moves_the_time_counts_who_would_be_told(self, impact, field, after):
        impact.changes = [{"field": field, "after": after}]

        result = service.change_request_impact(EVENT_ID, USER_ID)

        assert impact.requests == impact.bookings == impact.counts == [EVENT_ID]
        assert result.attendees_notified == 12

    def test_another_field_tells_no_attendee(self, impact):
        impact.changes = [{"field": "expected_attendance", "after": 80}]

        service.change_request_impact(EVENT_ID, USER_ID)

        assert impact.counts == impact.shortfalls == []

    def test_equipment_is_checked_for_the_new_window(self, impact):
        new_end = "2031-06-10T13:00:00+08:00"
        impact.changes = [{"field": "ends_at", "after": new_end}]

        service.change_request_impact(EVENT_ID, USER_ID)

        assert impact.shortfalls == [(EVENT_ID, service._parse_datetime(STARTS_AT), service._parse_datetime(new_end))]


class TestConcurrentSaves:
    def test_submit_is_refused_when_the_draft_changed_during_the_save(self, monkeypatch):
        monkeypatch.setattr(service, "_owned_event", lambda *args: _event(status="draft"))
        monkeypatch.setattr(service, "_validate_submission", lambda row: None)
        monkeypatch.setattr(repository, "update_event", lambda *args: None)

        with pytest.raises(service.EventConflictError):
            service.submit(EVENT_ID, USER_ID, EventUpdateRequest(name="Open Day"))

    def test_submit_is_refused_when_another_save_won_the_status_change(self, monkeypatch):
        monkeypatch.setattr(service, "_owned_event", lambda *args: _event(status="draft"))
        monkeypatch.setattr(service, "_validate_submission", lambda row: None)
        monkeypatch.setattr(repository, "transition_event", lambda *args: None)

        with pytest.raises(service.EventConflictError):
            service.submit(EVENT_ID, USER_ID)

    def test_resubmit_is_refused_when_its_edit_lost_to_another_save(self, monkeypatch):
        monkeypatch.setattr(service, "_owned_event", lambda *args: _event(status="returned"))
        monkeypatch.setattr(service, "_validate_submission", lambda row: None)
        monkeypatch.setattr(repository, "edit_event", lambda *args: None)
        body = SimpleNamespace(model_dump=lambda **kwargs: {"purpose": "New purpose"}, resubmission_note="Done")

        with pytest.raises(service.EventConflictError) as error:
            service.resubmit(EVENT_ID, USER_ID, body)

        assert error.value.detail == service.STALE_EVENT_MESSAGE


class TestSpaceAndEventSchemas:
    def test_moving_a_space_outside_the_event_is_refused(self, monkeypatch):
        space = _space(starts_at=STARTS_AT, ends_at=ENDS_AT, version=1, facilities_required=[])
        monkeypatch.setattr(service, "_space_event", lambda *args: (_event(), space))
        body = EventSpaceRequestUpdate(starts_at="2031-06-10T08:00:00+08:00", ends_at=ENDS_AT)

        with pytest.raises(HTTPException) as error:
            service.update_space(SPACE_ID, USER_ID, body)

        assert error.value.status_code == 422
        assert error.value.detail[0]["loc"] == ["body", "spaces", 0, "starts_at"]

    def test_a_space_cannot_end_when_it_starts(self):
        with pytest.raises(ValidationError, match="Space end time must be after its start time"):
            EventSpaceRequestFields(
                label="Hall", expected_pax=5, layout_preference="theatre", starts_at=STARTS_AT, ends_at=STARTS_AT,
            )

    def test_a_space_update_must_move_both_ends_together(self):
        with pytest.raises(ValidationError, match="starts_at and ends_at must be updated together"):
            EventSpaceRequestUpdate(starts_at=STARTS_AT)

    def test_an_event_without_a_timezone_is_valid(self):
        assert EventUpdateRequest(event_timezone=None).event_timezone is None

    @pytest.mark.parametrize("zone", ["Mars/Olympus", "../etc/passwd"])
    def test_an_unknown_timezone_is_refused(self, zone):
        with pytest.raises(ValidationError, match="event_timezone must be a valid IANA timezone"):
            EventUpdateRequest(event_timezone=zone)

    def test_required_text_must_be_text(self):
        with pytest.raises(ValueError, match="A reason is required"):
            _required_text(None, "A reason is required")
