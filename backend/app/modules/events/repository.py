from collections.abc import Iterable
from datetime import datetime

from app.db.supabase import get_supabase_admin_client

_EVENT_COLUMNS = (
    "id, organiser_id, coordinator_id, status, name, event_timezone, purpose, description, starts_at, ends_at, "
    "expected_attendance, layout_preference, facilities_required, accessibility_needs, "
    "preliminary_equipment_needs, registration_enabled, registration_capacity, "
    "registration_opens_at, registration_closes_at, withdrawal_closes_at, technical_readiness, submitted_at, "
    "version, created_at, updated_at"
)
_SPACE_COLUMNS = "id, event_id, label, expected_pax, layout_preference, facilities_required, starts_at, ends_at, version, is_primary"


def list_event_spaces(event_id: str) -> list[dict]:
    response = (
        get_supabase_admin_client()
        .table("event_space_requests")
        .select(_SPACE_COLUMNS)
        .eq("event_id", event_id)
        # First space first, the same order populate_booking_space_request uses.
        .order("created_at")
        .order("id")
        .execute()
    )
    return response.data or []


def create_space(event_id: str, values: dict) -> dict:
    response = (
        get_supabase_admin_client()
        .table("event_space_requests")
        .insert({**values, "event_id": event_id})
        .select(_SPACE_COLUMNS)
        .execute()
    )
    return response.data[0] if isinstance(response.data, list) else response.data


def update_space(space_id: str, values: dict, version: int) -> dict | None:
    response = (
        get_supabase_admin_client()
        .table("event_space_requests")
        .update({**values, "version": version + 1})
        .eq("id", space_id)
        .eq("version", version)
        .select(_SPACE_COLUMNS)
        .execute()
    )
    if not response or not response.data:
        return None
    return response.data[0] if isinstance(response.data, list) else response.data


def delete_space(space_id: str, version: int) -> bool:
    response = (
        get_supabase_admin_client()
        .table("event_space_requests")
        .delete()
        .eq("id", space_id)
        .eq("version", version)
        .execute()
    )
    return bool(response and response.data)


def get_space(space_id: str) -> dict | None:
    response = (
        get_supabase_admin_client()
        .table("event_space_requests")
        .select(_SPACE_COLUMNS)
        .eq("id", space_id)
        .maybe_single()
        .execute()
    )
    return response.data if response else None


def _with_spaces(row: dict | None) -> dict | None:
    if row is None:
        return None
    # Keep narrow repository-unit fixtures that return only the updated fields
    # focused on the event write itself; full event rows carry status.
    if "status" not in row:
        return row
    return {**row, "spaces": list_event_spaces(row["id"])}


def list_events(organiser_id: str) -> list[dict]:
    response = (
        get_supabase_admin_client()
        .table("events")
        .select(_EVENT_COLUMNS)
        .eq("organiser_id", organiser_id)
        .order("updated_at", desc=True)
        .execute()
    )
    return [_with_spaces(row) for row in response.data or []]


# SCRUM-72: the coordinator dashboard's reads. The organiser is embedded through
# the named FK: `events` points at `profiles` twice (organiser and coordinator),
# so a bare `profiles(...)` embed fails the whole query with PGRST201.
_COORDINATOR_DASHBOARD_COLUMNS = (
    "id, name, status, starts_at, submitted_at, technical_readiness, preliminary_equipment_needs, "
    "organiser:profiles!events_organiser_id_fkey(full_name), spaces:event_space_requests(id, label)"
)


def list_coordinator_events(coordinator_id: str, statuses: Iterable[str]) -> list[dict]:
    response = (
        get_supabase_admin_client()
        .table("events")
        .select(_COORDINATOR_DASHBOARD_COLUMNS)
        .eq("coordinator_id", coordinator_id)
        .in_("status", list(statuses))
        .execute()
    )
    return response.data or []


def list_latest_resubmissions(event_ids: Iterable[str]) -> dict[str, str]:
    """`{event_id: resubmitted_at}` of each event's most recent answered amendment."""
    ids = list(event_ids)
    if not ids:
        return {}
    response = (
        get_supabase_admin_client()
        .table("amendment_requests")
        .select("event_id, resubmitted_at")
        .in_("event_id", ids)
        .not_.is_("resubmitted_at", "null")
        .order("resubmitted_at", desc=True)
        .execute()
    )
    latest: dict[str, str] = {}
    for row in response.data or []:
        latest.setdefault(row["event_id"], row["resubmitted_at"])
    return latest


