"""All Supabase access for the notifications module (113).

Every query is scoped to the recipient AND the role they are acting as
(`recipient_role`, stamped by trigger from `notification_types`), so a user who
holds two roles never sees one role's rows while acting as the other. Reads
use the secret-key admin client, so callers must already have a verified user.
"""

from datetime import datetime, timezone

from app.db.supabase import get_supabase_admin_client

_LIST_COLUMNS = "id, event_id, type, message, read_at, created_at"


def _inbox(query, recipient_id: str, role: str):
    return query.eq("recipient_id", recipient_id).eq("recipient_role", role)


def count_unread(recipient_id: str, role: str) -> dict:
    """`{count, latest_at}`: unread rows, and the newest row's time (read or not)."""
    client = get_supabase_admin_client()
    counted = (
        _inbox(client.table("notifications").select("id", count="exact"), recipient_id, role)
        .is_("read_at", "null")
        .limit(1)
        .execute()
    )
    newest = (
        _inbox(client.table("notifications").select("created_at"), recipient_id, role)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = newest.data or []
    return {"count": counted.count or 0, "latest_at": rows[0]["created_at"] if rows else None}


def list_page(recipient_id: str, role: str, limit: int, before: tuple[str, str] | None) -> list[dict]:
    """Up to `limit + 1` rows, newest first. The extra row tells the caller whether
    another page exists. `before` is `(created_at, id)` of the last row already
    shown; rows created in one transaction share a time, so the id breaks the tie."""
    query = _inbox(get_supabase_admin_client().table("notifications").select(_LIST_COLUMNS), recipient_id, role)
    if before:
        created_at, row_id = before
        query = query.or_(f"created_at.lt.{created_at},and(created_at.eq.{created_at},id.lt.{row_id})")
    response = query.order("created_at", desc=True).order("id", desc=True).limit(limit + 1).execute()
    return response.data or []


def mark_read(notification_id: str, recipient_id: str, role: str) -> bool:
    """True when the row is the caller's in this role. An already-read row keeps its
    original `read_at`: the update only touches unread rows."""
    client = get_supabase_admin_client()
    updated = (
        _inbox(client.table("notifications").update({"read_at": _now()}), recipient_id, role)
        .eq("id", notification_id)
        .is_("read_at", "null")
        .execute()
    )
    if updated.data:
        return True
    found = _inbox(client.table("notifications").select("id"), recipient_id, role).eq("id", notification_id).execute()
    return bool(found.data)


def mark_all_read(recipient_id: str, role: str) -> int:
    updated = (
        _inbox(get_supabase_admin_client().table("notifications").update({"read_at": _now()}), recipient_id, role)
        .is_("read_at", "null")
        .execute()
    )
    return len(updated.data or [])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
