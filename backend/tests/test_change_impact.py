"""Story 37: which venue bookings an approved change touches, and how (REQUIREMENTS
§6.19 CR-R5, BR-R15; Q11, Q15, Q17, Q18). Pure, so no I/O is mocked."""

from datetime import datetime

from app.modules.events.change_impact import BookingPlan, ChangeBooking, booking_plans

START = "2031-05-10T10:00:00+08:00"
END = "2031-05-10T12:00:00+08:00"


def event(**overrides):
    return {"starts_at": START, "ends_at": END, "expected_attendance": 80, "layout_preference": "theatre",
            "spaces": [], **overrides}


def space(space_id="s1", **overrides):
    return {"id": space_id, "label": "Main hall", "expected_pax": None, "layout_preference": None,
            "starts_at": None, "ends_at": None, **overrides}


def booking(booking_id="b1", space_id="s1", status="approved", capacity=200, flag=None, flag_reason=None):
    return ChangeBooking(id=booking_id, space_id=space_id, status=status, venue_name="Grand Ballroom",
                         flag=flag, flag_reason=flag_reason, capacity_for=lambda layout: capacity)


def at(value):
    return datetime.fromisoformat(value)


class TestTimeChanges:
    def test_a_new_event_time_moves_a_booking_that_inherits_it_and_marks_it(self):
        plans = booking_plans(event(spaces=[space()]), {"starts_at": "2031-05-10T14:00:00+08:00",
                                                        "ends_at": "2031-05-10T16:00:00+08:00"},
                              {}, [booking()])

        assert plans == [BookingPlan(booking_id="b1",
                                     period=(at("2031-05-10T14:00:00+08:00"), at("2031-05-10T16:00:00+08:00")),
                                     mark="Date or time changed.")]

    def test_a_space_with_its_own_window_keeps_it_when_only_the_event_moves(self):
        own = space(starts_at="2031-05-10T10:30:00+08:00", ends_at="2031-05-10T11:30:00+08:00")

        plans = booking_plans(event(spaces=[own]), {"ends_at": "2031-05-10T13:00:00+08:00"}, {}, [booking()])

        assert plans == []

    def test_a_space_window_change_moves_only_that_spaces_booking(self):
        """BR-R15."""
        spaces = [space("s1"), space("s2", label="Breakout")]

        plans = booking_plans(event(spaces=spaces), {}, {"s2": {"starts_at": "2031-05-10T10:30:00+08:00",
                                                                "ends_at": "2031-05-10T11:00:00+08:00"}},
                              [booking("b1", "s1"), booking("b2", "s2")])

        assert [plan.booking_id for plan in plans] == ["b2"]
        assert plans[0].period == (at("2031-05-10T10:30:00+08:00"), at("2031-05-10T11:00:00+08:00"))

    def test_the_same_instant_in_another_spelling_is_no_move(self):
        plans = booking_plans(event(spaces=[space()]), {"starts_at": "2031-05-10T02:00:00Z"}, {}, [booking()])

        assert plans == []

    def test_a_held_booking_moves_without_a_mark(self):
        """Q15: venue staff will decide it against the new details anyway."""
        plans = booking_plans(event(spaces=[space()]), {"ends_at": "2031-05-10T13:00:00+08:00"}, {},
                              [booking(status="held")])

        assert plans[0].period is not None
        assert plans[0].mark is None


class TestLayoutChanges:
    def test_an_event_layout_change_marks_bookings_whose_space_has_no_layout(self):
        spaces = [space("s1"), space("s2", label="Breakout", layout_preference="boardroom")]

        plans = booking_plans(event(spaces=spaces), {"layout_preference": "banquet"}, {},
                              [booking("b1", "s1"), booking("b2", "s2")])

        assert plans == [BookingPlan(booking_id="b1", mark="Layout changed.")]

    def test_time_and_layout_together_name_both(self):
        plans = booking_plans(event(spaces=[space()]), {"layout_preference": "banquet",
                                                        "ends_at": "2031-05-10T13:00:00+08:00"}, {}, [booking()])

        assert plans[0].mark == "Date or time changed. Layout changed."


class TestAttendance:
    def test_attendance_within_capacity_touches_nothing(self):
        """CR-R5: the system checks capacity, so venue staff aren't involved."""
        plans = booking_plans(event(spaces=[space()]), {"expected_attendance": 150}, {},
                              [booking(capacity=200)])

        assert plans == []

    def test_attendance_equal_to_capacity_still_fits(self):
        plans = booking_plans(event(spaces=[space()]), {"expected_attendance": 200}, {},
                              [booking(capacity=200)])

        assert plans == []

    def test_attendance_above_capacity_flags_the_booking_unsuitable(self):
        """Q17: the venue must be replaced, or the attendance reduced."""
        plans = booking_plans(event(spaces=[space()]), {"expected_attendance": 250}, {},
                              [booking(capacity=200)])

        assert plans == [BookingPlan(booking_id="b1", unsuitable=(
            "After an approved change: Main hall needs 250 people; Grand Ballroom seats 200."))]

    def test_a_space_attendance_is_judged_on_the_space_figure(self):
        plans = booking_plans(event(spaces=[space(expected_pax=100)]), {"expected_attendance": 500}, {},
                              [booking(capacity=200)])

        assert plans == []

    def test_capacity_is_read_for_the_new_layout(self):
        seen = []
        tight = ChangeBooking(id="b1", space_id="s1", status="approved", venue_name="Grand Ballroom",
                              flag=None, flag_reason=None,
                              capacity_for=lambda layout: seen.append(layout) or 50)

        plans = booking_plans(event(spaces=[space()]), {"layout_preference": "banquet"}, {}, [tight])

        assert seen == ["banquet"]
        assert plans[0].unsuitable.startswith("After an approved change:")

    def test_a_flag_37_set_is_cleared_once_attendance_fits_again(self):
        flagged = booking(capacity=200, flag="unsuitable",
                          flag_reason="After an approved change: Main hall needs 250 people; Grand Ballroom seats 200.")

        plans = booking_plans(event(spaces=[space()], expected_attendance=250), {"expected_attendance": 180}, {},
                              [flagged])

        assert plans == [BookingPlan(booking_id="b1", clear_unsuitable=True)]

    def test_a_flag_from_a_venue_edit_is_never_cleared(self):
        flagged = booking(capacity=200, flag="unsuitable", flag_reason="Capacity reduced below attendance.")

        plans = booking_plans(event(spaces=[space()], expected_attendance=250), {"expected_attendance": 180}, {},
                              [flagged])

        assert plans == []


class TestWhichBookings:
    def test_only_bookings_that_occupy_the_venue_are_planned(self):
        bookings = [booking("b1", status=status) for status in ("rejected", "cancelled", "released", "expired")]

        plans = booking_plans(event(spaces=[space()]), {"ends_at": "2031-05-10T13:00:00+08:00"}, {}, bookings)

        assert plans == []

    def test_a_re_review_booking_is_moved_and_marked_again(self):
        """Q22: staff always decide against the latest details."""
        plans = booking_plans(event(spaces=[space()]), {"ends_at": "2031-05-10T13:00:00+08:00"}, {},
                              [booking(status="re_review")])

        assert plans[0].period is not None and plans[0].mark == "Date or time changed."

    def test_a_booking_without_a_space_follows_the_event(self):
        plans = booking_plans(event(), {"layout_preference": "banquet"}, {}, [booking(space_id=None)])

        assert plans == [BookingPlan(booking_id="b1", mark="Layout changed.")]