def list_open_cancellation_requests(event_ids: Iterable[str]) -> dict[str, str]:
    """Story 84: `{event_id: requested_at}` of each event's open cancellation request
    (at most one per event, CR-R1), for the coordinator dashboard."""
    return _list_open_requests(event_ids, "cancellation")


def list_open_change_requests(event_ids: Iterable[str]) -> dict[str, str]:
    """Story 32: the same for open change requests."""
    return _list_open_requests(event_ids, "change")


def _list_open_requests(event_ids: Iterable[str], kind: str) -> dict[str, str]:
    ids = list(event_ids)
    if not ids:
        return {}
    response = (
        get_supabase_admin_client()
        .table("event_change_requests")
        .select("event_id, requested_at")
        .in_("event_id", ids)
        .eq("kind", kind)
        .eq("status", "open")
        .execute()
    )
    return {row["event_id"]: row["requested_at"] for row in response.data or []}


def list_event_names(event_ids: Iterable[str]) -> dict[str, str]:
    """`{event_id: name}` for the ids given, skipping any that no longer exist.

    Only the two columns are read: this serves other modules that hold an
    `event_id` and need a label, not the full event record.
    """
    ids = sorted({str(event_id) for event_id in event_ids if event_id})
    if not ids:
        return {}
    response = get_supabase_admin_client().table("events").select("id, name").in_("id", ids).execute()
    return {row["id"]: row["name"] for row in response.data or []}


def list_spaces_by_ids(space_ids: Iterable[str]) -> list[dict]:
    """The requirement fields of the spaces given (CR-94): expected pax,
    preferred layout and required facilities. Skips any id that no longer exists."""
    ids = sorted({str(space_id) for space_id in space_ids if space_id})
    if not ids:
        return []
    response = (
        get_supabase_admin_client()
        .table("event_space_requests")
        .select("id, expected_pax, layout_preference, facilities_required")
        .in_("id", ids)
        .execute()
    )
    return response.data or []


def list_planning_context(event_ids: Iterable[str]) -> list[dict]:
    """The event fields another module needs to judge an event's requirements
    (SCRUM-63): name, status, assigned coordinator, expected attendance,
    preferred layout, required facilities and accessibility needs (SCRUM-38).
    Skips any id that no longer exists.
    """
    ids = sorted({str(event_id) for event_id in event_ids if event_id})
    if not ids:
        return []
    response = (
        get_supabase_admin_client()
        .table("events")
        .select("id, name, status, coordinator_id, expected_attendance, layout_preference, facilities_required, "
                "accessibility_needs")
        .in_("id", ids)
        .execute()
    )
    return response.data or []


# The single-event read also names the assigned coordinator for the organiser's
# page, and the organiser and their organisation for the coordinator's (SCRUM-49
# AC3). The FKs are named because `events` references `profiles` twice, and a bare
# `profiles(...)` embed fails the whole query with PGRST201.
_EVENT_READ_COLUMNS = (_EVENT_COLUMNS + ", coordinator:profiles!events_coordinator_id_fkey(id, full_name)"
                       + ", organiser:profiles!events_organiser_id_fkey(full_name, organisation_name)"
                       # CR-110 AC4: the shape equipment.service.technical_preparation reads.
                       + ", preparation_record:event_technical_preparation(stage, note, updated_at, "
                       "updater:profiles!event_technical_preparation_updated_by_fkey(full_name))")


def get_event(event_id: str) -> dict | None:
    response = (
        get_supabase_admin_client()
        .table("events")
        .select(_EVENT_READ_COLUMNS)
        .eq("id", event_id)
        .maybe_single()
        .execute()
    )
    return _with_spaces(response.data if response else None)


def create_event(organiser_id: str, values: dict) -> dict:
    response = (
        get_supabase_admin_client()
        .table("events")
        .insert({**values, "organiser_id": organiser_id, "status": "draft"})
        .select(_EVENT_COLUMNS)
        .execute()
    )
    if isinstance(response.data, list):
        return _with_spaces(response.data[0])
    return _with_spaces(response.data)


def update_event(event_id: str, values: dict, version: int) -> dict:
    response = (
        get_supabase_admin_client()
        .table("events")
        .update({**values, "version": version + 1})
        .eq("id", event_id)
        .eq("version", version)
        .select(_EVENT_COLUMNS)
        .execute()
    )
    if not response or not response.data:
        return None
    return _with_spaces(response.data[0] if isinstance(response.data, list) else response.data)


