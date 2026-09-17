from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase_auth.errors import AuthError, AuthRetryableError
from pydantic import BaseModel

from app.core.exceptions import (
    AuthServiceUnavailableError,
    InsufficientRoleError,
    InvalidOrExpiredTokenError,
    ProfileNotFoundError,
)
from app.db.supabase import get_supabase_admin_client, get_supabase_anon_client

_bearer_scheme = HTTPBearer(auto_error=False)
_EXPECTED_AUDIENCE = "authenticated"


class CurrentUser(BaseModel):
    """The authenticated principal, combining the verified JWT claims
    with the corresponding `public.profiles` row.

    `role` is the role this *session* is currently acting as (SCRUM-75), not
    necessarily the account's default `profiles.role` — see `resolve_active_role`.
    """

    id: str
    email: str
    full_name: str
    role: str
    organisation_name: str | None = None
    department: str | None = None
    phone_number: str | None = None
    session_id: str
    access_token: str


def decode_access_token(token: str) -> dict:
    """Verify a Supabase-issued JWT's signature and expiry, returning its claims.

    Delegates to the Supabase SDK's `get_claims`, which transparently handles
    both the legacy HS256 shared-secret scheme and the newer asymmetric
    (ES256) JWT signing-key scheme — fetching and locally caching this
    project's JWKS as needed — rather than hand-rolling verification against
    a single hardcoded algorithm. `get_claims` does not itself check the
    `aud` claim, so that is verified explicitly below.
    """
    anon_client = get_supabase_anon_client()
    try:
        claims_response = anon_client.auth.get_claims(token)
    except AuthRetryableError as exc:
        # Fetching the JWKS failed; that says nothing about the token itself.
        raise AuthServiceUnavailableError() from exc
    except AuthError as exc:
        raise InvalidOrExpiredTokenError() from exc

    if claims_response is None:
        raise InvalidOrExpiredTokenError()

    # ClaimsResponse is a TypedDict (a plain dict at runtime), not an object
    # with attribute access.
    claims = claims_response["claims"]
    if claims.get("aud") != _EXPECTED_AUDIENCE:
        raise InvalidOrExpiredTokenError()

    return claims


def resolve_active_role(admin_client, session_id: str, default_role: str) -> str:
    """The role `session_id` is currently acting as (SCRUM-75).

    Falls back to `default_role` (the account's `profiles.role`) when this
    session has never switched — most sessions, most of the time.
    """
    response = (
        admin_client.table("session_active_roles")
        .select("role")
        .eq("session_id", session_id)
        .maybe_single()
        .execute()
    )
    row = response.data if response else None
    return row["role"] if row else default_role


def load_profile_with_active_role(admin_client, user_id: str, session_id: str) -> dict:
    """Fetch `user_id`'s profile row, with `role` overridden to whatever
    `session_id` is currently acting as (SCRUM-75). Shared by `get_current_user`
    (the per-request auth dependency) and `auth.service._fetch_profile` (login/
    refresh/active-role responses), so active-role resolution only lives once.
    """
    response = (
        admin_client.table("profiles")
        .select("id, email, full_name, role, organisation_name, department, phone_number")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    profile = response.data if response else None
    if not profile:
        raise ProfileNotFoundError()

    active_role = resolve_active_role(admin_client, session_id, default_role=profile["role"])
    return {**profile, "role": active_role}


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> CurrentUser:
    """FastAPI dependency: verify the bearer token and load the caller's profile.

    Raises 401 if the token is missing, malformed, expired, or fails signature
    verification; raises 404 if the token is valid but no profile row exists.
    Plain `def` because the Supabase client is synchronous (FastAPI runs sync
    dependencies in its threadpool rather than on the event loop).
    """
    if credentials is None:
        raise InvalidOrExpiredTokenError()

    token = credentials.credentials
    payload = decode_access_token(token)
    user_id = payload.get("sub")
    session_id = payload.get("session_id")
    if not user_id or not session_id:
        raise InvalidOrExpiredTokenError()

    admin_client = get_supabase_admin_client()
    profile = load_profile_with_active_role(admin_client, user_id, session_id)
    return CurrentUser(**profile, session_id=session_id, access_token=token)


def require_roles(allowed_roles: list[str]):
    """Dependency factory: restrict an endpoint to the given profile roles."""

    def _dependency(
        current_user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CurrentUser:
        if current_user.role not in allowed_roles:
            raise InsufficientRoleError(allowed_roles)
        return current_user

    return _dependency
