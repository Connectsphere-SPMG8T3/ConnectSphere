"""Pure venue search rules (SCRUM-39, REQUIREMENTS §6.10 / §6.14).

No Supabase involved: `search.evaluate` and `search.search` take plain venue,
criteria and occupant objects, so every boundary case is a unit test.
"""

from datetime import datetime, time, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.modules.venues import search
from app.modules.venues.schemas import (
    AccessibilityFeature,
    Availability,
    Facility,
    LayoutOption,
    Occupant,
    Period,
    ReasonCode,
    VenueLayout,
    VenueSearchCriteria,
    VenueSummary,
)

SGT = timezone(timedelta(hours=8))
VENUE_ID = "b0000000-0000-4000-8000-000000000001"


def sgt(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=SGT)


def make_venue(**overrides) -> VenueSummary:
    fields = {
        "id": VENUE_ID,
        "name": "Hall A",
        "location": "Bukit Timah Campus, Block A",
        "capacity": 150,
        "layouts": [LayoutOption(layout=VenueLayout.theatre, capacity_for_layout=None)],
        "facilities": [Facility.projector, Facility.wifi],
        "accessibility_features": [AccessibilityFeature.wheelchair_access],
        "opens_at": time(8, 0),
        "closes_at": time(22, 0),
        "is_active": True,
        "description": None,
    }
    fields.update(overrides)
    return VenueSummary(**fields)


def make_criteria(**overrides) -> VenueSearchCriteria:
    fields = {"starts_at": sgt(10, 14), "ends_at": sgt(10, 17)}
    fields.update(overrides)
    return VenueSearchCriteria(**fields)


def booking(status: str, start: datetime, end: datetime) -> Occupant:
    return Occupant(kind="booking", period=Period(starts_at=start, ends_at=end), detail=status)


def block(reason: str, start: datetime, end: datetime) -> Occupant:
    return Occupant(kind="block", period=Period(starts_at=start, ends_at=end), detail=reason)


def codes(result) -> list[ReasonCode]:
    return [reason.code for reason in result.reasons]


class TestCriteriaValidation:
    def test_period_must_be_both_or_neither(self):
        with pytest.raises(ValidationError):
            VenueSearchCriteria(starts_at=sgt(10, 14))
        with pytest.raises(ValidationError):
            VenueSearchCriteria(ends_at=sgt(10, 17))

    def test_end_must_be_after_start(self):
        with pytest.raises(ValidationError):
            VenueSearchCriteria(starts_at=sgt(10, 14), ends_at=sgt(10, 14))
        with pytest.raises(ValidationError):
            VenueSearchCriteria(starts_at=sgt(10, 17), ends_at=sgt(10, 14))

    def test_period_must_be_timezone_aware(self):
        with pytest.raises(ValidationError):
            VenueSearchCriteria(starts_at=datetime(2026, 10, 10, 14), ends_at=datetime(2026, 10, 10, 17))

    def test_empty_criteria_are_valid(self):
        criteria = VenueSearchCriteria()
        assert criteria.period is None
        assert criteria.facilities == []


class TestPeriodOverlap:
    def test_half_open_ranges_touching_at_the_boundary_do_not_overlap(self):
        a = Period(starts_at=sgt(10, 9), ends_at=sgt(10, 12))
        b = Period(starts_at=sgt(10, 12), ends_at=sgt(10, 15))
        assert not a.overlaps(b)
        assert not b.overlaps(a)

    def test_one_minute_of_overlap_counts(self):
        a = Period(starts_at=sgt(10, 9), ends_at=sgt(10, 12))
        b = Period(starts_at=sgt(10, 11, 59), ends_at=sgt(10, 13))
        assert a.overlaps(b)

    def test_containment_counts(self):
        outer = Period(starts_at=sgt(1, 0), ends_at=sgt(15, 0))
        inner = Period(starts_at=sgt(10, 14), ends_at=sgt(10, 17))
        assert outer.overlaps(inner)
        assert inner.overlaps(outer)


