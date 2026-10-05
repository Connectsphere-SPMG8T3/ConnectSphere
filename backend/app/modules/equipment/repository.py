"""All Supabase reads for the equipment module.

This is the module's only I/O seam (REQUIREMENTS §3.3 `repository.py`); the
service never sees a Supabase client. Tests patch the functions here. Reads use
the secret-key admin client, so callers must already have passed the role check
in the router.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from app.db.supabase import get_supabase_admin_client

# Reservations in these statuses still hold their units. `cancelled` and
# `completed` have released them, so they never reduce availability.
OCCUPYING_RESERVATION_STATUSES = ("confirmed",)


@dataclass(frozen=True)
class EquipmentRow:
    id: str
    name: str
    total_quantity: int


@dataclass(frozen=True)
class CommitmentRow:
    """A quantity of one equipment type committed over a half-open window.

    Covers both reservations and maintenance outages: availability treats them
    identically, differing only in which total they feed.
    """

    equipment_id: str
    quantity: int
    start_at: datetime
    end_at: datetime


@dataclass(frozen=True)
class MaintenanceRow:
    id: str
    equipment_id: str
    equipment_name: str
    start_at: datetime
    end_at: datetime
    reason: str | None


def _overlapping(query, start_at: datetime, end_at: datetime):
    """Restrict `query` to rows overlapping `[start_at, end_at)`.

    Half-open on both sides, so a row that ends exactly when the window opens
    does not overlap it — equipment has no turnaround time (QA-126), meaning
    back-to-back bookings are legitimate rather than a clash.
    """
    return query.lt("start_at", end_at.isoformat()).gt("end_at", start_at.isoformat())


def list_equipment(equipment_ids: Iterable[str] | None = None) -> list[EquipmentRow]:
    """Equipment types, optionally narrowed to `equipment_ids`."""
    query = get_supabase_admin_client().table("equipment").select("id, name, total_quantity")
    ids = None if equipment_ids is None else sorted({str(i) for i in equipment_ids})
    if ids is not None:
        if not ids:
            return []
        query = query.in_("id", ids)
    response = query.order("name").execute()
    return [
        EquipmentRow(id=row["id"], name=row["name"], total_quantity=row["total_quantity"])
        for row in response.data or []
    ]


def list_reservations(
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    equipment_ids: Iterable[str] | None = None,
) -> list[CommitmentRow]:
    """Reservations still holding units, optionally scoped to a window and ids.

    With no window every occupying reservation comes back, which is what the
    unfiltered inventory view reports.
    """
    query = (
        get_supabase_admin_client()
        .table("equipment_reservations")
        .select("equipment_id, quantity, start_at, end_at")
        .in_("status", list(OCCUPYING_RESERVATION_STATUSES))
    )
    return _commitments(query, start_at, end_at, equipment_ids)


def list_unavailability(
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    equipment_ids: Iterable[str] | None = None,
) -> list[CommitmentRow]:
    """Maintenance/damage outages, optionally scoped to a window and ids."""
    query = (
        get_supabase_admin_client()
        .table("equipment_unavailability")
        .select("equipment_id, quantity, start_at, end_at")
    )
    return _commitments(query, start_at, end_at, equipment_ids)


def _commitments(
    query,
    start_at: datetime | None,
    end_at: datetime | None,
    equipment_ids: Iterable[str] | None,
) -> list[CommitmentRow]:
    ids = None if equipment_ids is None else sorted({str(i) for i in equipment_ids})
    if ids is not None:
        if not ids:
            return []
        query = query.in_("equipment_id", ids)
    if start_at is not None and end_at is not None:
        query = _overlapping(query, start_at, end_at)
    response = query.execute()
    return [
        CommitmentRow(
            equipment_id=row["equipment_id"],
            quantity=row["quantity"],
            start_at=datetime.fromisoformat(row["start_at"]),
            end_at=datetime.fromisoformat(row["end_at"]),
        )
        for row in response.data or []
    ]


def list_maintenance() -> list[MaintenanceRow]:
    """Every maintenance record with its equipment's name, soonest first.

    No date filter: the dashboard shows completed records too, marked as such
    by the service (TC-TSD-006).
    """
    response = (
        get_supabase_admin_client()
        .table("equipment_unavailability")
        .select("id, equipment_id, start_at, end_at, reason, equipment(name)")
        .order("start_at")
        .execute()
    )
    rows = []
    for row in response.data or []:
        embedded = row.get("equipment")
        # PostgREST returns a to-one embed as a dict, but falls back to a
        # one-element list when it cannot prove the relationship is to-one.
        if isinstance(embedded, list):
            embedded = embedded[0] if embedded else None
        rows.append(
            MaintenanceRow(
                id=row["id"],
                equipment_id=row["equipment_id"],
                equipment_name=(embedded or {}).get("name", ""),
                start_at=datetime.fromisoformat(row["start_at"]),
                end_at=datetime.fromisoformat(row["end_at"]),
                reason=row.get("reason"),
            )
        )
    return rows


def list_reserved_event_ids(event_ids: Iterable[str], statuses: Iterable[str]) -> list[str]:
    """The ids among `event_ids` that hold at least one reservation in `statuses`."""
    ids = list(event_ids)
    if not ids:
        return []
    response = (
        get_supabase_admin_client()
        .table("equipment_reservations")
        .select("event_id")
        .in_("event_id", ids)
        .in_("status", list(statuses))
        .execute()
    )
    return [row["event_id"] for row in response.data or []]
