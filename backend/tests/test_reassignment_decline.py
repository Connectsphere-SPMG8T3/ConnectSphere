"""CR-106 AC5: a Lead declines a coordinator's reassignment request with a reason,
`POST /events/{id}/reassignment-request/decline`. The RPC's own guards are checked against
the real database by supabase/verification/reassignment_request_checks.sql."""

from types import SimpleNamespace

import pytest

from app.modules.events import repository

LEAD = "a0000000-0000-4000-8000-0000000000a1"
OTHER_LEAD = "a0000000-0000-4000-8000-0000000000a2"
COORDINATOR = "a0000000-0000-4000-8000-000000000002"
EVENT = "e0000000-0000-4000-8000-0000000010e1"
REQUEST_ID = "c0000000-0000-4000-8000-000000001061"
REASON = "No other coordinator is free this month"


def lead_row(**overrides):
    row = {
        "id": EVENT, "name": "Annual Conference", "status": "planning", "version": 3,
        "coordinator_id": COORDINATOR, "assigned_by": LEAD, "assigned_at": "2026-10-20T00:00:00Z",
        "coordinator": {"id": COORDINATOR, "full_name": "Marcus Lim"}, "organiser": {"full_name": "Olivia Tan"},
    }
    row.update(overrides)
    return row


@pytest.fixture()
def data(monkeypatch):
    state = SimpleNamespace(event=lead_row(), lead_ids={LEAD}, outcome="ok", calls=[])
    monkeypatch.setattr(repository, "get_lead_event", lambda event_id: state.event)
    monkeypatch.setattr(repository, "list_lead_ids", lambda: state.lead_ids)

    def decline_reassignment_request(event_id, lead_id, reason, coordinator_message):
        state.calls.append({"event_id": event_id, "lead_id": lead_id, "reason": reason,
                            "coordinator_message": coordinator_message})
        if state.outcome != "ok":
            return {"outcome": state.outcome, "request": None}
        return {"outcome": "ok", "request": {
            "id": REQUEST_ID, "kind": "reassignment", "status": "declined", "reason": "On leave",
            "requested_by": {"id": COORDINATOR, "full_name": "Marcus Lim"},
            "requested_at": "2026-10-27T09:00:00+00:00",
        }}

    monkeypatch.setattr(repository, "decline_reassignment_request", decline_reassignment_request, raising=False)
    return state


@pytest.fixture()
def as_lead(authenticate_as):
    def _as(role="event_coordinator_lead", user_id=LEAD):
        return authenticate_as(role, user_id=user_id)
    return _as


def decline(client, auth_headers, reason=REASON, event_id=EVENT):
    return client.post(f"/api/v1/events/{event_id}/reassignment-request/decline",
                       json={"reason": reason}, headers=auth_headers)


def test_the_lead_declines_with_a_reason_and_the_coordinator_is_told(client, auth_headers, as_lead, data):
    as_lead()

    response = decline(client, auth_headers)

    assert response.status_code == 200
    assert response.json()["status"] == "declined"
    [call] = data.calls
    assert call["event_id"] == EVENT and call["lead_id"] == LEAD and call["reason"] == REASON
    assert "Annual Conference" in call["coordinator_message"]
    assert REASON in call["coordinator_message"]


def test_the_reason_is_trimmed(client, auth_headers, as_lead, data):
    as_lead()

    decline(client, auth_headers, reason=f"  {REASON}  ")

    assert data.calls[0]["reason"] == REASON


@pytest.mark.parametrize("reason", ["", "   ", None])
def test_a_reason_is_required(client, auth_headers, as_lead, data, reason):
    as_lead()

    assert decline(client, auth_headers, reason=reason).status_code == 422
    assert data.calls == []


def test_declining_changes_no_assignment(client, auth_headers, as_lead, data, monkeypatch):
    reassigned = []
    monkeypatch.setattr(repository, "reassign_event", lambda *a, **k: reassigned.append(a))
    as_lead()

    decline(client, auth_headers)

    assert reassigned == []


def test_no_open_request_is_a_conflict(client, auth_headers, as_lead, data):
    data.outcome = "no_open_request"
    as_lead()

    response = decline(client, auth_headers)

    assert response.status_code == 409
    assert "no open" in response.json()["detail"].lower()


def test_a_missing_event_or_draft_is_not_found(client, auth_headers, as_lead, data):
    as_lead()
    data.event = None
    assert decline(client, auth_headers).status_code == 404
    data.event = lead_row(status="draft")
    assert decline(client, auth_headers).status_code == 404
    assert data.calls == []


def test_an_event_another_current_lead_manages_is_forbidden(client, auth_headers, as_lead, data):
    data.lead_ids = {LEAD, OTHER_LEAD}
    data.event = lead_row(assigned_by=OTHER_LEAD)
    as_lead()

    assert decline(client, auth_headers).status_code == 403
    assert data.calls == []


@pytest.mark.parametrize("role", ["event_coordinator", "event_organiser"])
def test_only_the_lead_may_decline(client, auth_headers, as_lead, data, role):
    """The active role decides. The assigned coordinator can't decline their own request."""
    as_lead(role=role, user_id=COORDINATOR)

    assert decline(client, auth_headers).status_code == 403
    assert data.calls == []


def test_the_rpc_rechecks_the_outcome(client, auth_headers, as_lead, data):
    data.outcome = "not_found"
    as_lead()

    assert decline(client, auth_headers).status_code == 404
