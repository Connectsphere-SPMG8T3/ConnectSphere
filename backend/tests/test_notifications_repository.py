"""113 notifications repository: every query is scoped to the recipient AND the active role."""

from types import SimpleNamespace

import pytest

from app.modules.notifications import repository

USER = "a0000000-0000-4000-8000-000000000002"
ROLE = "event_coordinator"


class Recorder:
    """A Supabase query builder that records every call and answers `execute()`."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return self
        return record

    def execute(self):
        self.calls.append(("execute", (), {}))
        return self.responses.pop(0)

    def has(self, name, *args, **kwargs):
        return (name, args, kwargs) in self.calls

    def names(self):
        return [c[0] for c in self.calls]


class Client:
    def __init__(self, *responses):
        self.queries = []
        self.responses = list(responses)

    def table(self, name):
        assert name == "notifications"
        query = Recorder([self.responses.pop(0)])
        self.queries.append(query)
        return query


@pytest.fixture()
def use_client(monkeypatch):
    def _use(*responses):
        client = Client(*responses)
        monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: client)
        return client
    return _use


def scoped(query):
    return query.has("eq", "recipient_id", USER) and query.has("eq", "recipient_role", ROLE)


class TestCountUnread:
    def test_counts_unread_rows_and_reports_the_newest_row(self, use_client):
        client = use_client(SimpleNamespace(data=[{"id": "1"}], count=3),
                            SimpleNamespace(data=[{"created_at": "2026-10-20T03:00:00+00:00"}]))

        result = repository.count_unread(USER, ROLE)

        assert result == {"count": 3, "latest_at": "2026-10-20T03:00:00+00:00"}
        counted, newest = client.queries
        assert scoped(counted) and counted.has("is_", "read_at", "null")
        assert scoped(newest) and newest.has("order", "created_at", desc=True)

    def test_no_rows_is_zero_and_none(self, use_client):
        use_client(SimpleNamespace(data=[], count=0), SimpleNamespace(data=[]))

        assert repository.count_unread(USER, ROLE) == {"count": 0, "latest_at": None}

    def test_a_missing_count_is_zero(self, use_client):
        use_client(SimpleNamespace(data=[], count=None), SimpleNamespace(data=None))

        assert repository.count_unread(USER, ROLE) == {"count": 0, "latest_at": None}


class TestListPage:
    def test_newest_first_with_a_one_row_look_ahead(self, use_client):
        rows = [{"id": "b"}, {"id": "a"}]
        client = use_client(SimpleNamespace(data=rows))

        assert repository.list_page(USER, ROLE, 20, None) == rows

        [query] = client.queries
        assert scoped(query)
        assert query.has("order", "created_at", desc=True) and query.has("order", "id", desc=True)
        assert query.has("limit", 21)
        assert "or_" not in query.names()

    def test_after_a_cursor_it_asks_for_strictly_older_rows(self, use_client):
        client = use_client(SimpleNamespace(data=[]))

        repository.list_page(USER, ROLE, 5, ("2026-10-20T03:00:00+00:00", "id-9"))

        [query] = client.queries
        assert query.has(
            "or_",
            "created_at.lt.2026-10-20T03:00:00+00:00,"
            "and(created_at.eq.2026-10-20T03:00:00+00:00,id.lt.id-9)",
        )

    def test_no_data_is_an_empty_list(self, use_client):
        use_client(SimpleNamespace(data=None))

        assert repository.list_page(USER, ROLE, 5, None) == []


class TestMarkRead:
    def test_marks_an_unread_row_of_this_recipient_and_role(self, use_client):
        client = use_client(SimpleNamespace(data=[{"id": "n1"}]))

        assert repository.mark_read("n1", USER, ROLE) is True

        [query] = client.queries
        assert scoped(query) and query.has("eq", "id", "n1") and query.has("is_", "read_at", "null")
        [update] = [c for c in query.calls if c[0] == "update"]
        assert list(update[1][0]) == ["read_at"] and update[1][0]["read_at"]

    def test_an_already_read_row_is_still_true_and_not_rewritten(self, use_client):
        client = use_client(SimpleNamespace(data=[]), SimpleNamespace(data=[{"id": "n1"}]))

        assert repository.mark_read("n1", USER, ROLE) is True

        lookup = client.queries[1]
        assert scoped(lookup) and lookup.has("eq", "id", "n1")
        assert "update" not in lookup.names()

    def test_a_row_that_is_not_theirs_is_false(self, use_client):
        use_client(SimpleNamespace(data=[]), SimpleNamespace(data=[]))

        assert repository.mark_read("n1", USER, ROLE) is False


class TestMarkAllRead:
    def test_updates_only_this_recipients_unread_rows_in_the_role(self, use_client):
        client = use_client(SimpleNamespace(data=[{"id": "1"}, {"id": "2"}]))

        assert repository.mark_all_read(USER, ROLE) == 2

        [query] = client.queries
        assert scoped(query) and query.has("is_", "read_at", "null")

    def test_nothing_to_update_is_zero(self, use_client):
        use_client(SimpleNamespace(data=None))

        assert repository.mark_all_read(USER, ROLE) == 0
