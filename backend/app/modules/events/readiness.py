"""SCRUM-82 AC1, AC2, AC9, AC10: readiness (REQUIREMENTS §6.6), without I/O."""
from app.modules.events.schemas import BookingReadiness, ReadinessState, SafetyReadiness

ACTIVE_BOOKING_STATUSES = frozenset({"held", "approved", "re_review"})
FLAG_LABELS = {"affected": "Affected", "conflict": "Conflict", "unsuitable": "Unsuitable", "expired": "Expired"}


def safety_readiness(bookings: list[BookingReadiness], technical: ReadinessState) -> SafetyReadiness:
    active = [booking for booking in bookings if booking.status in ACTIVE_BOOKING_STATUSES]
    missing = []
    if not active:
        missing.append("No venue booking is approved.")
    if any(booking.status == "held" for booking in active):
        missing.append("A venue booking is awaiting venue staff approval.")
    if any(booking.status == "re_review" for booking in active):
        missing.append("A venue booking is under re-review.")
    flags = {flag for booking in active for flag in booking.flags}
    for flag, label in FLAG_LABELS.items():
        if flag in flags:
            missing.append(f"A venue booking is flagged {label}.")
    if technical not in (ReadinessState.ready, ReadinessState.not_required):
        missing.append("Technical status is not Ready.")
    return SafetyReadiness(ready=not missing, missing=missing)
