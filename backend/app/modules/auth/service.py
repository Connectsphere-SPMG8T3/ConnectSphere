from postgrest.exceptions import APIError
from supabase_auth.errors import AuthApiError, AuthError, AuthRetryableError

from app.core.exceptions import (
    AuthServiceUnavailableError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidOrExpiredTokenError,
    RoleNotAssignedError,
)
from app.core.security import (
    CurrentUser,
    decode_access_token,
    load_profile_with_active_role,
    resolve_active_role,
)

_FOREIGN_KEY_VIOLATION = "23503"
from app.db.supabase import create_auth_client, get_supabase_admin_client, get_supabase_anon_client
from app.modules.auth.schemas import (
    ProfileResponse,
    SignupRequest,
    TokenResponse,
    UserLoginRequest,
    UserResponse,
)


def get_roles(profile_id: str) -> list[str]:
    """The roles `profile_id` is allowed to act as (ACC-R4), for the nav dropdown (SCRUM-74)."""
    admin_client = get_supabase_admin_client()
    response = (
        admin_client.table("user_roles")
        .select("role")
        .eq("profile_id", profile_id)
        .order("role")
        .execute()
    )
    return [row["role"] for row in (response.data or [])]


def _fetch_profile(user_id: str, session_id: str) -> ProfileResponse:
    admin_client = get_supabase_admin_client()
    profile = load_profile_with_active_role(admin_client, user_id, session_id)
    return ProfileResponse(**profile, roles=get_roles(user_id))


def _token_response(session, user) -> TokenResponse:
    # The session_id claim is only known once Supabase has minted the token, so
    # it's read back off the token we were just issued. Reuses core.security's
    # decode_access_token (shared anon client, warm JWKS cache, and outage
    # handling) rather than decoding on the per-login auth_client directly.
    claims = decode_access_token(session.access_token)
    session_id = claims.get("session_id")
    if not session_id:
        raise InvalidOrExpiredTokenError()
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

    return _token_response(auth_response.session, auth_response.user)


def signup(request: SignupRequest) -> ProfileResponse:
    """Create a confirmed account for an external user (SCRUM-80, ADR-0003).

    Goes through the admin API rather than GoTrue sign-up so the account can
    log in immediately and a duplicate email surfaces as an error. The
    business role rides in `user_metadata` for `handle_new_user()`, which
    creates the `profiles` and `user_roles` rows in the same transaction.
    """
    admin_client = get_supabase_admin_client()
    try:
        created = admin_client.auth.admin.create_user(
            {
                "email": request.email,
                "password": request.password,
                "email_confirm": True,
                "user_metadata": {
                    "role": request.role,
                    "full_name": request.full_name,
                    "organisation_name": request.organisation_name,
                    "phone_number": request.phone_number,
                },
            }
        )
    except AuthRetryableError as exc:
        raise AuthServiceUnavailableError() from exc
    except AuthApiError as exc:
        # Matched on GoTrue's error code, not its message text.
        if exc.code == "email_exists":
            raise EmailAlreadyRegisteredError() from exc
        raise
    user_id = created.user.id
    profile = (
        admin_client.table("profiles")
        .select("id, email, full_name, role, organisation_name, department, phone_number")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    return ProfileResponse(**profile.data, roles=get_roles(user_id))


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

    return _token_response(auth_response.session, auth_response.user)


def set_active_role(current_user: CurrentUser, role: str) -> ProfileResponse:
    """Switch the caller's session to `role` (SCRUM-75), after checking they hold it."""
    roles = get_roles(current_user.id)
    if role not in roles:
        raise RoleNotAssignedError(role)

    admin_client = get_supabase_admin_client()
    try:
        admin_client.table("session_active_roles").upsert(
            {"session_id": current_user.session_id, "profile_id": current_user.id, "role": role}
        ).execute()
    except APIError as exc:
        if exc.code == _FOREIGN_KEY_VIOLATION:
            # TOCTOU: the role was revoked (a system admin deleting it from
            # user_roles) between the membership check above and this write.
            # The composite FK added in 20260918000000 rejects the upsert
            # rather than letting a revoked role stay active.
            raise RoleNotAssignedError(role) from exc
        raise

    # current_user already carries every other profile field, so only the
    # active role needs reading back — but it's read back rather than assumed
    # to be `role`, since a concurrent switch for the same session (e.g. two
    # tabs) can race this upsert, and the response should report whichever
    # write actually won, not just what this request asked for.
    active_role = resolve_active_role(
        admin_client, user_id=current_user.id, session_id=current_user.session_id, default_role=role
    )
    return ProfileResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=active_role,
        organisation_name=current_user.organisation_name,
        department=current_user.department,
        phone_number=current_user.phone_number,
        roles=roles,
    )


def logout(access_token: str) -> None:
    """Revoke the caller's own session (this device only) with Supabase Auth."""
    anon_client = get_supabase_anon_client()
    try:
        anon_client.auth.admin.sign_out(access_token, "local")
    except AuthApiError:
        # Best-effort: an already-expired or already-revoked session should not
        # surface as an error to the client, which has cleared its session anyway.
        pass
