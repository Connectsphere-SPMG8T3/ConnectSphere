from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Equipment, EquipmentReservation, EquipmentUnavailability, ReservationStatus
from app.modules.equipment.schemas import (
    EquipmentAvailabilityResponse,
    EquipmentCheckItem,
    EquipmentInventoryItem,
    EquipmentInventoryResponse,
    ItemAvailabilityResult,
)


def check_equipment_availability(
    db: Session,
    start_at: datetime,
    end_at: datetime,
    items: Sequence[EquipmentCheckItem],
) -> EquipmentAvailabilityResponse:
    equipment_ids = {item.equipment_id for item in items}

    reservations = (
        select(
            EquipmentReservation.equipment_id,
            func.coalesce(func.sum(EquipmentReservation.quantity), 0).label("reserved_quantity"),
        )
        .where(
            EquipmentReservation.equipment_id.in_(equipment_ids),
            EquipmentReservation.status == ReservationStatus.CONFIRMED.value,
            EquipmentReservation.start_at < end_at,
            EquipmentReservation.end_at > start_at,
        )
        .group_by(EquipmentReservation.equipment_id)
        .subquery()
    )
    unavailable = (
        select(
            EquipmentUnavailability.equipment_id,
            func.coalesce(func.sum(EquipmentUnavailability.quantity), 0).label("unavailable_quantity"),
        )
        .where(
            EquipmentUnavailability.equipment_id.in_(equipment_ids),
            EquipmentUnavailability.start_at < end_at,
            EquipmentUnavailability.end_at > start_at,
        )
        .group_by(EquipmentUnavailability.equipment_id)
        .subquery()
    )

    statement = (
        select(
            Equipment.id,
            Equipment.name,
            Equipment.total_quantity,
            func.coalesce(reservations.c.reserved_quantity, 0).label("reserved_quantity"),
            func.coalesce(unavailable.c.unavailable_quantity, 0).label("unavailable_quantity"),
        )
        .outerjoin(reservations, reservations.c.equipment_id == Equipment.id)
        .outerjoin(unavailable, unavailable.c.equipment_id == Equipment.id)
        .where(Equipment.id.in_(equipment_ids))
    )
    rows = db.execute(statement).mappings().all()
    by_id = {row["id"]: row for row in rows}

    results = []
    for item in items:
        row = by_id.get(item.equipment_id)
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

        quantity_available = max(
            0,
            row["total_quantity"] - row["reserved_quantity"] - row["unavailable_quantity"],
        )
        results.append(
            ItemAvailabilityResult(
                equipment_id=item.equipment_id,
                name=row["name"],
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
    db: Session,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> EquipmentInventoryResponse:
    reservation_filters = [EquipmentReservation.status == ReservationStatus.CONFIRMED.value]
    maintenance_filters = []
    if start_at and end_at:
        reservation_filters.extend(
            [
                EquipmentReservation.start_at < end_at,
                EquipmentReservation.end_at > start_at,
            ]
        )
        maintenance_filters.extend(
            [
                EquipmentUnavailability.start_at < end_at,
                EquipmentUnavailability.end_at > start_at,
            ]
        )

    reservations = (
        select(
            EquipmentReservation.equipment_id,
            func.coalesce(func.sum(EquipmentReservation.quantity), 0).label("reserved_quantity"),
        )
        .where(*reservation_filters)
        .group_by(EquipmentReservation.equipment_id)
        .subquery()
    )
    maintenance = (
        select(
            EquipmentUnavailability.equipment_id,
            func.coalesce(func.sum(EquipmentUnavailability.quantity), 0).label("maintenance_quantity"),
        )
        .where(*maintenance_filters)
        .group_by(EquipmentUnavailability.equipment_id)
        .subquery()
    )
    statement = select(
        Equipment.id,
        Equipment.name,
        Equipment.total_quantity,
        func.coalesce(reservations.c.reserved_quantity, 0).label("reserved_quantity"),
        func.coalesce(maintenance.c.maintenance_quantity, 0).label("maintenance_quantity"),
    ).outerjoin(reservations, reservations.c.equipment_id == Equipment.id).outerjoin(
        maintenance, maintenance.c.equipment_id == Equipment.id
    )

    items = []
    for row in db.execute(statement).mappings():
        net_available = max(0, row["total_quantity"] - row["reserved_quantity"] - row["maintenance_quantity"])
        items.append(
            EquipmentInventoryItem(
                equipment_id=row["id"],
                name=row["name"],
                total_quantity=row["total_quantity"],
                reserved_quantity=row["reserved_quantity"],
                maintenance_quantity=row["maintenance_quantity"],
                net_available=net_available,
            )
        )
    return EquipmentInventoryResponse(items=items)