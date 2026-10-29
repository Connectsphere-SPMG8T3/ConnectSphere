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


def test_submit_moves_draft_to_submitted():
    """Submission is a lifecycle transition so it reaches event_status_history; the event
    then waits in the Lead's unassigned queue (SCRUM-12)."""
    assert lifecycle.target("submit", "draft") == EventStatus.submitted


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


# SCRUM-82 / CR-104 groundwork: the Operational Safety Check (W7 CR-06).
SAFETY_TRANSITIONS = {
    "send_to_safety": ("planning", EventStatus.safety_review),
    "safety_approve": ("safety_review", EventStatus.confirmed),
    "safety_request_changes": ("safety_review", EventStatus.planning),
    "safety_reject": ("safety_review", EventStatus.planning),
    "safety_withdraw": ("safety_review", EventStatus.planning),
}


@pytest.mark.parametrize("action", SAFETY_TRANSITIONS)
def test_safety_action_moves_its_one_source_to_its_target(action):
    source, destination = SAFETY_TRANSITIONS[action]

    assert lifecycle.target(action, source) == destination
    assert lifecycle.allowed_from(action) == [source]


@pytest.mark.parametrize(
    "action, status",
    [(action, status) for action, (source, _) in SAFETY_TRANSITIONS.items() for status in ALL_STATUSES if status != source],
)
def test_safety_action_is_blocked_from_every_other_status(action, status):
    with pytest.raises(EventTransitionError) as raised:
        lifecycle.target(action, status)

    assert raised.value.status_code == 409


def test_the_blocked_message_names_the_action_in_words():
    with pytest.raises(EventTransitionError) as raised:
        lifecycle.target("send_to_safety", "safety_review")

    assert raised.value.detail == "Cannot send to safety an event that is safety review"


def test_only_safety_approval_reaches_confirmed():
    """82 AC5, CR-104 AC5: the coordinator can no longer confirm an event."""
    confirming = [action for action, (_, destination) in lifecycle.TRANSITIONS.items() if destination == EventStatus.confirmed]

    assert confirming == ["safety_approve"]


def test_start_preparation_moves_confirmed_to_preparation():
    """68 AC1, CR-110 AC3: the first preparation update on a Confirmed event."""
    assert lifecycle.target("start_preparation", "confirmed") == EventStatus.preparation
    assert lifecycle.allowed_from("start_preparation") == ["confirmed"]


@pytest.mark.parametrize("status", [s for s in ALL_STATUSES if s != "confirmed"])
def test_start_preparation_is_blocked_from_every_other_status(status):
    with pytest.raises(EventTransitionError):
        lifecycle.target("start_preparation", status)


def test_only_starting_preparation_reaches_preparation():
    """68 AC1: no other action moves an event to Preparation."""
    preparing = [action for action, (_, destination) in lifecycle.TRANSITIONS.items()
                 if destination == EventStatus.preparation]

    assert preparing == ["start_preparation"]
