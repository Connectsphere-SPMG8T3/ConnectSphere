"""SCRUM-82: which events are ready for the Operational Safety Check. Pure rules, no I/O."""
import pytest
from app.modules.events.readiness import safety_readiness
from app.modules.events.schemas import BookingReadiness as B, ReadinessState as T, SpaceReadiness as S

NO_BOOKING = "No venue booking is approved."
HELD = "A venue booking is awaiting venue staff approval."
RE_REVIEW = "A venue booking is under re-review."
TECH = "Technical status is not Ready."

def test_an_approved_booking_and_ready_technical_status_is_ready():
    result = safety_readiness([B(status="approved")], T.ready)
    assert result.ready is True and result.missing == []

def test_not_required_technical_status_counts_as_ready():  # AC3
    assert safety_readiness([B(status="approved")], T.not_required).ready is True

def test_no_booking_at_all_is_not_ready():  # [Assumption] spec §2
    assert safety_readiness([], T.ready).missing == [NO_BOOKING]

# CR-99 AC6: an expired hold never counts as a booking for the safety check.
@pytest.mark.parametrize("closed", ["rejected", "cancelled", "released", "expired"])
def test_closed_bookings_are_ignored(closed):
    assert safety_readiness([B(status=closed)], T.ready).missing == [NO_BOOKING]
    assert safety_readiness([B(status=closed, flags=["affected"]), B(status="approved")], T.ready).ready is True

def test_a_held_booking_blocks():  # AC9
    assert safety_readiness([B(status="held")], T.ready).missing == [HELD]

def test_a_booking_under_re_review_blocks():
    assert safety_readiness([B(status="re_review")], T.ready).missing == [RE_REVIEW]

def test_one_approved_and_one_held_booking_blocks():  # Review Focus 1, CR-97
    assert safety_readiness([B(status="approved"), B(status="held")], T.ready).missing == [HELD]

def test_each_distinct_flag_blocks_once_in_a_fixed_order():  # AC10, AC9 expired
    result = safety_readiness(
        [B(status="approved", flags=["unsuitable", "affected"]), B(status="approved", flags=["affected", "expired"])],
        T.ready,
    )
    assert result.missing == [
        "A venue booking is flagged Affected.",
        "A venue booking is flagged Unsuitable.",
        "A venue booking is flagged Expired.",
    ]

def test_an_unknown_flag_is_ignored():
    assert safety_readiness([B(status="approved", flags=["something_new"])], T.ready).ready is True

@pytest.mark.parametrize("technical", [T.pending, T.issue])
def test_technical_status_other_than_ready_or_not_required_blocks(technical):  # AC1, AC2
    assert safety_readiness([B(status="approved")], technical).missing == [TECH]

def test_every_missing_item_is_listed_in_order():
    result = safety_readiness([B(status="re_review"), B(status="held")], T.issue)
    assert result.missing == [HELD, RE_REVIEW, TECH]
    assert result.ready is False


def test_conflict_and_duplicate_status_reasons_are_reported_once():
    assert safety_readiness([B(status="held", flags=["conflict"]), B(status="held", flags=["conflict"])], T.ready).missing == [HELD, "A venue booking is flagged Conflict."]


# CR-97 AC10: an event with event spaces needs every space's own booking approved,
# and the readiness list names the space that is holding it back.
def test_an_event_space_without_a_booking_is_named():
    spaces = [S(label="Main hall", bookings=[B(status="approved")]), S(label="Breakout room")]
    assert safety_readiness([B(status="approved")], T.ready, spaces).missing == [
        "Breakout room: no approved venue booking.",
    ]

def test_an_event_space_whose_booking_is_held_is_named():
    spaces = [S(label="Main hall", bookings=[B(status="approved")]), S(label="Breakout room", bookings=[B(status="held")])]
    bookings = [booking for space in spaces for booking in space.bookings]
    assert safety_readiness(bookings, T.ready, spaces).missing == ["Breakout room: awaiting venue staff approval."]

def test_an_event_space_whose_booking_is_under_re_review_is_named():
    spaces = [S(label="Main hall", bookings=[B(status="re_review")]), S(label="Breakout room", bookings=[B(status="approved")])]
    bookings = [booking for space in spaces for booking in space.bookings]
    assert safety_readiness(bookings, T.ready, spaces).missing == ["Main hall: under re-review."]

def test_a_flagged_event_space_booking_is_named_with_its_flag():
    spaces = [S(label="Main hall", bookings=[B(status="approved", flags=["unsuitable", "affected"])]), S(label="Breakout room", bookings=[B(status="approved")])]
    bookings = [booking for space in spaces for booking in space.bookings]
    assert safety_readiness(bookings, T.ready, spaces).missing == [
        "Main hall: flagged Affected.",
        "Main hall: flagged Unsuitable.",
    ]

def test_every_event_space_approved_is_ready():
    spaces = [S(label="Main hall", bookings=[B(status="approved")]), S(label="Breakout room", bookings=[B(status="rejected"), B(status="approved")])]
    bookings = [booking for space in spaces for booking in space.bookings]
    assert safety_readiness(bookings, T.ready, spaces).ready is True

@pytest.mark.parametrize("closed", ["rejected", "cancelled", "released", "expired"])
def test_an_event_space_with_only_a_closed_booking_has_none(closed):  # CR-97 AC4
    spaces = [S(label="Main hall", bookings=[B(status="approved")]), S(label="Breakout room", bookings=[B(status=closed, flags=["affected"])])]
    bookings = [booking for space in spaces for booking in space.bookings]
    assert safety_readiness(bookings, T.issue, spaces).missing == ["Breakout room: no approved venue booking.", TECH]


def test_safety_rejected_booking_is_not_ready_event_wide():
    result=safety_readiness([B(status='approved',flags=['safety_rejected'])],T.ready)
    assert result.ready is False
    assert result.missing==['A venue booking is flagged Safety rejected.']

def test_only_the_rejected_space_is_reported():
    from app.modules.events.schemas import SpaceReadiness
    spaces=[SpaceReadiness(label='Hall A',bookings=[B(status='approved',flags=['safety_rejected'])]),SpaceReadiness(label='Hall B',bookings=[B(status='approved')])]
    assert safety_readiness([],T.ready,spaces).missing==['Hall A: flagged Safety rejected.']


def test_a_space_booking_that_needs_re_review_is_named():
    """Story 37 Q13."""
    spaces = [S(label="Main hall", bookings=[B(status="approved", needs_re_review=True)])]
    assert safety_readiness([], T.ready, spaces).missing == ["Main hall: needs re-review."]
