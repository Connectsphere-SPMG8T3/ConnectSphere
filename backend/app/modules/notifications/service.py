"""Notifications for the signed-in user, in the role they are acting as (113)."""

import base64
import binascii

from app.core.exceptions import InvalidNotificationCursorError, NotificationNotFoundError
from app.modules.notifications import repository
from app.modules.notifications.schemas import (
    MarkReadResponse,
    NotificationItem,
    NotificationPage,
    ReadAllResponse,
    UnreadCount,
)

# Where each role's notification leads. Roles with an event page open that
# event; venue staff and attendees have no event page yet, so they land on
# their own queue or dashboard.
_EVENT_PAGES = {
    "event_organiser": "/events/{id}",
    "event_coordinator": "/coordinator/events/{id}",
    "event_coordinator_lead": "/lead/events/{id}",
    "tech_support": "/tech-support/events/{id}",
    "safety_officer": "/safety/events/{id}",
}
_FIXED_PAGES = {
    "venue_staff": "/dashboard/venue-staff/requests",
    "attendee": "/dashboard/attendee",
}


def link_for(role: str, event_id: str | None) -> str | None:
    if role in _FIXED_PAGES:
        return _FIXED_PAGES[role]
    if role in _EVENT_PAGES and event_id:
        return _EVENT_PAGES[role].format(id=event_id)
    return None


def encode_cursor(created_at: str, row_id: str) -> str:
    """Opaque and URL-safe: a timestamp's `+00:00` would otherwise read as a space."""
    return base64.urlsafe_b64encode(f"{created_at}|{row_id}".encode()).decode()


def decode_cursor(value: str) -> tuple[str, str]:
    try:
        created_at, row_id = base64.urlsafe_b64decode(value.encode()).decode().split("|")
    except (ValueError, binascii.Error, UnicodeError) as exc:
        raise ValueError("malformed cursor") from exc
    if not created_at or not row_id:
        raise ValueError("malformed cursor")
    return created_at, row_id


def unread_count(user_id: str, role: str) -> UnreadCount:
    return UnreadCount(**repository.count_unread(user_id, role))


def list_notifications(user_id: str, role: str, limit: int, before: str | None) -> NotificationPage:
    try:
        cursor = decode_cursor(before) if before else None
    except ValueError as exc:
        raise InvalidNotificationCursorError() from exc
    rows = repository.list_page(user_id, role, limit, cursor)
    page, has_more = rows[:limit], len(rows) > limit
    items = [
        NotificationItem(
            id=row["id"],
            event_id=row.get("event_id"),
            type=row["type"],
            message=row["message"],
            link=link_for(role, row.get("event_id")),
            read=row.get("read_at") is not None,
            created_at=row["created_at"],
        )
        for row in page
    ]
    next_before = encode_cursor(page[-1]["created_at"], page[-1]["id"]) if has_more else None
    return NotificationPage(items=items, next_before=next_before)


def mark_read(user_id: str, role: str, notification_id: str) -> MarkReadResponse:
    if not repository.mark_read(notification_id, user_id, role):
        raise NotificationNotFoundError()
    return MarkReadResponse(id=notification_id, read=True)


def mark_all_read(user_id: str, role: str) -> ReadAllResponse:
    return ReadAllResponse(updated=repository.mark_all_read(user_id, role))
