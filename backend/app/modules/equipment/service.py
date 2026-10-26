from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from functools import wraps

from httpx import HTTPError
from postgrest.exceptions import APIError

from app.core.exceptions import (
    EquipmentArrangementConflictError,
    EquipmentInsufficientError,
    EquipmentLineNotFoundError,
    EquipmentNotAvailableReasonError,
    EquipmentNotInCatalogueError,
    EquipmentRequestNotAllowedError,
    EquipmentServiceUnavailableError,
    NotAssignedCoordinatorError,
)
from app.modules.equipment import repository, rules
from app.modules.equipment.repository import CommitmentRow
# A module import, not names: `events.service` imports this module too, and a
# module reference resolves at call time, so the cycle is harmless.
from app.modules.events import service as events_service
from app.modules.events.schemas import ReadinessState
from app.modules.equipment.schemas import (
    CatalogueItem,
    CatalogueResponse,
    EquipmentLineUpdate,
    EquipmentRequestCreate,
    EquipmentRequestLine,
    EquipmentRequestLinesResponse,
    ExitConfirmation,
    LineActionResponse,
    TechnicalEvent,
    TechnicalEventResponse,
    TechnicalHistoryEntry,
    TechnicalHistoryResponse,
    PendingEquipmentLine,
    PendingEquipmentLinesResponse,
    EquipmentAvailabilityResponse,
    EquipmentCheckItem,
    EquipmentInventoryItem,
    EquipmentInventoryResponse,
    EquipmentMaintenanceItem,
    EquipmentMaintenanceResponse,
    ItemAvailabilityResult,
)


def _totals_by_equipment(commitments: Iterable[CommitmentRow]) -> dict[str, int]:
    totals: dict[str, int] = defaultdict(int)
    for row in commitments:
        totals[row.equipment_id] += row.quantity
    return totals


def check_equipment_availability(
    start_at: datetime,
    end_at: datetime,
    items: Sequence[EquipmentCheckItem],
) -> EquipmentAvailabilityResponse:
    """SCRUM-23, by the §6.16 worst-moment rule (AV-R2). The numbers come from
    `public.equipment_availability`, the calculation reserving uses (D45)."""
    equipment_ids = {str(item.equipment_id) for item in items}

    equipment = {row.id: row for row in repository.list_equipment(equipment_ids)}
    free = {row.equipment_id: row.free_quantity for row in repository.availability(equipment_ids, start_at, end_at)}

    results = []
    for item in items:
        key = str(item.equipment_id)
        row = equipment.get(key)
        quantity_available = free.get(key, 0) if row else 0
        results.append(
            ItemAvailabilityResult(
                equipment_id=item.equipment_id,
                name=row.name if row else "Unknown equipment",
                storage_location=row.storage_location if row else None,
                quantity_needed=item.quantity_needed,
                quantity_available=quantity_available,
                quantity_missing=max(0, item.quantity_needed - quantity_available),
                sufficient=quantity_available >= item.quantity_needed,
            )
        )

    return EquipmentAvailabilityResponse(
        sufficient=all(item.sufficient for item in results),
        items=results,
    )


