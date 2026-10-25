from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from functools import wraps
from zoneinfo import ZoneInfo

from httpx import HTTPError
from postgrest.exceptions import APIError

from fastapi import HTTPException, status

from app.core.exceptions import (
    ChangeRequestInvalidError,
    CoordinatorNotEligibleError,
    EventNotInLeadScopeError,
    EventServiceUnavailableError,
    NotAssignedCoordinatorError,
    UnknownEventArrangementError,
)
# Module imports, not names: `venues.service` imports this module too, and a
# module reference resolves at call time, so the cycle is harmless.
from app.modules.equipment import service as equipment_service
from app.modules.events import change_fields, lead_scope, lifecycle, repository
from app.modules.events.readiness import safety_readiness
from app.modules.venues import service as venues_service
from app.modules.events.schemas import (
    SafetyDecision,
    SafetyDecisionSummary,
    SafetyHistoryItem,
    SafetyHistoryResponse,
    SafetyQueueItem,
    SafetyQueueResponse,
    SafetyReviewResponse,
    SafetyApproveRequest,
    SafetyChangesRequest,
    SafetyRejectRequest,
    ReturnReason,
    COMMENTABLE_STATUSES,
    SpaceReadiness,
    SafetyReadiness,
    AmendmentRequest,
    CoordinatorActionItem,
    CoordinatorActionKind,
    CoordinatorActiveEvent,
    CoordinatorDashboard,
    CoordinatorRejectedEvent,
    LeadCoordinator,
    LeadDashboard,
    LeadEvent,
    EventComment,
    EventCommentsResponse,
    ChangeRequestCreate,
    EventChangeRequest,
    EventCreateRequest,
    EventHistoryEntry,
    EventHistoryResponse,
    EventPlanningContext,
    SpaceRequirements,
    EventResponse,
    EventSpaceVenueBooking,
    EventSpaceRequest,
    EventSpaceRequestCreate,
    EventSpaceRequestFields,
    EventSpaceRequestUpdate,
    EventResubmitRequest,
    EventReturnRequest,
    EventStatus,
    EventUpdateRequest,
    EventRejectedBooking,
    EventVenueBooking,
    Readiness,
    ReadinessState,
)


def _safety_service_available(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (HTTPError, APIError) as exc:
            raise EventServiceUnavailableError() from exc
    return wrapped


DEFAULT_EVENT_TIMEZONE = "Asia/Singapore"

# The statuses an assigned coordinator still has work in (SCRUM-72 AC2). Drafts
# are private to their organiser (DR-R2) and terminal statuses aren't active.
ACTIVE_COORDINATOR_STATUSES = ("under_review", "returned", "planning", "safety_review", "confirmed")


CLONE_FIELDS = (
    "name",
    "event_timezone",
    "purpose",
    "description",
    "expected_attendance",
    "layout_preference",
    "facilities_required",
    "accessibility_needs",
    "preliminary_equipment_needs",
    "registration_enabled",
    "registration_capacity",
    "re_registration_allowed",
    "waitlist_enabled",
)


class EventNotFoundError(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")


class EventConflictError(HTTPException):
    def __init__(self, detail: str = "The event was changed by another request.") -> None:
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


class EventSpaceConflictError(HTTPException):
    def __init__(self, detail: str = "The event space was changed by another request.") -> None:
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


def names_by_id(event_ids: Iterable[str]) -> dict[str, str]:
    """`{event_id: name}` for the ids given — the events module's answer to
    "what is this event called?" for modules that only hold an `event_id`.

    No ownership check: the callers are already behind their own role and
    relationship guards, and an event's name is the least of what they are
    cleared to see. `venue_bookings.event_id` has no foreign key to `events`
    (BUILD_LOG §4.9), so a PostgREST embed is not available and a caller that
    needs names asks here rather than reading another module's table.
    """
    return repository.list_event_names(event_ids)


def planning_context_by_id(event_ids: Iterable[str]) -> dict[str, EventPlanningContext]:
    """`{event_id: EventPlanningContext}` for the ids given — the events module's
    answer to "what does this event need?" for a module that only holds an
    `event_id` (SCRUM-63: `venues.service` uses this to judge whether a venue
    edit newly breaks one of its upcoming bookings).

    No ownership check, for the same reason as `names_by_id`: callers are
    already behind their own role and relationship guards.
    """
    return {
        row["id"]: EventPlanningContext(
            name=row.get("name"),
            status=row.get("status"),
            coordinator_id=row.get("coordinator_id"),
            expected_attendance=row.get("expected_attendance"),
            layout_preference=row.get("layout_preference"),
            facilities_required=row.get("facilities_required") or [],
            accessibility_needs=row.get("accessibility_needs"),
        )
        for row in repository.list_planning_context(event_ids)
    }


def space_requirements_by_id(space_ids: Iterable[str]) -> dict[str, SpaceRequirements]:
    """`{space_id: SpaceRequirements}` for the ids given — the events module's
    answer to "what does this requested space need?" for a module that only
    holds an `event_space_request_id` (CR-94: `venues.service` judges a venue
    edit on each booked space's own requirements). No ownership check, for the
    same reason as `names_by_id`.
    """
    return {
        row["id"]: SpaceRequirements(
            expected_pax=row.get("expected_pax"),
            layout_preference=row.get("layout_preference"),
            facilities_required=row.get("facilities_required"),
        )
        for row in repository.list_spaces_by_ids(space_ids)
    }


def _to_response(row: dict) -> EventResponse:
    return EventResponse(**row)


def _space_event(space_id: str, organiser_id: str) -> tuple[dict, dict]:
    space = repository.get_space(space_id)
    if not space:
        raise EventNotFoundError()
    event = _owned_event(space["event_id"], organiser_id)
    if event.get("status") not in ("draft", "returned"):
        raise EventConflictError("Event spaces can only be changed while the event is draft or returned.")
    return event, space


def create_space(event_id: str, organiser_id: str, body: EventSpaceRequestCreate) -> EventSpaceRequest:
    event = _owned_event(event_id, organiser_id)
    if event.get("status") not in ("draft", "returned"):
        raise EventConflictError("Event spaces can only be changed while the event is draft or returned.")
    values = body.model_dump(mode="json", exclude={"version"})
    errors = _space_schedule_errors(values, event, 0)
    if errors:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=errors)
    return EventSpaceRequest(**repository.create_space(event_id, values))


def update_space(space_id: str, organiser_id: str, body: EventSpaceRequestUpdate) -> EventSpaceRequest:
    event, space = _space_event(space_id, organiser_id)
    values = body.model_dump(mode="json", exclude_unset=True, exclude={"version"})
    editable_fields = ("label", "expected_pax", "layout_preference", "facilities_required", "starts_at", "ends_at")
    merged = {field: space.get(field) for field in editable_fields}
    merged.update(values)
    validated = EventSpaceRequestFields(**merged)
    errors = _space_schedule_errors(validated.model_dump(mode="python"), event, 0)
    if errors:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=errors)
    updated = repository.update_space(space_id, values, space["version"])
    if not updated:
        raise EventSpaceConflictError()
    return EventSpaceRequest(**updated)


def delete_space(space_id: str, organiser_id: str) -> None:
    _event, space = _space_event(space_id, organiser_id)
    if not repository.delete_space(space_id, space["version"]):
        raise EventSpaceConflictError()


def _with_amendment(row: dict) -> EventResponse:
    """A single event, carrying its open amendment while it is returned (SCRUM-33)."""
    response = _to_response(row)
    if response.status == EventStatus.returned:
        amendment = repository.get_open_amendment(row["id"])
        if amendment:
            response.amendment = AmendmentRequest(**amendment)
    return response


