from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.modules.auth.dependencies import CurrentUser, require_roles

from app.modules.registrations import service
from app.modules.registrations.schemas import (
    AttendeeRegistrationList,
    PublicEvent,
    PublicEventDirectory,
    RegistrationResult,
    WithdrawalResult,
)

router = APIRouter(prefix="/public", tags=["public events"])
attendee_router = APIRouter(prefix="/registrations", tags=["attendee registrations"])
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
    if result.status in {"already_registered", "already_waitlisted", "invited"}:
        response.status_code = status.HTTP_200_OK
    return result


@attendee_router.post("/{event_id}/withdraw", response_model=WithdrawalResult)
def withdraw_from_event(event_id: UUID, current_user: Attendee) -> WithdrawalResult:
    return service.withdraw_attendee(str(event_id), current_user.id)


@attendee_router.post("/{registration_id}/accept", response_model=RegistrationResult)
def accept_invitation(registration_id: UUID, current_user: Attendee) -> RegistrationResult:
    return service.accept_invitation(str(registration_id), current_user.id)


@attendee_router.delete("/{registration_id}", status_code=status.HTTP_204_NO_CONTENT)
def leave_waitlist(registration_id: UUID, current_user: Attendee) -> Response:
    service.leave_waitlist(str(registration_id), current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@attendee_router.get("/me", response_model=AttendeeRegistrationList)
def list_my_registrations(current_user: Attendee) -> AttendeeRegistrationList:
    return service.attendee_registrations(current_user.id)