class TestCapacityRule:
    def test_capacity_below_minimum_excludes_with_reason(self):
        result = search.evaluate(make_venue(capacity=100), make_criteria(min_capacity=150), [])

        assert result.excluded is True
        assert codes(result) == [ReasonCode.capacity_below_minimum]
        assert result.reasons[0].message == "Capacity 100 is below the required 150"

    def test_capacity_equal_to_minimum_passes(self):
        result = search.evaluate(make_venue(capacity=150), make_criteria(min_capacity=150), [])
        assert result.excluded is False

    def test_per_layout_capacity_is_used_when_layout_is_requested(self):
        venue = make_venue(
            capacity=200,
            layouts=[LayoutOption(layout=VenueLayout.theatre, capacity_for_layout=80)],
        )

        result = search.evaluate(venue, make_criteria(min_capacity=150, layout=VenueLayout.theatre), [])

        assert codes(result) == [ReasonCode.capacity_below_minimum]
        assert result.reasons[0].message == "Theatre capacity 80 is below the required 150"

    def test_venue_capacity_is_used_when_layout_has_no_own_figure(self):
        venue = make_venue(capacity=200, layouts=[LayoutOption(layout=VenueLayout.theatre, capacity_for_layout=None)])
        result = search.evaluate(venue, make_criteria(min_capacity=150, layout=VenueLayout.theatre), [])
        assert result.excluded is False

    def test_a_layout_without_its_own_figure_reports_the_venue_capacity(self):
        venue = make_venue(capacity=100, layouts=[LayoutOption(layout=VenueLayout.theatre, capacity_for_layout=None)])

        result = search.evaluate(venue, make_criteria(min_capacity=150, layout=VenueLayout.theatre), [])

        assert result.reasons[0].message == "Capacity 100 is below the required 150"

    def test_no_minimum_means_no_capacity_check(self):
        result = search.evaluate(make_venue(capacity=1), make_criteria(), [])
        assert result.excluded is False


class TestAttributeRules:
    def test_unsupported_layout_excludes(self):
        result = search.evaluate(make_venue(), make_criteria(layout=VenueLayout.banquet), [])
        assert codes(result) == [ReasonCode.layout_not_supported]
        assert result.reasons[0].message == "Banquet layout is not supported"

    def test_missing_facilities_are_named(self):
        criteria = make_criteria(facilities=[Facility.projector, Facility.stage, Facility.sound_system])

        result = search.evaluate(make_venue(), criteria, [])

        assert codes(result) == [ReasonCode.missing_facility]
        assert result.reasons[0].message == "Missing facilities: sound system, stage"

    def test_missing_accessibility_features_are_named(self):
        criteria = make_criteria(
            accessibility=[
                AccessibilityFeature.wheelchair_access,
                AccessibilityFeature.lift_access,
                AccessibilityFeature.hearing_loop,
            ]
        )

        result = search.evaluate(make_venue(), criteria, [])

        assert codes(result) == [ReasonCode.missing_accessibility_feature]
        assert result.reasons[0].message == "Missing accessibility features: hearing loop, lift access"

    def test_location_is_a_case_insensitive_substring_match(self):
        assert search.evaluate(make_venue(), make_criteria(location="bukit"), []).excluded is False
        assert search.evaluate(make_venue(), make_criteria(location="  Block A "), []).excluded is False

        result = search.evaluate(make_venue(), make_criteria(location="Jurong"), [])
        assert codes(result) == [ReasonCode.location_mismatch]

    def test_inactive_venue_is_excluded(self):
        result = search.evaluate(make_venue(is_active=False), make_criteria(), [])
        assert codes(result) == [ReasonCode.inactive]

    def test_a_deactivated_venue_is_excluded_and_returns_once_reactivated(self):
        # SCRUM-64 AC2/AC4: the reason is for people; is_active alone decides search.
        deactivated = make_venue(is_active=False, inactive_reason="long_term_renovation", inactive_note="Roof works")
        assert codes(search.evaluate(deactivated, make_criteria(), [])) == [ReasonCode.inactive]

        reactivated = make_venue(is_active=True, inactive_reason=None, inactive_note=None)
        assert search.evaluate(reactivated, make_criteria(), []).excluded is False

    def test_reasons_accumulate(self):
        criteria = make_criteria(min_capacity=500, layout=VenueLayout.banquet, facilities=[Facility.stage])
        result = search.evaluate(make_venue(is_active=False), criteria, [])
        assert codes(result) == [
            ReasonCode.inactive,
            ReasonCode.capacity_below_minimum,
            ReasonCode.layout_not_supported,
            ReasonCode.missing_facility,
        ]


