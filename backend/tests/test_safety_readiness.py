"""SCRUM-82: which events are ready for the Operational Safety Check. Pure rules, no I/O."""
import pytest
from app.modules.events.readiness import safety_readiness
from app.modules.events.schemas import BookingReadiness as B, ReadinessState as T

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

@pytest.mark.parametrize("closed", ["rejected", "cancelled", "released"])
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
