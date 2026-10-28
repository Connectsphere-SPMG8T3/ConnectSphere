"""SCRUM-82 AC1, AC2, AC9, AC10 and CR-97 AC10: readiness (REQUIREMENTS §6.6), without I/O."""
from app.modules.events.schemas import BookingReadiness, ReadinessState, SafetyReadiness, SpaceReadiness

ACTIVE_BOOKING_STATUSES = frozenset({"held", "approved", "re_review"})
FLAG_LABELS = {"safety_rejected": "Safety rejected", "affected": "Affected", "conflict": "Conflict", "unsuitable": "Unsuitable", "expired": "Expired"}


def safety_readiness(
    bookings: list[BookingReadiness], technical: ReadinessState, spaces: list[SpaceReadiness] = (),
) -> SafetyReadiness:
    """An event with event spaces is checked space by space, naming the space
    (CR-97). One without any keeps the event-wide rule over `bookings`."""
    missing = _per_space_missing(spaces) if spaces else _event_wide_missing(bookings)
    if technical not in (ReadinessState.ready, ReadinessState.not_required):
        missing.append("Technical status is not Ready.")
    return SafetyReadiness(ready=not missing, missing=missing)


def _active(bookings: list[BookingReadiness]) -> list[BookingReadiness]:
    return [booking for booking in bookings if booking.status in ACTIVE_BOOKING_STATUSES]


def _flag_labels(bookings: list[BookingReadiness]) -> list[str]:
    flags = {flag for booking in bookings for flag in booking.flags}
    return [label for flag, label in FLAG_LABELS.items() if flag in flags]


def _per_space_missing(spaces: list[SpaceReadiness]) -> list[str]:
    missing = []
    for space in spaces:
        active = _active(space.bookings)
        statuses = {booking.status for booking in active}
        if not active:
            missing.append(f"{space.label}: no approved venue booking.")
        elif "held" in statuses:
            missing.append(f"{space.label}: awaiting venue staff approval.")
        elif "re_review" in statuses:
            missing.append(f"{space.label}: under re-review.")
        if any(booking.needs_re_review for booking in active):
            missing.append(f"{space.label}: needs re-review.")
        missing += [f"{space.label}: flagged {label}." for label in _flag_labels(active)]
    return missing


def _event_wide_missing(bookings: list[BookingReadiness]) -> list[str]:
    active = _active(bookings)
    statuses = {booking.status for booking in active}
    missing = []
    if not active:
        missing.append("No venue booking is approved.")
    if "held" in statuses:
        missing.append("A venue booking is awaiting venue staff approval.")
    if "re_review" in statuses:
        missing.append("A venue booking is under re-review.")
    if any(booking.needs_re_review for booking in active):
        missing.append("A venue booking needs re-review.")
    missing += [f"A venue booking is flagged {label}." for label in _flag_labels(active)]
    return missing
