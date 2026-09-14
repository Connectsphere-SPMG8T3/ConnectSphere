import threading
import time
from types import SimpleNamespace
from typing import Annotated
from unittest.mock import MagicMock

from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from supabase_auth.errors import AuthApiError, AuthInvalidJwtError, AuthRetryableError

from app.main import app
from app.modules.auth import service as auth_service_module

SUPABASE_GATEWAY_UNAVAILABLE = AuthRetryableError("upstream unavailable", 503)

TEST_USER_ID = "11111111-1111-1111-1111-111111111111"
TEST_EMAIL = "coordinator@connectsphere.dev"
FAKE_ACCESS_TOKEN = "fake-access-token"  # nosec: opaque in tests; verification is mocked, not decoded
FAKE_REFRESH_TOKEN = "fake-refresh-token"  # nosec: opaque in tests

PROFILE_ROW = {
    "id": TEST_USER_ID,
    "email": TEST_EMAIL,
    "full_name": "Test Coordinator",
    "role": "event_coordinator",
    "organisation_name": None,
    "department": "Operations",
    "phone_number": None,
}


def _make_table_mock(row: dict | None, *, delay_seconds: float = 0.0) -> MagicMock:
    """Build a mock replicating `.table("profiles").select(...).eq(...).maybe_single().execute()`."""

    def _execute():
        if delay_seconds:
            time.sleep(delay_seconds)
        return SimpleNamespace(data=row)

    query = MagicMock()
    query.select.return_value = query
    query.eq.return_value = query
    query.maybe_single.return_value = query
    query.execute.side_effect = _execute

    table_client = MagicMock()
    table_client.table.return_value = query
    return table_client


def _make_anon_client_with_claims(claims: dict | None = None, *, raises: Exception | None = None) -> MagicMock:
    """Build a mock replicating `.auth.get_claims(token)`.

    `get_claims` returns `ClaimsResponse`, a `TypedDict` — a plain dict at
    runtime — so the mock returns a dict, not an object with attribute access.
    """
    anon_client = MagicMock()
    if raises is not None:
        anon_client.auth.get_claims.side_effect = raises
    else:
        anon_client.auth.get_claims.return_value = {"claims": claims}
    return anon_client


def _shared_client_that_must_not_hold_sessions() -> MagicMock:
    """A stand-in for the process-wide cached client that fails loudly if a session is created on it."""
    shared = MagicMock()
    shared.auth.sign_in_with_password.side_effect = AssertionError(
        "sign-in must not run on the shared cached client"
    )
    shared.auth.refresh_session.side_effect = AssertionError(
        "refresh must not run on the shared cached client"
    )
    return shared


def _auth_response(access_token: str = FAKE_ACCESS_TOKEN, refresh_token: str = FAKE_REFRESH_TOKEN):
    return SimpleNamespace(
        session=SimpleNamespace(access_token=access_token, refresh_token=refresh_token, expires_in=3600),
        user=SimpleNamespace(id=TEST_USER_ID, email=TEST_EMAIL),
    )


def _valid_claims() -> dict:
    return {"sub": TEST_USER_ID, "aud": "authenticated", "email": TEST_EMAIL}


def _authenticate_requests_as_test_user(monkeypatch) -> MagicMock:
    anon_client = _make_anon_client_with_claims(_valid_claims())
    monkeypatch.setattr("app.core.security.get_supabase_anon_client", lambda: anon_client)
    monkeypatch.setattr("app.core.security.get_supabase_admin_client", lambda: _make_table_mock(PROFILE_ROW))
    return anon_client


