"""Story 37: what an approved change does to each venue booking (REQUIREMENTS §6.19
CR-R5, BR-R15). Pure: no I/O. The database re-checks each move for conflicts under
its locks, so a plan says what to try, not what is guaranteed."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

OCCUPYING_STATUSES = frozenset({"held", "approved", "re_review"})

# Q17: the prefix marks the Unsuitable flags this story sets, the only ones it may clear.
CAPACITY_FLAG_PREFIX = "After an approved change: "


@dataclass(frozen=True)
class ChangeBooking:
    id: str
    space_id: str | None
    status: str
    venue_name: str
    flag: str | None
    flag_reason: str | None
    # The venue's capacity for a layout (venues.suitability.effective_capacity).
    capacity_for: Callable[[str | None], int]


@dataclass(frozen=True)
class BookingPlan:
    booking_id: str
    # The booking's own new time, when the change moves it (Q11).
    period: tuple[datetime, datetime] | None = None
    # Why it needs re-review, when venue staff approved what the change touches.
    mark: str | None = None
    unsuitable: str | None = None
    clear_unsuitable: bool = False


def _instant(value) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _window(event: dict, space: dict | None) -> tuple[datetime | None, datetime | None]:
    """A space with its own pair keeps it; otherwise it inherits the event's (QA3-23)."""
    if space and space.get("starts_at") is not None and space.get("ends_at") is not None:
        return _instant(space["starts_at"]), _instant(space["ends_at"])
    return _instant(event.get("starts_at")), _instant(event.get("ends_at"))


def _value(event: dict, space: dict | None, space_field: str, event_field: str):
    """The space's value, else the event's (CR-94, BR-R15)."""
    if space and space.get(space_field) is not None:
        return space[space_field]
    return event.get(event_field)


def booking_plans(event: dict, event_values: dict, space_values: dict,
                  bookings: list[ChangeBooking]) -> list[BookingPlan]:
    """One plan per occupying booking the change touches, in the order given.

    A new window moves the booking; a new window or layout marks an approved or
    re-review booking Needs re-review (a held one is still for venue staff to
    decide); attendance above the venue's capacity for the layout flags it
    Unsuitable, and an Unsuitable flag this story set clears once it fits again."""
    after_event = {**event, **event_values}
    spaces = {space["id"]: space for space in event.get("spaces") or []}
    plans = []
    for booking in bookings:
        if booking.status not in OCCUPYING_STATUSES:
            continue
        before_space = spaces.get(booking.space_id)
        after_space = {**before_space, **space_values.get(booking.space_id, {})} if before_space else None

        window = _window(after_event, after_space)
        moved = window != _window(event, before_space)
        layout = _value(after_event, after_space, "layout_preference", "layout_preference")
        relaid = layout != _value(event, before_space, "layout_preference", "layout_preference")
        pax = _value(after_event, after_space, "expected_pax", "expected_attendance")
        repaxed = pax != _value(event, before_space, "expected_pax", "expected_attendance")

        reasons = [reason for reason, applies in (("Date or time changed.", moved), ("Layout changed.", relaid))
                   if applies]
        mark = " ".join(reasons) if reasons and booking.status != "held" else None

        unsuitable, clear = None, False
        if relaid or repaxed:
            capacity = booking.capacity_for(layout)
            label = (after_space or {}).get("label") or "The event"
            if pax is not None and pax > capacity:
                unsuitable = (f"{CAPACITY_FLAG_PREFIX}{label} needs {pax} people; "
                              f"{booking.venue_name} seats {capacity}.")
            elif booking.flag == "unsuitable" and (booking.flag_reason or "").startswith(CAPACITY_FLAG_PREFIX):
                clear = True

        plan = BookingPlan(booking_id=booking.id, period=window if moved else None, mark=mark,
                           unsuitable=unsuitable, clear_unsuitable=clear)
        if plan != BookingPlan(booking_id=booking.id):
            plans.append(plan)
    return plans
