from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.modules.auth import service
from app.modules.auth.dependencies import CurrentUser, get_current_user
from app.modules.auth.schemas import ProfileResponse, TokenResponse, UserLoginRequest

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def login(credentials: UserLoginRequest) -> TokenResponse:
    """Authenticate with email and password, returning a session and profile."""
    return await service.login(credentials)


@router.get("/me", response_model=ProfileResponse, status_code=status.HTTP_200_OK)
async def read_current_user(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ProfileResponse:
    """Return the authenticated user's profile.

    `get_current_user` already fetched this profile to build `CurrentUser`,
    so this builds the response from it directly rather than re-querying —
    `/auth/me` doing two round trips to `public.profiles` for one request
    would be a needless, easy-to-miss inefficiency.
    """
    return ProfileResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        organisation_name=current_user.organisation_name,
        department=current_user.department,
        phone_number=current_user.phone_number,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> None:
    """Invalidate the current session."""
    await service.logout(current_user.access_token)