def _owned_event(event_id: str, organiser_id: str) -> dict:
    row = repository.get_event(event_id)
    if not row or row.get("organiser_id") != organiser_id:
        raise EventNotFoundError()
    return row


STALE_EVENT_MESSAGE = "This event was updated by someone else. Reload."


def _assigned_event(event_id: str, coordinator_id: str) -> dict:
    """The event, if the caller is its assigned coordinator. Unlike `_owned_event`,
    a coordinator who isn't assigned gets 403, not 404: coordinators may already
    search every non-draft event (QA-87), so the 403 confirms nothing new, and
    SCRUM-34/52 name the case Forbidden. A draft answers 404 to every coordinator,
    assigned or not: drafts are private to their organiser (DR-R2)."""
    row = repository.get_event(event_id)
    if not row or row.get("status") == "draft":
        raise EventNotFoundError()
    if row.get("coordinator_id") != coordinator_id:
        raise NotAssignedCoordinatorError()
    return row


def assigned_event(event_id: str, coordinator_id: str) -> dict:
    """The event row for its assigned coordinator, for other modules acting on
    the coordinator's behalf (SCRUM-19's venue booking request, SCRUM-45's
    equipment request). Same answers as every coordinator action here: 404 for a
    missing event or a draft, 403 for a coordinator who isn't assigned."""
    return _assigned_event(event_id, coordinator_id)


def assigned_space(space_id: str, coordinator_id: str) -> tuple[dict, dict]:
    """Return a requested space and its event for the assigned coordinator."""
    space = repository.get_space(space_id)
    if not space:
        raise EventNotFoundError()
    return _assigned_event(space["event_id"], coordinator_id), space


def _transition(row: dict, actor_id: str, action: str, *, reason: str | None,
                notify_type: str, notify_message: str) -> EventResponse:
    to_status = lifecycle.target(action, row["status"])
    updated = repository.transition_event(
        row["id"], actor_id, lifecycle.allowed_from(action), to_status.value, row["version"],
        reason=reason, notify_type=notify_type, notify_message=notify_message,
    )
    if not updated:
        raise EventConflictError(STALE_EVENT_MESSAGE)
    return _to_response(updated)


def _safety_readiness_for(row: dict) -> SafetyReadiness:
    # CR-97 AC10: an event with event spaces is ready only when each space's own
    # booking is; one without any keeps the event-wide rule (Q15).
    if row.get("spaces"):
        by_space = venues_service.booking_readiness_by_space(row["id"])
        spaces = [
            SpaceReadiness(label=space["label"], bookings=by_space.get(space["id"], []))
            for space in row["spaces"]
        ]
        return safety_readiness([], technical_status(row), spaces)
    bookings = venues_service.booking_readiness_by_event([row["id"]]).get(row["id"], [])
    return safety_readiness(bookings, technical_status(row))


def set_primary_space(event_id: str, space_id: str | None, coordinator_id: str) -> EventResponse:
    """CR-97 AC9: the assigned coordinator marks one event space as the primary venue."""
    _assigned_event(event_id, coordinator_id)
    outcome = repository.set_primary_space(event_id, space_id, coordinator_id)
    if outcome == "not_planning":
        raise EventConflictError("The primary venue can only be changed while the event is in planning.")
    if outcome == "space_not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event space not found.")
    if outcome == "not_assigned":
        raise NotAssignedCoordinatorError()
    if outcome == "event_not_found":
        raise EventNotFoundError()
    return read(event_id, coordinator_id, "event_coordinator")


def send_for_safety_check(event_id: str, coordinator_id: str) -> EventResponse:
    row = _assigned_event(event_id, coordinator_id)
    destination = lifecycle.target("send_to_safety", row["status"])
    readiness = _safety_readiness_for(row)
    if not readiness.ready:
        raise EventConflictError("Not ready for safety check: " + " ".join(readiness.missing))
    updated = repository.send_to_safety_review(
        event_id, coordinator_id, lifecycle.allowed_from("send_to_safety"), destination.value, row["version"],
        organiser_message=f'Your event "{row["name"]}" is with the Safety Officer for its operational safety check.',
        officer_message=f'"{row["name"]}" is ready for its operational safety check.',
    )
    if not updated:
        raise EventConflictError(STALE_EVENT_MESSAGE)
    return _to_response(updated)


def approve(event_id: str, coordinator_id: str) -> EventResponse:
    row = _assigned_event(event_id, coordinator_id)
    return _transition(
        row, coordinator_id, "approve", reason=None, notify_type="event_approved",
        notify_message=f'Your event "{row["name"]}" passed its initial review and is now in planning.',
    )


def reject(event_id: str, coordinator_id: str, reason: str) -> EventResponse:
    row = _assigned_event(event_id, coordinator_id)
    return _transition(
        row, coordinator_id, "reject", reason=reason, notify_type="event_rejected",
        notify_message=f'Your event "{row["name"]}" was rejected: {reason}',
    )


def return_for_amendment(event_id: str, coordinator_id: str, body: EventReturnRequest) -> EventResponse:
    row = _assigned_event(event_id, coordinator_id)
    to_status = lifecycle.target("return", row["status"])
    updated = repository.return_event(
        row["id"], coordinator_id, lifecycle.allowed_from("return"), to_status.value, row["version"],
        message=body.message,
        flagged_fields=[field.value for field in body.flagged_fields],
        notify_message=f'Your event "{row["name"]}" was returned for amendment: {body.message}',
    )
    if not updated:
        raise EventConflictError(STALE_EVENT_MESSAGE)
    return _with_amendment(updated)


def resubmit(event_id: str, organiser_id: str, body: EventResubmitRequest) -> EventResponse:
    """Like `submit`: apply the form's edits, check the request is still complete, then
    move it back to its coordinator. Edits that land before a lost race stay saved; the
    event stays returned and the organiser is told to reload."""
    row = _owned_event(event_id, organiser_id)
    to_status = lifecycle.target("resubmit", row["status"])
    values = body.model_dump(mode="json", exclude_unset=True, exclude={"resubmission_note"})
    _validate_submission({**row, **values})
    if values:
        updated = repository.update_event(event_id, values, row["version"])
        if not updated:
            raise EventConflictError(STALE_EVENT_MESSAGE)
        row = updated
    updated = repository.resubmit_event(
        event_id, organiser_id, lifecycle.allowed_from("resubmit"), to_status.value, row["version"],
        note=body.resubmission_note,
        notify_message=f'"{row["name"]}" was amended and resubmitted: {body.resubmission_note}',
    )
    if not updated:
        raise EventConflictError(STALE_EVENT_MESSAGE)
    return _to_response(updated)


def request_cancellation(event_id: str, organiser_id: str, organiser_name: str, reason: str) -> EventChangeRequest:
    """Story 84: record the owner's cancellation request. Nothing is released until the
    coordinator decides (story 115)."""
    row = _owned_event(event_id, organiser_id)
    if row["status"] == EventStatus.draft:
        raise EventConflictError("A draft can't be cancelled. Discard the draft instead.")
    if row["status"] not in lifecycle.cancellation_requestable_from():
        raise EventConflictError(f"Cancellation can't be requested for an event that is {row['status']}.")
    result = repository.request_event_cancellation(
        event_id, organiser_id, reason, lifecycle.cancellation_requestable_from(),
        coordinator_message=f'{organiser_name} requested to cancel "{row["name"]}". Reason: {reason}',
        lead_message=f'Cancellation requested for unassigned event "{row["name"]}".',
    )
    outcome = result["outcome"]
    if outcome in ("not_found", "not_owner"):
        raise EventNotFoundError()
    if outcome == "already_open":
        raise EventConflictError("A cancellation request is already open for this event.")
    if outcome != "ok":
        raise EventConflictError(STALE_EVENT_MESSAGE)
    return EventChangeRequest(**result["request"])


