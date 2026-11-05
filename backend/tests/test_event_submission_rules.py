"""Features 2-3 and 19: the rules a request must pass to be submitted, and to be changed.

Calls the rule functions directly with a frozen clock and compares whole error lists: the
SPA shows each `msg` under the field its `loc` names, so a wrong or extra error is a defect
even when the right text is also present.
"""

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.modules.events import service

# 20:00 UTC on 1 May: 2 May in Singapore and Kiritimati, still 1 May in Honolulu.
NOW = datetime(2031, 5, 1, 20, tzinfo=timezone.utc)
STARTS_AT = "2031-06-10T09:00:00+08:00"
ENDS_AT = "2031-06-10T12:00:00+08:00"
OPENS_AT = "2031-05-10T09:00:00+08:00"
CLOSES_AT = "2031-06-01T09:00:00+08:00"
VALID = {
    "name": "Open Day", "purpose": "Outreach", "starts_at": STARTS_AT, "ends_at": ENDS_AT,
    "expected_attendance": 50, "layout_preference": "theatre", "event_timezone": "Asia/Singapore",
}
REGISTRATION = {
    "registration_enabled": True, "registration_capacity": 50,
    "registration_opens_at": OPENS_AT, "registration_closes_at": CLOSES_AT,
}


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW.astimezone(tz)


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch):
    monkeypatch.setattr(service, "datetime", _FrozenDatetime)


def _errors(**changes) -> list[dict]:
    return service._submission_errors({**VALID, **changes})


def _error(loc: list, msg: str, kind: str = "value_error") -> dict:
    return {"loc": ["body", *loc], "msg": msg, "type": kind}


def _space(**fields) -> dict:
    return {"label": "Hall", "expected_pax": 50, "layout_preference": "theatre", **fields}


class TestEventSchedule:
    def test_a_complete_request_has_no_errors(self):
        assert _errors() == []

    @pytest.mark.parametrize("field", ["purpose", "starts_at", "ends_at", "expected_attendance", "layout_preference"])
    @pytest.mark.parametrize("value", [None, ""], ids=["null", "blank"])
    def test_each_required_field_is_named(self, field, value):
        assert _error([field], "Field required", "missing") in _errors(**{field: value})

    def test_a_request_with_spaces_needs_no_layout_of_its_own(self):
        assert _errors(layout_preference=None, spaces=[_space()]) == []

    def test_an_event_cannot_end_when_it_starts(self):
        assert _errors(ends_at=STARTS_AT) == [_error(["ends_at"], "End time must be after start time.")]

    def test_an_event_today_is_refused_and_tomorrow_is_allowed(self):
        today = _error(["starts_at"], "Event date must be after today.")

        assert today in _errors(starts_at="2031-05-02T09:00:00+08:00")
        assert today not in _errors(starts_at="2031-05-03T00:30:00+08:00", ends_at="2031-05-03T02:00:00+08:00")

    def test_today_is_judged_in_the_events_own_timezone(self):
        # 2 May there and 1 May now in Honolulu, though it is already that day in Singapore.
        assert _errors(
            event_timezone="Pacific/Honolulu", starts_at="2031-05-02T00:30:00-10:00", ends_at="2031-05-02T02:00:00-10:00",
        ) == []

    def test_a_time_later_today_in_a_zone_ahead_of_utc_is_still_tomorrow_there(self):
        assert _errors(
            event_timezone="Pacific/Kiritimati", starts_at="2031-05-03T00:30:00+14:00", ends_at="2031-05-03T02:00:00+14:00",
        ) == []

    def test_no_timezone_falls_back_to_singapore(self):
        assert _errors(event_timezone=None, starts_at="2031-05-02T09:00:00+08:00", ends_at=ENDS_AT) == [
            _error(["starts_at"], "Event date must be after today.")
        ]

    def test_a_time_with_no_offset_is_refused(self):
        with pytest.raises(HTTPException) as error:
            _errors(starts_at="2031-06-10T09:00:00")

        assert error.value.status_code == 422