def edit_event(event_id: str, actor_id: str, values: dict, version: int, from_statuses: list[str]) -> dict | None:
    """Story 62 AC1: saves the edit and records each changed field in one transaction,
    unless the event is a draft. None when the version or status has moved on."""
    response = get_supabase_admin_client().rpc("edit_event", {
        "p_event_id": event_id,
        "p_actor_id": actor_id,
        "p_values": values,
        "p_expected_version": version,
        "p_from_statuses": from_statuses,
    }).execute()
    rows = (response.data or []) if response else []
    if not rows:
        return None
    # The same shape as update_event's select.
    columns = [column.strip() for column in _EVENT_COLUMNS.split(",")]
    return _with_spaces({column: rows[0].get(column) for column in columns})


def delete_event(event_id: str) -> None:
    get_supabase_admin_client().table("events").delete().eq("id", event_id).execute()


def transition_event(
    event_id: str,
    actor_id: str,
    from_statuses: list[str],
    to_status: str,
    expected_version: int,
    reason: str | None = None,
    notify_type: str | None = None,
    notify_message: str | None = None,
) -> dict | None:
    """Run `public.transition_event`: status, history, hold release and notification in
    one transaction. Returns the updated row, or None when the event had moved on
    (another version or status), which the service reports as 409."""
    response = (
        get_supabase_admin_client()
        .rpc(
            "transition_event",
            {
                "p_event_id": event_id,
                "p_actor_id": actor_id,
                "p_from_statuses": from_statuses,
                "p_to_status": to_status,
                "p_expected_version": expected_version,
                "p_reason": reason,
                "p_notify_type": notify_type,
                "p_notify_message": notify_message,
            },
        )
        .execute()
    )
    rows = response.data or [] if response else []
    return rows[0] if rows else None


def request_event_cancellation(
    event_id: str,
    actor_id: str,
    reason: str,
    from_statuses: list[str],
    coordinator_message: str,
    lead_message: str,
) -> dict:
    """Story 84: run `public.request_event_cancellation` under the event's lock. It
    records the request, supersedes an open change request (CR-R1) and notifies the
    assigned coordinator, or every Lead while the event is unassigned. Answers
    `{outcome, request}`: ok / not_found / not_owner / status_changed / already_open."""
    response = get_supabase_admin_client().rpc("request_event_cancellation", {
        "p_event_id": event_id,
        "p_actor_id": actor_id,
        "p_reason": reason,
        "p_from_statuses": from_statuses,
        "p_coordinator_message": coordinator_message,
        "p_lead_message": lead_message,
    }).execute()
    return response.data


def request_reassignment(
    event_id: str,
    actor_id: str,
    reason: str,
    active_statuses: list[str],
    lead_message: str,
) -> dict:
    """CR-106: run `public.request_reassignment` under the event's lock. It records the
    coordinator's request and notifies the Lead whose scope holds the event, or every
    Lead if none does, without touching the assignment. Answers `{outcome, request}`:
    ok / not_found / not_assigned / status_changed / already_open."""
    response = get_supabase_admin_client().rpc("request_reassignment", {
        "p_event_id": event_id,
        "p_actor_id": actor_id,
        "p_reason": reason,
        "p_active_statuses": active_statuses,
        "p_lead_message": lead_message,
    }).execute()
    return response.data


def decline_reassignment_request(
    event_id: str,
    lead_id: str,
    reason: str,
    coordinator_message: str,
) -> dict:
    """CR-106 AC5: run `public.decline_reassignment_request` under the event's lock. It closes
    the open request as declined with the Lead's reason and notifies the coordinator. Answers
    `{outcome, request}`: ok / not_found / no_open_request."""
    response = get_supabase_admin_client().rpc("decline_reassignment_request", {
        "p_event_id": event_id,
        "p_lead_id": lead_id,
        "p_reason": reason,
        "p_coordinator_message": coordinator_message,
    }).execute()
    return response.data


def request_event_change(
    event_id: str,
    actor_id: str,
    reason: str,
    changes: dict,
    significant: bool,
    from_statuses: list[str],
    expected_version: int,
    coordinator_message: str,
    lead_message: str,
) -> dict:
    """Story 32: run `public.request_event_change` under the event's lock. It records
    the change request and notifies the assigned coordinator, or every Lead while the
    event is unassigned. Answers `{outcome, request}`: ok / not_found / not_owner /
    status_changed / stale / cancellation_open / already_open."""
    response = get_supabase_admin_client().rpc("request_event_change", {
        "p_event_id": event_id,
        "p_actor_id": actor_id,
        "p_reason": reason,
        "p_changes": changes,
        "p_significant": significant,
        "p_from_statuses": from_statuses,
        "p_expected_version": expected_version,
        "p_coordinator_message": coordinator_message,
        "p_lead_message": lead_message,
    }).execute()
    return response.data