def _refuse_change_request(row: dict) -> None:
    """AC4 and CR-R15: a draft or returned request is edited directly, a closed event
    takes no requests, and nor does one that has started (as CR-R10)."""
    if row["status"] == EventStatus.draft:
        raise EventConflictError("A draft can be edited directly.")
    if row["status"] == EventStatus.returned:
        raise EventConflictError("Edit and resubmit the returned request instead.")
    if row["status"] not in lifecycle.change_requestable_from():
        raise EventConflictError(f"Changes can't be requested for an event that is {row['status']}.")
    if row.get("starts_at") and _parse_datetime(row["starts_at"]) <= datetime.now(timezone.utc):
        raise EventConflictError("This event has already started, so changes can't be requested.")


def _proposed_changes(row: dict, body: ChangeRequestCreate) -> tuple[dict, dict]:
    """CR-R16: the proposal diffed against the stored event and its spaces, and the
    event as it would be with the changes applied."""
    spaces = {space["id"]: space for space in row.get("spaces") or []}
    proposed_spaces = {
        str(space.id): {field: change_fields.trimmed(value)
                        for field, value in space.model_dump(mode="json", exclude_unset=True, exclude={"id"}).items()}
        for space in body.spaces
    }
    if not proposed_spaces.keys() <= spaces.keys():
        raise ChangeRequestInvalidError("One of the spaces is not part of this event.")
    proposed = {field: change_fields.trimmed(value)
                for field, value in body.event.model_dump(mode="json", exclude_unset=True).items()}
    changes = {"event": change_fields.diff(row, proposed), "spaces": []}
    for space_id, values in proposed_spaces.items():
        fields = change_fields.diff(spaces[space_id], values)
        if fields:
            changes["spaces"].append({"space_id": space_id, "label": spaces[space_id]["label"], "fields": fields})
    if not changes["event"] and not changes["spaces"]:
        raise ChangeRequestInvalidError("Change at least one detail.")
    candidate = {**row, **proposed,
                 "spaces": [{**space, **proposed_spaces.get(space["id"], {})} for space in row.get("spaces") or []]}
    return changes, candidate


def _refuse_new_submission_errors(row: dict, candidate: dict) -> None:
    """CR-R19: the changed event must pass the submission rules, but a rule the event
    already breaks (registration that opened yesterday, say) doesn't block the request."""
    existing = {(tuple(error["loc"]), error["msg"]) for error in _submission_errors(row)}
    errors = [error for error in _submission_errors(candidate)
              if (tuple(error["loc"]), error["msg"]) not in existing]
    if not candidate.get("name"):
        errors.append({"loc": ["body", "event", "name"], "msg": "Field required", "type": "missing"})
    if errors:
        raise ChangeRequestInvalidError(errors)


def request_change(event_id: str, organiser_id: str, organiser_name: str,
                   body: ChangeRequestCreate) -> EventChangeRequest:
    """Story 32: record the owner's proposed changes. Nothing changes on the event
    until the coordinator approves them (story 37)."""
    row = _owned_event(event_id, organiser_id)
    _refuse_change_request(row)
    changes, candidate = _proposed_changes(row, body)
    _refuse_new_submission_errors(row, candidate)
    result = repository.request_event_change(
        event_id, organiser_id, body.reason, changes, change_fields.is_significant(changes),
        lifecycle.change_requestable_from(), body.version,
        coordinator_message=(f'{organiser_name} requested changes to "{row["name"]}": '
                             f'{change_fields.describe(changes)}. Reason: {body.reason}'),
        lead_message=f'Changes requested for unassigned event "{row["name"]}".',
    )
    outcome = result["outcome"]
    if outcome in ("not_found", "not_owner"):
        raise EventNotFoundError()
    if outcome == "cancellation_open":
        raise EventConflictError("A cancellation request is open for this event; ask your coordinator "
                                 "to reject it before requesting changes.")
    if outcome == "already_open":
        raise EventConflictError("A change request is already open for this event.")
    if outcome != "ok":
        raise EventConflictError(STALE_EVENT_MESSAGE)
    return EventChangeRequest(**result["request"])


NO_OPEN_CANCELLATION_MESSAGE = "There is no open cancellation request for this event."
EVENT_STARTED_MESSAGE = "This event has already started, so it can't be cancelled."


def _refuse_cancelling_closed_or_started(row: dict) -> None:
    """Story 115 AC4 and LC-R5: a closed event can't be cancelled, and nor can one that
    has started (Q11). A submitted event always has a start time, so a missing one
    fails closed (Q5)."""
    if row["status"] in lifecycle.CANCELLATION_REQUEST_REFUSED:
        raise EventConflictError(f"An event that is {row['status']} can't be cancelled.")
    if row.get("starts_at") is None:
        raise EventConflictError("This event has no start time, so it can't be cancelled.")
    if _parse_datetime(row["starts_at"]) <= datetime.now(timezone.utc):
        raise EventConflictError(EVENT_STARTED_MESSAGE)


def _cancel(row: dict, coordinator_id: str, from_statuses: list[str], reason: str, *,
            require_open_request: bool, organiser_message: str) -> EventResponse:
    """Story 115: the cancellation both approval and direct cancel end in. The RPC
    rechecks everything under the event's lock."""
    name = row["name"]
    result = repository.cancel_event(
        row["id"], coordinator_id, row["version"], from_statuses, reason,
        require_open_request=require_open_request,
        organiser_message=organiser_message,
        staff_message=f'"{name}" was cancelled. Its venue bookings and equipment reservations are released.',
        attendee_message=f'"{name}" has been cancelled. Your registration is cancelled.',
        safety_message=f'"{name}" was cancelled and no longer needs its safety check.',
    )
    outcome = result["outcome"]
    if outcome == "not_found":
        raise EventNotFoundError()
    if outcome == "not_assigned":
        raise NotAssignedCoordinatorError()
    if outcome == "no_open_request":
        raise EventConflictError(NO_OPEN_CANCELLATION_MESSAGE)
    if outcome == "started":
        raise EventConflictError(EVENT_STARTED_MESSAGE)
    if outcome != "ok":
        raise EventConflictError(STALE_EVENT_MESSAGE)
    return _to_response(result["event"])


def approve_cancellation(event_id: str, coordinator_id: str) -> EventResponse:
    """Story 115 AC1: the assigned coordinator approves the organiser's open request."""
    row = _assigned_event(event_id, coordinator_id)
    _refuse_cancelling_closed_or_started(row)
    request = repository.get_open_cancellation_request(event_id)
    if not request:
        raise EventConflictError(NO_OPEN_CANCELLATION_MESSAGE)
    return _cancel(
        row, coordinator_id, lifecycle.cancellation_requestable_from(),
        f"Cancellation approved. Organiser's reason: {request['reason']}",
        require_open_request=True,
        organiser_message=f'Your request to cancel "{row["name"]}" was approved. The event is cancelled.',
    )


def reject_cancellation(event_id: str, coordinator_id: str, reason: str) -> EventResponse:
    """Story 115 AC2: the assigned coordinator rejects the open request with a reason.
    The event keeps its status and its arrangements."""
    row = _assigned_event(event_id, coordinator_id)
    if not repository.get_open_cancellation_request(event_id):
        raise EventConflictError(NO_OPEN_CANCELLATION_MESSAGE)
    result = repository.reject_cancellation_request(
        event_id, coordinator_id, reason,
        organiser_message=f'Your request to cancel "{row["name"]}" was rejected: {reason}',
    )
    outcome = result["outcome"]
    if outcome == "not_found":
        raise EventNotFoundError()
    if outcome == "not_assigned":
        raise NotAssignedCoordinatorError()
    if outcome != "ok":
        raise EventConflictError(NO_OPEN_CANCELLATION_MESSAGE)
    return _to_response(row)


