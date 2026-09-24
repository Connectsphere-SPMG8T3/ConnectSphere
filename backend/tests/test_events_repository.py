from types import SimpleNamespace
from app.modules.events import repository


def test_update_event_reads_the_updated_row_from_a_list_response(monkeypatch):
    updated_row = {"id": "event-1", "name": "Updated workshop", "version": 2}

    class UpdateQuery:
        def update(self, values):
            self.values = values
            return self

        def eq(self, field, value):
            return self

        def select(self, columns):
            return self

        def execute(self):
            return SimpleNamespace(data=[updated_row])

    class AdminClient:
        def table(self, name):
            return UpdateQuery()

    client = AdminClient()
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: client)

    result = repository.update_event("event-1", {"name": "Updated workshop"}, 1)

    assert result == updated_row

def test_status_history_puts_the_creation_entry_last_when_timestamps_tie(monkeypatch):
    """A creation row (no from_status) and a later row can share a timestamp,
    e.g. seeded events whose created_at and submitted_at are both now(); newest
    first must still end with the creation row."""
    orders = []

    class HistoryQuery:
        def select(self, columns):
            return self

        def eq(self, field, value):
            return self

        def order(self, column, *, desc=False, nullsfirst=None):
            orders.append((column, desc, nullsfirst))
            return self

        def execute(self):
            return SimpleNamespace(data=[])

    class AdminClient:
        def table(self, name):
            return HistoryQuery()

    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: AdminClient())

    repository.list_status_history("event-1")

    assert orders == [("at", True, None), ("from_status", True, False)]
