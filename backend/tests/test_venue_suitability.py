"""Pure suitability rules (CR-94; the module story 18 extends): does one venue
meet one set of requirements, and how badly does it miss?

Capacity and required facilities are hard rules (the venue is Unsuitable);
layout and operating hours only warn.
"""

from datetime import datetime, time, timedelta, timezone

from app.modules.venues.schemas import (
    Facility,
    LayoutOption,
    Period,
    SuitabilityCode,
    SuitabilitySeverity,
    SuitabilityVerdict,
    VenueLayout,
    VenueRequirements,
    VenueSummary,
)
from app.modules.venues.suitability import check

SGT = timezone(timedelta(hours=8))


def make_venue(**overrides) -> VenueSummary:
    fields = {
        "id": "b0000000-0000-4000-8000-000000000001",
        "name": "Hall A",
        "location": "Bukit Timah Campus",
        "capacity": 150,
        "layouts": [LayoutOption(layout=VenueLayout.theatre, capacity_for_layout=None)],
        "facilities": [Facility.projector, Facility.microphone],
        "opens_at": time(8, 0),
        "closes_at": time(22, 0),
        "is_active": True,
    }
    fields.update(overrides)
    return VenueSummary(**fields)


def sgt_period(start: tuple[int, int], end: tuple[int, int]) -> Period:
    return Period(
        starts_at=datetime(2026, 10, 10, *start, tzinfo=SGT), ends_at=datetime(2026, 10, 10, *end, tzinfo=SGT)
    )


def codes(result) -> set[SuitabilityCode]:
    return {reason.code for reason in result.reasons}


class TestCapacity:
    def test_attendance_above_capacity_is_unsuitable(self):
        result = check(make_venue(capacity=100), VenueRequirements(expected_attendance=120))

        assert result.verdict == SuitabilityVerdict.unsuitable
        assert codes(result) == {SuitabilityCode.capacity}
        assert result.reasons[0].severity == SuitabilitySeverity.unsuitable
        assert result.reasons[0].message == "Capacity 100 is below the expected attendance of 120."

    def test_attendance_equal_to_capacity_is_suitable(self):
        result = check(make_venue(capacity=120), VenueRequirements(expected_attendance=120))

        assert result.verdict == SuitabilityVerdict.suitable
        assert result.reasons == []

    def test_per_layout_capacity_applies_when_the_requested_layout_records_one(self):
        venue = make_venue(capacity=150, layouts=[LayoutOption(layout=VenueLayout.theatre, capacity_for_layout=100)])

        result = check(venue, VenueRequirements(expected_attendance=120, layout_preference=VenueLayout.theatre))

        assert result.verdict == SuitabilityVerdict.unsuitable
        assert result.reasons[0].message == "Capacity 100 is below the expected attendance of 120."

    def test_venue_wide_capacity_applies_when_no_layout_is_requested(self):
        venue = make_venue(capacity=150, layouts=[LayoutOption(layout=VenueLayout.theatre, capacity_for_layout=100)])

        assert check(venue, VenueRequirements(expected_attendance=120)).verdict == SuitabilityVerdict.suitable

    def test_no_expected_attendance_never_fails_capacity(self):
        assert check(make_venue(capacity=1), VenueRequirements()).verdict == SuitabilityVerdict.suitable


class TestFacilities:
    def test_a_missing_required_facility_is_unsuitable_and_named(self):
        venue = make_venue(facilities=[Facility.microphone])

        result = check(venue, VenueRequirements(facilities_required=[Facility.sound_system, Facility.projector]))

        assert result.verdict == SuitabilityVerdict.unsuitable
        assert codes(result) == {SuitabilityCode.missing_facility}
        assert result.reasons[0].severity == SuitabilitySeverity.unsuitable
        assert result.reasons[0].message == "Missing facilities this event needs: projector, sound system."

    def test_missing_facilities_are_listed_alphabetically(self):
        """Five of them, so a set's arbitrary order can't pass for sorted by luck."""
        required = [Facility.wifi, Facility.stage, Facility.catering_space, Facility.whiteboard, Facility.sound_system]

        result = check(make_venue(facilities=[]), VenueRequirements(facilities_required=required))

        assert result.reasons[0].message == (
            "Missing facilities this event needs: catering space, sound system, stage, whiteboard, wifi."
        )

    def test_every_required_facility_present_is_suitable(self):
        venue = make_venue(facilities=[Facility.projector, Facility.microphone, Facility.stage])

        result = check(venue, VenueRequirements(facilities_required=[Facility.projector, Facility.microphone]))

        assert result.verdict == SuitabilityVerdict.suitable