NO_OPEN_CHANGE_MESSAGE = "There is no open change request for this event."
CHANGE_STARTED_MESSAGE = "This event has already started, so its change request can't be decided."


def _refuse_deciding_change(row: dict) -> None:
    """Story 37 AC8 and Q5: a change is decided only where it could be requested
    (CR-R15), and not once the event has started. A missing start fails closed."""
    if row["status"] not in lifecycle.change_requestable_from():
        raise EventConflictError(f"A change request can't be decided on an event that is {row['status']}.")
    if row.get("starts_at") is None or _parse_datetime(row["starts_at"]) <= datetime.now(timezone.utc):
        raise EventConflictError(CHANGE_STARTED_MESSAGE)


def _raise_for_change_outcome(outcome: str) -> None:
    if outcome == "not_found":
        raise EventNotFoundError()
    if outcome == "not_assigned":
        raise NotAssignedCoordinatorError()
    if outcome == "no_open_request":
        raise EventConflictError(NO_OPEN_CHANGE_MESSAGE)
    if outcome == "started":
        raise EventConflictError(CHANGE_STARTED_MESSAGE)
    if outcome != "ok":
        raise EventConflictError(STALE_EVENT_MESSAGE)


CHANGED_SINCE_REQUEST_MESSAGE = "This event has changed since the request was made; reject it and ask for a new one."


def _approved_values(row: dict, changes: dict) -> tuple[dict, dict]:
    """Q8: the request's `after` values, provided every `before` still matches the
    event as stored. Otherwise approving would overwrite a value nobody reviewed."""
    spaces = {space["id"]: space for space in row.get("spaces") or []}
    event_values = {change["field"]: change["after"] for change in changes.get("event") or []}
    stale = change_fields.diff(row, {change["field"]: change["before"] for change in changes.get("event") or []})
    space_values = {}
    for space_change in changes.get("spaces") or []:
        space = spaces.get(space_change["space_id"])
        fields = space_change["fields"]
        if space is None or change_fields.diff(space, {change["field"]: change["before"] for change in fields}):
            stale = True
        space_values[space_change["space_id"]] = {change["field"]: change["after"] for change in fields}
    if stale:
        raise EventConflictError(CHANGED_SINCE_REQUEST_MESSAGE)
    return event_values, space_values


def approve_change(event_id: str, coordinator_id: str, version: int) -> EventResponse:
    """Story 37 AC2, AC4: the assigned coordinator approves the open change request.
    The values are applied as one transaction by the database."""
    row = _assigned_event(event_id, coordinator_id)
    _refuse_deciding_change(row)
    request = repository.get_open_change_request(event_id)
    if not request:
        raise EventConflictError(NO_OPEN_CHANGE_MESSAGE)
    if version != row["version"]:
        raise EventConflictError(STALE_EVENT_MESSAGE)
    event_values, space_values = _approved_values(row, request["changes"])
    candidate = {**row, **event_values,
                 "spaces": [{**space, **space_values.get(space["id"], {})} for space in row.get("spaces") or []]}
    _refuse_new_submission_errors(row, candidate)
    name = row["name"]
    moved = bool(event_values.keys() & {"starts_at", "ends_at", "event_timezone"})
    result = repository.approve_event_change(
        event_id, coordinator_id, version, lifecycle.change_requestable_from(), event_values, space_values,
        organiser_message=f'Your requested changes to "{name}" were approved.',
        history_reason=f"Change approved: {change_fields.describe(request['changes'])}",
        officer_message=f'"{name}" returned to planning. {_RETURN_REASONS["approved_details_changed"]}',
        # RG-R4, Q9: attendees act on a new date or time, not on attendance or layout.
        attendee_message=(f'The date or time of "{name}" has changed. Check the event page for the new time.'
                          if moved else None),
    )
    _raise_for_change_outcome(result["outcome"])
    return _to_response(result["event"])


def reject_change(event_id: str, coordinator_id: str, reason: str) -> EventResponse:
    """Story 37 AC2, AC4: the assigned coordinator rejects the open change request with
    a reason (CR-R3). The event keeps its details, status and arrangements."""
    row = _assigned_event(event_id, coordinator_id)
    _refuse_deciding_change(row)
    if not repository.get_open_change_request(event_id):
        raise EventConflictError(NO_OPEN_CHANGE_MESSAGE)
    result = repository.reject_event_change(
        event_id, coordinator_id, reason, lifecycle.change_requestable_from(),
        organiser_message=f'Your requested changes to "{row["name"]}" were rejected: {reason}',
    )
    _raise_for_change_outcome(result["outcome"])
    return _to_response(row)


def cancel_event(event_id: str, coordinator_id: str, reason: str) -> EventResponse:
    """Story 115 AC3: the assigned coordinator cancels without an organiser request. An
    open request is closed as approved by the same call (Q9)."""
    row = _assigned_event(event_id, coordinator_id)
    _refuse_cancelling_closed_or_started(row)
    lifecycle.target("cancel", row["status"])
    return _cancel(
        row, coordinator_id, lifecycle.allowed_from("cancel"), reason,
        require_open_request=False,
        organiser_message=f'"{row["name"]}" was cancelled by its coordinator. Reason: {reason}',
    )


def _validate_submission(row: dict) -> None:
    errors = _submission_errors(row)
    if errors:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=errors)


def _submission_errors(row: dict) -> list[dict]:
    errors = []
    has_space_requests = bool(row.get("spaces"))
    required_fields = ("purpose", "starts_at", "ends_at")
    if not has_space_requests:
        required_fields += ("expected_attendance", "layout_preference")
    for field in required_fields:
        if row.get(field) in (None, ""):
            errors.append({"loc": ["body", field], "msg": "Field required", "type": "missing"})

    starts_at = row.get("starts_at")
    ends_at = row.get("ends_at")
    event_timezone = ZoneInfo(row.get("event_timezone") or DEFAULT_EVENT_TIMEZONE)
    event_ends_at = None
    if starts_at and ends_at:
        starts_at = _parse_datetime(starts_at)
        ends_at = _parse_datetime(ends_at)
        event_ends_at = ends_at
        if ends_at <= starts_at:
            errors.append({"loc": ["body", "ends_at"], "msg": "End time must be after start time.", "type": "value_error"})
        if starts_at.astimezone(event_timezone).date() <= datetime.now(event_timezone).date():
            errors.append({"loc": ["body", "starts_at"], "msg": "Event date must be after today.", "type": "value_error"})

    for index, space in enumerate(row.get("spaces") or []):
        for field in ("label", "expected_pax", "layout_preference"):
            if space.get(field) in (None, ""):
                errors.append({"loc": ["body", "spaces", index, field], "msg": "Field required", "type": "missing"})
        errors.extend(_space_schedule_errors(space, row, index))

    if row.get("registration_enabled"):
        if not row.get("registration_capacity"):
            errors.append({"loc": ["body", "registration_capacity"], "msg": "Registration capacity is required when registration is enabled.", "type": "value_error"})
        if row.get("registration_opens_at") is None:
            errors.append({"loc": ["body", "registration_opens_at"], "msg": "Registration opening time is required when registration is enabled.", "type": "value_error"})
        if row.get("registration_closes_at") is None:
            errors.append({"loc": ["body", "registration_closes_at"], "msg": "Registration closing time is required when registration is enabled.", "type": "value_error"})
        registration_opens_at = row.get("registration_opens_at")
        registration_closes_at = row.get("registration_closes_at")
        if registration_opens_at and registration_closes_at:
            registration_opens_at = _parse_datetime(registration_opens_at)
            registration_closes_at = _parse_datetime(registration_closes_at)
            if registration_opens_at.astimezone(event_timezone).date() <= datetime.now(event_timezone).date():
                errors.append({"loc": ["body", "registration_opens_at"], "msg": "Registration opening date must be after today.", "type": "value_error"})
            if registration_closes_at <= registration_opens_at:
                errors.append({"loc": ["body", "registration_closes_at"], "msg": "Registration closing time must be after opening time.", "type": "value_error"})
            if registration_closes_at.astimezone(event_timezone).date() <= datetime.now(event_timezone).date():
                errors.append({"loc": ["body", "registration_closes_at"], "msg": "Registration closing date must be after today.", "type": "value_error"})
            if event_ends_at and registration_closes_at > event_ends_at:
                errors.append({"loc": ["body", "registration_closes_at"], "msg": "Registration closing time cannot be after the event end time.", "type": "value_error"})

    return errors


