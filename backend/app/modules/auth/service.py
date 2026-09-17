from supabase_auth.errors import AuthApiError, AuthError, AuthRetryableError

from app.core.exceptions import (
    AuthServiceUnavailableError,
    InvalidCredentialsError,
    InvalidOrExpiredTokenError,
    ProfileNotFoundError,
    RoleNotAssignedError,
)
from app.core.security import CurrentUser, resolve_active_role
from app.db.supabase import create_auth_client, get_supabase_admin_client, get_supabase_anon_client
from app.modules.auth.schemas import ProfileResponse, TokenResponse, UserLoginRequest, UserResponse


def get_roles(profile_id: str) -> list[str]:
    """The roles `profile_id` is allowed to act as (ACC-R4), for the nav dropdown (SCRUM-74)."""
    admin_client = get_supabase_admin_client()
    response = admin_client.table("user_roles").select("role").eq("profile_id", profile_id).execute()
    return [row["role"] for row in (response.data or [])]


def _fetch_profile(user_id: str, session_id: str) -> ProfileResponse:
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
    profile = response.data
    active_role = resolve_active_role(admin_client, session_id, default_role=profile["role"])
    return ProfileResponse(**{**profile, "role": active_role}, roles=get_roles(user_id))


def _token_response(session, user, auth_client) -> TokenResponse:
    # The session_id claim is only known once Supabase has minted the token,
    # so it's read back off the token we were just issued, not decoded ahead of time.
    claims_response = auth_client.auth.get_claims(session.access_token)
    session_id = claims_response["claims"]["session_id"]
    profile = _fetch_profile(user.id, session_id)
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
    except AuthRetryableError as exc:
        raise AuthServiceUnavailableError() from exc
    except AuthApiError as exc:
        raise InvalidCredentialsError() from exc

    if auth_response.session is None or auth_response.user is None:
        raise InvalidCredentialsError()

    return _token_response(auth_response.session, auth_response.user, auth_client)


def refresh(refresh_token: str) -> TokenResponse:
    """Exchange a refresh token for a new session. Supabase rotates the refresh token on use."""
    auth_client = create_auth_client()
    try:
        auth_response = auth_client.auth.refresh_session(refresh_token)
    except AuthRetryableError as exc:
        # Supabase unreachable or failing: the refresh token may still be good,
        # so this must not read as a rejected session (401 signs the SPA out).
        raise AuthServiceUnavailableError() from exc
    except AuthError as exc:
        raise InvalidOrExpiredTokenError() from exc

    if auth_response.session is None or auth_response.user is None:
        raise InvalidOrExpiredTokenError()

    return _token_response(auth_response.session, auth_response.user, auth_client)


def set_active_role(current_user: CurrentUser, role: str) -> ProfileResponse:
    """Switch the caller's session to `role` (SCRUM-75), after checking they hold it."""
    if role not in get_roles(current_user.id):
        raise RoleNotAssignedError(role)

    admin_client = get_supabase_admin_client()
    admin_client.table("session_active_roles").upsert(
        {"session_id": current_user.session_id, "profile_id": current_user.id, "role": role}
    ).execute()

    return _fetch_profile(current_user.id, current_user.session_id)


def logout(access_token: str) -> None:
    """Revoke the caller's own session (this device only) with Supabase Auth."""
    anon_client = get_supabase_anon_client()
    try:
        anon_client.auth.admin.sign_out(access_token, "local")
    except AuthApiError:
        # Best-effort: an already-expired or already-revoked session should not
        # surface as an error to the client, which has cleared its session anyway.
        pass