class TestAvailability:
    def test_no_period_means_availability_is_not_checked(self):
        result = search.evaluate(make_venue(), make_criteria(starts_at=None, ends_at=None), [])
        assert result.availability == Availability.not_checked
        assert result.excluded is False

    def test_free_venue_is_available(self):
        result = search.evaluate(make_venue(), make_criteria(), [])
        assert result.availability == Availability.available
        assert result.reasons == []

    def test_back_to_back_booking_leaves_the_venue_available(self):
        occupants = [booking("approved", sgt(10, 11), sgt(10, 14))]
        result = search.evaluate(make_venue(), make_criteria(), occupants)
        assert result.availability == Availability.available

    def test_overlapping_hold_makes_the_venue_unavailable(self):
        occupants = [booking("held", sgt(10, 13), sgt(10, 16))]

        result = search.evaluate(make_venue(), make_criteria(), occupants)

        assert result.availability == Availability.unavailable
        assert result.excluded is True
        assert codes(result) == [ReasonCode.held]
        assert result.reasons[0].message == "Held by another event 10 Oct 13:00–16:00"

    @pytest.mark.parametrize("status", ["approved", "re_review"])
    def test_overlapping_booking_makes_the_venue_unavailable(self, status):
        occupants = [booking(status, sgt(10, 16, 59), sgt(10, 18))]

        result = search.evaluate(make_venue(), make_criteria(), occupants)

        assert codes(result) == [ReasonCode.booked]
        assert result.reasons[0].message == "Booked by another event 10 Oct 16:59–18:00"

    @pytest.mark.parametrize("reason", ["maintenance", "renovation", "safety", "internal_activity", "other"])
    def test_any_block_reason_makes_the_venue_unavailable(self, reason):
        occupants = [block(reason, sgt(1, 0), sgt(15, 0))]

        result = search.evaluate(make_venue(), make_criteria(), occupants)

        assert result.availability == Availability.unavailable
        assert codes(result) == [ReasonCode.blocked]
        assert result.reasons[0].message == f"Blocked: {reason.replace('_', ' ')} 1 Oct 00:00 – 15 Oct 00:00"

    def test_occupant_times_are_shown_in_the_searchers_timezone(self):
        # Stored in UTC, searched in Singapore time: 05:00Z is 13:00 SGT.
        occupants = [booking("held", datetime(2026, 10, 10, 5, tzinfo=timezone.utc), datetime(2026, 10, 10, 8, tzinfo=timezone.utc))]
        result = search.evaluate(make_venue(), make_criteria(), occupants)
        assert result.reasons[0].message == "Held by another event 10 Oct 13:00–16:00"

    def test_occupant_times_follow_the_offset_the_period_was_searched_in(self):
        # Searched in UTC: the same 13:00 SGT hold reads as 05:00.
        criteria = make_criteria(
            starts_at=datetime(2026, 10, 10, 6, tzinfo=timezone.utc), ends_at=datetime(2026, 10, 10, 9, tzinfo=timezone.utc)
        )
        occupants = [booking("held", sgt(10, 13), sgt(10, 16))]

        result = search.evaluate(make_venue(), criteria, occupants)

        assert result.reasons[0].message == "Held by another event 10 Oct 05:00–08:00"

    def test_occupants_that_do_not_overlap_are_ignored(self):
        occupants = [booking("held", sgt(11, 14), sgt(11, 17)), block("safety", sgt(20, 0), sgt(22, 0))]
        result = search.evaluate(make_venue(), make_criteria(), occupants)
        assert result.availability == Availability.available

    def test_an_earlier_occupant_that_does_not_overlap_does_not_hide_a_later_conflict(self):
        occupants = [booking("held", sgt(10, 15), sgt(10, 16)), booking("approved", sgt(10, 9), sgt(10, 10))]

        result = search.evaluate(make_venue(), make_criteria(), occupants)

        assert codes(result) == [ReasonCode.held]

    def test_availability_and_suitability_reasons_stay_distinguishable(self):
        occupants = [block("maintenance", sgt(10, 8), sgt(10, 15))]
        result = search.evaluate(make_venue(capacity=100), make_criteria(min_capacity=150), occupants)
        assert codes(result) == [ReasonCode.capacity_below_minimum, ReasonCode.blocked]
        assert result.availability == Availability.unavailable


class TestSearch:
    def _venues(self):
        return [
            make_venue(id="b0000000-0000-4000-8000-000000000003", name="Zeta Hall", capacity=200),
            make_venue(id="b0000000-0000-4000-8000-000000000002", name="Beta Hall", capacity=50),
            make_venue(id="b0000000-0000-4000-8000-000000000001", name="Alpha Hall", capacity=200),
        ]

    def test_included_venues_come_first_then_excluded_each_by_name(self):
        occupants = {"b0000000-0000-4000-8000-000000000001": [booking("held", sgt(10, 15), sgt(10, 16))]}

        results = search.search(self._venues(), make_criteria(min_capacity=100), occupants)

        assert [(r.venue.name, r.excluded) for r in results] == [
            ("Zeta Hall", False),
            ("Alpha Hall", True),
            ("Beta Hall", True),
        ]

    def test_occupants_are_matched_to_their_venue(self):
        occupants = {"b0000000-0000-4000-8000-000000000002": [block("safety", sgt(1, 0), sgt(31, 0))]}

        results = {r.venue.name: r for r in search.search(self._venues(), make_criteria(), occupants)}

        assert results["Beta Hall"].availability == Availability.unavailable
        assert results["Alpha Hall"].availability == Availability.available
