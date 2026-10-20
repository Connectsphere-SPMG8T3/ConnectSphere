"""SCRUM-24 equipment rules without I/O, so other modules can call them and they
are unit-tested without mocks.

The event's technical status itself is derived in the database
(`public.derive_technical_status`, AC11) and cached on the event, so the API and
every trigger agree; these are only the pieces the screens need.
"""

from collections.abc import Iterable

from app.modules.events.schemas import ReadinessState

# How each line status reads on the screens (AC9: "Not available" is `rejected`).
LINE_STATUS_LABELS = {
    "pending": "Pending",
    "reserved": "Reserved",
    "rejected": "Not available",
    "re_review": "Re-review",
    "released": "Released",
}


def line_status_label(status: str) -> str:
    return LINE_STATUS_LABELS.get(status, status.replace("_", " ").capitalize())


def equipment_readiness(statuses: Iterable[str]) -> ReadinessState:
    """The coordinator dashboard's equipment column: the lines alone, without
    the exit tick that technical status also needs (AC11)."""
    live = [status for status in statuses if status != "released"]
    if not live:
        return ReadinessState.not_required
    if "rejected" in live:
        return ReadinessState.issue
    if all(status == "reserved" for status in live):
        return ReadinessState.ready
    return ReadinessState.pending


def line_label(quantity: int | None, equipment_name: str | None) -> str | None:
    """`3 × 4K Projector`, as history and notices name a line."""
    if quantity is None:
        return None
    return f"{quantity} × {equipment_name or 'equipment'}"
