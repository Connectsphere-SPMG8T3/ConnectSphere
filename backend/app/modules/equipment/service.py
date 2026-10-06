from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone

from app.core.exceptions import EquipmentNotInCatalogueError, EquipmentRequestNotAllowedError, NotAssignedCoordinatorError
from app.modules.equipment import repository
from app.modules.equipment.repository import CommitmentRow
# A module import, not names: `events.service` imports this module too, and a
# module reference resolves at call time, so the cycle is harmless.
from app.modules.events import service as events_service
from app.modules.equipment.schemas import (
    CatalogueItem,
    CatalogueResponse,
    EquipmentRequestCreate,
    EquipmentRequestLine,
    EquipmentRequestLinesResponse,
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
    equipment_ids = {str(item.equipment_id) for item in items}

    equipment = {row.id: row for row in repository.list_equipment(equipment_ids)}
    reserved = _totals_by_equipment(repository.list_reservations(start_at, end_at, equipment_ids))
    unavailable = _totals_by_equipment(repository.list_unavailability(start_at, end_at, equipment_ids))

    results = []
    for item in items:
        key = str(item.equipment_id)
        row = equipment.get(key)
        if row is None:
            results.append(
                ItemAvailabilityResult(
                    equipment_id=item.equipment_id,
                    name="Unknown equipment",
                    quantity_needed=item.quantity_needed,
                    quantity_available=0,
                    sufficient=False,
                )
            )
            continue

        quantity_available = max(0, row.total_quantity - reserved.get(key, 0) - unavailable.get(key, 0))
        results.append(
            ItemAvailabilityResult(
                equipment_id=item.equipment_id,
                name=row.name,
                quantity_needed=item.quantity_needed,
                quantity_available=quantity_available,
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
    # A lone start or end is ignored rather than half-applied: an overlap needs
    # both ends, and filtering on one would misreport stock.
    window = (start_at, end_at) if start_at and end_at else (None, None)

    reserved = _totals_by_equipment(repository.list_reservations(*window))
    maintenance = _totals_by_equipment(repository.list_unavailability(*window))

    items = []
    for row in repository.list_equipment():
        reserved_quantity = reserved.get(row.id, 0)
        maintenance_quantity = maintenance.get(row.id, 0)
        items.append(
            EquipmentInventoryItem(
                equipment_id=row.id,
                name=row.name,
                total_quantity=row.total_quantity,
                reserved_quantity=reserved_quantity,
                maintenance_quantity=maintenance_quantity,
                net_available=max(0, row.total_quantity - reserved_quantity - maintenance_quantity),
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


# A reservation that was made and not cancelled means tech support settled the
# line: `confirmed` still holds units, `completed` has used them.
RESERVED_STATUSES = ("confirmed", "completed")


def reserved_event_ids(event_ids: Iterable[str]) -> set[str]:
    """The events among `event_ids` that tech support has reserved equipment for.

    [Assumption] REQUIREMENTS §6.21.1: SCRUM-24's per-event equipment requests
    don't exist yet, so "every request reserved" (§6.6) is read as "at least one
    reservation". Used by the coordinator dashboard (SCRUM-72).
    """
    return set(repository.list_reserved_event_ids(event_ids, RESERVED_STATUSES))



# --- SCRUM-45 equipment request lines (REQUIREMENTS 6.15) ---------------------

RETURNED_MESSAGE = (
    "Equipment can't be requested while the event is returned for amendment. "
    "It can be requested once the event is back in planning."
)

# Tech support's queue leaves out lines on closed events. Releasing those lines
# (6.15 `released`) is SCRUM-24's; until then they are only hidden.
QUEUE_EVENT_STATUSES = ("planning", "confirmed")


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
    assigned one. They are the same person until reassignment exists."""
    events_service.assigned_event(event_id, coordinator_id)
    return EquipmentRequestLinesResponse(
        lines=[EquipmentRequestLine(**_embedded_line_fields(row)) for row in repository.list_event_requests(event_id)]
    )


def pending_queue() -> PendingEquipmentLinesResponse:
    """Pending lines across every open event, soonest event first."""
    lines = []
    for row in repository.list_pending_requests():
        event = _one(row.get("event")) or {}
        if event.get("status") not in QUEUE_EVENT_STATUSES:
            continue
        lines.append(
            PendingEquipmentLine(
                **_embedded_line_fields(row),
                event_name=event.get("name") or "",
                event_starts_at=event.get("starts_at"),
            )
        )
    far_future = datetime.max.replace(tzinfo=timezone.utc)
    lines.sort(key=lambda line: (line.event_starts_at or far_future, line.created_at))
    return PendingEquipmentLinesResponse(lines=lines)
