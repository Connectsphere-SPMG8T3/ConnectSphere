from typing import Annotated

from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import CurrentUser, require_roles
from app.modules.equipment import service
from app.modules.equipment.schemas import (
    EquipmentAvailabilityRequest,
    EquipmentAvailabilityResponse,
    EquipmentInventoryResponse,
    EquipmentMaintenanceResponse,
)

router = APIRouter(prefix="/equipment", tags=["equipment"])


@router.get("/maintenance", response_model=EquipmentMaintenanceResponse, status_code=status.HTTP_200_OK)
def maintenance(
    current_user: Annotated[CurrentUser, Depends(require_roles(["tech_support"]))],
    db: Annotated[Session, Depends(get_db)],
) -> EquipmentMaintenanceResponse:
    return service.get_equipment_maintenance(db)


@router.get("/inventory", response_model=EquipmentInventoryResponse, status_code=status.HTTP_200_OK)
def inventory(
    current_user: Annotated[CurrentUser, Depends(require_roles(["tech_support"]))],
    db: Annotated[Session, Depends(get_db)],
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
) -> EquipmentInventoryResponse:
    return service.get_equipment_inventory(db, start_at, end_at)


@router.post(
    "/availability/check",
    response_model=EquipmentAvailabilityResponse,
    status_code=status.HTTP_200_OK,
)
def check_availability(
    request: EquipmentAvailabilityRequest,
    current_user: Annotated[CurrentUser, Depends(require_roles(["tech_support"]))],
    db: Annotated[Session, Depends(get_db)],
) -> EquipmentAvailabilityResponse:
    return service.check_equipment_availability(
        db,
        request.start_at,
        request.end_at,
        request.items,
    )