def cancel_event(
    event_id: str,
    actor_id: str,
    expected_version: int,
    from_statuses: list[str],
    reason: str,
    require_open_request: bool,
    organiser_message: str,
    staff_message: str,
    attendee_message: str,
    safety_message: str,
) -> dict:
    """Story 115: run `public.cancel_event` under the event's lock. It cancels the event,
    closes an open cancellation request as approved, releases its venue bookings,
    equipment and registrations, and notifies everyone involved, in one transaction.
    Answers `{outcome, event}`: ok / not_found / not_assigned / status_changed /
    no_open_request / started."""
    response = get_supabase_admin_client().rpc("cancel_event", {
        "p_event_id": event_id,
        "p_actor_id": actor_id,
        "p_expected_version": expected_version,
        "p_from_statuses": from_statuses,
        "p_reason": reason,
        "p_require_open_request": require_open_request,
        "p_organiser_message": organiser_message,
        "p_staff_message": staff_message,
        "p_attendee_message": attendee_message,
        "p_safety_message": safety_message,
    }).execute()
    return response.data


def reject_cancellation_request(event_id: str, actor_id: str, reason: str, organiser_message: str) -> dict:
    """Story 115 AC2: run `public.reject_cancellation_request` under the event's lock. It
    closes the open request as rejected with the reason and notifies the organiser; the
    event keeps its status. Answers `{outcome}`: ok / not_found / not_assigned /
    no_open_request."""
    response = get_supabase_admin_client().rpc("reject_cancellation_request", {
        "p_event_id": event_id,
        "p_actor_id": actor_id,
        "p_reason": reason,
        "p_organiser_message": organiser_message,
    }).execute()
    return response.data


def approve_event_change(event_id: str, actor_id: str, expected_version: int, from_statuses: list[str],
                         event_values: dict, space_values: dict, organiser_message: str,
                         history_reason: str, officer_message: str, attendee_message: str | None,
                         booking_plans: list[dict], staff_again_message: str) -> dict:
    """Story 37 AC2: run `public.approve_event_change` under the event's lock. It applies
    the changed event and space values, bumps the version, closes the request as
    approved and notifies the organiser. A significant change returns a Confirmed,
    Preparation or Safety review event to Planning, recorded with `history_reason`,
    and the Safety Officers hear of it (`officer_message`); registered attendees hear
    `attendee_message` unless it is None. `booking_plans` says what the change does to
    each booking (`change_impact.BookingPlan`); each move is re-checked for conflicts
    under the booking's lock; venue staff hear `staff_again_message` for a booking
    already under re-review that the change touches (Q22). Answers `{outcome, event}`: ok / not_found /
    not_assigned / status_changed / started / stale / no_open_request."""
    response = get_supabase_admin_client().rpc("approve_event_change", {
        "p_event_id": event_id,
        "p_actor_id": actor_id,
        "p_expected_version": expected_version,
        "p_from_statuses": from_statuses,
        "p_event_values": event_values,
        "p_space_values": space_values,
        "p_organiser_message": organiser_message,
        "p_history_reason": history_reason,
        "p_officer_message": officer_message,
        "p_attendee_message": attendee_message,
        "p_bookings": booking_plans,
        "p_staff_again_message": staff_again_message,
    }).execute()
    return response.data


def reject_event_change(event_id: str, actor_id: str, reason: str, from_statuses: list[str],
                        organiser_message: str) -> dict:
    """Story 37 AC2: run `public.reject_event_change` under the event's lock. It closes
    the open change request as rejected with the reason and notifies the organiser; the
    event keeps its details and status. Answers `{outcome}`: ok / not_found /
    not_assigned / status_changed / started / no_open_request."""
    response = get_supabase_admin_client().rpc("reject_event_change", {
        "p_event_id": event_id,
        "p_actor_id": actor_id,
        "p_reason": reason,
        "p_from_statuses": from_statuses,
        "p_organiser_message": organiser_message,
    }).execute()
    return response.data


def list_status_history(event_id: str) -> list[dict]:
    """Newest first. The actor is embedded through the FK named in the migration.
    On a timestamp tie the creation row (no from_status) sorts last, since
    nothing can precede an event's creation."""
    response = (
        get_supabase_admin_client()
        .table("event_status_history")
        .select("id, from_status, to_status, reason, at, actor:profiles!event_status_history_actor_id_fkey(id, full_name)")
        .eq("event_id", event_id)
        .order("at", desc=True)
        .order("from_status", desc=True, nullsfirst=False)
        .execute()
    )
    return response.data or []