def _parse_datetime(value: datetime | str) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise HTTPException(status_code=422, detail="Date and time values must include a timezone offset.")
    return parsed


def _space_schedule_errors(space: dict, event: dict, index: int) -> list[dict]:
    starts_at = space.get("starts_at")
    ends_at = space.get("ends_at")
    if starts_at is None and ends_at is None:
        return []

    errors = []
    event_starts_at = event.get("starts_at")
    event_ends_at = event.get("ends_at")
    if event_starts_at is None or event_ends_at is None:
        return [{
            "loc": ["body", "spaces", index, "starts_at"],
            "msg": "An individual space schedule requires the event's overall schedule.",
            "type": "value_error",
        }]

    starts_at = _parse_datetime(starts_at)
    ends_at = _parse_datetime(ends_at)
    event_starts_at = _parse_datetime(event_starts_at)
    event_ends_at = _parse_datetime(event_ends_at)
    if starts_at < event_starts_at:
        errors.append({
            "loc": ["body", "spaces", index, "starts_at"],
            "msg": "A space schedule must be within the event's overall schedule.",
            "type": "value_error",
        })
    if ends_at > event_ends_at:
        errors.append({
            "loc": ["body", "spaces", index, "ends_at"],
            "msg": "A space schedule must be within the event's overall schedule.",
            "type": "value_error",
        })
    return errors


def create(organiser_id: str, body: EventCreateRequest) -> EventResponse:
    values = body.model_dump(mode="json", exclude_unset=True)
    return _to_response(repository.create_event(organiser_id, values))


def clone(event_id: str, organiser_id: str) -> EventResponse:
    source = _owned_event(event_id, organiser_id)
    values = {field: source.get(field) for field in CLONE_FIELDS}
    return _to_response(repository.create_event(organiser_id, values))


def list_owned(organiser_id: str) -> list[EventResponse]:
    return [_to_response(row) for row in repository.list_events(organiser_id)]


def _visible_event(event_id: str, user_id: str, role: str) -> dict:
    """Organisers see their own events (404 otherwise); coordinators see the non-draft
    events assigned to them (403 if unassigned, 404 if draft or missing). The router's
    role gate admits no one else."""
    if role == "event_coordinator":
        return _assigned_event(event_id, user_id)
    return _owned_event(event_id, user_id)


def _for_role(booking: dict, role: str) -> dict:
    """The flag and the replacement link are the coordinator's follow-up (CR-95);
    an organiser sees a confirmed event's venue, not what is wrong with it."""
    if role == "event_coordinator":
        return booking
    return {**booking, "flag": None, "flag_reason": None, "replaces_booking_id": None}


@_safety_service_available
def read(event_id: str, user_id: str, role: str = "event_organiser") -> EventResponse:
    row = _visible_event(event_id, user_id, role)
    response = _with_amendment(row)
    open_request = repository.get_open_cancellation_request(event_id)
    if open_request:
        response.open_cancellation_request = EventChangeRequest(**open_request)
    open_change = repository.get_open_change_request(event_id)
    if open_change:
        response.open_change_request = EventChangeRequest(**open_change)
    if role == "event_coordinator" and row["status"] == "planning":
        response.safety_readiness = _safety_readiness_for(row)
    if role == "event_coordinator" or row["status"] == "confirmed":
        booking = venues_service.active_booking_for_event(event_id)
        if booking:
            response.venue_booking = EventVenueBooking(**_for_role(booking, role))
        response.venue_bookings = [
            EventSpaceVenueBooking(**_for_role(booking, role))
            for booking in venues_service.active_bookings_for_event(event_id)
        ]
    if role == "event_coordinator":
        # SCRUM-38 AC6: why venue staff said no, for the coordinator only.
        response.rejected_bookings = [
            EventRejectedBooking(**booking) for booking in venues_service.rejected_bookings_for_event(event_id)
        ]
    eligible = ((role == "event_coordinator" and row["status"] == "planning")
                or (role == "event_organiser" and row["status"] in ("planning", "safety_review", "confirmed")))
    if eligible:
        decisions = repository.list_safety_decisions(event_id)
        if decisions:
            latest = SafetyDecision(**decisions[0])
            if role == "event_coordinator":
                response.latest_safety_decision = _named_decisions(decisions[:1])[0]
            else:
                response.latest_safety_decision = SafetyDecisionSummary(
                    decision=latest.decision, reason_label=_SAFETY_LABELS[latest.decision], decided_at=latest.decided_at,
                )
    return response


def history(event_id: str, user_id: str, role: str) -> EventHistoryResponse:
    _visible_event(event_id, user_id, role)
    entries = [EventHistoryEntry(**row) for row in repository.list_status_history(event_id)]
    entries += [EventHistoryEntry(kind="reassignment", **row) for row in repository.list_assignment_history(event_id)]
    requests = repository.list_cancellation_requests(event_id)
    entries += [
        EventHistoryEntry(kind="cancellation_requested", id=row["id"], actor=row["requested_by"],
                          reason=row["reason"], at=row["requested_at"])
        for row in requests
    ]
    # Story 115 AC6: a rejection is its own entry. An approval is the status change
    # to cancelled, which already carries who and why.
    entries += [
        EventHistoryEntry(kind="cancellation_rejected", id=f"{row['id']}:rejected", actor=row["decided_by"],
                          reason=row["decision_reason"], at=row["decided_at"])
        for row in requests if row.get("status") == "rejected"
    ]
    changes = repository.list_change_requests(event_id)
    entries += [
        EventHistoryEntry(kind="change_requested", id=row["id"], actor=row["requested_by"],
                          reason=row["reason"], changes=row["changes"], at=row["requested_at"])
        for row in changes
    ]
    # 84 AC4 / CR-R18: a superseded request says when and why it closed.
    entries += [
        EventHistoryEntry(kind="change_request_closed", id=f"{row['id']}:closed", actor=row["decided_by"],
                          reason=row["decision_reason"], at=row["decided_at"])
        for row in changes if row.get("status") == "superseded"
    ]
    # Story 37 Q18: each decision is its own entry, with who made it; a rejection says
    # why, and an approval repeats what changed.
    entries += [
        EventHistoryEntry(kind="change_rejected", id=f"{row['id']}:rejected", actor=row["decided_by"],
                          reason=row["decision_reason"], at=row["decided_at"])
        for row in changes if row.get("status") == "rejected"
    ]
    entries += [
        EventHistoryEntry(kind="change_approved", id=f"{row['id']}:approved", actor=row["decided_by"],
                          changes=row["changes"], at=row["decided_at"])
        for row in changes if row.get("status") == "approved"
    ]
    # Stable, so entries sharing a time keep the repository's order (the creation row last).
    entries.sort(key=lambda entry: entry.at, reverse=True)
    return EventHistoryResponse(entries=entries)