class TestLogin:
    def test_successful_login_returns_token_and_profile(self, client, monkeypatch):
        auth_client = MagicMock()
        auth_client.auth.sign_in_with_password.return_value = _auth_response()
        monkeypatch.setattr(auth_service_module, "create_auth_client", lambda: auth_client, raising=False)
        monkeypatch.setattr(
            auth_service_module, "get_supabase_anon_client", _shared_client_that_must_not_hold_sessions
        )
        monkeypatch.setattr(
            auth_service_module, "get_supabase_admin_client", lambda: _make_table_mock(PROFILE_ROW)
        )

        response = client.post("/api/v1/auth/login", json={"email": TEST_EMAIL, "password": "Cs1234"})

        assert response.status_code == 200
        body = response.json()
        assert body["access_token"] == FAKE_ACCESS_TOKEN
        assert body["refresh_token"] == FAKE_REFRESH_TOKEN
        assert body["profile"]["role"] == "event_coordinator"
        assert body["user"]["email"] == TEST_EMAIL

    def test_invalid_login_returns_401(self, client, monkeypatch):
        auth_client = MagicMock()
        auth_client.auth.sign_in_with_password.side_effect = AuthApiError(
            "Invalid login credentials", 400, "invalid_credentials"
        )
        monkeypatch.setattr(auth_service_module, "create_auth_client", lambda: auth_client, raising=False)
        monkeypatch.setattr(
            auth_service_module, "get_supabase_anon_client", _shared_client_that_must_not_hold_sessions
        )

        response = client.post("/api/v1/auth/login", json={"email": TEST_EMAIL, "password": "wrong-password"})

        assert response.status_code == 401
        assert "Invalid email or password" in response.json()["detail"]

    def test_each_login_signs_in_on_its_own_fresh_client(self, client, monkeypatch):
        """D1: sign-in stores the session on the client instance, so two logins must never share one."""
        created_clients = []

        def _create_auth_client():
            auth_client = MagicMock()
            auth_client.auth.sign_in_with_password.return_value = _auth_response()
            created_clients.append(auth_client)
            return auth_client

        monkeypatch.setattr(auth_service_module, "create_auth_client", _create_auth_client, raising=False)
        monkeypatch.setattr(
            auth_service_module, "get_supabase_anon_client", _shared_client_that_must_not_hold_sessions
        )
        monkeypatch.setattr(
            auth_service_module, "get_supabase_admin_client", lambda: _make_table_mock(PROFILE_ROW)
        )

        client.post("/api/v1/auth/login", json={"email": "organiser@connectsphere.dev", "password": "Cs1234"})
        client.post("/api/v1/auth/login", json={"email": TEST_EMAIL, "password": "Cs1234"})

        assert len(created_clients) == 2
        assert created_clients[0] is not created_clients[1]
        for auth_client in created_clients:
            auth_client.auth.sign_in_with_password.assert_called_once()

    def test_login_when_supabase_is_unavailable_returns_503(self, client, monkeypatch):
        """A Supabase outage is not a wrong password: it must not surface as 401 or 500."""
        auth_client = MagicMock()
        auth_client.auth.sign_in_with_password.side_effect = SUPABASE_GATEWAY_UNAVAILABLE
        monkeypatch.setattr(auth_service_module, "create_auth_client", lambda: auth_client)

        response = client.post("/api/v1/auth/login", json={"email": TEST_EMAIL, "password": "Cs1234"})

        assert response.status_code == 503


class TestAuthClientFactory:
    """D1: exercises the real supabase-py client objects (no network) rather than mocks,
    because the defect lived in how the SDK stores and auto-refreshes sessions."""

    def test_create_auth_client_returns_a_new_client_each_call(self):
        from app.db.supabase import create_auth_client

        assert create_auth_client() is not create_auth_client()

    def test_create_auth_client_neither_persists_nor_auto_refreshes_sessions(self):
        from app.db.supabase import create_auth_client

        auth = create_auth_client().auth

        assert auth._persist_session is False
        assert auth._auto_refresh_token is False


