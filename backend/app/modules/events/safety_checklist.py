"""Pure rules for the safety review checklist (CR-108 AC1-AC3, QA3-17). No I/O.

Five factors are answered for each venue booking; equipment placement is answered once for the event.
The same rules run in SQL (`safety_approve_event`, `safety_return_event`); this gives the officer a
readable 422 before the transaction.
"""
from typing import Iterable
from uuid import UUID

from app.modules.events.schemas import SafetyChecklistAnswer, SafetyFactor, SafetyRating

EQUIPMENT_FACTOR = SafetyFactor.equipment_placement.value
VENUE_FACTORS = tuple(
    factor.value for factor in SafetyFactor if factor.value != EQUIPMENT_FACTOR
)

FACTOR_LABELS = {
    "attendance_capacity": "Attendance/capacity",
    "layout": "Layout",
    "emergency_access": "Emergency access",
    "accessibility": "Accessibility",
    "equipment_placement": "Equipment placement",
    "venue_restrictions": "Venue restrictions",
}

CONCERN_BLOCKS_APPROVAL = "A factor marked Concern blocks approval: request changes or reject instead"


def checklist_problems(
    answers: Iterable[SafetyChecklistAnswer], booking_ids: Iterable[UUID], outcome: str
) -> list[str]:
    """Everything wrong with the checklist for this outcome; empty when it can be recorded."""
    answers = list(answers)
    bookings = set(booking_ids)
    problems: list[str] = []
    seen: set[tuple[str, UUID | None]] = set()

    for answer in answers:
        factor = answer.factor.value
        label = FACTOR_LABELS[factor]
        if factor == EQUIPMENT_FACTOR and answer.booking_id is not None:
            problems.append(f"{label} applies to the whole event, not a venue booking")
            key = (factor, None)
        elif factor != EQUIPMENT_FACTOR and answer.booking_id is None:
            problems.append(f"{label} needs a venue booking")
            continue
        else:
            key = (factor, answer.booking_id)
        if key in seen:
            where = "" if factor == EQUIPMENT_FACTOR else f" for venue booking {answer.booking_id}"
            problems.append(f"{label}{where} is marked more than once")
        seen.add(key)

    for booking in dict.fromkeys(a.booking_id for a in answers if a.booking_id and a.booking_id not in bookings):
        problems.append(f"Venue booking {booking} is not part of this event")

    for booking in bookings:
        for factor in VENUE_FACTORS:
            if (factor, booking) not in seen:
                problems.append(f"Mark {FACTOR_LABELS[factor].lower()} for venue booking {booking}")
    if (EQUIPMENT_FACTOR, None) not in seen:
        problems.append(f"Mark {FACTOR_LABELS[EQUIPMENT_FACTOR].lower()}")

    if outcome == "approved" and any(a.rating is SafetyRating.concern for a in answers):
        problems.append(CONCERN_BLOCKS_APPROVAL)
    return problems
