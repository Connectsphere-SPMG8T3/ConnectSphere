from pydantic import BaseModel


class UnreadCount(BaseModel):
    """The 10-second poll (ADR-0004): how many unread, and when the newest row arrived."""

    count: int
    latest_at: str | None = None


class NotificationItem(BaseModel):
    id: str
    event_id: str | None = None
    type: str
    message: str
    link: str | None = None
    read: bool
    created_at: str


class NotificationPage(BaseModel):
    items: list[NotificationItem]
    # Pass back as `before` for the next page; null on the last page.
    next_before: str | None = None


class MarkReadResponse(BaseModel):
    id: str
    read: bool


class ReadAllResponse(BaseModel):
    updated: int