def list_assignment_history(event_id: str) -> list[dict]:
    """Reassignments, newest first, with the Lead and both coordinators named (SCRUM-12).
    Kept apart from the status history because a reassignment is not a status change."""
    response = (
        get_supabase_admin_client()
        .table("event_assignment_history")
        .select(
            "id, at, "
            "actor:profiles!event_assignment_history_actor_id_fkey(id, full_name), "
            "from_coordinator:profiles!event_assignment_history_from_coordinator_id_fkey(id, full_name), "
            "to_coordinator:profiles!event_assignment_history_to_coordinator_id_fkey(id, full_name)"
        )
        .eq("event_id", event_id)
        .order("at", desc=True)
        .execute()
    )
    return response.data or []


def list_edit_history(event_id: str) -> list[dict]:
    """Story 62 AC1: each recorded field edit, newest first, with who made it."""
    response = (
        get_supabase_admin_client()
        .table("event_edit_history")
        .select("id, field, old_value, new_value, at, actor:profiles!event_edit_history_actor_id_fkey(id, full_name)")
        .eq("event_id", event_id)
        .order("at", desc=True)
        .execute()
    )
    return response.data or []


def _first_row(response) -> dict | None:
    rows = (response.data or []) if response else []
    return rows[0] if rows else None


def return_event(
    event_id: str,
    actor_id: str,
    from_statuses: list[str],
    to_status: str,
    expected_version: int,
    *,
    message: str,
    flagged_fields: list[str],
    notify_message: str,
) -> dict | None:
    """Run `public.return_event_for_amendment` (SCRUM-33): the transition, its history
    row, the organiser's notification and the amendment row in one transaction.
    None when the event had moved on, which the service reports as 409."""
    response = (
        get_supabase_admin_client()
        .rpc(
            "return_event_for_amendment",
            {
                "p_event_id": event_id,
                "p_actor_id": actor_id,
                "p_from_statuses": from_statuses,
                "p_to_status": to_status,
                "p_expected_version": expected_version,
                "p_message": message,
                "p_flagged_fields": flagged_fields,
                "p_notify_message": notify_message,
            },
        )
        .execute()
    )
    return _first_row(response)


def resubmit_event(
    event_id: str,
    actor_id: str,
    from_statuses: list[str],
    to_status: str,
    expected_version: int,
    *,
    note: str,
    notify_message: str,
) -> dict | None:
    """Run `public.resubmit_event` (SCRUM-33): back to the same coordinator, the open
    amendment closed with the note, the coordinator notified. None when stale."""
    response = (
        get_supabase_admin_client()
        .rpc(
            "resubmit_event",
            {
                "p_event_id": event_id,
                "p_actor_id": actor_id,
                "p_from_statuses": from_statuses,
                "p_to_status": to_status,
                "p_expected_version": expected_version,
                "p_note": note,
                "p_notify_message": notify_message,
            },
        )
        .execute()
    )
    return _first_row(response)


def get_open_amendment(event_id: str) -> dict | None:
    """The amendment the organiser still has to answer, if any. At most one is open
    per event (partial unique index in the migration)."""
    response = (
        get_supabase_admin_client()
        .table("amendment_requests")
        .select("id, message, flagged_fields, returned_at")
        .eq("event_id", event_id)
        .is_("resubmitted_at", "null")
        .maybe_single()
        .execute()
    )
    return response.data if response else None


_REQUESTED_BY = "requested_by:profiles!event_change_requests_requested_by_fkey(id, full_name)"
_DECIDED_BY = "decided_by:profiles!event_change_requests_decided_by_fkey(id, full_name)"


def get_open_cancellation_request(event_id: str) -> dict | None:
    """Story 84: the event's open cancellation request, with who asked. At most one
    is open per event (partial unique index, CR-R1)."""
    return _open_request(event_id, "cancellation", f"id, kind, status, reason, requested_at, {_REQUESTED_BY}")


def get_open_change_request(event_id: str) -> dict | None:
    """Story 32: the event's open change request, with its proposed changes."""
    return _open_request(event_id, "change",
                         f"id, kind, status, reason, changes, significant, requested_at, {_REQUESTED_BY}")


def _open_request(event_id: str, kind: str, columns: str) -> dict | None:
    response = (
        get_supabase_admin_client()
        .table("event_change_requests")
        .select(columns)
        .eq("event_id", event_id)
        .eq("kind", kind)
        .eq("status", "open")
        .maybe_single()
        .execute()
    )
    return response.data if response else None


