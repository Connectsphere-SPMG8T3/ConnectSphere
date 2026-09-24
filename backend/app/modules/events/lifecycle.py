"""Which lifecycle actions each event status allows (REQUIREMENTS §5). Pure: no I/O.

One row per coordinator action. SCRUM-12 (assign) and SCRUM-33 (return,
resubmit) add their rows here rather than checking statuses inline.
"""

from app.core.exceptions import EventTransitionError
from app.modules.events.schemas import EventStatus

TRANSITIONS: dict[str, tuple[frozenset[EventStatus], EventStatus]] = {
    # Initial feasibility decision, not confirmation (SCRUM-34, QA2-8).
    "approve": (frozenset({EventStatus.under_review}), EventStatus.planning),
    # Only before confirmation; a confirmed event is cancelled instead (QA2-6).
    "reject": (frozenset({EventStatus.under_review, EventStatus.planning}), EventStatus.rejected),
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
