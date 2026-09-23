from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.modules.auth.dependencies import CurrentUser, require_roles
from app.modules.events import service
from app.modules.events.schemas import EventCreateRequest, EventRejectRequest, EventResponse, EventUpdateRequest

router = APIRouter(prefix="/events", tags=["events"])
EventOrganiser = Annotated[CurrentUser, Depends(require_roles(["event_organiser"]))]
EventCoordinator = Annotated[CurrentUser, Depends(require_roles(["event_coordinator"]))]


@router.post("", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
def create_event(body: EventCreateRequest, current_user: EventOrganiser) -> EventResponse:
    return service.create(current_user.id, body)


@router.get("", response_model=list[EventResponse])
def list_events(current_user: EventOrganiser) -> list[EventResponse]:
    return service.list_owned(current_user.id)


@router.get("/{event_id}", response_model=EventResponse)
def read_event(event_id: UUID, current_user: EventOrganiser) -> EventResponse:
    return service.read(str(event_id), current_user.id)


@router.patch("/{event_id}", response_model=EventResponse)
def update_event(event_id: UUID, body: EventUpdateRequest, current_user: EventOrganiser) -> EventResponse:
    return service.update(str(event_id), current_user.id, body)


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(event_id: UUID, current_user: EventOrganiser) -> Response:
    service.discard(str(event_id), current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{event_id}/submit", response_model=EventResponse)
def submit_event(
    event_id: UUID,
    current_user: EventOrganiser,
    body: EventUpdateRequest | None = None,
) -> EventResponse:
    return service.submit(str(event_id), current_user.id, body)


@router.post("/{event_id}/approve", response_model=EventResponse)
def approve_event(event_id: UUID, current_user: EventCoordinator) -> EventResponse:
    return service.approve(str(event_id), current_user.id)


@router.post("/{event_id}/reject", response_model=EventResponse)
def reject_event(event_id: UUID, body: EventRejectRequest, current_user: EventCoordinator) -> EventResponse:
    return service.reject(str(event_id), current_user.id, body.reason)
