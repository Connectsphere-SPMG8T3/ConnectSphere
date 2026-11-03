"""D53/D54: named CR-104 decisions and the first coordinator response."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.modules.events import service, repository
from app.modules.venues import service as venues, repository as venues_repository
from app.modules.equipment import service as equipment, repository as equipment_repository
from tests.test_event_review_api import EVENT_ID, COORDINATOR_ID
from tests.test_safety_queue_and_review import state, DECISION, BOOKING, LINE  # noqa: F401

B1, L1, V1 = BOOKING, LINE, str(uuid4())
ROW = dict(DECISION)
URL = f"/api/v1/events/{EVENT_ID}/safety-decisions"
REVIEW_URL = f"/api/v1/events/{EVENT_ID}/safety-review"


@pytest.fixture()
def decisions(monkeypatch, state):
    data = dict(rows=[], booking_names={}, venue_names={}, line_names={}, revisions=[], calls={})
    monkeypatch.setattr(repository, "list_safety_decisions", lambda _: deepcopy(data["rows"]))
    for module, name, key in [(venues, "booking_venue_names", "booking_names"),
                              (venues, "venue_names", "venue_names"),
                              (venues, "safety_revisions", "revisions"),
                              (equipment, "line_names", "line_names")]:
        def lookup(ids, name=name, key=key):
            data["calls"][name] = data["calls"].get(name, 0) + 1
            return deepcopy(data[key])
        monkeypatch.setattr(module, name, lookup, raising=False)
    return data


@pytest.mark.parametrize("role", ["safety_officer", "event_coordinator"])
def test_decisions_name_their_venues_equipment_and_rejected_venue(client, auth_headers, authenticate_as, decisions, role):
    decisions["rows"] = [dict(ROW, decision="arrangement_rejected", affected_booking_ids=[B1], rejected_venue_ids=[V1], affected_equipment_request_ids=[L1])]
    decisions.update(booking_names={B1: "Heritage Hall"}, venue_names={V1: "Heritage Hall"}, line_names={L1: "Projector"})
    authenticate_as(role, COORDINATOR_ID)
    response = client.get(URL, headers=auth_headers)
    assert response.status_code == 200
    [body] = response.json()
    assert body["affected_bookings"] == [{"booking_id": B1, "venue_name": "Heritage Hall"}]
    assert body["rejected_venues"] == [{"venue_id": V1, "venue_name": "Heritage Hall"}]
    assert body["affected_equipment"] == [{"id": L1, "equipment_name": "Projector"}]
    assert body["affected_booking_ids"] == [B1]


def test_a_rejection_carries_the_first_response_after_it(client, auth_headers, authenticate_as, decisions):
    decisions["rows"] = [dict(ROW, decision="arrangement_rejected", affected_booking_ids=[B1], decided_at="2031-01-01T10:00:00Z")]
    decisions["revisions"] = [
        dict(booking_id=B1, note=note, by_name="Marcus", at=at) for note, at in [
            ("Before", "2030-12-31T10:00:00Z"), ("At decision", "2031-01-01T10:00:00Z"),
            ("Moved the barriers", "2031-01-02T10:00:00Z"), ("Later", "2031-01-03T10:00:00Z")]]
    authenticate_as("safety_officer")
    [body] = client.get(URL, headers=auth_headers).json()
    assert body["revision"]["note"] == "Moved the barriers"
    assert body["revision"]["by_name"] == "Marcus"


def test_missing_names_are_null_and_other_decisions_have_no_revision(client, auth_headers, authenticate_as, decisions):
    decisions["rows"] = [dict(ROW, affected_booking_ids=[B1], affected_equipment_request_ids=[L1], rejected_venue_ids=[V1])]
    authenticate_as("safety_officer")
    [body] = client.get(URL, headers=auth_headers).json()
    assert body["affected_bookings"] == [{"booking_id": B1, "venue_name": None}]
    assert body["affected_equipment"] == [{"id": L1, "equipment_name": None}]
    assert body["rejected_venues"] == [{"venue_id": V1, "venue_name": None}]
    assert body["revision"] is None


def test_lookups_run_once_for_all_decisions(client, auth_headers, authenticate_as, decisions):
    decisions["rows"] = [dict(ROW, id=str(uuid4()), affected_booking_ids=[B1]) for _ in range(5)]
    authenticate_as("safety_officer")
    assert client.get(URL, headers=auth_headers).status_code == 200
    assert decisions["calls"] == dict(booking_venue_names=1, venue_names=1, line_names=1, safety_revisions=1)


@pytest.mark.parametrize("latest", [False, True])
def test_review_and_coordinator_latest_use_named_decisions(client, auth_headers, authenticate_as, decisions, state, latest):
    decisions["rows"] = [dict(ROW, affected_booking_ids=[B1])]
    decisions["booking_names"] = {B1: "Heritage Hall"}
    if latest:
        state["event"]["status"] = "planning"
    authenticate_as("event_coordinator" if latest else "safety_officer", COORDINATOR_ID)
    response = client.get(f"/api/v1/events/{EVENT_ID}" if latest else REVIEW_URL, headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    decision = body["latest_safety_decision"] if latest else body["decisions"][0]
    assert decision["affected_bookings"][0]["venue_name"] == "Heritage Hall"


@pytest.mark.parametrize("module,name,table,ids_key,rows,expected", [
    (venues_repository, "booking_venue_names", "venue_bookings", "id", [{"id": B1, "venue": {"name": "Hall"}}], {B1: "Hall"}),
    (venues_repository, "venue_names", "venues", "id", [{"id": B1, "name": "Hall"}], {B1: "Hall"}),
    (equipment_repository, "line_names", "equipment_requests", "id", [{"id": B1, "equipment": {"name": "Projector"}}], {B1: "Projector"}),
    (venues_repository, "safety_revisions", "venue_booking_history", "booking_id", [{"booking_id": B1, "reason": "Moved", "actor": {"full_name": "Marcus"}, "created_at": "2031-01-02T10:00:00Z"}], [{"booking_id": B1, "note": "Moved", "by_name": "Marcus", "at": "2031-01-02T10:00:00Z"}]),
])
def test_repository_lookups_batch_and_short_circuit(monkeypatch, module, name, table, ids_key, rows, expected):
    admin, query = MagicMock(), MagicMock()
    admin.table.return_value = query
    for method in ("select", "eq", "in_", "is_", "order"):
        getattr(query, method).return_value = query
    query.not_ = query
    query.execute.return_value = SimpleNamespace(data=rows)
    monkeypatch.setattr(module, "get_supabase_admin_client", lambda: admin)
    lookup = getattr(module, name, None)
    assert callable(lookup), f"{name} lookup exists"
    assert lookup([]) == ([] if name == "safety_revisions" else {})
    admin.table.assert_not_called()
    assert lookup([B1]) == expected
    admin.table.assert_called_once_with(table)
    query.in_.assert_called_once_with(ids_key, [B1])
    query.execute.assert_called_once()
    if name == "safety_revisions":
        query.eq.assert_called_once_with("action", "safety_revised")
        query.is_.assert_not_called()  # Keep legacy null-note revisions as cycle boundaries.
        query.order.assert_called_once_with("created_at")


def test_dashboard_history_uses_the_same_names_and_response(client, auth_headers, authenticate_as, decisions, monkeypatch):
    row = dict(ROW, event_id=EVENT_ID, event_name="Partner Summit", decision="arrangement_rejected",
               affected_booking_ids=[B1], rejected_venue_ids=[V1])
    monkeypatch.setattr(repository, "list_recent_safety_decisions", lambda _: [row])
    decisions["booking_names"] = {B1: "Heritage Hall"}
    decisions["venue_names"] = {V1: "Heritage Hall"}
    decisions["revisions"] = [dict(booking_id=B1, note="Moved the barriers", by_name="Marcus", at="2031-01-02T10:00:00Z")]
    authenticate_as("safety_officer")
    response = client.get("/api/v1/events/safety-history", headers=auth_headers)
    assert response.status_code == 200
    [body] = response.json()["items"]
    assert body["rejected_venues"] == [{"venue_id": V1, "venue_name": "Heritage Hall"}]
    assert body["affected_bookings"] == [{"booking_id": B1, "venue_name": "Heritage Hall"}]
    assert body["revision"]["note"] == "Moved the barriers"
    assert body["event_name"] == "Partner Summit"


def test_legacy_revision_without_note_does_not_borrow_the_next_cycles_response(client, auth_headers, authenticate_as, decisions):
    first = dict(ROW, decision="arrangement_rejected", affected_booking_ids=[B1], decided_at="2031-01-01T10:00:00Z")
    second = dict(first, id=str(uuid4()), decided_at="2031-01-03T10:00:00Z")
    decisions["rows"] = [second, first]
    decisions["revisions"] = [
        dict(booking_id=B1, note=None, by_name="Marcus", at="2031-01-02T10:00:00Z"),
        dict(booking_id=B1, note="Second cycle response", by_name="Marcus", at="2031-01-04T10:00:00Z"),
    ]
    authenticate_as("safety_officer")
    response = client.get(URL, headers=auth_headers)
    assert response.status_code == 200
    later, legacy = response.json()
    assert later["revision"]["note"] == "Second cycle response"
    assert legacy["revision"] is None


def test_recent_decision_repository_includes_arrangement_ids(monkeypatch):
    from datetime import datetime, timezone
    query, admin = MagicMock(), MagicMock()
    admin.table.return_value = query
    query.select.return_value = query.gte.return_value = query.order.return_value = query
    query.execute.return_value = SimpleNamespace(data=[dict(ROW, event_id=EVENT_ID,
        affected_booking_ids=[B1], affected_equipment_request_ids=[L1], rejected_venue_ids=[V1],
        event={"name": "Summit"})])
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: admin)
    [row] = repository.list_recent_safety_decisions(datetime.now(timezone.utc))
    assert row["affected_booking_ids"] == [B1]
    assert row["affected_equipment_request_ids"] == [L1]
    assert row["rejected_venue_ids"] == [V1]
    for field in ("affected_booking_ids", "affected_equipment_request_ids", "rejected_venue_ids"):
        assert field in query.select.call_args.args[0]


def test_checklist_rows_are_named_by_venue_and_looked_up_once(client, auth_headers, authenticate_as, decisions):
    # CR-108 AC2: the venue factors are answered per booking, so each row names its venue.
    rows = [dict(factor="layout", booking_id=B1, rating="concern", note="Aisle too narrow"),
            dict(factor="equipment_placement", booking_id=None, rating="satisfactory", note=None)]
    decisions["rows"] = [dict(ROW, id=str(uuid4()), checklist=rows) for _ in range(3)]
    decisions["booking_names"] = {B1: "Heritage Hall"}
    authenticate_as("safety_officer")
    response = client.get(URL, headers=auth_headers)
    assert response.status_code == 200
    for body in response.json():
        assert body["checklist"] == [
            dict(factor="layout", booking_id=B1, venue_name="Heritage Hall", rating="concern", note="Aisle too narrow"),
            dict(factor="equipment_placement", booking_id=None, venue_name=None, rating="satisfactory", note=None)]
    assert decisions["calls"]["booking_venue_names"] == 1


def test_dashboard_history_carries_both_texts_for_officers(client, auth_headers, authenticate_as, decisions, monkeypatch):
    row = dict(ROW, event_id=EVENT_ID, event_name="Partner Summit", organiser_comment="Fix the exits")
    monkeypatch.setattr(repository, "list_recent_safety_decisions", lambda _: [row])
    authenticate_as("safety_officer")
    [body] = client.get("/api/v1/events/safety-history", headers=auth_headers).json()["items"]
    assert body["organiser_comment"] == "Fix the exits"
    assert body["private_note"] == ROW["comment"]
