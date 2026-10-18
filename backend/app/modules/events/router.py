from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.modules.auth.dependencies import CurrentUser, require_roles
from app.modules.events import service
from app.modules.events.schemas import (
    SafetyDecision,
    SafetyHistoryResponse,
    SafetyQueueResponse,
    SafetyReviewResponse,
    SafetyApproveRequest,
    SafetyChangesRequest,
    SafetyRejectRequest,
    CoordinatorDashboard,
    LeadDashboard,
    EventComment,
    EventCommentCreate,
    EventCommentsResponse,
    EventCreateRequest,
    EventHistoryResponse,
    EventReassignRequest,
    EventRejectRequest,
    EventResponse,
    EventResubmitRequest,
    EventReturnRequest,
    EventSpaceRequest,
    EventSpaceRequestCreate,
    EventSpaceRequestUpdate,
    EventUpdateRequest,
)

router = APIRouter(prefix="/events", tags=["events"])
SafetyOfficer = Annotated[CurrentUser, Depends(require_roles(["safety_officer"]))]
EventOrganiser = Annotated[CurrentUser, Depends(require_roles(["event_organiser"]))]
EventCoordinator = Annotated[CurrentUser, Depends(require_roles(["event_coordinator"]))]
EventCoordinatorLead = Annotated[CurrentUser, Depends(require_roles(["event_coordinator_lead"]))]
SafetyDecisionReader = Annotated[CurrentUser, Depends(require_roles(["event_coordinator", "safety_officer"]))]
EventParticipant = Annotated[CurrentUser, Depends(require_roles(["event_organiser", "event_coordinator"]))]


