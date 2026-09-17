from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.modules.auth import service
from app.modules.auth.dependencies import CurrentUser, get_current_user
from app.modules.auth.schemas import (
    ProfileResponse,
    RefreshTokenRequest,
    SetActiveRoleRequest,
    TokenResponse,
    UserLoginRequest,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# Endpoints are plain `def`: the supabase-py client is synchronous, and FastAPI
# runs sync endpoints in its threadpool instead of blocking the event loop.


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
def login(credentials: UserLoginRequest) -> TokenResponse:
    """Authenticate with email and password, returning a session and profile."""
    return service.login(credentials)


@router.post("/refresh", response_model=TokenResponse, status_code=status.HTTP_200_OK)
def refresh(body: RefreshTokenRequest) -> TokenResponse:
    """Exchange a refresh token for a new session. The returned refresh token replaces the old one."""
    return service.refresh(body.refresh_token)


@router.get("/me", response_model=ProfileResponse, status_code=status.HTTP_200_OK)
def read_current_user(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ProfileResponse:
    """Return the authenticated user's profile.

    `get_current_user` already fetched this profile to build `CurrentUser`,
    so this builds the response from it directly rather than re-querying.
    """
    return ProfileResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        organisation_name=current_user.organisation_name,
        department=current_user.department,
        phone_number=current_user.phone_number,
        roles=service.get_roles(current_user.id),
    )


@router.post("/active-role", response_model=ProfileResponse, status_code=status.HTTP_200_OK)
def set_active_role(
    body: SetActiveRoleRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ProfileResponse:
    """Switch the caller's session to a role they hold (SCRUM-75)."""
    return service.set_active_role(current_user, body.role)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> None:
    """Revoke the caller's current session."""
    service.logout(current_user.access_token)
