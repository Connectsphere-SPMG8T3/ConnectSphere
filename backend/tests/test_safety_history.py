"""CR-103 AC7: the Safety Officer dashboard's recent decisions, across events."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.modules.events import repository
from tests.test_event_comments_api import acting_as_another_role
from tests.test_event_review_api import COORDINATOR_ID
from tests.test_safety_decisions_api import ROLES

URL = "/api/v1/events/safety-history"


def history_row(id, decision, decided_at, decided_by_name="Hafiz Ismail", comment="Crowd near exit"):
    return dict(id=id, event_id="e0000000-0000-4000-8000-000000000831", event_name="Year-End Dinner",
                decision=decision, comment=comment, decided_by_name=decided_by_name, decided_at=decided_at)


@pytest.fixture()
def state(monkeypatch):
    state = {"rows": [], "since": None}

    def list_recent(since):
        state["since"] = since
        return deepcopy(state["rows"])

    monkeypatch.setattr(repository, "list_recent_safety_decisions", list_recent, raising=False)
    return state


def test_officer_reads_every_recent_decision_newest_first(client, auth_headers, authenticate_as, state):
    authenticate_as("safety_officer")
    state["rows"] = [
        history_row("a0000000-0000-4000-8000-0000000000a1", "approved", "2026-10-01T01:00:00Z"),
        history_row("a0000000-0000-4000-8000-0000000000a3", "withdrawn", "2026-10-09T01:00:00Z",
                    decided_by_name=None, comment=None),
        history_row("a0000000-0000-4000-8000-0000000000a2", "arrangement_rejected", "2026-10-05T01:00:00Z"),
    ]
    response = client.get(URL, headers=auth_headers)
    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["decision"] for item in items] == ["withdrawn", "arrangement_rejected", "approved"]
    assert items[0]["decided_by_name"] is None and items[0]["comment"] is None
    assert items[1] == dict(id="a0000000-0000-4000-8000-0000000000a2", event_id="e0000000-0000-4000-8000-000000000831",
                            event_name="Year-End Dinner", decision="arrangement_rejected", comment="Crowd near exit",
                            decided_by_name="Hafiz Ismail", decided_at="2026-10-05T01:00:00Z",
                            affected_bookings=[], affected_equipment=[], rejected_venues=[], revision=None)


def test_reads_only_the_last_30_days(client, auth_headers, authenticate_as, state):
    authenticate_as("safety_officer")
    before = datetime.now(timezone.utc)
    assert client.get(URL, headers=auth_headers).status_code == 200
    after = datetime.now(timezone.utc)
    assert before - timedelta(days=30) <= state["since"] <= after - timedelta(days=30)


def test_no_recent_decisions_is_an_empty_list(client, auth_headers, authenticate_as, state):
    authenticate_as("safety_officer")
    assert client.get(URL, headers=auth_headers).json() == {"items": []}


@pytest.mark.parametrize("role", ROLES)
def test_other_roles_are_denied(client, auth_headers, authenticate_as, state, role):
    authenticate_as(role, COORDINATOR_ID)
    assert client.get(URL, headers=auth_headers).status_code == 403
    assert state["since"] is None


def test_officer_acting_as_another_role_is_denied(client, auth_headers, monkeypatch, state):
    acting_as_another_role(monkeypatch, COORDINATOR_ID, "safety_officer", "event_coordinator")
    assert client.get(URL, headers=auth_headers).status_code == 403


def test_outage_is_503(client, auth_headers, authenticate_as, monkeypatch):
    authenticate_as("safety_officer")

    def unavailable(_):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(repository, "list_recent_safety_decisions", unavailable, raising=False)
    assert client.get(URL, headers=auth_headers).status_code == 503
