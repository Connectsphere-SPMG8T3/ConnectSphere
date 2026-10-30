import os

os.environ.setdefault("SUPABASE_URL", "https://vuiryrzzyfecjqftwicj.supabase.co")
os.environ.setdefault("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test-key")
os.environ.setdefault("SUPABASE_SECRET_KEY", "sb_secret_test-key")

import threading
import time
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


def make_table_mock(
    profile_row: dict | None,
    *,
    profile_update: dict | None = None,
    delay_seconds: float = 0.0,
    session_active_role: dict | None = None,
    user_roles: list[dict] | None = None,
) -> MagicMock:
    """Build a mock replicating `.table(name)...execute()`, routed by table name.

    `profiles` and `session_active_roles` each return one row (or none) via
    `.maybe_single()`; `user_roles` returns a list. Routing by table name (as
    opposed to one canned response for every `.table()` call) matters once a
    request touches more than one table — `get_current_user` alone queries
    both `profiles` and `session_active_roles` — since a single-shape mock
    would otherwise hand `session_active_roles` a `profiles` row and read
    whatever meaning out of its `role` key was left over. `delay_seconds` only
    delays the `profiles` lookup, matching the one query call sites that time
    it expect.
    """

    def _build_query(name: str) -> MagicMock:
        query = MagicMock()
        query.select.return_value = query
        query.eq.return_value = query
        query.update.return_value = query
        query.maybe_single.return_value = query
        query.upsert.return_value = query
        query.order.return_value = query

        if name == "profiles":

            def _execute():
                if delay_seconds:
                    time.sleep(delay_seconds)
                data = ([profile_update] if profile_update else []) if query.update.called else profile_row
                return SimpleNamespace(data=data)

            query.execute.side_effect = _execute
        elif name == "session_active_roles":
            query.execute.side_effect = lambda: SimpleNamespace(data=session_active_role)
        elif name == "user_roles":
            query.execute.side_effect = lambda: SimpleNamespace(data=user_roles or [])
        else:
            query.execute.side_effect = lambda: SimpleNamespace(data=None)

        return query

    # One query mock per table name, reused across calls, so a test can assert
    # on `admin_client.table("...")` after the request already ran. Guarded by
    # a lock because TestEventLoopIsNotBlocked drives this same mock from
    # several real threads at once, and the check-then-act on the dict would
    # otherwise be a race (currently benign — every build for the same name is
    # equivalent — but a future test asserting identity on the first-built
    # mock under concurrency could get a different, if equivalent, instance).
    queries_by_table: dict[str, MagicMock] = {}
    lock = threading.Lock()

    def _query_for(name: str) -> MagicMock:
        with lock:
            if name not in queries_by_table:
                queries_by_table[name] = _build_query(name)
            return queries_by_table[name]

    table_client = MagicMock()
    table_client.table.side_effect = _query_for
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
        session_id = "22222222-2222-2222-2222-222222222222"
        anon_client = MagicMock()
        anon_client.auth.get_claims.return_value = {
            "claims": {
                "sub": user_id,
                "aud": "authenticated",
                "email": profile["email"],
                "session_id": session_id,
            }
        }
        monkeypatch.setattr("app.core.security.get_supabase_anon_client", lambda: anon_client)
        monkeypatch.setattr("app.core.security.get_supabase_admin_client", lambda: make_table_mock(profile))
        return profile

    return _authenticate


@pytest.fixture(autouse=True)
def safety_decisions_offline(monkeypatch, request):
    """Older event-read fixtures predate CR-104; default to no decision rows.

    Safety tests override this with their own decision data. No old test may
    reach the real decision table through an eligible event read.
    """
    if request.node.path.name != "test_safety_contracts.py":
        monkeypatch.setattr("app.modules.events.repository.list_safety_decisions", lambda event_id: [])


@pytest.fixture(autouse=True)
def change_history_offline(monkeypatch, request):
    """Event history reads predate story 62; default to no recorded edits.

    Story 62's tests set their own, and the repository's own test needs the real
    function. No other test may reach the real table through a history read.
    """
    if request.node.path.name != "test_events_repository.py":
        monkeypatch.setattr("app.modules.events.repository.list_edit_history", lambda event_id: [])
        monkeypatch.setattr("app.modules.venues.service.event_booking_history", lambda event_id: [])
        monkeypatch.setattr("app.modules.equipment.service.event_technical_history", lambda event_id: [])
        monkeypatch.setattr("app.modules.venues.service.event_venue_edits", lambda event_id: [])


@pytest.fixture(autouse=True)
def cancellation_requests_offline(monkeypatch, request):
    """Event reads predate stories 84 and 32; default to no cancellation or change requests.

    Cancellation tests set their own request, and the repository's own test
    needs the real function. No other test may reach the real table through an
    event read.
    """
    if request.node.path.name != "test_events_repository.py":
        monkeypatch.setattr("app.modules.events.repository.get_open_cancellation_request", lambda event_id: None)
        monkeypatch.setattr("app.modules.events.repository.list_cancellation_requests", lambda event_id: [])
        monkeypatch.setattr("app.modules.events.repository.list_open_cancellation_requests", lambda event_ids: {})
        monkeypatch.setattr("app.modules.events.repository.get_open_change_request", lambda event_id: None)
        monkeypatch.setattr("app.modules.events.repository.list_change_requests", lambda event_id: [])
        monkeypatch.setattr("app.modules.events.repository.list_open_change_requests", lambda event_ids: {})


@pytest.fixture(autouse=True)
def rejected_bookings_offline(monkeypatch, request):
    """Coordinator event reads predate SCRUM-38; default to no rejected bookings.

    Tests about rejections set their own rows, and the repository's own test
    needs the real function. No other test may reach the real booking table
    through a coordinator's event read.
    """
    if request.node.path.name != "test_venue_booking_decision_repository.py":
        monkeypatch.setattr("app.modules.venues.repository.list_rejected_bookings", lambda event_id: [])


@pytest.fixture(autouse=True)
def active_space_bookings_offline(monkeypatch, request):
    """Event-read tests default to no per-space bookings unless they provide rows.

    Keep API tests isolated from Supabase when the branch adds the space-booking
    read path; the helper's mapping behavior has its own repository-backed test.
    """
    # Stubbed at the repository, like the two fixtures above, so a test can
    # supply rows and the service's per-space mapping still runs (CR-97).
    if request.node.name != "test_list_active_bookings_reads_rows_and_returns_empty_on_schema_read_failure":
        monkeypatch.setattr("app.modules.venues.repository.list_active_bookings", lambda event_id: [])
