from collections.abc import Iterable
from datetime import datetime

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


def submit_event(event_id: str, version: int, submitted_at: datetime) -> dict | None:
    response = (
        get_supabase_admin_client()
        .table("events")
        .update({"status": "under_review", "submitted_at": submitted_at.isoformat(), "version": version + 1})
        .eq("id", event_id)
        .eq("version", version)
        .select(_EVENT_COLUMNS)
        .execute()
    )
    if not response or not response.data:
        return None
    return response.data[0] if isinstance(response.data, list) else response.data


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
    """Newest first. The actor is embedded through the FK named in the migration."""
    response = (
        get_supabase_admin_client()
        .table("event_status_history")
        .select("id, from_status, to_status, reason, at, actor:profiles!event_status_history_actor_id_fkey(id, full_name)")
        .eq("event_id", event_id)
        .order("at", desc=True)
        .execute()
    )
    return response.data or []
