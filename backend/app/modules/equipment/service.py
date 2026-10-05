from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone

from app.modules.equipment import repository
from app.modules.equipment.repository import CommitmentRow
from app.modules.equipment.schemas import (
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
