"""Which lifecycle actions each event status allows (REQUIREMENTS §5). Pure: no I/O.

One row per lifecycle action. SCRUM-12 (assign) adds its row here rather than
checking statuses inline.
"""

from app.core.exceptions import EventTransitionError
from app.modules.events.schemas import EventStatus

TRANSITIONS: dict[str, tuple[frozenset[EventStatus], EventStatus]] = {
    # The organiser's submission.
    "submit": (frozenset({EventStatus.draft}), EventStatus.under_review),
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
    # Changes or a rejected arrangement send the event back to planning, not the
    # event itself to rejected (CR-104 AC2, AC3).
    "safety_request_changes": (frozenset({EventStatus.safety_review}), EventStatus.planning),
    "safety_reject": (frozenset({EventStatus.safety_review}), EventStatus.planning),
    # An arrangement stopped being ready during review (CR-104 AC10).
    "safety_withdraw": (frozenset({EventStatus.safety_review}), EventStatus.planning),
}


def allowed_from(action: str) -> list[str]:
    sources, _ = TRANSITIONS[action]
    return sorted(status.value for status in sources)


def target(action: str, current: str | EventStatus) -> EventStatus:
    sources, destination = TRANSITIONS[action]
    current_status = EventStatus(current)
    if current_status not in sources:
        raise EventTransitionError(action, current_status.value)
    return destination
