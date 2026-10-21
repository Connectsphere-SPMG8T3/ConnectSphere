from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.modules.auth.dependencies import CurrentUser, get_current_user
from app.modules.notifications import service
from app.modules.notifications.schemas import MarkReadResponse, NotificationPage, ReadAllResponse, UnreadCount

router = APIRouter(prefix="/notifications", tags=["notifications"])

# Every role has a bell, so any signed-in user may call these. What they get is
# scoped to the role the session is acting as (`current_user.role`), never to
# every role the account holds.
Notified = Annotated[CurrentUser, Depends(get_current_user)]


@router.get("/unread-count", response_model=UnreadCount, status_code=status.HTTP_200_OK)
def unread_count(current_user: Notified) -> UnreadCount:
    return service.unread_count(current_user.id, current_user.role)


@router.get("", response_model=NotificationPage, status_code=status.HTTP_200_OK)
def list_notifications(
    current_user: Notified,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    before: str | None = None,
) -> NotificationPage:
    return service.list_notifications(current_user.id, current_user.role, limit, before)


@router.post("/read-all", response_model=ReadAllResponse, status_code=status.HTTP_200_OK)
def read_all(current_user: Notified) -> ReadAllResponse:
    return service.mark_all_read(current_user.id, current_user.role)


@router.post("/{notification_id}/read", response_model=MarkReadResponse, status_code=status.HTTP_200_OK)
def read_one(notification_id: UUID, current_user: Notified) -> MarkReadResponse:
    return service.mark_read(current_user.id, current_user.role, str(notification_id))
