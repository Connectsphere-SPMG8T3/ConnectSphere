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


def test_submit_moves_draft_to_under_review():
    """Submission is a lifecycle transition so it reaches event_status_history."""
    assert lifecycle.target("submit", "draft") == EventStatus.under_review


@pytest.mark.parametrize("status", [s for s in ALL_STATUSES if s != "draft"])
def test_submit_is_blocked_from_every_other_status(status):
    with pytest.raises(EventTransitionError):
        lifecycle.target("submit", status)


def test_return_moves_under_review_to_returned():
    """SCRUM-33: the coordinator returns a request for amendment (QA-22)."""
    assert lifecycle.target("return", "under_review") == EventStatus.returned


@pytest.mark.parametrize("status", [s for s in ALL_STATUSES if s != "under_review"])
def test_return_is_blocked_from_every_other_status(status):
    with pytest.raises(EventTransitionError) as raised:
        lifecycle.target("return", status)

    assert raised.value.status_code == 409
    assert raised.value.detail == f"Cannot return an event that is {status.replace('_', ' ')}"


def test_resubmit_moves_returned_back_to_under_review():
    """SCRUM-33: the organiser resubmits to the same coordinator (QA-77)."""
    assert lifecycle.target("resubmit", "returned") == EventStatus.under_review


@pytest.mark.parametrize("status", [s for s in ALL_STATUSES if s != "returned"])
def test_resubmit_is_blocked_from_every_other_status(status):
    with pytest.raises(EventTransitionError) as raised:
        lifecycle.target("resubmit", status)

    assert raised.value.detail == f"Cannot resubmit an event that is {status.replace('_', ' ')}"


def test_allowed_from_lists_the_amendment_sources_for_the_rpc():
    assert lifecycle.allowed_from("return") == ["under_review"]
    assert lifecycle.allowed_from("resubmit") == ["returned"]


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_a_returned_event_cannot_be_approved_or_rejected(action):
    """SCRUM-33 AC7: the decision waits for the organiser's resubmission."""
    with pytest.raises(EventTransitionError) as raised:
        lifecycle.target(action, "returned")

    assert raised.value.status_code == 409