class TestRegistrationRules:
    def _registration(self, **changes) -> list[dict]:
        return _errors(**{**REGISTRATION, **changes})

    def test_complete_registration_settings_have_no_errors(self):
        assert self._registration() == []

    def test_settings_are_not_checked_while_registration_is_off(self):
        assert _errors(registration_enabled=False, registration_capacity=None) == []

    @pytest.mark.parametrize("capacity", [None, 0], ids=["missing", "zero"])
    def test_a_capacity_is_required(self, capacity):
        assert self._registration(registration_capacity=capacity) == [
            _error(["registration_capacity"], "Registration capacity is required when registration is enabled.")
        ]

    def test_an_opening_time_is_required(self):
        assert self._registration(registration_opens_at=None) == [
            _error(["registration_opens_at"], "Registration opening time is required when registration is enabled.")
        ]

    def test_a_closing_time_is_required(self):
        assert self._registration(registration_closes_at=None) == [
            _error(["registration_closes_at"], "Registration closing time is required when registration is enabled.")
        ]

    def test_opening_today_is_refused(self):
        assert self._registration(registration_opens_at="2031-05-02T09:00:00+08:00") == [
            _error(["registration_opens_at"], "Registration opening date must be after today.")
        ]

    def test_opening_tomorrow_in_the_events_timezone_is_allowed(self):
        assert self._registration(
            event_timezone="Pacific/Honolulu", registration_opens_at="2031-05-02T00:30:00-10:00",
        ) == []

    def test_closing_when_it_opens_is_refused(self):
        assert self._registration(registration_closes_at=OPENS_AT) == [
            _error(["registration_closes_at"], "Registration closing time must be after opening time.")
        ]

    def test_closing_today_is_refused(self):
        assert _error(["registration_closes_at"], "Registration closing date must be after today.") in self._registration(
            registration_closes_at="2031-05-02T23:00:00+08:00",
        )

    def test_closing_tomorrow_in_the_events_timezone_is_allowed(self):
        assert self._registration(
            event_timezone="Pacific/Honolulu", registration_opens_at="2031-05-02T00:30:00-10:00",
            registration_closes_at="2031-05-02T02:00:00-10:00",
        ) == []

    def test_closing_exactly_when_the_event_ends_is_allowed(self):
        assert self._registration(registration_closes_at=ENDS_AT) == []

    def test_closing_after_the_event_ends_is_refused(self):
        assert self._registration(registration_closes_at="2031-06-10T12:01:00+08:00") == [
            _error(["registration_closes_at"], "Registration closing time cannot be after the event end time.")
        ]

    def test_with_no_event_end_only_the_end_itself_is_reported(self):
        assert self._registration(ends_at=None) == [_error(["ends_at"], "Field required", "missing")]


class TestSpaceSchedules:
    OUTSIDE = "A space schedule must be within the event's overall schedule."

    def test_a_space_with_no_times_of_its_own_is_fine(self):
        assert _errors(spaces=[_space()]) == []

    def test_a_space_may_fill_the_event_exactly(self):
        assert _errors(spaces=[_space(starts_at=STARTS_AT, ends_at=ENDS_AT)]) == []

    def test_each_error_names_the_space_it_belongs_to(self):
        early = _space(starts_at="2031-06-10T08:59:00+08:00", ends_at=ENDS_AT)
        late = _space(starts_at=STARTS_AT, ends_at="2031-06-10T12:01:00+08:00")

        assert _errors(spaces=[_space(), early, late]) == [
            _error(["spaces", 1, "starts_at"], self.OUTSIDE),
            _error(["spaces", 2, "ends_at"], self.OUTSIDE),
        ]

    @pytest.mark.parametrize("missing", ["starts_at", "ends_at"])
    def test_space_times_need_the_events_whole_schedule(self, missing):
        space = _space(starts_at=STARTS_AT, ends_at=ENDS_AT)

        assert service._space_schedule_errors(space, {**VALID, missing: None}, 3) == [
            _error(["spaces", 3, "starts_at"], "An individual space schedule requires the event's overall schedule.")
        ]

    @pytest.mark.parametrize("field", ["label", "expected_pax", "layout_preference"])
    def test_each_space_field_is_required(self, field):
        assert _errors(spaces=[_space(), _space(**{field: ""})]) == [
            _error(["spaces", 1, field], "Field required", "missing")
        ]


class TestWithdrawalCutoff:
    def test_no_cutoff_has_no_errors(self):
        assert service._withdrawal_cutoff_errors({"withdrawal_closes_at": None}) == []

    def test_a_cutoff_needs_a_start_time(self):
        assert service._withdrawal_cutoff_errors({"withdrawal_closes_at": STARTS_AT}) == [
            _error(["withdrawal_closes_at"], "Withdrawal cutoff requires an event start time.")
        ]

    def test_a_cutoff_exactly_at_the_start_is_allowed(self):
        assert service._withdrawal_cutoff_errors({"withdrawal_closes_at": STARTS_AT, "starts_at": STARTS_AT}) == []

    def test_a_cutoff_after_the_start_is_refused(self):
        row = {"withdrawal_closes_at": "2031-06-10T09:01:00+08:00", "starts_at": STARTS_AT}

        assert service._withdrawal_cutoff_errors(row) == [
            _error(["withdrawal_closes_at"], "Withdrawal cutoff cannot be after the event start time.")
        ]

    def test_saving_a_bad_cutoff_is_a_validation_error(self):
        with pytest.raises(HTTPException) as error:
            service._validate_withdrawal_cutoff({"withdrawal_closes_at": STARTS_AT})

        assert error.value.status_code == 422
        assert error.value.detail[0]["loc"] == ["body", "withdrawal_closes_at"]


class TestChangedEventsPassTheSameRules:
    def test_a_rule_the_event_already_breaks_does_not_block_a_change(self):
        broken = {**VALID, **REGISTRATION, "registration_opens_at": "2031-04-01T09:00:00+08:00"}

        assert service._refuse_new_submission_errors(broken, dict(broken)) is None

    def test_only_what_the_change_newly_breaks_is_reported(self):
        broken = {**VALID, "purpose": ""}

        with pytest.raises(service.ChangeRequestInvalidError) as error:
            service._refuse_new_submission_errors(broken, {**broken, "ends_at": STARTS_AT})

        assert error.value.detail == [_error(["ends_at"], "End time must be after start time.")]

    def test_a_change_cannot_blank_the_name(self):
        with pytest.raises(service.ChangeRequestInvalidError) as error:
            service._refuse_new_submission_errors(VALID, {**VALID, "name": ""})

        assert error.value.detail == [_error(["event", "name"], "Field required", "missing")]
