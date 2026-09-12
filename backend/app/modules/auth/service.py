from supabase_auth.errors import AuthApiError

from app.core.exceptions import InvalidCredentialsError, ProfileNotFoundError
from app.db.supabase import get_supabase_admin_client, get_supabase_anon_client
from app.modules.auth.schemas import ProfileResponse, TokenResponse, UserLoginRequest, UserResponse


def _fetch_profile(user_id: str) -> ProfileResponse:
    admin_client = get_supabase_admin_client()
    response = (
        admin_client.table("profiles")
        .select("id, email, full_name, role, organisation_name, department, phone_number")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    if not response or not response.data:
        raise ProfileNotFoundError()
    return ProfileResponse(**response.data)


async def login(credentials: UserLoginRequest) -> TokenResponse:
    """Authenticate a user against Supabase Auth (GoTrue) and return a session."""
    anon_client = get_supabase_anon_client()
    try:
        auth_response = anon_client.auth.sign_in_with_password(
            {"email": credentials.email, "password": credentials.password}
        )
    except AuthApiError as exc:
        raise InvalidCredentialsError() from exc

    session = auth_response.session
    user = auth_response.user
    if session is None or user is None:
        raise InvalidCredentialsError()

    profile = _fetch_profile(user.id)

    return TokenResponse(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        expires_in=session.expires_in,
        user=UserResponse(id=user.id, email=user.email or profile.email),
        profile=profile,
    )


async def get_profile(user_id: str) -> ProfileResponse:
    return _fetch_profile(user_id)


async def logout(access_token: str) -> None:
    """Invalidate the given session with Supabase Auth."""
    anon_client = get_supabase_anon_client()
    try:
        anon_client.auth.sign_out()
    except AuthApiError:
        # Sign-out is best-effort: an already-expired or already-revoked
        # session should not surface as an error to the client.
        pass
