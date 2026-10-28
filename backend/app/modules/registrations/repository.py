from app.db.supabase import get_supabase_admin_client

_PUBLIC_EVENT_COLUMNS = (
    "id, name, description, starts_at, ends_at, event_timezone, status, registration_enabled, "
    "registration_capacity, registration_opens_at, registration_closes_at, waitlist_enabled, "
    "event_space_requests(id, is_primary, venue_bookings!venue_bookings_event_space_request_id_fkey("
    "status, venue:venues!venue_bookings_venue_id_fkey(id, name, location, capacity)))"
)

_ATTENDEE_REGISTRATION_COLUMNS = (
    "id, status, registered_at, "
    "event:events!event_registrations_event_id_fkey("
    "id, name, description, starts_at, ends_at, event_timezone, status, "
    "event_space_requests(id, is_primary, "
    "venue_bookings!venue_bookings_event_space_request_id_fkey("
    "status, venue:venues!venue_bookings_venue_id_fkey(id, name, location, capacity)))"
    ")"
)


def list_public_event_rows() -> list[dict]:
    response = (
        get_supabase_admin_client()
        .table("events")
        .select(_PUBLIC_EVENT_COLUMNS)
        .in_("status", ["confirmed", "preparation"])
        .order("starts_at")
        .execute()
    )
    return response.data or []


def get_public_event_row(event_id: str) -> dict | None:
    response = (
        get_supabase_admin_client()
        .table("events")
        .select(_PUBLIC_EVENT_COLUMNS)
        .eq("id", event_id)
        .in_("status", ["confirmed", "preparation"])
        .maybe_single()
        .execute()
    )
    return response.data if response else None


def list_attendee_registration_rows(attendee_id: str) -> list[dict]:
    response = (
        get_supabase_admin_client()
        .table("event_registrations")
        .select(_ATTENDEE_REGISTRATION_COLUMNS)
        .eq("attendee_id", attendee_id)
        .in_("status", ["registered", "waitlisted"])
        .order("registered_at", desc=True)
        .execute()
    )
    return response.data or []


def registered_count(event_id: str) -> int:
    response = (
        get_supabase_admin_client()
        .table("event_registrations")
        .select("id", count="exact")
        .eq("event_id", event_id)
        .eq("status", "registered")
        .execute()
    )
    return response.count or 0


def register_for_event(event_id: str, attendee_id: str) -> dict:
    response = get_supabase_admin_client().rpc(
        "register_for_event",
        {"p_event_id": event_id, "p_attendee_id": attendee_id},
    ).execute()
    return response.data