class TestLogout:
    def test_logout_revokes_only_the_callers_own_session(self, client, monkeypatch):
        """D1: logout must revoke the caller's token with scope `local`, never whatever
        session happens to be stored on a shared client."""
        anon_client = _authenticate_requests_as_test_user(monkeypatch)
        monkeypatch.setattr(auth_service_module, "get_supabase_anon_client", lambda: anon_client)

        response = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {FAKE_ACCESS_TOKEN}"})

        assert response.status_code == 204
        anon_client.auth.admin.sign_out.assert_called_once_with(FAKE_ACCESS_TOKEN, "local")
        anon_client.auth.sign_out.assert_not_called()

    def test_logout_succeeds_when_session_is_already_revoked(self, client, monkeypatch):
        anon_client = _authenticate_requests_as_test_user(monkeypatch)
        anon_client.auth.admin.sign_out.side_effect = AuthApiError("Session not found", 404, "session_not_found")
        monkeypatch.setattr(auth_service_module, "get_supabase_anon_client", lambda: anon_client)

        response = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {FAKE_ACCESS_TOKEN}"})

        assert response.status_code == 204

    def test_logout_without_token_returns_401(self, client):
        response = client.post("/api/v1/auth/logout")
        assert response.status_code == 401


class TestRefresh:
    def test_refresh_returns_rotated_session_and_profile(self, client, monkeypatch):
        """D4: an expired access token must be renewable without re-entering credentials."""
        auth_client = MagicMock()
        auth_client.auth.refresh_session.return_value = _auth_response(
            access_token="rotated-access-token", refresh_token="rotated-refresh-token"
        )
        monkeypatch.setattr(auth_service_module, "create_auth_client", lambda: auth_client, raising=False)
        monkeypatch.setattr(
            auth_service_module, "get_supabase_anon_client", _shared_client_that_must_not_hold_sessions
        )
        monkeypatch.setattr(
            auth_service_module, "get_supabase_admin_client", lambda: _make_table_mock(PROFILE_ROW)
        )

        response = client.post("/api/v1/auth/refresh", json={"refresh_token": FAKE_REFRESH_TOKEN})

        assert response.status_code == 200
        body = response.json()
        assert body["access_token"] == "rotated-access-token"
        assert body["refresh_token"] == "rotated-refresh-token"
        assert body["profile"]["email"] == TEST_EMAIL
        auth_client.auth.refresh_session.assert_called_once_with(FAKE_REFRESH_TOKEN)

    def test_refresh_with_revoked_or_unknown_token_returns_401(self, client, monkeypatch):
        auth_client = MagicMock()
        auth_client.auth.refresh_session.side_effect = AuthApiError(
            "Invalid Refresh Token: Refresh Token Not Found", 400, "refresh_token_not_found"
        )
        monkeypatch.setattr(auth_service_module, "create_auth_client", lambda: auth_client, raising=False)

        response = client.post("/api/v1/auth/refresh", json={"refresh_token": "revoked-refresh-token"})

        assert response.status_code == 401

    def test_refresh_when_supabase_is_unavailable_returns_503(self, client, monkeypatch):
        """A 401 tells the SPA the session is dead and signs the user out; an outage must not."""
        auth_client = MagicMock()
        auth_client.auth.refresh_session.side_effect = SUPABASE_GATEWAY_UNAVAILABLE
        monkeypatch.setattr(auth_service_module, "create_auth_client", lambda: auth_client)

        response = client.post("/api/v1/auth/refresh", json={"refresh_token": FAKE_REFRESH_TOKEN})

        assert response.status_code == 503

    def test_refresh_with_empty_token_returns_422(self, client):
        response = client.post("/api/v1/auth/refresh", json={"refresh_token": ""})
        assert response.status_code == 422


