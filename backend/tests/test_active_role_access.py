"""Endpoint access follows the session's *active* role, never every role held (SCRUM-76).

An account can hold several roles but acts as one per login session. Whatever an
endpoint decides for an account acting as role Y must be exactly what it decides
for an account whose only role is Y, so holding another, permitted role must
never open the endpoint. The matrix runs over every route the app mounts, so a
new endpoint is covered automatically and one left open to every role fails.

The database half of SCRUM-76 (private.current_user_role() reads the active role)
is checked against the real project by supabase/verification/active_role_checks.sql.
"""

import uuid

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from tests.conftest import make_table_mock

settings = get_settings()
ROLES = [
    "event_organiser",
    "event_coordinator",
    "event_coordinator_lead",
    "venue_staff",
    "tech_support",
    "safety_officer",
    "attendee",
]
USER_ID = "11111111-1111-1111-1111-111111111111"
SESSION_ID = "22222222-2222-2222-2222-222222222222"
# Auth endpoints are public or open to any signed-in user by design.
OPEN_PREFIX = f"{settings.api_v1_prefix}/auth"


def _protected_routes() -> list[tuple[str, str]]:
    routes = []
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith(settings.api_v1_prefix):
            continue
        if route.path.startswith(OPEN_PREFIX):
            continue
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            routes.append((method, route.path))
    return routes


def _concrete(path: str) -> str:
    """Fill each `{param}` with a UUID so the URL matches the route."""
    parts = [str(uuid.uuid4()) if part.startswith("{") else part for part in path.split("/")]
    return "/".join(parts)


@pytest.fixture()
def raw_client() -> TestClient:
    # A handler that trips over the empty mocked data raises 500 rather than the
    # test client re-raising it: only the access decision is under test.
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def request_as(monkeypatch, raw_client):
    """Send a request as an account whose default role is `default_role` and whose
    session is acting as `active_role` (a `session_active_roles` row when they differ).
    """

    def _request(method: str, path: str, *, default_role: str, active_role: str) -> int:
        profile = {
            "id": USER_ID,
            "email": "multi@connectsphere.dev",
            "full_name": "Multi Role",
            "role": default_role,
            "organisation_name": None,
            "department": None,
            "phone_number": None,
        }
        session_row = {"role": active_role} if active_role != default_role else None
        anon_client = type("Anon", (), {})()
        anon_client.auth = type("Auth", (), {})()
        anon_client.auth.get_claims = lambda token: {
            "claims": {"sub": USER_ID, "aud": "authenticated", "email": profile["email"], "session_id": SESSION_ID}
        }
        monkeypatch.setattr("app.core.security.get_supabase_anon_client", lambda: anon_client)
        monkeypatch.setattr(
            "app.core.security.get_supabase_admin_client",
            lambda: make_table_mock(profile, session_active_role=session_row),
        )
        response = raw_client.request(
            method, _concrete(path), headers={"Authorization": "Bearer raw-request-token"}, json={}
        )
        return response.status_code

    return _request


@pytest.mark.parametrize(("method", "path"), _protected_routes())
def test_a_role_held_but_not_active_never_opens_the_endpoint(request_as, method, path):
    """Acting as Y while also holding X is denied exactly when a Y-only account is."""
    for active_role in ROLES:
        only_this_role = request_as(method, path, default_role=active_role, active_role=active_role) == 403
        for held_role in ROLES:
            if held_role == active_role:
                continue
            holds_another = request_as(method, path, default_role=held_role, active_role=active_role) == 403
            assert holds_another == only_this_role, (
                f"{method} {path}: acting as {active_role} while also holding {held_role} "
                f"was {'denied' if holds_another else 'allowed'}, but a {active_role}-only account is "
                f"{'denied' if only_this_role else 'allowed'}"
            )


@pytest.mark.parametrize(("method", "path"), _protected_routes())
def test_every_protected_endpoint_names_the_roles_it_allows(request_as, method, path):
    """An endpoint no role is denied on has no role gate and would serve any signed-in user."""
    denied = [r for r in ROLES if request_as(method, path, default_role=r, active_role=r) == 403]
    assert denied, f"{method} {path} is not restricted to any role: add require_roles([...])"
    assert len(denied) < len(ROLES), f"{method} {path} denies every role, so nobody can use it"


def test_the_matrix_covers_the_mounted_modules():
    covered = {path.split("/")[3] for _, path in _protected_routes()}
    assert {"events", "venues"} <= covered