def update(event_id: str, organiser_id: str, body: EventUpdateRequest) -> EventResponse:
    row = _owned_event(event_id, organiser_id)
    if row.get("status") not in ("draft", "returned"):
        raise EventConflictError("Only draft or returned events can be edited.")
    values = body.model_dump(mode="json", exclude_unset=True)
    candidate = {**row, **values}
    errors = [
        error
        for index, space in enumerate(candidate.get("spaces") or [])
        for error in _space_schedule_errors(space, candidate, index)
    ]
    if errors:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=errors)
    updated = repository.update_event(event_id, values, row["version"])
    if not updated:
        raise EventConflictError()
    return _with_amendment(updated)


def discard(event_id: str, organiser_id: str) -> None:
    row = _owned_event(event_id, organiser_id)
    if row.get("status") != "draft":
        raise EventConflictError("Only draft events can be discarded.")
    repository.delete_event(event_id)


def submit(event_id: str, organiser_id: str, body: EventUpdateRequest | None = None) -> EventResponse:
    row = _owned_event(event_id, organiser_id)
    if row.get("status") != "draft":
        raise EventConflictError("Only draft events can be submitted.")
    values = body.model_dump(mode="json", exclude_unset=True) if body is not None else {}
    candidate = {**row, **values}
    _validate_submission(candidate)
    if values:
        updated = repository.update_event(event_id, values, row["version"])
        if not updated:
            raise EventConflictError()
        row = updated
    updated = repository.transition_event(
        event_id, organiser_id, lifecycle.allowed_from("submit"),
        lifecycle.target("submit", row["status"]).value, row["version"],
    )
    if not updated:
        raise EventConflictError()
    return _to_response(updated)


def _venue_readiness(booking_statuses: list[str], affected: bool = False) -> ReadinessState:
    # An Affected booking (CR-95) is not ready, even one that was approved.
    if affected:
        return ReadinessState.issue
    # REQUIREMENTS §6.6: the venue is ready once a booking is approved.
    return ReadinessState.ready if "approved" in booking_statuses else ReadinessState.pending


def technical_status(row: dict) -> ReadinessState:
    """Single reader of technical status. The column is SCRUM-24's derived status
    (AC11), kept current by the database whenever a line, the exit tick or the
    venue changes, so reading it is reading the derived value."""
    return ReadinessState(row["technical_readiness"])


def _action_kind(row: dict, resubmitted_at: str | None, venue_affected: bool = False) -> CoordinatorActionKind | None:
    status = row["status"]
    # CR-95 AC3: a venue that became unavailable is the most urgent thing a
    # coordinator can have; the event's status is not changed by it (AC7).
    if venue_affected and status in ("planning", "safety_review", "confirmed"):
        return CoordinatorActionKind.needs_alternative_venue
    if status == "under_review":
        # A resubmission is the organiser's answer to a return (QA-22, QA-77):
        # SCRUM-72's "clarification response", not a first review.
        return CoordinatorActionKind.resubmitted if resubmitted_at else CoordinatorActionKind.awaiting_review
    # REQUIREMENTS §6.21.1: technical status is Issue when tech support marked a
    # line Not available (SCRUM-24 AC11).
    if status in ("planning", "safety_review", "confirmed") and technical_status(row) == ReadinessState.issue:
        return CoordinatorActionKind.arrangement_issue
    # `returned` is waiting on the organiser, not the coordinator.
    return None


def coordinator_dashboard(coordinator_id: str) -> CoordinatorDashboard:
    """Everything the Event Coordinator dashboard shows, in one round trip (SCRUM-72).

    Only events assigned to the caller, never drafts (DR-R2). Action kinds whose
    data doesn't exist yet (change requests, booking and equipment decisions,
    re-review outcomes) are not produced, so their widgets stay empty rather
    than invent anything (REQUIREMENTS §6.21). An open cancellation request
    (story 84) is an item of its own, beside the event's other one. The SPA
    ranks the items, so they are returned unordered.

    The caller's rejected events come back in the same query, listed apart:
    they are closed, so no arrangement or action is looked up for them.
    """
    all_rows = repository.list_coordinator_events(coordinator_id, (*ACTIVE_COORDINATOR_STATUSES, "rejected"))
    rows = [row for row in all_rows if row["status"] != "rejected"]
    rejected_events = [
        CoordinatorRejectedEvent(event_id=row["id"], event_name=row["name"], starts_at=row.get("starts_at"))
        for row in all_rows
        if row["status"] == "rejected"
    ]
    event_ids = [row["id"] for row in rows]
    under_review_ids = [row["id"] for row in rows if row["status"] == "under_review"]

    resubmissions = repository.list_latest_resubmissions(under_review_ids)
    cancellation_requests = repository.list_open_cancellation_requests(event_ids)
    change_requests = repository.list_open_change_requests(event_ids)
    bookings = venues_service.booking_statuses_by_event(event_ids) if event_ids else {}
    affected = venues_service.affected_event_ids(event_ids) if event_ids else set()
    equipment = equipment_service.equipment_readiness_by_event(event_ids) if event_ids else {}

    action_items: list[CoordinatorActionItem] = []
    active_events: list[CoordinatorActiveEvent] = []
    for row in rows:
        resubmitted_at = resubmissions.get(row["id"])
        kind = _action_kind(row, resubmitted_at, row["id"] in affected)
        if kind is not None:
            action_items.append(
                CoordinatorActionItem(
                    event_id=row["id"],
                    event_name=row["name"],
                    kind=kind,
                    starts_at=row.get("starts_at"),
                    occurred_at=resubmitted_at or row.get("submitted_at"),
                    organiser_name=(row.get("organiser") or {}).get("full_name"),
                )
            )
        for open_requests, request_kind in ((cancellation_requests, CoordinatorActionKind.cancellation_request),
                                            (change_requests, CoordinatorActionKind.change_request)):
            if row["id"] in open_requests:
                action_items.append(
                    CoordinatorActionItem(
                        event_id=row["id"],
                        event_name=row["name"],
                        kind=request_kind,
                        starts_at=row.get("starts_at"),
                        occurred_at=open_requests[row["id"]],
                        organiser_name=(row.get("organiser") or {}).get("full_name"),
                    )
                )

        technical = technical_status(row)
        active_events.append(
            CoordinatorActiveEvent(
                event_id=row["id"],
                event_name=row["name"],
                status=row["status"],
                starts_at=row.get("starts_at"),
                flags=(["technical_issue"] if technical is ReadinessState.issue else [])
                + (["venue_affected"] if row["id"] in affected else []),
                readiness=Readiness(
                    venue=_venue_readiness(bookings.get(row["id"], []), row["id"] in affected),
                    equipment=equipment.get(row["id"], ReadinessState.not_required),
                    technical=technical,
                ),
            )
        )

    return CoordinatorDashboard(action_items=action_items, active_events=active_events, rejected_events=rejected_events)


def _lead_event(row: dict) -> LeadEvent:
    return LeadEvent(
        event_id=row["id"],
        event_name=row["name"],
        status=row["status"],
        starts_at=row.get("starts_at"),
        organiser_name=(row.get("organiser") or {}).get("full_name"),
        purpose=row.get("purpose"),
        expected_attendance=row.get("expected_attendance"),
        coordinator=row.get("coordinator"),
        assigned_at=row.get("assigned_at"),
        submitted_at=row.get("submitted_at"),
        layout_preference=row.get("layout_preference"),
        facilities_required=row.get("facilities_required") or [],
        version=row["version"],
    )