@router.post("", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
def create_event(body: EventCreateRequest, current_user: EventOrganiser) -> EventResponse:
    return service.create(current_user.id, body)


@router.get("", response_model=list[EventResponse])
def list_events(current_user: EventOrganiser) -> list[EventResponse]:
    return service.list_owned(current_user.id)


@router.post("/{event_id}/spaces", response_model=EventSpaceRequest, status_code=status.HTTP_201_CREATED)
def create_event_space(
    event_id: UUID, body: EventSpaceRequestCreate, current_user: EventOrganiser
) -> EventSpaceRequest:
    return service.create_space(str(event_id), current_user.id, body)


@router.patch("/{event_id}/spaces/{space_id}", response_model=EventSpaceRequest)
def update_event_space(
    event_id: UUID,
    space_id: UUID,
    body: EventSpaceRequestUpdate,
    current_user: EventOrganiser,
) -> EventSpaceRequest:
    # The event id is part of the route for a stable client URL; ownership and
    # parentage are rechecked by the service using the space id.
    return service.update_space(str(space_id), current_user.id, body)


# Declared above `/{event_id}/spaces/{space_id}`, which would otherwise take
# "primary" as a space id and answer with the organiser-only route's 403.
@router.delete("/{event_id}/spaces/primary", response_model=EventResponse)
def clear_primary_space(event_id: UUID, current_user: EventCoordinator) -> EventResponse:
    return service.set_primary_space(str(event_id), None, current_user.id)


@router.delete("/{event_id}/spaces/{space_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event_space(event_id: UUID, space_id: UUID, current_user: EventOrganiser) -> Response:
    service.delete_space(str(space_id), current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Declared above `/{event_id}`: that path is typed UUID, so this one would
# otherwise reach `read_event` and answer 422 instead of the dashboard.
@router.get("/dashboard/coordinator", response_model=CoordinatorDashboard)
def coordinator_dashboard(current_user: EventCoordinator) -> CoordinatorDashboard:
    return service.coordinator_dashboard(current_user.id)


@router.get("/dashboard/lead", response_model=LeadDashboard)
def lead_dashboard(current_user: EventCoordinatorLead) -> LeadDashboard:
    return service.lead_dashboard(current_user.id)


@router.get("/safety-queue", response_model=SafetyQueueResponse)
def safety_queue(current_user: SafetyOfficer) -> SafetyQueueResponse:
    return service.safety_queue()


@router.get("/safety-history", response_model=SafetyHistoryResponse)
def safety_history(current_user: SafetyOfficer) -> SafetyHistoryResponse:
    return service.safety_history()


@router.post("/{event_id}/clone", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
def clone_event(event_id: UUID, current_user: EventOrganiser) -> EventResponse:
    return service.clone(str(event_id), current_user.id)


@router.get("/{event_id}", response_model=EventResponse)
def read_event(event_id: UUID, current_user: EventParticipant) -> EventResponse:
    return service.read(str(event_id), current_user.id, current_user.role)


@router.get("/{event_id}/history", response_model=EventHistoryResponse)
def read_event_history(event_id: UUID, current_user: EventParticipant) -> EventHistoryResponse:
    return service.history(str(event_id), current_user.id, current_user.role)


@router.get("/{event_id}/comments", response_model=EventCommentsResponse)
def read_event_comments(event_id: UUID, current_user: EventParticipant) -> EventCommentsResponse:
    return service.comments(str(event_id), current_user.id, current_user.role)


@router.post("/{event_id}/comments", response_model=EventComment, status_code=status.HTTP_201_CREATED)
def add_event_comment(event_id: UUID, body: EventCommentCreate, current_user: EventParticipant) -> EventComment:
    return service.add_comment(str(event_id), current_user.id, current_user.role, current_user.full_name, body.body)


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


@router.put("/{event_id}/spaces/{space_id}/primary", response_model=EventResponse)
def set_primary_space(event_id: UUID, space_id: UUID, current_user: EventCoordinator) -> EventResponse:
    return service.set_primary_space(str(event_id), str(space_id), current_user.id)


@router.post("/{event_id}/send-for-safety-check", response_model=EventResponse)
def send_for_safety_check(event_id: UUID, current_user: EventCoordinator) -> EventResponse:
    return service.send_for_safety_check(str(event_id), current_user.id)


@router.post("/{event_id}/approve", response_model=EventResponse)
def approve_event(event_id: UUID, current_user: EventCoordinator) -> EventResponse:
    return service.approve(str(event_id), current_user.id)


@router.post("/{event_id}/reject", response_model=EventResponse)
def reject_event(event_id: UUID, body: EventRejectRequest, current_user: EventCoordinator) -> EventResponse:
    return service.reject(str(event_id), current_user.id, body.reason)


@router.post("/{event_id}/reassign", response_model=EventResponse)
def reassign_event(event_id: UUID, body: EventReassignRequest, current_user: EventCoordinatorLead) -> EventResponse:
    return service.reassign(str(event_id), current_user.id, str(body.coordinator_id), body.expected_version)


@router.post("/{event_id}/return", response_model=EventResponse)
def return_event(event_id: UUID, body: EventReturnRequest, current_user: EventCoordinator) -> EventResponse:
    return service.return_for_amendment(str(event_id), current_user.id, body)


@router.post("/{event_id}/resubmit", response_model=EventResponse)
def resubmit_event(event_id: UUID, body: EventResubmitRequest, current_user: EventOrganiser) -> EventResponse:
    return service.resubmit(str(event_id), current_user.id, body)


@router.post("/{event_id}/safety-approve", response_model=EventResponse)
def safety_approve(event_id: UUID, current_user: SafetyOfficer,
                   body: SafetyApproveRequest | None = None) -> EventResponse:
    return service.safety_approve(str(event_id), current_user.id, body)


@router.post("/{event_id}/safety-request-changes", response_model=EventResponse)
def safety_request_changes(event_id: UUID, body: SafetyChangesRequest, current_user: SafetyOfficer) -> EventResponse:
    return service.safety_request_changes(str(event_id), current_user.id, body)


@router.post("/{event_id}/safety-reject", response_model=EventResponse)
def safety_reject(event_id: UUID, body: SafetyRejectRequest, current_user: SafetyOfficer) -> EventResponse:
    return service.safety_reject(str(event_id), current_user.id, body)


@router.get("/{event_id}/safety-review", response_model=SafetyReviewResponse)
def safety_review(event_id: UUID, current_user: SafetyOfficer) -> SafetyReviewResponse:
    return service.safety_review(str(event_id))


@router.get("/{event_id}/safety-decisions", response_model=list[SafetyDecision])
def safety_decisions(event_id: UUID, current_user: SafetyDecisionReader) -> list[SafetyDecision]:
    return service.safety_decisions(str(event_id), current_user.id, current_user.role)
