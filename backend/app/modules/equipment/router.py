from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.modules.auth.dependencies import CurrentUser, require_roles
from app.modules.equipment import service
from app.modules.equipment.schemas import (
    EquipmentAvailabilityRequest,
    EquipmentAvailabilityResponse,
    EquipmentInventoryResponse,
    EquipmentMaintenanceResponse,
)

router = APIRouter(prefix="/equipment", tags=["equipment"])

# Equipment is Technical Support's own workspace (§6.16), so every read here
# sits behind the same guard.
EquipmentReader = Annotated[CurrentUser, Depends(require_roles(["tech_support"]))]


@router.get("/maintenance", response_model=EquipmentMaintenanceResponse, status_code=status.HTTP_200_OK)
def maintenance(current_user: EquipmentReader) -> EquipmentMaintenanceResponse:
    return service.get_equipment_maintenance()


@router.get("/inventory", response_model=EquipmentInventoryResponse, status_code=status.HTTP_200_OK)
def inventory(
    current_user: EquipmentReader,
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
) -> EquipmentInventoryResponse:
    return service.get_equipment_inventory(start_at, end_at)


@router.post(
    "/availability/check",
    response_model=EquipmentAvailabilityResponse,
    status_code=status.HTTP_200_OK,
)
def check_availability(
    request: EquipmentAvailabilityRequest,
    current_user: EquipmentReader,
) -> EquipmentAvailabilityResponse:
    return service.check_equipment_availability(request.start_at, request.end_at, request.items)