def lead_dashboard(lead_id: str) -> LeadDashboard:
    """The Event Coordinator Lead's view (CR-101): the shared unassigned queue plus
    the active events in this Lead's scope (AC5), and each coordinator's active
    count over that scope. Filtering by coordinator and status is the SPA's job."""
    lead_ids = repository.list_lead_ids()
    rows = [
        row
        for row in repository.list_lead_events(("submitted", *ACTIVE_COORDINATOR_STATUSES))
        if lead_scope.in_lead_scope(row, lead_id, lead_ids)
    ]
    counts = lead_scope.active_counts(rows)
    return LeadDashboard(
        unassigned=[
            _lead_event(r)
            for r in sorted(
                (r for r in rows if r.get("coordinator_id") is None),
                key=lambda r: r.get("submitted_at") or "",
            )
        ],
        active_events=[_lead_event(r) for r in rows if r.get("coordinator_id") is not None],
        coordinators=[
            LeadCoordinator(id=c["id"], full_name=c["full_name"], active_count=counts.get(c["id"], 0))
            for c in repository.list_coordinators()
        ],
    )


ALREADY_ASSIGNED_MESSAGE = "This event is already assigned."


def assign(event_id: str, lead_id: str, coordinator_id: str) -> EventResponse:
    """A Lead assigns a coordinator to a queued event (SCRUM-12). Only a `submitted` event
    can be assigned here; changing an assignment is `reassign` (story 81). The database
    repeats the status check under a lock, so of two simultaneous assignments one wins."""
    row = repository.get_lead_event(event_id)
    if not row or row.get("status") == "draft":
        raise EventNotFoundError()
    if row.get("coordinator_id") is not None or row["status"] in ACTIVE_COORDINATOR_STATUSES:
        raise EventConflictError(ALREADY_ASSIGNED_MESSAGE)
    target_status = lifecycle.target("assign", row["status"])
    target = repository.get_coordinator(coordinator_id)
    if target is None:
        raise CoordinatorNotEligibleError()
    name = row["name"]
    updated = repository.assign_event(
        event_id, lead_id, coordinator_id,
        from_statuses=lifecycle.allowed_from("assign"),
        to_status=target_status.value,
        reason=f"Assigned to {target['full_name']}",
        notify_assigned=f'"{name}" has been assigned to you.',
        notify_organiser=f'Your event "{name}" is now coordinated by {target["full_name"]}.',
    )
    if not updated:
        raise EventConflictError(ALREADY_ASSIGNED_MESSAGE)
    return _to_response(updated)


def reassign(event_id: str, lead_id: str, coordinator_id: str, expected_version: int) -> EventResponse:
    """A Lead (re)assigns an event in their scope to a coordinator (CR-101 AC3).
    Story 81 builds on this; the update, history and notices are one RPC."""
    row = repository.get_lead_event(event_id)
    if not row or row.get("status") == "draft":
        raise EventNotFoundError()
    if row["status"] not in ACTIVE_COORDINATOR_STATUSES:
        raise EventConflictError(f"Cannot reassign an event that is {row['status'].replace('_', ' ')}")
    if not lead_scope.in_lead_scope(row, lead_id, repository.list_lead_ids()):
        raise EventNotInLeadScopeError()
    target = repository.get_coordinator(coordinator_id)
    if target is None:
        raise CoordinatorNotEligibleError()
    if row["version"] != expected_version:
        raise EventConflictError(STALE_EVENT_MESSAGE)
    if row.get("coordinator_id") == coordinator_id:
        raise EventConflictError("This event is already assigned to that coordinator.")
    name = row["name"]
    updated = repository.reassign_event(
        event_id, lead_id, coordinator_id, row["version"],
        active_statuses=list(ACTIVE_COORDINATOR_STATUSES),
        notify_assigned=f'"{name}" has been assigned to you.',
        notify_previous=f'"{name}" has been reassigned to {target["full_name"]}.',
        notify_organiser=f'Your event "{name}" is now coordinated by {target["full_name"]}.',
    )
    if not updated:
        raise EventConflictError(STALE_EVENT_MESSAGE)
    return _to_response(updated)


def _comment_role(event: dict, author_id: str | None) -> str | None:
    """The role an author holds on this event. None for someone no longer on it,
    such as a coordinator since reassigned."""
    if author_id and author_id == event.get("organiser_id"):
        return "event_organiser"
    if author_id and author_id == event.get("coordinator_id"):
        return "event_coordinator"
    return None


def _to_comment(event: dict, row: dict) -> EventComment:
    author = row.get("author")
    if author:
        author = {**author, "role": _comment_role(event, author.get("id"))}
    return EventComment(id=row["id"], body=row["body"], created_at=row["created_at"], author=author)


def comments(event_id: str, user_id: str, role: str) -> EventCommentsResponse:
    """The discussion thread (SCRUM-61), visible to the same people as the event."""
    event = _visible_event(event_id, user_id, role)
    if event["status"] == EventStatus.draft.value:
        return EventCommentsResponse(comments=[])
    return EventCommentsResponse(comments=[_to_comment(event, row) for row in repository.list_comments(event_id)])


def add_comment(event_id: str, user_id: str, role: str, full_name: str, body: str) -> EventComment:
    """`full_name` is the caller's, from their verified profile (`CurrentUser`). Nothing after
    the RPC reads the database: by then the comment and its notification are committed, and a
    failed read would report a saved comment as failed, inviting a duplicate retry."""
    event = _visible_event(event_id, user_id, role)
    event_status = EventStatus(event["status"])
    if event_status == EventStatus.draft:
        raise EventConflictError("Comments open once the request is submitted.")
    if event_status not in COMMENTABLE_STATUSES:
        raise EventConflictError(f"Comments are closed for a {event_status.value.replace('_', ' ')} event.")
    who = "The organiser" if role == "event_organiser" else "Your coordinator"
    row = repository.add_comment(
        event_id, user_id, body, notify_message=f'{who} commented on "{event["name"]}".',
    )
    if not row:
        raise EventConflictError("Comments are closed for this event. Reload.")
    return _to_comment(event, {**row, "author": {"id": user_id, "full_name": full_name}})


_RETURN_REASONS = {
    "arrangement_flagged": "An arrangement was flagged for re-review.",
    "booking_cancelled": "A venue booking was cancelled.",
    "technical_not_ready": "Technical status is no longer Ready.",
    "approved_details_changed": "Approved event details changed.",
}


@_safety_service_available
def return_to_planning(event_id: str, *, reason_code: ReturnReason, message: str | None = None,
                       actor_id: str | None = None) -> EventResponse | None:
    """Return arrangements to planning, or None if no longer applicable/stale.

    `message` is caller audit context only: never stored or sent. `actor_id` is
    accepted for interface stability; the RPC records a system action instead.
    No callers are wired until their owning stories land (CR-104 AC6/AC10).
    """
    row = repository.get_event(event_id)
    if not row or row["status"] not in ("safety_review", "confirmed"):
        return None
    action = "safety_withdraw" if row["status"] == "safety_review" else "approved_change"
    lifecycle.target(action, row["status"])
    reason = ReturnReason(reason_code)
    fixed = f'"{row["name"]}" returned to planning. {_RETURN_REASONS[reason]}'
    updated = repository.return_to_planning(
        event_id, row["version"], from_status=lifecycle.allowed_from(action)[0], reason_code=reason.value,
        coordinator_message=fixed, officer_message=fixed if action == "safety_withdraw" else None,
    )
    return _to_response(updated) if updated else None