def list_cancellation_requests(event_id: str) -> list[dict]:
    """Story 84 AC5: every cancellation request on the event, newest first, for its
    history, with story 115's decision. Who asked and who decided are embedded; each
    is null if their profile was deleted."""
    return _list_requests(event_id, "cancellation",
                          f"id, reason, requested_at, status, decision_reason, decided_at, {_REQUESTED_BY}, {_DECIDED_BY}")


def list_change_requests(event_id: str) -> list[dict]:
    """Story 32 AC2: every change request on the event, newest first, for its history."""
    return _list_requests(event_id, "change",
                          "id, reason, changes, significant, requested_at, status, decision_reason, decided_at, "
                          f"{_REQUESTED_BY}, {_DECIDED_BY}")


def _list_requests(event_id: str, kind: str, columns: str) -> list[dict]:
    response = (
        get_supabase_admin_client()
        .table("event_change_requests")
        .select(columns)
        .eq("event_id", event_id)
        .eq("kind", kind)
        .order("requested_at", desc=True)
        .execute()
    )
    return response.data or []


_REASSIGNMENT_REQUESTED_BY = "requested_by:profiles!event_reassignment_requests_requested_by_fkey(id, full_name)"
_REASSIGNMENT_DECIDED_BY = "decided_by:profiles!event_reassignment_requests_decided_by_fkey(id, full_name)"


def get_open_reassignment_request(event_id: str) -> dict | None:
    """CR-106: the event's open reassignment request, with who asked. At most one is
    open per event (partial unique index)."""
    response = (
        get_supabase_admin_client()
        .table("event_reassignment_requests")
        .select(f"id, status, reason, requested_at, {_REASSIGNMENT_REQUESTED_BY}")
        .eq("event_id", event_id)
        .eq("status", "open")
        .maybe_single()
        .execute()
    )
    return response.data if response else None


def list_open_reassignment_requests(event_ids: Iterable[str]) -> dict[str, dict]:
    """CR-106 AC2: `{event_id: request}` of each event's open reassignment request, for
    the Lead's dashboard."""
    ids = list(event_ids)
    if not ids:
        return {}
    response = (
        get_supabase_admin_client()
        .table("event_reassignment_requests")
        .select(f"id, event_id, status, reason, requested_at, {_REASSIGNMENT_REQUESTED_BY}")
        .in_("event_id", ids)
        .eq("status", "open")
        .execute()
    )
    return {row["event_id"]: row for row in response.data or []}


def list_reassignment_requests(event_id: str) -> list[dict]:
    """CR-106 AC6: every reassignment request on the event, newest first, for its
    history, with the Lead's decision. Who asked and who decided are embedded; each is
    null if their profile was deleted."""
    response = (
        get_supabase_admin_client()
        .table("event_reassignment_requests")
        .select("id, status, reason, requested_at, decision_reason, decided_at, "
                f"{_REASSIGNMENT_REQUESTED_BY}, {_REASSIGNMENT_DECIDED_BY}")
        .eq("event_id", event_id)
        .order("requested_at", desc=True)
        .execute()
    )
    return response.data or []


def list_comments(event_id: str) -> list[dict]:
    """The event's discussion thread, oldest first (SCRUM-61). The author is embedded
    through the FK named in the migration; it is null if their profile was deleted."""
    response = (
        get_supabase_admin_client()
        .table("event_comments")
        .select("id, body, created_at, author_id, author:profiles!event_comments_author_id_fkey(id, full_name)")
        .eq("event_id", event_id)
        .order("created_at", desc=False)
        .execute()
    )
    return response.data or []


def add_comment(event_id: str, author_id: str, body: str, *, notify_message: str) -> dict | None:
    """Run `public.add_event_comment`: the comment and the other party's notification in
    one transaction. None when the event is missing, a draft or closed."""
    response = (
        get_supabase_admin_client()
        .rpc(
            "add_event_comment",
            {
                "p_event_id": event_id,
                "p_author_id": author_id,
                "p_body": body,
                "p_notify_message": notify_message,
            },
        )
        .execute()
    )
    return _first_row(response)


def send_to_safety_review(
    event_id: str, actor_id: str, from_statuses: list[str], to_status: str, expected_version: int,
    *, organiser_message: str, officer_message: str,
) -> dict | None:
    """SCRUM-82: transition, history and both recipient groups in one transaction."""
    response = get_supabase_admin_client().rpc("send_event_to_safety_review", {
        "p_event_id": event_id, "p_actor_id": actor_id, "p_from_statuses": from_statuses,
        "p_to_status": to_status, "p_expected_version": expected_version,
        "p_organiser_message": organiser_message, "p_officer_message": officer_message,
    }).execute()
    return _first_row(response)


