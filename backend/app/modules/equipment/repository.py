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


@dataclass(frozen=True)
class AvailabilityRow:
    """One item's §6.16 availability over a window (SCRUM-24, D45)."""

    equipment_id: str
    total_quantity: int
    outage_quantity: int
    reserved_quantity: int
    free_quantity: int


def availability(equipment_ids: Iterable[str], start_at: datetime, end_at: datetime) -> list[AvailabilityRow]:
    """Run `public.equipment_availability`: total minus the peak concurrent
    outage and reservations over `[start_at, end_at)` (AV-R2). The reserve
    function uses the same calculation, so the check and a reserve agree."""
    ids = sorted({str(i) for i in equipment_ids})
    if not ids:
        return []
    response = (
        get_supabase_admin_client()
        .rpc("equipment_availability", {
            "p_equipment_ids": ids, "p_start_at": start_at.isoformat(), "p_end_at": end_at.isoformat(),
        })
        .execute()
    )
    return [AvailabilityRow(**row) for row in response.data or []]


# --- SCRUM-45 equipment request lines -----------------------------------------

# A retired item has left the catalogue: it can't be requested any more.
REQUESTABLE_EQUIPMENT_STATUSES = ("active", "maintenance")

# One line with the names the screens show. The FK names are spelled out
# because `equipment_requests` points at both `events` and `profiles`.
REQUEST_LINE_SELECT = (
    "id, submission_id, event_id, equipment_id, quantity, technical_requirements, status, "
    "technical_notes, not_available_reason, requested_by, created_at, "
    "equipment:equipment!equipment_requests_equipment_id_fkey(name, equipment_type), "
    "requester:profiles!equipment_requests_requested_by_fkey(id, full_name), "
    "event:events!equipment_requests_event_id_fkey(name, starts_at, status)"
)


def list_catalogue(equipment_ids: Iterable[str] | None = None) -> list[dict]:
    """Requestable catalogue items by name, optionally narrowed to `equipment_ids`."""
    query = (
        get_supabase_admin_client()
        .table("equipment")
        .select("id, name, equipment_type, total_quantity, status")
        .in_("status", list(REQUESTABLE_EQUIPMENT_STATUSES))
    )
    if equipment_ids is not None:
        ids = sorted({str(i) for i in equipment_ids})
        if not ids:
            return []
        query = query.in_("id", ids)
    return query.order("name").execute().data or []


def submit_request(event_id: str, actor_id: str, items: list[dict]) -> tuple[str, list[dict]]:
    """Run `public.submit_equipment_request`: every line pending, all or none.
    Returns `(outcome, inserted rows)`; a refusal is an outcome code, never a
    raised database error."""
    response = (
        get_supabase_admin_client()
        .rpc(
            "submit_equipment_request",
            {"p_event_id": event_id, "p_actor_id": actor_id, "p_items": items},
        )
        .execute()
    )
    row = (response.data or [{}])[0]
    return row.get("outcome", ""), row.get("lines") or []


def list_event_requests(event_id: str) -> list[dict]:
    """Every line for one event, oldest first."""
    response = (
        get_supabase_admin_client()
        .table("equipment_requests")
        .select(REQUEST_LINE_SELECT)
        .eq("event_id", event_id)
        .order("created_at")
        .execute()
    )
    return response.data or []


def list_requests(statuses: list[str] | None = None) -> list[dict]:
    """Lines across all events (tech support are a pool, AUTH-R5), oldest
    first; only those in `statuses` when given. The pending queue asks for
    `pending` and `re_review` (SCRUM-24 AC7); the requests page for all."""
    query = get_supabase_admin_client().table("equipment_requests").select(REQUEST_LINE_SELECT)
    if statuses is not None:
        query = query.in_("status", list(statuses))
    return query.order("created_at").execute().data or []


# --- SCRUM-24 reservation ------------------------------------------------------
# Each staff action is one database function that locks, decides, writes history
# and notices, and answers an outcome code instead of raising.


def _rpc_row(name: str, params: dict) -> dict:
    data = get_supabase_admin_client().rpc(name, params).execute().data
    if isinstance(data, list):
        return data[0] if data else {}
    return {"outcome": data} if isinstance(data, str) else data or {}


