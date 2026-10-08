from collections.abc import Iterable

from app.db.supabase import get_supabase_admin_client

_EVENT_COLUMNS = (
    "id, organiser_id, coordinator_id, status, name, event_timezone, purpose, description, starts_at, ends_at, "
    "expected_attendance, layout_preference, facilities_required, accessibility_needs, "
    "preliminary_equipment_needs, registration_enabled, registration_capacity, "
    "registration_opens_at, registration_closes_at, technical_readiness, submitted_at, "
    "version, created_at, updated_at"
)


def list_events(organiser_id: str) -> list[dict]:
    response = (
        get_supabase_admin_client()
        .table("events")
        .select(_EVENT_COLUMNS)
        .eq("organiser_id", organiser_id)
        .order("updated_at", desc=True)
        .execute()
    )
    return response.data or []


# SCRUM-72: the coordinator dashboard's reads. The organiser is embedded through
# the named FK: `events` points at `profiles` twice (organiser and coordinator),
# so a bare `profiles(...)` embed fails the whole query with PGRST201.
_COORDINATOR_DASHBOARD_COLUMNS = (
    "id, name, status, starts_at, submitted_at, technical_readiness, preliminary_equipment_needs, "
    "organiser:profiles!events_organiser_id_fkey(full_name)"
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


def list_planning_context(event_ids: Iterable[str]) -> list[dict]:
    """The event fields another module needs to judge an event's requirements
    (SCRUM-63): name, assigned coordinator, expected attendance, preferred
    layout and required facilities. Skips any id that no longer exists.
    """
    ids = sorted({str(event_id) for event_id in event_ids if event_id})
    if not ids:
        return []
    response = (
        get_supabase_admin_client()
        .table("events")
        .select("id, name, coordinator_id, expected_attendance, layout_preference, facilities_required")
        .in_("id", ids)
        .execute()
    )
    return response.data or []


def get_event(event_id: str) -> dict | None:
    response = (
        get_supabase_admin_client()
        .table("events")
        .select(_EVENT_COLUMNS)
        .eq("id", event_id)
        .maybe_single()
        .execute()
    )
    return response.data if response else None


def create_event(organiser_id: str, values: dict) -> dict:
    response = (
        get_supabase_admin_client()
        .table("events")
        .insert({**values, "organiser_id": organiser_id, "status": "draft"})
        .select(_EVENT_COLUMNS)
        .execute()
    )
    if isinstance(response.data, list):
        return response.data[0]
    return response.data


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
    return response.data[0] if isinstance(response.data, list) else response.data


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
