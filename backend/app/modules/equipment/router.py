from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import CurrentUser, require_roles
from app.modules.equipment import service
from app.modules.equipment.schemas import EquipmentAvailabilityRequest, EquipmentAvailabilityResponse

router = APIRouter(prefix="/equipment", tags=["equipment"])


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