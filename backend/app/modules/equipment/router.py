from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.modules.auth.dependencies import CurrentUser, require_roles
from app.modules.equipment import service
from app.modules.events.schemas import ReReviewSendRequest
from app.modules.equipment.schemas import (
    CatalogueResponse,
    EquipmentRequestCreate,
    EquipmentRequestLinesResponse,
    PendingEquipmentLinesResponse,
    EquipmentAvailabilityRequest,
    EquipmentAvailabilityResponse,
    EquipmentInventoryResponse,
    EquipmentLineUpdate,
    EquipmentMaintenanceResponse,
    ExitConfirmationRequest,
    LineActionResponse,
    LiveLineStatus,
    LineNoteRequest,
    NotAvailableRequest,
    TechnicalEventResponse,
    TechnicalHistoryResponse,
    TechnicalPreparationRequest,
    TechnicalPreparationUpdated,
)

router = APIRouter(prefix="/equipment", tags=["equipment"])

# Equipment is Technical Support's own workspace (§6.16), so every read here
# sits behind the same guard.
EquipmentReader = Annotated[CurrentUser, Depends(require_roles(["tech_support"]))]
# SCRUM-45: coordinators pick request items from the catalogue too.
CatalogueReader = Annotated[CurrentUser, Depends(require_roles(["event_coordinator", "tech_support"]))]
EquipmentRequester = Annotated[CurrentUser, Depends(require_roles(["event_coordinator"]))]
# SCRUM-24 AC8: only Technical Support arrange equipment; every other active
# role gets 403, whatever else the account holds (SCRUM-76).
EquipmentArranger = Annotated[CurrentUser, Depends(require_roles(["tech_support"]))]


@router.get("/catalogue", response_model=CatalogueResponse, status_code=status.HTTP_200_OK)
def catalogue(current_user: CatalogueReader) -> CatalogueResponse:
    return service.catalogue()


@router.post("/requests", response_model=EquipmentRequestLinesResponse, status_code=status.HTTP_201_CREATED)
def submit_request(body: EquipmentRequestCreate, current_user: EquipmentRequester) -> EquipmentRequestLinesResponse:
    return service.submit_request(current_user.id, current_user.full_name, body)


@router.get("/requests", response_model=PendingEquipmentLinesResponse, status_code=status.HTTP_200_OK)
def request_list(current_user: EquipmentReader) -> PendingEquipmentLinesResponse:
    return service.request_list()


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


@router.get(
    "/requests/event/{event_id}/history",
    response_model=TechnicalHistoryResponse,
    status_code=status.HTTP_200_OK,
)
def event_history(event_id: UUID, current_user: EquipmentRequester) -> TechnicalHistoryResponse:
    return service.event_history(str(event_id), current_user.id)


# SCRUM-44: the assigned coordinator changes or removes a line while the event
# is in Planning. `expected_status` is the status they saw (AC6).
@router.patch("/requests/{line_id}", response_model=LineActionResponse, status_code=status.HTTP_200_OK)
def update_line(line_id: UUID, body: EquipmentLineUpdate, current_user: EquipmentRequester) -> LineActionResponse:
    return service.update_line(str(line_id), current_user.id, body)


@router.delete("/requests/{line_id}", response_model=LineActionResponse, status_code=status.HTTP_200_OK)
def remove_line(
    line_id: UUID,
    current_user: EquipmentRequester,
    expected_status: LiveLineStatus = Query(),
) -> LineActionResponse:
    return service.remove_line(str(line_id), current_user.id, expected_status)


@router.post("/requests/{line_id}/reserve", response_model=LineActionResponse, status_code=status.HTTP_200_OK)
def reserve_line(line_id: UUID, current_user: EquipmentArranger) -> LineActionResponse:
    return service.reserve_line(str(line_id), current_user.id)


@router.post("/requests/{line_id}/not-available", response_model=LineActionResponse, status_code=status.HTTP_200_OK)
def mark_not_available(line_id: UUID, body: NotAvailableRequest, current_user: EquipmentArranger) -> LineActionResponse:
    return service.mark_not_available(str(line_id), current_user.id, body.reason)


@router.post("/requests/{line_id}/send-for-re-review", status_code=status.HTTP_204_NO_CONTENT)
def send_line_for_re_review(line_id: UUID, body: ReReviewSendRequest, current_user: EquipmentRequester) -> Response:
    """Story 37 AC6: send a line an approved time change left short to technical
    support, with an optional note. It keeps its reservation until they decide."""
    service.send_line_for_re_review(str(line_id), current_user.id, body.note)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/requests/{line_id}/notes", response_model=LineActionResponse, status_code=status.HTTP_200_OK)
def set_note(line_id: UUID, body: LineNoteRequest, current_user: EquipmentArranger) -> LineActionResponse:
    return service.set_note(str(line_id), current_user.id, body.note)


@router.put("/events/{event_id}/exit-confirmation", status_code=status.HTTP_204_NO_CONTENT)
def set_exit_confirmation(event_id: UUID, body: ExitConfirmationRequest, current_user: EquipmentArranger) -> None:
    service.set_exit_confirmation(str(event_id), current_user.id, body.confirmed)


@router.put("/events/{event_id}/preparation", response_model=TechnicalPreparationUpdated,
            status_code=status.HTTP_200_OK)
def set_technical_preparation(
    event_id: UUID, body: TechnicalPreparationRequest, current_user: EquipmentArranger
) -> TechnicalPreparationUpdated:
    """CR-110: only Technical Support record technical preparation (AC6)."""
    return service.set_technical_preparation(str(event_id), current_user.id, body.stage.value, body.note)


@router.get("/events/{event_id}/technical", response_model=TechnicalEventResponse, status_code=status.HTTP_200_OK)
def technical_view(event_id: UUID, current_user: EquipmentArranger) -> TechnicalEventResponse:
    return service.technical_view(str(event_id))


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