class TestMe:
    def test_me_with_valid_token_returns_profile(self, client, monkeypatch):
        _authenticate_requests_as_test_user(monkeypatch)

        response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {FAKE_ACCESS_TOKEN}"})

        assert response.status_code == 200
        assert response.json()["email"] == TEST_EMAIL

    def test_me_without_token_returns_401(self, client):
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 401

    def test_me_with_invalid_token_returns_401(self, client):
        # "not-a-real-token" fails Supabase's own local JWT-structure check
        # (no `.`-separated header/payload/signature) before any network call.
        response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
        assert response.status_code == 401

    def test_me_with_expired_or_bad_signature_token_returns_401(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.core.security.get_supabase_anon_client",
            lambda: _make_anon_client_with_claims(raises=AuthInvalidJwtError("JWT has expired")),
        )

        response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {FAKE_ACCESS_TOKEN}"})

        assert response.status_code == 401

    def test_me_with_wrong_audience_returns_401(self, client, monkeypatch):
        wrong_audience_claims = {**_valid_claims(), "aud": "some-other-service"}
        monkeypatch.setattr(
            "app.core.security.get_supabase_anon_client",
            lambda: _make_anon_client_with_claims(wrong_audience_claims),
        )

        response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {FAKE_ACCESS_TOKEN}"})

        assert response.status_code == 401

    def test_me_when_supabase_is_unavailable_returns_503(self, client, monkeypatch):
        """Token verification fetches the JWKS from Supabase; failing to fetch it is not an invalid token."""
        monkeypatch.setattr(
            "app.core.security.get_supabase_anon_client",
            lambda: _make_anon_client_with_claims(raises=SUPABASE_GATEWAY_UNAVAILABLE),
        )

        response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {FAKE_ACCESS_TOKEN}"})

        assert response.status_code == 503

    def test_me_when_profile_row_is_missing_returns_404(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.core.security.get_supabase_anon_client",
            lambda: _make_anon_client_with_claims(_valid_claims()),
        )
        monkeypatch.setattr("app.core.security.get_supabase_admin_client", lambda: _make_table_mock(None))

        response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {FAKE_ACCESS_TOKEN}"})

        assert response.status_code == 404


class TestEventLoopIsNotBlocked:
    def test_concurrent_authenticated_requests_run_in_parallel(self, monkeypatch):
        """D5: supabase-py is synchronous; declaring its callers `async def` blocks the event
        loop, so concurrent requests queue behind each other's network calls."""
        per_request_delay = 0.25
        concurrent_requests = 4
        monkeypatch.setattr(
            "app.core.security.get_supabase_anon_client",
            lambda: _make_anon_client_with_claims(_valid_claims()),
        )
        monkeypatch.setattr(
            "app.core.security.get_supabase_admin_client",
            lambda: _make_table_mock(PROFILE_ROW, delay_seconds=per_request_delay),
        )
        statuses: list[int] = []

        with TestClient(app) as shared_loop_client:

            def _call_me():
                response = shared_loop_client.get(
                    "/api/v1/auth/me", headers={"Authorization": f"Bearer {FAKE_ACCESS_TOKEN}"}
                )
                statuses.append(response.status_code)

            threads = [threading.Thread(target=_call_me) for _ in range(concurrent_requests)]
            started = time.perf_counter()
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            elapsed = time.perf_counter() - started

        assert statuses == [200] * concurrent_requests
        serialised_duration = per_request_delay * concurrent_requests
        assert elapsed < serialised_duration * 0.6, f"requests were serialised: {elapsed:.2f}s"


class TestRoleGuard:
    def test_require_roles_blocks_mismatched_role(self, monkeypatch):
        from app.core.security import CurrentUser, require_roles

        _authenticate_requests_as_test_user(monkeypatch)
        probe_router = APIRouter()

        @probe_router.get("/probe/venue-only")
        def _probe(
            current_user: Annotated[CurrentUser, Depends(require_roles(["venue_staff"]))],
        ) -> dict:
            return {"ok": True}

        # A throwaway app, so the probe route never leaks into the shared `app.main.app`.
        probe_app = FastAPI()
        probe_app.include_router(probe_router)

        response = TestClient(probe_app).get(
            "/probe/venue-only", headers={"Authorization": f"Bearer {FAKE_ACCESS_TOKEN}"}
        )

        assert response.status_code == 403
