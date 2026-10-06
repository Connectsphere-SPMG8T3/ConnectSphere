from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.modules.auth.dependencies import CurrentUser, require_roles
from app.modules.equipment import service
from app.modules.equipment.schemas import (
    CatalogueResponse,
    EquipmentRequestCreate,
    EquipmentRequestLinesResponse,
    PendingEquipmentLinesResponse,
    EquipmentAvailabilityRequest,
    EquipmentAvailabilityResponse,
    EquipmentInventoryResponse,
    EquipmentMaintenanceResponse,
)

router = APIRouter(prefix="/equipment", tags=["equipment"])

# Equipment is Technical Support's own workspace (§6.16), so every read here
# sits behind the same guard.
EquipmentReader = Annotated[CurrentUser, Depends(require_roles(["tech_support"]))]
# SCRUM-45: coordinators pick request items from the catalogue too.
CatalogueReader = Annotated[CurrentUser, Depends(require_roles(["event_coordinator", "tech_support"]))]
EquipmentRequester = Annotated[CurrentUser, Depends(require_roles(["event_coordinator"]))]


@router.get("/catalogue", response_model=CatalogueResponse, status_code=status.HTTP_200_OK)
def catalogue(current_user: CatalogueReader) -> CatalogueResponse:
    return service.catalogue()


@router.post("/requests", response_model=EquipmentRequestLinesResponse, status_code=status.HTTP_201_CREATED)
def submit_request(body: EquipmentRequestCreate, current_user: EquipmentRequester) -> EquipmentRequestLinesResponse:
    return service.submit_request(current_user.id, current_user.full_name, body)


@router.get("/requests/pending", response_model=PendingEquipmentLinesResponse, status_code=status.HTTP_200_OK)
def pending_requests(current_user: EquipmentReader) -> PendingEquipmentLinesResponse:
    return service.pending_queue()


@router.get(
    "/requests/event/{event_id}",
    response_model=EquipmentRequestLinesResponse,
    status_code=status.HTTP_200_OK,
)
def event_requests(event_id: UUID, current_user: EquipmentRequester) -> EquipmentRequestLinesResponse:
    return service.event_requests(str(event_id), current_user.id)


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