def safety_approve(event_id: str, actor_id: str, expected_version: int, *, comment: str | None,
                   organiser_message: str, staff_message: str) -> dict | None:
    return _first_row(get_supabase_admin_client().rpc("safety_approve_event", {
        "p_event_id": event_id, "p_actor_id": actor_id, "p_expected_version": expected_version,
        "p_comment": comment, "p_organiser_message": organiser_message, "p_staff_message": staff_message,
    }).execute())


def safety_return(event_id: str, actor_id: str, expected_version: int, *, decision: str, comment: str,
                  booking_ids: list[str], equipment_request_ids: list[str], coordinator_message: str) -> dict | None:
    return _first_row(get_supabase_admin_client().rpc("safety_return_event", {
        "p_event_id": event_id, "p_actor_id": actor_id, "p_expected_version": expected_version,
        "p_decision": decision, "p_comment": comment, "p_booking_ids": booking_ids,
        "p_equipment_request_ids": equipment_request_ids, "p_coordinator_message": coordinator_message,
    }).execute())


def return_to_planning(event_id: str, expected_version: int, *, from_status: str, reason_code: str,
                       coordinator_message: str, officer_message: str | None) -> dict | None:
    return _first_row(get_supabase_admin_client().rpc("return_event_to_planning", {
        "p_event_id": event_id, "p_expected_version": expected_version, "p_from_status": from_status,
        "p_reason_code": reason_code, "p_coordinator_message": coordinator_message,
        "p_officer_message": officer_message,
    }).execute())


def set_primary_space(event_id: str, space_id: str | None, actor_id: str) -> str:
    """CR-97 AC9: mark the event's primary space (or clear it with None) under the
    event's lock. Answers ok / event_not_found / not_planning / not_assigned /
    space_not_found."""
    response = get_supabase_admin_client().rpc("set_primary_space", {
        "p_event_id": event_id, "p_space_id": space_id, "p_actor_id": actor_id,
    }).execute()
    return response.data


def list_safety_decisions(event_id: str) -> list[dict]:
    response = (get_supabase_admin_client().table("event_safety_decisions")
                .select("*, decider:profiles!event_safety_decisions_decided_by_fkey(full_name)")
                .eq("event_id", event_id).order("decided_at", desc=True).execute())
    return [{**{k: v for k, v in row.items() if k != "decider"},
             "decided_by_name": (row.get("decider") or {}).get("full_name")}
            for row in response.data or []]


def list_recent_safety_decisions(since: datetime) -> list[dict]:
    """Every decision since `since`, any event, with its event and decider names (CR-103 AC7)."""
    response = (get_supabase_admin_client().table("event_safety_decisions")
                .select("id, event_id, decision, comment, decided_at, affected_booking_ids, "
                        "affected_equipment_request_ids, rejected_venue_ids, event:events(name), "
                        "decider:profiles!event_safety_decisions_decided_by_fkey(full_name)")
                .gte("decided_at", since.isoformat()).order("decided_at", desc=True).execute())
    return [dict(id=row["id"], event_id=row["event_id"], event_name=(row.get("event") or {}).get("name", ""),
                 decision=row["decision"], comment=row.get("comment"), decided_at=row["decided_at"],
                 decided_by_name=(row.get("decider") or {}).get("full_name"),
                 affected_booking_ids=row.get("affected_booking_ids", []),
                 affected_equipment_request_ids=row.get("affected_equipment_request_ids", []),
                 rejected_venue_ids=row.get("rejected_venue_ids", []))
            for row in response.data or []]


def list_safety_queue() -> list[dict]:
    client = get_supabase_admin_client()
    response = (client.table("events")
                .select("id, name, starts_at, expected_attendance, organiser:profiles!events_organiser_id_fkey(full_name)")
                .eq("status", "safety_review").execute())
    events = response.data or []
    if not events:
        return []
    history = (client.table("event_status_history").select("event_id, at")
               .in_("event_id", [row["id"] for row in events]).eq("to_status", "safety_review")
               .order("at", desc=True).execute())
    latest = {}
    for row in history.data or []:
        latest.setdefault(row["event_id"], row["at"])
    items = [dict(event_id=row["id"], name=row["name"], starts_at=row.get("starts_at"),
                  expected_attendance=row.get("expected_attendance"),
                  organiser_name=(row.get("organiser") or {}).get("full_name"),
                  entered_review_at=latest[row["id"]]) for row in events if row["id"] in latest]
    return sorted(items, key=lambda row: (row["entered_review_at"], row["event_id"]))


