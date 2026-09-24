"""The event lifecycle table for SCRUM-34 (approve) and SCRUM-52 (reject), REQUIREMENTS §5."""

import pytest

from app.core.exceptions import EventTransitionError
from app.modules.events import lifecycle
from app.modules.events.schemas import EventStatus

ALL_STATUSES = [status.value for status in EventStatus]


def test_approve_moves_under_review_to_planning():
    assert lifecycle.target("approve", "under_review") == EventStatus.planning


@pytest.mark.parametrize("status", [s for s in ALL_STATUSES if s != "under_review"])
def test_approve_is_blocked_from_every_other_status(status):
    with pytest.raises(EventTransitionError) as raised:
        lifecycle.target("approve", status)

    assert raised.value.status_code == 409
    assert raised.value.detail == f"Cannot approve an event that is {status.replace('_', ' ')}"


@pytest.mark.parametrize("status", ["under_review", "planning"])
def test_reject_is_allowed_before_confirmation(status):
    assert lifecycle.target("reject", status) == EventStatus.rejected


@pytest.mark.parametrize("status", [s for s in ALL_STATUSES if s not in ("under_review", "planning")])
def test_reject_is_blocked_from_every_other_status(status):
    with pytest.raises(EventTransitionError) as raised:
        lifecycle.target("reject", status)

    assert raised.value.status_code == 409
    assert raised.value.detail == f"Cannot reject an event that is {status.replace('_', ' ')}"


def test_target_accepts_the_enum_as_well_as_its_value():
    assert lifecycle.target("approve", EventStatus.under_review) == EventStatus.planning


def test_allowed_from_lists_source_statuses_for_the_rpc():
    assert lifecycle.allowed_from("approve") == ["under_review"]
    assert lifecycle.allowed_from("reject") == ["planning", "under_review"]


def test_the_blocked_message_names_the_status_in_words():
    with pytest.raises(EventTransitionError) as raised:
        lifecycle.target("approve", "returned")

    assert raised.value.detail == "Cannot approve an event that is returned"