def get_equipment_inventory(
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> EquipmentInventoryResponse:
    equipment = repository.list_equipment()
    # A lone start or end is ignored rather than half-applied: an overlap needs
    # both ends, and filtering on one would misreport stock.
    if start_at and end_at:
        # A window reports its worst moment, like the availability check (D45).
        rows = {row.equipment_id: row for row in repository.availability([row.id for row in equipment], start_at, end_at)}
        breakdown = {
            key: (row.reserved_quantity, row.outage_quantity) for key, row in rows.items()
        }
    else:
        # No window: everything committed at any time, summed.
        reserved = _totals_by_equipment(repository.list_reservations())
        maintenance = _totals_by_equipment(repository.list_unavailability())
        breakdown = {row.id: (reserved.get(row.id, 0), maintenance.get(row.id, 0)) for row in equipment}

    items = []
    for row in equipment:
        reserved_quantity, maintenance_quantity = breakdown.get(row.id, (0, 0))
        items.append(
            EquipmentInventoryItem(
                equipment_id=row.id,
                name=row.name,
                total_quantity=row.total_quantity,
                reserved_quantity=reserved_quantity,
                maintenance_quantity=maintenance_quantity,
                net_available=0 if row.status == "retired" else max(0, row.total_quantity - reserved_quantity - maintenance_quantity),
            )
        )
    return EquipmentInventoryResponse(items=items)


def get_equipment_maintenance() -> EquipmentMaintenanceResponse:
    now = datetime.now(timezone.utc)
    items = []
    for row in repository.list_maintenance():
        if now < row.start_at:
            maintenance_status = "SCHEDULED"
        elif now < row.end_at:
            maintenance_status = "IN_PROGRESS"
        else:
            maintenance_status = "COMPLETED"
        items.append(
            EquipmentMaintenanceItem(
                maintenance_id=row.id,
                equipment_id=row.equipment_id,
                equipment_name=row.equipment_name,
                start_at=row.start_at,
                end_at=row.end_at,
                reason=row.reason,
                status=maintenance_status,
            )
        )
    return EquipmentMaintenanceResponse(items=items)


def equipment_readiness_by_event(event_ids: Iterable[str]) -> dict[str, ReadinessState]:
    """The coordinator dashboard's equipment readiness per event, from its lines
    (SCRUM-24 AC11). Events without lines are Not required."""
    statuses: dict[str, list[str]] = defaultdict(list)
    for row in repository.list_line_statuses(event_ids):
        # Story 37 Q14: a line an approved time change left short isn't ready, whatever its status.
        statuses[row["event_id"]].append("pending" if row.get("needs_re_review_since") else row["status"])
    return {event_id: rules.equipment_readiness(statuses.get(event_id, [])) for event_id in event_ids}



# --- SCRUM-45 equipment request lines (REQUIREMENTS 6.15) ---------------------

RETURNED_MESSAGE = (
    "Equipment can't be requested while the event is returned for amendment. "
    "It can be requested once the event is back in planning."
)

# Tech support's queue leaves out lines on closed events. Rejecting or
# cancelling an event releases its lines (SCRUM-24 AC6); completed events'
# lines are only hidden.
QUEUE_EVENT_STATUSES = ("planning", "safety_review", "confirmed")


def _not_planning_message(status: str) -> str:
    return f"Equipment can only be requested for an event in planning; this event is {status.replace('_', ' ')}."


def catalogue() -> CatalogueResponse:
    return CatalogueResponse(
        items=[
            CatalogueItem(
                equipment_id=row["id"],
                name=row["name"],
                equipment_type=row["equipment_type"],
                total_quantity=row["total_quantity"],
            )
            for row in repository.list_catalogue()
        ]
    )


def _one(embedded):
    # PostgREST returns a to-one embed as a dict, but falls back to a
    # one-element list when it cannot prove the relationship is to-one.
    if isinstance(embedded, list):
        return embedded[0] if embedded else None
    return embedded


def _line_fields(row: dict, equipment_name: str, requester: dict | None) -> dict:
    return {
        "id": row["id"],
        "submission_id": row["submission_id"],
        "event_id": row["event_id"],
        "equipment_id": row["equipment_id"],
        "equipment_name": equipment_name,
        "quantity": row["quantity"],
        "technical_requirements": row.get("technical_requirements"),
        "status": row["status"],
        "technical_notes": row.get("technical_notes"),
        "not_available_reason": row.get("not_available_reason"),
        "needs_re_review_reason": row.get("needs_re_review_reason"),
        "requested_by": requester,
        "created_at": row["created_at"],
    }


def _embedded_line_fields(row: dict) -> dict:
    equipment = _one(row.get("equipment")) or {}
    return _line_fields(row, equipment.get("name", ""), _one(row.get("requester")))


def submit_request(coordinator_id: str, full_name: str, body: EquipmentRequestCreate) -> EquipmentRequestLinesResponse:
    """Submit lines for an event the caller coordinates, all pending, all or none.

    `full_name` is the caller's, from their verified profile. Nothing after the
    RPC reads the database: by then the lines are committed, and a failed read
    would report a saved request as failed, inviting a duplicate retry."""
    event_id = str(body.event_id)
    event = events_service.assigned_event(event_id, coordinator_id)
    if event["status"] == "returned":
        raise EquipmentRequestNotAllowedError(RETURNED_MESSAGE)
    if event["status"] != "planning":
        raise EquipmentRequestNotAllowedError(_not_planning_message(event["status"]))

    names = {row["id"]: row["name"] for row in repository.list_catalogue(str(i.equipment_id) for i in body.items)}
    missing = [index for index, item in enumerate(body.items) if str(item.equipment_id) not in names]
    if missing:
        raise EquipmentNotInCatalogueError(missing)

    items = [
        {
            "equipment_id": str(item.equipment_id),
            "quantity": item.quantity,
            "technical_requirements": item.technical_requirements,
        }
        for item in body.items
    ]
    outcome, rows = repository.submit_request(event_id, coordinator_id, items)
    if outcome == "event_not_found":
        raise events_service.EventNotFoundError()
    if outcome == "not_assigned":
        raise NotAssignedCoordinatorError()
    if outcome == "returned":
        raise EquipmentRequestNotAllowedError(RETURNED_MESSAGE)
    if outcome == "not_planning":
        raise EquipmentRequestNotAllowedError("This event is no longer in planning. Reload.")
    if outcome == "unknown_equipment":
        raise EquipmentNotInCatalogueError()
    if outcome != "ok":
        raise RuntimeError(f"submit_equipment_request returned {outcome!r}")

    # Lines come back in the order the coordinator listed the items (ids are
    # unique within a submission), whatever order the insert returned them in.
    position = {item["equipment_id"]: index for index, item in enumerate(items)}
    rows = sorted(rows, key=lambda row: position.get(str(row["equipment_id"]), len(position)))
    requester = {"id": coordinator_id, "full_name": full_name}
    return EquipmentRequestLinesResponse(
        lines=[EquipmentRequestLine(**_line_fields(row, names[str(row["equipment_id"])], requester)) for row in rows]
    )


def event_requests(event_id: str, coordinator_id: str) -> EquipmentRequestLinesResponse:
    """Every line on an event, for its assigned coordinator.

    [Assumption] REQUIREMENTS 9: "the submitting coordinator" is read as the
    assigned one; after a reassignment that is the new coordinator (D13).
    SCRUM-24 AC9: with each line's status, reason and notes, the event's
    technical status and who ticked the exit box."""
    event = events_service.assigned_event(event_id, coordinator_id)
    return EquipmentRequestLinesResponse(
        lines=[EquipmentRequestLine(**_embedded_line_fields(row)) for row in repository.list_event_requests(event_id)],
        technical_status=event["technical_readiness"],
        exit_confirmation=exit_confirmation(event_id),
    )


# The lines waiting on tech support (SCRUM-24 AC7 adds re-review).
WAITING_LINE_STATUSES = ["pending", "re_review"]


def _queue(statuses: list[str] | None) -> PendingEquipmentLinesResponse:
    lines = []
    for row in repository.list_requests(statuses):
        event = _one(row.get("event")) or {}
        if event.get("status") not in QUEUE_EVENT_STATUSES:
            continue
        lines.append(
            PendingEquipmentLine(
                **_embedded_line_fields(row),
                event_name=event.get("name") or "",
                event_starts_at=event.get("starts_at"),
                equipment_type=(_one(row.get("equipment")) or {}).get("equipment_type"),
            )
        )
    far_future = datetime.max.replace(tzinfo=timezone.utc)
    lines.sort(key=lambda line: (line.event_starts_at or far_future, line.created_at))
    return PendingEquipmentLinesResponse(lines=lines)


def pending_queue() -> PendingEquipmentLinesResponse:
    """Pending and re-review lines across every open event, soonest event first."""
    return _queue(WAITING_LINE_STATUSES)


def request_list() -> PendingEquipmentLinesResponse:
    """Every line on every open event, any status, soonest event first: tech
    support's requests page, where resolved lines stay for reference."""
    return _queue(None)


def event_request_ids(event_id: str) -> set[str]:
    """Every equipment line id, any status, for officer validation."""
    return {row["id"] for row in repository.list_event_requests(event_id)}


def event_lines(event_id: str) -> list[dict]:
    """Every equipment line with its status, for the safety review."""
    return [dict(id=row["id"], equipment_name=(_one(row.get("equipment")) or {}).get("name", ""),
                 quantity=row["quantity"], status=row["status"])
            for row in repository.list_event_requests(event_id)]



# --- SCRUM-24 manage equipment reservation -------------------------------------

def _equipment_service_available(function):
    """A Supabase outage is a 503, not a 500 (backend AGENTS.md)."""
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (HTTPError, APIError) as exc:
            raise EquipmentServiceUnavailableError() from exc
    return wrapped


_CLOSED_MESSAGE = "This event is no longer open for equipment arrangements."


def _line(line_id: str) -> dict:
    line = repository.get_line(line_id)
    if line is None:
        raise EquipmentLineNotFoundError()
    return line


def _raise_for(outcome: str, not_reservable: str) -> None:
    if outcome == "ok":
        return
    if outcome == "line_not_found":
        raise EquipmentLineNotFoundError()
    if outcome == "event_not_found":
        raise events_service.EventNotFoundError()
    if outcome == "event_closed":
        raise EquipmentArrangementConflictError(_CLOSED_MESSAGE)
    if outcome == "not_reservable":
        raise EquipmentArrangementConflictError(not_reservable)
    if outcome == "no_schedule":
        raise EquipmentArrangementConflictError("This event has no date and time yet, so availability can't be checked.")
    if outcome == "no_equipment":
        raise EquipmentArrangementConflictError("This event has no equipment lines, so there is nothing to confirm.")
    raise RuntimeError(f"equipment function returned {outcome!r}")


def _after(event_id: str, left_ready: bool) -> None:
    """AC11 with CR-104 AC10: an event in Safety review or Confirmed that stops
    being technically Ready goes back to Planning. `return_to_planning` is a
    no-op for an event in any other status."""
    if left_ready:
        events_service.return_to_planning(event_id, reason_code="technical_not_ready")


@_equipment_service_available
def reserve_line(line_id: str, actor_id: str) -> LineActionResponse:
    """AC1-AC5: reserve the line's quantity for its event's window, if enough is
    free. The database locks the item, so two reserves of the last units can't
    both succeed (AC5)."""
    line = _line(line_id)
    outcome, free, left_ready = repository.reserve_line(line_id, actor_id)
    if outcome == "insufficient":
        raise EquipmentInsufficientError(free or 0, rules.line_status_label(line["status"]))
    _raise_for(outcome, "Only a Pending or Re-review line can be reserved. Reload.")
    _after(line["event_id"], left_ready)
    return LineActionResponse(line_id=line_id, status="reserved", free_quantity=free)


@_equipment_service_available
def mark_not_available(line_id: str, actor_id: str, reason: str) -> LineActionResponse:
    """AC3, AC9: mark a line Not available with a reason; any reservation it
    held is freed (RS-R3)."""
    line = _line(line_id)
    outcome, left_ready = repository.mark_not_available(line_id, actor_id, reason)
    if outcome == "reason_required":
        raise EquipmentNotAvailableReasonError()
    _raise_for(outcome, "This line is already Not available or released. Reload.")
    _after(line["event_id"], left_ready)
    return LineActionResponse(line_id=line_id, status="rejected")


@_equipment_service_available
def set_note(line_id: str, actor_id: str, note: str | None) -> LineActionResponse:
    """AC9, AC12: internal notes on a line; the coordinator is told."""
    line = _line(line_id)
    _raise_for(repository.set_note(line_id, actor_id, note), "")
    return LineActionResponse(line_id=line_id, status=line["status"])


def shortfalls(event_id: str, starts_at: datetime, ends_at: datetime) -> list[dict]:
    """Story 37 preview: the reserved lines a new time would leave short, as
    `{line_id, label, needed, free}`. A line already marked or under re-review is
    with the coordinator or technical support already, so it isn't listed."""
    short = []
    for line in repository.list_event_requests(event_id):
        if line["status"] != "reserved" or line.get("needs_re_review_since"):
            continue
        free = repository.line_free_quantity(line["id"], line["equipment_id"], starts_at, ends_at)
        if free < line["quantity"]:
            name = (_one(line.get("equipment")) or {}).get("name")
            short.append({"line_id": line["id"], "label": rules.line_label(line["quantity"], name),
                          "needed": line["quantity"], "free": free})
    return short


def send_line_for_re_review(line_id: str, coordinator_id: str, note: str | None) -> None:
    """Story 37 AC6, Q20: the assigned coordinator sends a line an approved time change
    left short to technical support. It keeps its reservation until they decide."""
    line = _line(line_id)
    name = events_service.names_by_id([line["event_id"]]).get(line["event_id"], "an event")
    message = f'Equipment for "{name}" needs re-review after an approved change.'
    if note:
        message += f" Note: {note}"
    outcome = repository.send_line_for_re_review(line_id, coordinator_id, note, message)["outcome"]
    if outcome == "not_found":
        raise EquipmentLineNotFoundError()
    if outcome == "not_assigned":
        raise NotAssignedCoordinatorError()
    if outcome == "status_changed":
        raise EquipmentArrangementConflictError(
            "Arrangements can be sent for re-review only while the event is in Planning.")
    if outcome != "ok":
        raise EquipmentArrangementConflictError("This equipment line doesn't need re-review.")


@_equipment_service_available
def set_exit_confirmation(event_id: str, actor_id: str, confirmed: bool) -> None:
    """AC10: tick or untick "Equipment does not block exits or walkways"."""
    outcome, left_ready = repository.set_exit_confirmation(event_id, actor_id, confirmed)
    _raise_for(outcome, "")
    _after(event_id, left_ready)


@_equipment_service_available
def recheck_event(event_id: str, actor_id: str | None = None) -> int:
    """AC7: re-check the event's reservations after its date or time changes.

    Each reservation moves to the new window; a reserved line that no longer fits
    keeps its reservation and is marked Needs re-review, for the coordinator to send
    to technical support (story 37 Q14). Story 37's approval runs the same database
    function inside its own transaction. Returns how many lines were marked."""
    outcome, flagged, left_ready = repository.recheck_event(event_id, actor_id)
    if outcome != "ok":
        return 0
    _after(event_id, left_ready)
    return flagged


# --- SCRUM-44 modify or remove equipment requirements ------------------------

PLANNING_ONLY_MESSAGE = "Equipment can only be changed while the event is in Planning."
STALE_LINE_MESSAGE = "This line changed while you were editing it. Reload to see its current status."


def _changeable_line(line_id: str, coordinator_id: str, expected_status: str) -> dict:
    """AC4, AC7: the line, if the caller is its event's assigned coordinator and
    the event is in Planning. The database re-checks all of it under its locks."""
    line = _line(line_id)
    event = events_service.assigned_event(line["event_id"], coordinator_id)
    if event["status"] != "planning":
        raise EquipmentArrangementConflictError(PLANNING_ONLY_MESSAGE)
    if line["status"] != expected_status:
        raise EquipmentArrangementConflictError(STALE_LINE_MESSAGE)
    return line


def _raise_for_change(outcome: str) -> None:
    if outcome in ("ok", "unchanged"):
        return
    if outcome == "line_not_found":
        raise EquipmentLineNotFoundError()
    if outcome == "not_assigned":
        raise NotAssignedCoordinatorError()
    if outcome == "not_planning":
        raise EquipmentArrangementConflictError(PLANNING_ONLY_MESSAGE)
    if outcome == "stale":
        raise EquipmentArrangementConflictError(STALE_LINE_MESSAGE)
    if outcome == "unknown_equipment":
        raise EquipmentNotInCatalogueError(loc=["body", "equipment_id"])
    raise RuntimeError(f"equipment function returned {outcome!r}")


@_equipment_service_available
def update_line(line_id: str, coordinator_id: str, body: EquipmentLineUpdate) -> LineActionResponse:
    """AC2, AC3: change a line's item, quantity or requirements. The database
    decides its next status (a Reserved line goes to re-review and keeps its
    reservation; a Not available one returns to Pending), alerts Technical
    Support and records the before and after values (AC8)."""
    _changeable_line(line_id, coordinator_id, body.expected_status)
    equipment_id = str(body.equipment_id)
    if not repository.list_catalogue([equipment_id]):
        raise EquipmentNotInCatalogueError(loc=["body", "equipment_id"])
    outcome, line_status = repository.update_line(
        line_id, coordinator_id, equipment_id, body.quantity, body.technical_requirements, body.expected_status,
    )
    _raise_for_change(outcome)
    return LineActionResponse(line_id=line_id, status=line_status)


@_equipment_service_available
def remove_line(line_id: str, coordinator_id: str, expected_status: str) -> LineActionResponse:
    """AC1: remove a line. It is kept as Released, so history still names it
    (AC8); any reservation is freed and Technical Support are alerted when it
    was Reserved or under re-review."""
    _changeable_line(line_id, coordinator_id, expected_status)
    _raise_for_change(repository.remove_line(line_id, coordinator_id, expected_status))
    return LineActionResponse(line_id=line_id, status="released")


def event_history(event_id: str, coordinator_id: str) -> TechnicalHistoryResponse:
    """AC8: the event's equipment history for its assigned coordinator, newest
    first: the same entries Technical Support see. Notes never appear in it
    (SCRUM-24 AC12)."""
    events_service.assigned_event(event_id, coordinator_id)
    return TechnicalHistoryResponse(
        history=[_history_entry(entry) for entry in repository.list_technical_history(event_id)],
    )


def exit_confirmation(event_id: str, row: dict | None = None) -> ExitConfirmation | None:
    """Who ticked the exit box and when, or None (AC10, shown on CR-103's page)."""
    row = row if row is not None else repository.get_event_technical(event_id)
    if not row or not row.get("exit_confirmed_at"):
        return None
    return ExitConfirmation(
        confirmed_by_name=(_one(row.get("exit_confirmer")) or {}).get("full_name"),
        confirmed_at=row["exit_confirmed_at"],
    )


def _history_entry(row: dict) -> TechnicalHistoryEntry:
    line = _one(row.get("line")) or {}
    return TechnicalHistoryEntry(
        action=row["action"],
        line_label=rules.line_label(line.get("quantity"), (_one(line.get("equipment")) or {}).get("name")),
        from_status=row.get("from_status"),
        to_status=row.get("to_status"),
        detail=row.get("detail"),
        actor_name=(_one(row.get("actor")) or {}).get("full_name"),
        created_at=row["created_at"],
    )


@_equipment_service_available
def technical_view(event_id: str) -> TechnicalEventResponse:
    """Technical Support's view of one event: lines with notes, the exit tick,
    the derived technical status and the history (AC9-AC13). Tech support work
    as a pool (AUTH-R5), so any non-draft event."""
    row = repository.get_event_technical(event_id)
    if not row or row["status"] == "draft":
        raise events_service.EventNotFoundError()
    lines = [EquipmentRequestLine(**_embedded_line_fields(line)) for line in repository.list_event_requests(event_id)]
    return TechnicalEventResponse(
        event=TechnicalEvent(
            id=row["id"], name=row["name"], status=row["status"],
            starts_at=row.get("starts_at"), ends_at=row.get("ends_at"),
            coordinator_name=(_one(row.get("coordinator")) or {}).get("full_name"),
        ),
        technical_status=row["technical_readiness"],
        exit_confirmation=exit_confirmation(event_id, row),
        lines=lines,
        history=[_history_entry(entry) for entry in repository.list_technical_history(event_id)],
        re_review_changes=(events_service.latest_approved_change(event_id)
                           if any(line.status == "re_review" for line in lines) else None),
    )


def line_names(line_ids: list[str]) -> dict[str, str | None]:
    return repository.line_names(line_ids)
