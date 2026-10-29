"""Which lifecycle actions each event status allows (REQUIREMENTS §5). Pure: no I/O.

One row per lifecycle action. SCRUM-12 (assign) adds its row here rather than
checking statuses inline. Approved changes return confirmed events to planning.
"""

from app.core.exceptions import EventTransitionError
from app.modules.events.schemas import EventStatus

TRANSITIONS: dict[str, tuple[frozenset[EventStatus], EventStatus]] = {
    # The organiser's submission.
    # It waits in the Lead's unassigned queue until a coordinator is assigned (SCRUM-12, QA3-2).
    "submit": (frozenset({EventStatus.draft}), EventStatus.submitted),
    # An Event Coordinator Lead assigns a coordinator; review starts (SCRUM-12 AC6).
    "assign": (frozenset({EventStatus.submitted}), EventStatus.under_review),
    # Initial feasibility decision, not confirmation (SCRUM-34, QA2-8).
    "approve": (frozenset({EventStatus.under_review}), EventStatus.planning),
    # Only before confirmation; a confirmed event is cancelled instead (QA2-6).
    "reject": (frozenset({EventStatus.under_review, EventStatus.planning}), EventStatus.rejected),
    # Back to the organiser with a message; planning waits for the answer (SCRUM-33, QA-22).
    "return": (frozenset({EventStatus.under_review}), EventStatus.returned),
    # Amended and sent back to the same coordinator (SCRUM-33, QA-77).
    "resubmit": (frozenset({EventStatus.returned}), EventStatus.under_review),
    # The coordinator sends a ready event for the Operational Safety Check (SCRUM-82, W7 CR-06).
    "send_to_safety": (frozenset({EventStatus.planning}), EventStatus.safety_review),
    # Only the Safety Officer's approval confirms an event (CR-104 AC1, AC5).
    "safety_approve": (frozenset({EventStatus.safety_review}), EventStatus.confirmed),
    # Request changes preserves arrangements; rejecting one venue flags its booking
    # Safety rejected. Both return the event to planning (CR-104 AC2/AC3).
    "safety_request_changes": (frozenset({EventStatus.safety_review}), EventStatus.planning),
    "safety_reject": (frozenset({EventStatus.safety_review}), EventStatus.planning),
    # The first venue or technical preparation update on a Confirmed event (68 AC1,
    # CR-109, CR-110, QA3-3). The system makes it inside the update's transaction.
    "start_preparation": (frozenset({EventStatus.confirmed}), EventStatus.preparation),
    # An approved change returns a confirmed event to planning (CR-104 AC6, QA3-16).
    "approved_change": (frozenset({EventStatus.confirmed}), EventStatus.planning),
    # An arrangement stopped being ready during review (CR-104 AC10).
    "safety_withdraw": (frozenset({EventStatus.safety_review}), EventStatus.planning),
    # The coordinator cancels without an organiser request (story 115 AC3, QA2-5, QA2-6).
    # An approved request cancels from any status a request is accepted in instead.
    "cancel": (frozenset({EventStatus.planning, EventStatus.confirmed, EventStatus.preparation}),
               EventStatus.cancelled),
}


# Story 84 AC2, CR-R4: a cancellation can be requested at any status after submission
# except these (QA-12). It changes no status, so it isn't a TRANSITIONS row, and it is
# defined by exclusion so Preparation (story 68) is covered as soon as it exists.
CANCELLATION_REQUEST_REFUSED = frozenset({
    EventStatus.draft, EventStatus.rejected, EventStatus.cancelled, EventStatus.completed,
})


def cancellation_requestable_from() -> list[str]:
    return sorted(status.value for status in EventStatus if status not in CANCELLATION_REQUEST_REFUSED)


# Story 32, CR-R15 [Assumption]: a change request has the same window, except that a
# returned request is edited and resubmitted directly (REQUIREMENTS §6.7).
CHANGE_REQUEST_REFUSED = CANCELLATION_REQUEST_REFUSED | {EventStatus.returned}


def change_requestable_from() -> list[str]:
    return sorted(status.value for status in EventStatus if status not in CHANGE_REQUEST_REFUSED)


def allowed_from(action: str) -> list[str]:
    sources, _ = TRANSITIONS[action]
    return sorted(status.value for status in sources)


def target(action: str, current: str | EventStatus) -> EventStatus:
    sources, destination = TRANSITIONS[action]
    current_status = EventStatus(current)
    if current_status not in sources:
        raise EventTransitionError(action, current_status.value)
    return destination
