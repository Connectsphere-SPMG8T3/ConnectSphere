from datetime import datetime

from app.db.supabase import get_supabase_admin_client

_EVENT_COLUMNS = (
    "id, organiser_id, coordinator_id, status, name, purpose, description, starts_at, ends_at, "
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
        .maybe_single()
        .execute()
    )
    return response.data if response else None


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
        .maybe_single()
        .execute()
    )
    return response.data if response else None
