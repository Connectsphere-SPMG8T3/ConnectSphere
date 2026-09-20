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