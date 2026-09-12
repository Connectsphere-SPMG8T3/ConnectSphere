from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase_auth.errors import AuthError
from pydantic import BaseModel

from app.core.exceptions import InsufficientRoleError, InvalidOrExpiredTokenError, ProfileNotFoundError
from app.db.supabase import get_supabase_admin_client, get_supabase_anon_client

_bearer_scheme = HTTPBearer(auto_error=False)
_EXPECTED_AUDIENCE = "authenticated"


class CurrentUser(BaseModel):
    """The authenticated principal, combining the verified JWT claims
    with the corresponding `public.profiles` row."""

    id: str
    email: str
    full_name: str
    role: str
    organisation_name: str | None = None
    department: str | None = None
    phone_number: str | None = None
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


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> CurrentUser:
    """FastAPI dependency: verify the bearer token and load the caller's profile.

    Raises 401 if the token is missing, malformed, expired, or fails signature
    verification; raises 404 if the token is valid but no profile row exists.
    """
    if credentials is None:
        raise InvalidOrExpiredTokenError()

    token = credentials.credentials
    payload = decode_access_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise InvalidOrExpiredTokenError()

    admin_client = get_supabase_admin_client()
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

    return CurrentUser(**profile, access_token=token)


def require_roles(allowed_roles: list[str]):
    """Dependency factory: restrict an endpoint to the given profile roles."""

    async def _dependency(
        current_user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CurrentUser:
        if current_user.role not in allowed_roles:
            raise InsufficientRoleError(allowed_roles)
        return current_user

    return _dependency
