"""Pure rules for REQUIREMENTS VC-R2 (SCRUM-63): does editing a venue put an
upcoming booking's event at odds with the venue's new attributes?

Only *newly* broken rules are reported: a pre-existing mismatch the edit did
not cause must never surface as a warning about this edit.
"""

from datetime import datetime, time, timedelta, timezone

from app.modules.venues.impact import affected_bookings
from app.modules.venues.schemas import AccessibilityFeature, BookingImpactContext, Facility, LayoutOption, Period, VenueLayout, VenueSummary

SGT = timezone(timedelta(hours=8))


def make_venue(**overrides) -> VenueSummary:
    fields = {
        "id": "b0000000-0000-4000-8000-000000000001",
        "name": "Hall A",
        "location": "Bukit Timah Campus",
        "capacity": 150,
        "layouts": [LayoutOption(layout=VenueLayout.theatre, capacity_for_layout=None)],
        "facilities": [Facility.projector, Facility.microphone],
        "accessibility_features": [AccessibilityFeature.wheelchair_access],
        "opens_at": time(8, 0),
        "closes_at": time(22, 0),
        "is_active": True,
        "description": None,
    }
    fields.update(overrides)
    return VenueSummary(**fields)


def make_booking(**overrides) -> BookingImpactContext:
    fields = {
        "booking_id": "d0000000-0000-4000-8000-000000000001",
        "event_id": "e0000000-0000-4000-8000-000000000101",
        "event_name": "Annual Gala",
        "coordinator_id": "a0000000-0000-4000-8000-000000000009",
        "period": Period(
            starts_at=datetime(2026, 10, 10, 9, tzinfo=SGT), ends_at=datetime(2026, 10, 10, 12, tzinfo=SGT)
        ),
        "expected_attendance": 120,
        "layout_preference": VenueLayout.theatre,
        "facilities_required": [Facility.projector],
    }
    fields.update(overrides)
    return BookingImpactContext(**fields)


class TestCapacity:
    def test_reducing_capacity_below_expected_attendance_warns(self):
        before = make_venue(capacity=150)
        after = make_venue(capacity=100)
        booking = make_booking(expected_attendance=120)

        result = affected_bookings(before, after, [booking])

        assert len(result) == 1
        assert result[0].booking_id == booking.booking_id
        assert result[0].event_name == "Annual Gala"
        assert any("120" in reason for reason in result[0].reasons)

    def test_capacity_reduced_but_still_above_attendance_does_not_warn(self):
        before = make_venue(capacity=150)
        after = make_venue(capacity=130)
        booking = make_booking(expected_attendance=120)

        assert affected_bookings(before, after, [booking]) == []

    def test_capacity_already_insufficient_before_the_edit_is_not_reported_again(self):
        """A pre-existing shortfall is not this edit's problem (newly-broken only)."""
        before = make_venue(capacity=100)
        after = make_venue(capacity=90)
        booking = make_booking(expected_attendance=120)

        assert affected_bookings(before, after, [booking]) == []

    def test_per_layout_capacity_is_used_when_the_event_requested_that_layout(self):
        before = make_venue(capacity=150, layouts=[LayoutOption(layout=VenueLayout.theatre, capacity_for_layout=None)])
        after = make_venue(capacity=150, layouts=[LayoutOption(layout=VenueLayout.theatre, capacity_for_layout=100)])
        booking = make_booking(expected_attendance=120, layout_preference=VenueLayout.theatre)

        result = affected_bookings(before, after, [booking])

        assert len(result) == 1

    def test_no_expected_attendance_on_the_event_never_warns_on_capacity(self):
        before = make_venue(capacity=150)
        after = make_venue(capacity=10)
        booking = make_booking(expected_attendance=None)

        assert affected_bookings(before, after, [booking]) == []


class TestFacilities:
    def test_removing_a_required_facility_warns(self):
        before = make_venue(facilities=[Facility.projector, Facility.microphone])
        after = make_venue(facilities=[Facility.microphone])
        booking = make_booking(facilities_required=[Facility.projector])

        result = affected_bookings(before, after, [booking])

        assert len(result) == 1
        assert "projector" in result[0].reasons[0]

    def test_removing_an_unrequired_facility_does_not_warn(self):
        before = make_venue(facilities=[Facility.projector, Facility.microphone, Facility.stage])
        after = make_venue(facilities=[Facility.projector, Facility.microphone])
        booking = make_booking(facilities_required=[Facility.projector])

        assert affected_bookings(before, after, [booking]) == []


class TestLayout:
    def test_dropping_the_requested_layout_warns(self):
        before = make_venue(layouts=[LayoutOption(layout=VenueLayout.theatre, capacity_for_layout=None)])
        after = make_venue(layouts=[LayoutOption(layout=VenueLayout.boardroom, capacity_for_layout=None)])
        booking = make_booking(layout_preference=VenueLayout.theatre)

        result = affected_bookings(before, after, [booking])

        assert len(result) == 1
        assert "theatre" in result[0].reasons[0]

    def test_no_layout_preference_on_the_event_never_warns_on_layout(self):
        before = make_venue(layouts=[LayoutOption(layout=VenueLayout.theatre, capacity_for_layout=None)])
        after = make_venue(layouts=[])
        booking = make_booking(layout_preference=None)

        assert affected_bookings(before, after, [booking]) == []


class TestOperatingHours:
    def test_narrowing_hours_past_the_booking_warns(self):
        before = make_venue(opens_at=time(8, 0), closes_at=time(22, 0))
        after = make_venue(opens_at=time(8, 0), closes_at=time(11, 0))
        booking = make_booking(
            period=Period(starts_at=datetime(2026, 10, 10, 9, tzinfo=SGT), ends_at=datetime(2026, 10, 10, 12, tzinfo=SGT))
        )

        result = affected_bookings(before, after, [booking])

        assert len(result) == 1

    def test_hours_that_still_cover_the_booking_do_not_warn(self):
        before = make_venue(opens_at=time(8, 0), closes_at=time(22, 0))
        after = make_venue(opens_at=time(9, 0), closes_at=time(18, 0))
        booking = make_booking(
            period=Period(starts_at=datetime(2026, 10, 10, 9, tzinfo=SGT), ends_at=datetime(2026, 10, 10, 12, tzinfo=SGT))
        )

        assert affected_bookings(before, after, [booking]) == []


class TestMultipleBookings:
    def test_only_the_affected_booking_is_reported(self):
        before = make_venue(capacity=150)
        after = make_venue(capacity=100)
        unaffected = make_booking(booking_id="d-unaffected", event_id="e-unaffected", expected_attendance=50)
        affected = make_booking(booking_id="d-affected", event_id="e-affected", expected_attendance=120)

        result = affected_bookings(before, after, [unaffected, affected])

        assert [r.booking_id for r in result] == ["d-affected"]

    def test_a_booking_can_carry_more_than_one_reason(self):
        before = make_venue(capacity=150, facilities=[Facility.projector])
        after = make_venue(capacity=50, facilities=[])
        booking = make_booking(expected_attendance=120, facilities_required=[Facility.projector])

        result = affected_bookings(before, after, [booking])

        assert len(result) == 1
        assert len(result[0].reasons) == 2