_SAFETY_LABELS = {
    "approved": "Approved by the Safety Officer.",
    "changes_requested": "The Safety Officer asked for changes to the arrangements.",
    "arrangement_rejected": "The Safety Officer rejected a venue for this event; its booking is flagged Safety rejected.",
    "withdrawn": "An arrangement changed, so the event went back to planning.",
}


def _officer_event(event_id: str) -> dict:
    row = repository.get_event(event_id)
    if not row or row["status"] == "draft":
        raise EventNotFoundError()
    return row


def _check_approval_readiness(row: dict) -> None:
    readiness = _safety_readiness_for(row)
    if not readiness.ready:
        raise EventConflictError("Not ready for approval: " + " ".join(readiness.missing))


@_safety_service_available
def safety_approve(event_id: str, officer_id: str, body: SafetyApproveRequest | None = None) -> EventResponse:
    row = _officer_event(event_id)
    lifecycle.target("safety_approve", row["status"])
    _check_approval_readiness(row)
    message = f'"{row["name"]}": {_SAFETY_LABELS["approved"]}'
    updated = repository.safety_approve(
        event_id, officer_id, row["version"], comment=body.comment if body else None,
        organiser_message=message, staff_message=message,
    )
    if not updated:
        _check_approval_readiness(repository.get_event(event_id) or row)
        raise EventConflictError(STALE_EVENT_MESSAGE)
    return _to_response(updated)


SAFETY_REJECT_REFUSED_MESSAGE = "This venue booking can't be rejected: it must be approved and not already flagged, or the event changed. Reload and try again."


def _safety_return(event_id: str, officer_id: str, body, action: str, decision: str, comment: str) -> EventResponse:
    row = _officer_event(event_id)
    lifecycle.target(action, row["status"])
    booking_ids = [str(body.booking_id)] if decision == "arrangement_rejected" else [str(id) for id in body.booking_ids]
    equipment_ids = [] if decision == "arrangement_rejected" else [str(id) for id in body.equipment_request_ids]
    if (set(booking_ids) - venues_service.event_booking_ids(event_id)
            or set(equipment_ids) - equipment_service.event_request_ids(event_id)):
        raise UnknownEventArrangementError()
    updated = repository.safety_return(
        event_id, officer_id, row["version"], decision=decision, comment=comment,
        booking_ids=booking_ids, equipment_request_ids=equipment_ids,
        coordinator_message=f'"{row["name"]}": {_SAFETY_LABELS[decision]}',
    )
    if not updated:
        raise EventConflictError(SAFETY_REJECT_REFUSED_MESSAGE if decision == "arrangement_rejected" else STALE_EVENT_MESSAGE)
    return _to_response(updated)


@_safety_service_available
def safety_request_changes(event_id: str, officer_id: str, body: SafetyChangesRequest) -> EventResponse:
    return _safety_return(event_id, officer_id, body, "safety_request_changes", "changes_requested", body.comment)


@_safety_service_available
def safety_reject(event_id: str, officer_id: str, body: SafetyRejectRequest) -> EventResponse:
    return _safety_return(event_id, officer_id, body, "safety_reject", "arrangement_rejected", body.reason)


@_safety_service_available
def safety_queue() -> SafetyQueueResponse:
    items = [SafetyQueueItem(**row) for row in repository.list_safety_queue()]
    items.sort(key=lambda item: (item.entered_review_at, item.event_id))
    return SafetyQueueResponse(items=items)


SAFETY_HISTORY_DAYS = 30


@_safety_service_available
def safety_history() -> SafetyHistoryResponse:
    """Every decision in the last 30 days, newest first, for the officers' dashboard (CR-103 AC7)."""
    since = datetime.now(timezone.utc) - timedelta(days=SAFETY_HISTORY_DAYS)
    rows = repository.list_recent_safety_decisions(since)
    items = [SafetyHistoryItem(**{**row, **decision.model_dump()})
             for row, decision in zip(rows, _named_decisions(rows))]
    items.sort(key=lambda item: (item.decided_at, str(item.id)), reverse=True)
    return SafetyHistoryResponse(items=items)


@_safety_service_available
def safety_decisions(event_id: str, user_id: str, role: str) -> list[SafetyDecision]:
    if role == "event_coordinator":
        _assigned_event(event_id, user_id)
    elif role == "safety_officer":
        _officer_event(event_id)
    else:
        raise NotAssignedCoordinatorError()
    return _named_decisions(repository.list_safety_decisions(event_id))


@_safety_service_available
def safety_review(event_id: str) -> SafetyReviewResponse:
    row = _officer_event(event_id)
    if row["status"] != "safety_review":
        raise EventNotFoundError()
    attendance = row.get("expected_attendance")
    venues = []
    for booking in venues_service.event_bookings_with_venues(event_id):
        capacity = booking.get("capacity")
        venues.append({**booking, "attendance_to_capacity": attendance / capacity if attendance is not None and capacity else None})
    return SafetyReviewResponse(
        event=dict(id=row["id"], name=row["name"], organiser_name=(row.get("organiser") or {}).get("full_name"),
                   coordinator_name=(row.get("coordinator") or {}).get("full_name"),
                   starts_at=row.get("starts_at"), ends_at=row.get("ends_at"), expected_attendance=attendance,
                   accessibility_needs=row.get("accessibility_needs"),
                   registration=dict(enabled=row["registration_enabled"], capacity=row.get("registration_capacity"),
                                     opens_at=row.get("registration_opens_at"), closes_at=row.get("registration_closes_at"))),
        venues=venues, equipment_lines=equipment_service.event_lines(event_id),
        exit_confirmation=equipment_service.exit_confirmation(event_id),
        decisions=_named_decisions(repository.list_safety_decisions(event_id)),
    )


def _named_decisions(rows: list[dict]) -> list[SafetyDecision]:
    """D53/D54: batch names and attach the first response after each rejection."""
    booking_ids = sorted({str(id) for row in rows for id in row.get("affected_booking_ids", [])})
    venue_ids = sorted({str(id) for row in rows for id in row.get("rejected_venue_ids", [])})
    line_ids = sorted({str(id) for row in rows for id in row.get("affected_equipment_request_ids", [])})
    bookings = venues_service.booking_venue_names(booking_ids)
    venues = venues_service.venue_names(venue_ids)
    lines = equipment_service.line_names(line_ids)
    revisions = venues_service.safety_revisions(booking_ids)
    decisions = []
    for row in rows:
        data = {
            **row,
            "affected_bookings": [{"booking_id": id, "venue_name": bookings.get(str(id))}
                                  for id in row.get("affected_booking_ids", [])],
            "affected_equipment": [{"id": id, "equipment_name": lines.get(str(id))}
                                   for id in row.get("affected_equipment_request_ids", [])],
            "rejected_venues": [{"venue_id": id, "venue_name": venues.get(str(id))}
                                for id in row.get("rejected_venue_ids", [])],
            "revision": None,
        }
        if row["decision"] == "arrangement_rejected":
            rejected_ids = {str(id) for id in row.get("affected_booking_ids", [])}
            decided_at = SafetyDecision(**row).decided_at
            candidates = [revision for revision in revisions
                          if revision["booking_id"] in rejected_ids
                          and datetime.fromisoformat(revision["at"]) > decided_at]
            if candidates:
                # A legacy revision without a note ends this rejection cycle too.
                # Never borrow a response from a later rejection of the same booking.
                first = min(candidates, key=lambda revision: datetime.fromisoformat(revision["at"]))
                if first["note"] is not None:
                    data["revision"] = first
        decisions.append(SafetyDecision(**data))
    return decisions
