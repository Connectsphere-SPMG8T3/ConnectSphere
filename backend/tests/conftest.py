import os

os.environ.setdefault("SUPABASE_URL", "https://vuiryrzzyfecjqftwicj.supabase.co")
os.environ.setdefault("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test-key")
os.environ.setdefault("SUPABASE_SECRET_KEY", "sb_secret_test-key")

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app

FAKE_ACCESS_TOKEN = "fake-access-token"  # nosec: opaque in tests; verification is mocked, not decoded


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {FAKE_ACCESS_TOKEN}"}


def _profile_table_mock(row: dict) -> MagicMock:
    """Replicates `.table("profiles").select(...).eq(...).maybe_single().execute()`."""
    query = MagicMock()
    query.select.return_value = query
    query.eq.return_value = query
    query.maybe_single.return_value = query
    query.execute.return_value = SimpleNamespace(data=row)
    table_client = MagicMock()
    table_client.table.return_value = query
    return table_client


@pytest.fixture()
def authenticate_as(monkeypatch):
    """Make every request verify as a user with the given profile role.

    Patches the two Supabase clients behind `app.core.security` so the JWT
    check and the profile lookup succeed offline; modules under test still
    mock their own data access separately.
    """

    def _authenticate(role: str, user_id: str = "11111111-1111-1111-1111-111111111111") -> dict:
        profile = {
            "id": user_id,
            "email": f"{role}@connectsphere.dev",
            "full_name": f"Test {role}",
            "role": role,
            "organisation_name": None,
            "department": None,
            "phone_number": None,
        }
        anon_client = MagicMock()
        anon_client.auth.get_claims.return_value = {
            "claims": {"sub": user_id, "aud": "authenticated", "email": profile["email"]}
        }
        monkeypatch.setattr("app.core.security.get_supabase_anon_client", lambda: anon_client)
        monkeypatch.setattr("app.core.security.get_supabase_admin_client", lambda: _profile_table_mock(profile))
        return profile

    return _authenticate