def get_line(line_id: str) -> dict | None:
    """A line's id, event and status, or None."""
    response = (
        get_supabase_admin_client()
        .table("equipment_requests")
        .select("id, event_id, status")
        .eq("id", line_id)
        .limit(1)
        .execute()
    )
    return (response.data or [None])[0]


def reserve_line(line_id: str, actor_id: str) -> tuple[str, int | None, bool]:
    """`(outcome, free_quantity, left_ready)` from `public.reserve_equipment_line`."""
    row = _rpc_row("reserve_equipment_line", {"p_line_id": line_id, "p_actor_id": actor_id})
    return row.get("outcome", ""), row.get("free_quantity"), bool(row.get("left_ready"))


def mark_not_available(line_id: str, actor_id: str, reason: str) -> tuple[str, bool]:
    row = _rpc_row("mark_equipment_line_not_available",
                   {"p_line_id": line_id, "p_actor_id": actor_id, "p_reason": reason})
    return row.get("outcome", ""), bool(row.get("left_ready"))


def set_note(line_id: str, actor_id: str, note: str | None) -> str:
    return _rpc_row("set_equipment_line_note",
                    {"p_line_id": line_id, "p_actor_id": actor_id, "p_note": note}).get("outcome", "")


def set_exit_confirmation(event_id: str, actor_id: str, confirmed: bool) -> tuple[str, bool]:
    row = _rpc_row("set_exit_confirmation",
                   {"p_event_id": event_id, "p_actor_id": actor_id, "p_confirmed": confirmed})
    return row.get("outcome", ""), bool(row.get("left_ready"))


def recheck_event(event_id: str, actor_id: str | None) -> tuple[str, int, bool]:
    row = _rpc_row("recheck_event_reservations", {"p_event_id": event_id, "p_actor_id": actor_id})
    return row.get("outcome", ""), row.get("flagged") or 0, bool(row.get("left_ready"))


def get_event_technical(event_id: str) -> dict | None:
    """The event fields the technical screens show, with the coordinator's and
    the exit-tick confirmer's names."""
    response = (
        get_supabase_admin_client()
        .table("events")
        .select(
            "id, name, status, coordinator_id, starts_at, ends_at, technical_readiness, exit_confirmed_at, "
            "coordinator:profiles!events_coordinator_id_fkey(full_name), "
            "exit_confirmer:profiles!events_exit_confirmed_by_fkey(full_name)"
        )
        .eq("id", event_id)
        .limit(1)
        .execute()
    )
    return (response.data or [None])[0]


def list_technical_history(event_id: str) -> list[dict]:
    """The event's technical history, newest first (AC13)."""
    response = (
        get_supabase_admin_client()
        .table("event_technical_history")
        .select(
            "id, request_id, action, from_status, to_status, detail, created_at, "
            "actor:profiles!event_technical_history_actor_id_fkey(full_name), "
            "line:equipment_requests!event_technical_history_request_id_fkey("
            "quantity, equipment:equipment!equipment_requests_equipment_id_fkey(name))"
        )
        .eq("event_id", event_id)
        .order("created_at", desc=True)
        .execute()
    )
    return response.data or []


def list_line_statuses(event_ids: Iterable[str]) -> list[dict]:
    """`{event_id, status, needs_re_review_since}` for every line on `event_ids`."""
    ids = sorted({str(i) for i in event_ids})
    if not ids:
        return []
    response = (
        get_supabase_admin_client()
        .table("equipment_requests")
        .select("event_id, status, needs_re_review_since")
        .in_("event_id", ids)
        .execute()
    )
    return response.data or []


def line_names(line_ids: list[str]) -> dict[str, str | None]:
    """D53: names for all equipment lines concerned by a decision history."""
    if not line_ids:
        return {}
    rows = (get_supabase_admin_client().table("equipment_requests")
            .select("id, equipment:equipment!equipment_requests_equipment_id_fkey(name)")
            .in_("id", line_ids).execute().data)
    return {row["id"]: (row.get("equipment") or {}).get("name") for row in rows or []}