# CR-101: the Lead's reads. Both profile embeds name their FK because `events`
# points at `profiles` twice (organiser and coordinator).
_LEAD_COLUMNS = (
    "id, name, status, starts_at, purpose, expected_attendance, version, "
    "submitted_at, layout_preference, facilities_required, "
    "coordinator_id, assigned_by, assigned_at, "
    "organiser:profiles!events_organiser_id_fkey(full_name), "
    "coordinator:profiles!events_coordinator_id_fkey(id, full_name)"
)


def list_lead_events(statuses: Iterable[str]) -> list[dict]:
    response = (
        get_supabase_admin_client()
        .table("events")
        .select(_LEAD_COLUMNS)
        .in_("status", list(statuses))
        .execute()
    )
    return response.data or []


def list_lead_ids() -> set[str]:
    """Profiles currently holding the Lead role. Used only to tell whether an
    event's assigner is still a Lead (never to authorise a caller)."""
    response = (
        get_supabase_admin_client()
        .table("user_roles")
        .select("profile_id")
        .eq("role", "event_coordinator_lead")
        .execute()
    )
    return {row["profile_id"] for row in response.data or []}


def list_coordinators() -> list[dict]:
    """`{id, full_name}` of every account holding the coordinator role, by name."""
    held = (
        get_supabase_admin_client()
        .table("user_roles")
        .select("profile_id")
        .eq("role", "event_coordinator")
        .execute()
    )
    ids = [row["profile_id"] for row in held.data or []]
    if not ids:
        return []
    response = (
        get_supabase_admin_client()
        .table("profiles")
        .select("id, full_name")
        .in_("id", ids)
        .order("full_name")
        .execute()
    )
    return response.data or []


def get_lead_event(event_id: str) -> dict | None:
    response = (
        get_supabase_admin_client()
        .table("events")
        .select(_LEAD_COLUMNS)
        .eq("id", event_id)
        .maybe_single()
        .execute()
    )
    return response.data if response else None


def get_coordinator(profile_id: str) -> dict | None:
    """`{id, full_name}` if the profile holds the coordinator role, else None.
    Eligibility of a reassignment *target*, never an authorisation of a caller."""
    held = (
        get_supabase_admin_client()
        .table("user_roles")
        .select("profile_id")
        .eq("profile_id", profile_id)
        .eq("role", "event_coordinator")
        .maybe_single()
        .execute()
    )
    if not held or not held.data:
        return None
    profile = (
        get_supabase_admin_client()
        .table("profiles")
        .select("id, full_name")
        .eq("id", profile_id)
        .maybe_single()
        .execute()
    )
    return profile.data if profile else None


def assign_event(
    event_id: str,
    lead_id: str,
    coordinator_id: str,
    *,
    from_statuses: list[str],
    to_status: str,
    reason: str,
    notify_assigned: str,
    notify_organiser: str,
) -> dict | None:
    """Run `public.assign_event`: assignment, status change, history and notices in one
    locked transaction. Returns the updated row, or None when the event was no longer
    in the queue (another Lead assigned it first) or the target lost the coordinator role."""
    response = (
        get_supabase_admin_client()
        .rpc(
            "assign_event",
            {
                "p_event_id": event_id,
                "p_lead_id": lead_id,
                "p_coordinator_id": coordinator_id,
                "p_from_statuses": from_statuses,
                "p_to_status": to_status,
                "p_reason": reason,
                "p_notify_assigned": notify_assigned,
                "p_notify_organiser": notify_organiser,
            },
        )
        .execute()
    )
    return _first_row(response)


def reassign_event(
    event_id: str,
    lead_id: str,
    coordinator_id: str,
    expected_version: int,
    *,
    active_statuses: list[str],
    notify_assigned: str,
    notify_previous: str,
    notify_organiser: str,
) -> dict | None:
    """Run `public.reassign_event`. Returns the updated row, or None when the event
    had moved on (version or status) or the target lost the coordinator role."""
    response = (
        get_supabase_admin_client()
        .rpc(
            "reassign_event",
            {
                "p_event_id": event_id,
                "p_lead_id": lead_id,
                "p_coordinator_id": coordinator_id,
                "p_expected_version": expected_version,
                "p_active_statuses": active_statuses,
                "p_notify_assigned": notify_assigned,
                "p_notify_previous": notify_previous,
                "p_notify_organiser": notify_organiser,
            },
        )
        .execute()
    )
    return _first_row(response)
