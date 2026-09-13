from supabase_auth.errors import AuthApiError, AuthError

from app.core.exceptions import InvalidCredentialsError, InvalidOrExpiredTokenError, ProfileNotFoundError
from app.db.supabase import create_auth_client, get_supabase_admin_client, get_supabase_anon_client
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


def _token_response(session, user) -> TokenResponse:
    profile = _fetch_profile(user.id)
    return TokenResponse(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        expires_in=session.expires_in,
        user=UserResponse(id=user.id, email=user.email or profile.email),
        profile=profile,
    )


def login(credentials: UserLoginRequest) -> TokenResponse:
    """Authenticate a user against Supabase Auth (GoTrue) and return a session."""
    auth_client = create_auth_client()
    try:
        auth_response = auth_client.auth.sign_in_with_password(
            {"email": credentials.email, "password": credentials.password}
        )
    except AuthApiError as exc:
        raise InvalidCredentialsError() from exc

    if auth_response.session is None or auth_response.user is None:
        raise InvalidCredentialsError()

    return _token_response(auth_response.session, auth_response.user)


def refresh(refresh_token: str) -> TokenResponse:
    """Exchange a refresh token for a new session. Supabase rotates the refresh token on use."""
    auth_client = create_auth_client()
    try:
        auth_response = auth_client.auth.refresh_session(refresh_token)
    except AuthError as exc:
        raise InvalidOrExpiredTokenError() from exc

    if auth_response.session is None or auth_response.user is None:
        raise InvalidOrExpiredTokenError()

    return _token_response(auth_response.session, auth_response.user)


def get_profile(user_id: str) -> ProfileResponse:
    return _fetch_profile(user_id)


def logout(access_token: str) -> None:
    """Revoke the caller's own session (this device only) with Supabase Auth."""
    anon_client = get_supabase_anon_client()
    try:
        anon_client.auth.admin.sign_out(access_token, "local")
    except AuthApiError:
        # Best-effort: an already-expired or already-revoked session should not
        # surface as an error to the client, which has cleared its session anyway.
        pass
