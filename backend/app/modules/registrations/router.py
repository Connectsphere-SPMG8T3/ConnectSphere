from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.modules.auth.dependencies import CurrentUser, require_roles

from app.modules.registrations import service
from app.modules.registrations.schemas import PublicEvent, PublicEventDirectory, RegistrationResult

router = APIRouter(prefix="/public", tags=["public events"])
Attendee = Annotated[CurrentUser, Depends(require_roles(["attendee"]))]


@router.get("/events", response_model=PublicEventDirectory)
def list_public_events() -> PublicEventDirectory:
    return PublicEventDirectory(events=service.public_directory())


@router.get("/events/{event_id}", response_model=PublicEvent)
def read_public_event(event_id: UUID) -> PublicEvent:
    return service.public_event(str(event_id))


@router.post(
    "/events/{event_id}/registrations",
    response_model=RegistrationResult,
    status_code=status.HTTP_201_CREATED,
)
def register_for_event(event_id: UUID, response: Response, current_user: Attendee) -> RegistrationResult:
    result = service.register_attendee(str(event_id), current_user.id)
    if result.status == "already_registered":
        response.status_code = status.HTTP_200_OK
    return result