class TestLayout:
    def test_an_unsupported_layout_only_warns(self):
        venue = make_venue(layouts=[LayoutOption(layout=VenueLayout.boardroom)])

        result = check(venue, VenueRequirements(layout_preference=VenueLayout.u_shape))

        assert result.verdict == SuitabilityVerdict.suitable_with_warnings
        assert codes(result) == {SuitabilityCode.layout_not_supported}
        assert result.reasons[0].severity == SuitabilitySeverity.warning
        assert result.reasons[0].message == "The u shape layout this event needs is not supported."

    def test_no_layout_preference_never_warns(self):
        assert check(make_venue(layouts=[]), VenueRequirements()).verdict == SuitabilityVerdict.suitable


class TestOperatingHours:
    def test_a_period_ending_after_closing_only_warns(self):
        venue = make_venue(opens_at=time(8, 0), closes_at=time(11, 0))

        result = check(venue, VenueRequirements(period=sgt_period((9, 0), (12, 0))))

        assert result.verdict == SuitabilityVerdict.suitable_with_warnings
        assert codes(result) == {SuitabilityCode.outside_operating_hours}
        assert result.reasons[0].severity == SuitabilitySeverity.warning
        assert result.reasons[0].message == "The booking's time falls outside the venue's operating hours (08:00–11:00)."

    def test_a_period_starting_before_opening_warns(self):
        venue = make_venue(opens_at=time(9, 0), closes_at=time(22, 0))

        assert codes(check(venue, VenueRequirements(period=sgt_period((8, 59), (12, 0))))) == {
            SuitabilityCode.outside_operating_hours
        }

    def test_a_period_exactly_matching_the_hours_is_suitable(self):
        venue = make_venue(opens_at=time(9, 0), closes_at=time(18, 0))

        assert check(venue, VenueRequirements(period=sgt_period((9, 0), (18, 0)))).reasons == []

    def test_hours_are_read_on_the_singapore_wall_clock(self):
        """09:00–12:00 SGT is 01:00–04:00 UTC: still inside 08:00–22:00 hours."""
        venue = make_venue(opens_at=time(8, 0), closes_at=time(22, 0))
        period = Period(
            starts_at=datetime(2026, 10, 10, 1, tzinfo=timezone.utc), ends_at=datetime(2026, 10, 10, 4, tzinfo=timezone.utc)
        )

        assert check(venue, VenueRequirements(period=period)).reasons == []

    def test_the_end_is_read_on_the_singapore_wall_clock_too(self):
        """12:00–15:00 UTC is 20:00–23:00 SGT: only the end, read in SGT, is past 22:00."""
        venue = make_venue(opens_at=time(8, 0), closes_at=time(22, 0))
        period = Period(
            starts_at=datetime(2026, 10, 10, 12, tzinfo=timezone.utc), ends_at=datetime(2026, 10, 10, 15, tzinfo=timezone.utc)
        )

        assert codes(check(venue, VenueRequirements(period=period))) == {SuitabilityCode.outside_operating_hours}

    def test_no_period_never_checks_hours(self):
        venue = make_venue(opens_at=time(8, 0), closes_at=time(9, 0))

        assert check(venue, VenueRequirements()).verdict == SuitabilityVerdict.suitable


class TestVerdict:
    def test_a_hard_failure_outranks_warnings(self):
        venue = make_venue(capacity=50, layouts=[], opens_at=time(10, 0))
        req = VenueRequirements(
            expected_attendance=120, layout_preference=VenueLayout.theatre, period=sgt_period((9, 0), (12, 0))
        )

        result = check(venue, req)

        assert result.verdict == SuitabilityVerdict.unsuitable
        assert codes(result) == {
            SuitabilityCode.capacity,
            SuitabilityCode.layout_not_supported,
            SuitabilityCode.outside_operating_hours,
        }
