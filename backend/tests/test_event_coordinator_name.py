"""D24: the organiser's event read names the assigned coordinator, not only their ID."""
from copy import deepcopy
from types import SimpleNamespace

from app.modules.events import repository
from app.modules.venues import repository as venues_repository
from tests.test_event_review_api import COORDINATOR_ID, EVENT_ID, ORGANISER_ID, event_row


def test_get_event_embeds_the_coordinator_through_the_named_foreign_key(monkeypatch):
    # `events` references `profiles` twice (organiser and coordinator), so a bare
    # `profiles(...)` embed fails the whole query with PGRST201.
    selected = []

    class Query:
        def table(self, name): return self
        def select(self, columns):
            selected.append(columns)
            return self
        def eq(self, field, value): return self
        def maybe_single(self): return self
        def execute(self): return SimpleNamespace(data={"id": EVENT_ID})

    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: Query())

    repository.get_event(EVENT_ID)

    assert "coordinator:profiles!events_coordinator_id_fkey(id, full_name)" in selected[0]


def read_as_organiser(client, auth_headers, authenticate_as, monkeypatch, row):
    monkeypatch.setattr(repository, "get_event", lambda event_id: deepcopy(row))
    monkeypatch.setattr(venues_repository, "get_active_booking", lambda event_id: None)
    authenticate_as("event_organiser", user_id=ORGANISER_ID)
    return client.get(f"/api/v1/events/{EVENT_ID}", headers=auth_headers)


def test_the_organiser_sees_the_assigned_coordinators_name(client, auth_headers, authenticate_as, monkeypatch):
    row = {**event_row("under_review"), "coordinator": {"id": COORDINATOR_ID, "full_name": "Marcus Lim"}}

    response = read_as_organiser(client, auth_headers, authenticate_as, monkeypatch, row)

    assert response.status_code == 200
    assert response.json()["coordinator"] == {"id": COORDINATOR_ID, "full_name": "Marcus Lim"}


def test_an_unassigned_event_has_no_coordinator(client, auth_headers, authenticate_as, monkeypatch):
    row = {**event_row("under_review", coordinator_id=None), "coordinator": None}

    response = read_as_organiser(client, auth_headers, authenticate_as, monkeypatch, row)

    assert response.status_code == 200
    assert response.json()["coordinator"] is None
