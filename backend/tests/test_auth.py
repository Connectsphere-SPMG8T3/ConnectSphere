from types import SimpleNamespace
from typing import Annotated
from unittest.mock import MagicMock

from fastapi import APIRouter, Depends
from supabase_auth.errors import AuthApiError, AuthInvalidJwtError

from app.modules.auth import service as auth_service_module

TEST_USER_ID = "11111111-1111-1111-1111-111111111111"
TEST_EMAIL = "coordinator@connectsphere.dev"
FAKE_ACCESS_TOKEN = "fake-access-token"  # nosec: opaque in tests; verification is mocked, not decoded

PROFILE_ROW = {
    "id": TEST_USER_ID,
    "email": TEST_EMAIL,
    "full_name": "Test Coordinator",
    "role": "event_coordinator",
    "organisation_name": None,
    "department": "Operations",
    "phone_number": None,
}


def _make_table_mock(row: dict | None) -> MagicMock:
    """Build a mock replicating `.table("profiles").select(...).eq(...).maybe_single().execute()`."""
    execute_result = SimpleNamespace(data=row)
    query = MagicMock()
    query.select.return_value = query
    query.eq.return_value = query
    query.maybe_single.return_value = query
    query.execute.return_value = execute_result

    table_client = MagicMock()
    table_client.table.return_value = query
    return table_client


def _make_anon_client_with_claims(claims: dict | None = None, *, raises: Exception | None = None) -> MagicMock:
    """Build a mock replicating `.auth.get_claims(token)`.

    `get_claims` is the Supabase SDK call `app.core.security.decode_access_token`
    delegates to; it transparently supports both the legacy HS256 shared-secret
    scheme and this project's newer asymmetric (ES256) JWT signing keys, so
    tests mock its return value directly rather than constructing a real JWT.
    Its return type, `ClaimsResponse`, is a `TypedDict` — a plain dict at
    runtime, accessed via `["claims"]` — so the mock must return a dict too,
    not an object with attribute access.
    """
    anon_client = MagicMock()
    if raises is not None:
        anon_client.auth.get_claims.side_effect = raises
    else:
        anon_client.auth.get_claims.return_value = {"claims": claims}
    return anon_client


def _valid_claims() -> dict:
    return {"sub": TEST_USER_ID, "aud": "authenticated", "email": TEST_EMAIL}


class TestLogin:
    def test_successful_login_returns_token_and_profile(self, client, monkeypatch):
        fake_session = SimpleNamespace(
            access_token=FAKE_ACCESS_TOKEN,
            refresh_token="fake-refresh-token",
            expires_in=3600,
        )
        fake_user = SimpleNamespace(id=TEST_USER_ID, email=TEST_EMAIL)
        anon_client = MagicMock()
        anon_client.auth.sign_in_with_password.return_value = SimpleNamespace(
            session=fake_session, user=fake_user
        )

        monkeypatch.setattr(auth_service_module, "get_supabase_anon_client", lambda: anon_client)
        monkeypatch.setattr(
            auth_service_module, "get_supabase_admin_client", lambda: _make_table_mock(PROFILE_ROW)
        )

        response = client.post(
            "/api/v1/auth/login",
            json={"email": TEST_EMAIL, "password": "Cs1234"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["access_token"] == FAKE_ACCESS_TOKEN
        assert body["profile"]["role"] == "event_coordinator"
        assert body["user"]["email"] == TEST_EMAIL

    def test_invalid_login_returns_401(self, client, monkeypatch):
        anon_client = MagicMock()
        anon_client.auth.sign_in_with_password.side_effect = AuthApiError(
            "Invalid login credentials", 400, "invalid_credentials"
        )
        monkeypatch.setattr(auth_service_module, "get_supabase_anon_client", lambda: anon_client)

        response = client.post(
            "/api/v1/auth/login",
            json={"email": TEST_EMAIL, "password": "wrong-password"},
        )

        assert response.status_code == 401
        assert "Invalid email or password" in response.json()["detail"]


class TestMe:
    def test_me_with_valid_token_returns_profile(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.core.security.get_supabase_anon_client",
            lambda: _make_anon_client_with_claims(_valid_claims()),
        )
        monkeypatch.setattr(
            "app.core.security.get_supabase_admin_client", lambda: _make_table_mock(PROFILE_ROW)
        )

        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {FAKE_ACCESS_TOKEN}"},
        )

        assert response.status_code == 200
        assert response.json()["email"] == TEST_EMAIL

    def test_me_without_token_returns_401(self, client):
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 401

    def test_me_with_invalid_token_returns_401(self, client):
        # "not-a-real-token" fails Supabase's own local JWT-structure check
        # (no `.`-separated header/payload/signature) before any network call,
        # so no mocking of get_claims is needed here.
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        assert response.status_code == 401

    def test_me_with_expired_or_bad_signature_token_returns_401(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.core.security.get_supabase_anon_client",
            lambda: _make_anon_client_with_claims(raises=AuthInvalidJwtError("JWT has expired")),
        )

        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {FAKE_ACCESS_TOKEN}"},
        )

        assert response.status_code == 401

    def test_me_with_wrong_audience_returns_401(self, client, monkeypatch):
        wrong_audience_claims = {**_valid_claims(), "aud": "some-other-service"}
        monkeypatch.setattr(
            "app.core.security.get_supabase_anon_client",
            lambda: _make_anon_client_with_claims(wrong_audience_claims),
        )

        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {FAKE_ACCESS_TOKEN}"},
        )

        assert response.status_code == 401


class TestRoleGuard:
    def test_require_roles_blocks_mismatched_role(self, client, monkeypatch):
        from app.core.security import CurrentUser, require_roles

        monkeypatch.setattr(
            "app.core.security.get_supabase_anon_client",
            lambda: _make_anon_client_with_claims(_valid_claims()),
        )
        monkeypatch.setattr(
            "app.core.security.get_supabase_admin_client", lambda: _make_table_mock(PROFILE_ROW)
        )

        probe_router = APIRouter()

        @probe_router.get("/probe/venue-only")
        async def _probe(
            current_user: Annotated[CurrentUser, Depends(require_roles(["venue_staff"]))],
        ) -> dict:
            return {"ok": True}

        client.app.include_router(probe_router, prefix="/api/v1")

        response = client.get(
            "/api/v1/probe/venue-only",
            headers={"Authorization": f"Bearer {FAKE_ACCESS_TOKEN}"},
        )

        assert response.status_code == 403
