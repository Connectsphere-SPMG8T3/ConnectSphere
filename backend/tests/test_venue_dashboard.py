"""Venue-staff dashboard internals (SCRUM-70): service partitioning and the
cross-venue repository reads.

`test_venues_api.py` covers the HTTP contract with the repository patched out.
This file goes one layer down and mocks the Supabase client itself, because the
thing most worth pinning here is the *query* the repository builds: the
"still relevant" cut-off moved out of Python and into Postgres, so the only
place that boundary can now be checked is the range literal handed to
`.overlaps(...)`.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.modules.venues import repository, service
from app.modules.venues.schemas import Period, VenueStaffBlock, VenueStaffBooking

SGT = timezone(timedelta(hours=8))
NOW = datetime(2026, 9, 19, 12, tzinfo=SGT)
HALL_A_ID = "b0000000-0000-4000-8000-000000000001"
HALL_B_ID = "b0000000-0000-4000-8000-000000000002"


def make_booking(booking_id: str, status: str, requested_at: datetime, **overrides) -> VenueStaffBooking:
    fields = {
        "id": booking_id,
        "event_id": "e0000000-0000-4000-8000-000000000101",
        "venue_id": HALL_A_ID,
        "venue_name": "Hall A",
        "period": Period(
            starts_at=datetime(2026, 10, 10, 9, tzinfo=SGT),
            ends_at=datetime(2026, 10, 10, 12, tzinfo=SGT),
        ),
        "status": status,
        "requested_at": requested_at,
    }
    fields.update(overrides)
    return VenueStaffBooking(**fields)


class TestServicePartitioning:
    """The service splits one booking read into the two queues the UI shows."""

    @pytest.fixture()
    def queue(self, monkeypatch):
        bookings = [
            make_booking("d-2", "held", datetime(2026, 9, 3, 10, 30, tzinfo=SGT)),
            make_booking("d-4", "held", datetime(2026, 8, 28, 16, 15, tzinfo=SGT)),
            make_booking("d-5", "re_review", datetime(2026, 9, 10, 11, 45, tzinfo=SGT)),
        ]
        calls = {"bookings": [], "blocks": []}
        monkeypatch.setattr(repository, "list_venues", list)
        monkeypatch.setattr(repository, "list_all_upcoming_blocks", lambda since: calls["blocks"].append(since) or [])
        monkeypatch.setattr(
            repository,
            "list_all_upcoming_bookings",
            lambda since, statuses: calls["bookings"].append((since, set(statuses))) or bookings,
        )
        return calls

    def test_holds_come_back_oldest_first(self, queue):
        result = service.venue_staff_dashboard(now=NOW)
        assert [h.id for h in result.pending_holds] == ["d-4", "d-2"]

    def test_equal_ages_are_broken_by_id_so_the_order_is_stable(self, monkeypatch):
        """Two holds requested in the same instant must not shuffle between loads."""
        same = datetime(2026, 9, 3, 10, 30, tzinfo=SGT)
        monkeypatch.setattr(repository, "list_venues", list)
        monkeypatch.setattr(repository, "list_all_upcoming_blocks", lambda since: [])
        monkeypatch.setattr(
            repository,
            "list_all_upcoming_bookings",
            lambda since, statuses: [make_booking("d-9", "held", same), make_booking("d-1", "held", same)],
        )

        result = service.venue_staff_dashboard(now=NOW)

        assert [h.id for h in result.pending_holds] == ["d-1", "d-9"]

    def test_re_review_is_kept_out_of_the_holds_queue(self, queue):
        result = service.venue_staff_dashboard(now=NOW)
        assert [b.id for b in result.re_review_bookings] == ["d-5"]
        assert "d-5" not in [h.id for h in result.pending_holds]

    def test_it_asks_for_held_and_re_review_only(self, queue):
        """`approved` is settled work; it belongs on §6.9's per-venue calendar."""
        service.venue_staff_dashboard(now=NOW)
        _, statuses = queue["bookings"][0]
        assert statuses == {"held", "re_review"}

    def test_a_settled_status_that_slips_through_lands_in_neither_queue(self, monkeypatch):
        """Defence in depth: the filter is the query's job, but partitioning
        must not silently reclassify anything the query over-returns."""
        monkeypatch.setattr(repository, "list_venues", list)
        monkeypatch.setattr(repository, "list_all_upcoming_blocks", lambda since: [])
        monkeypatch.setattr(
            repository,
            "list_all_upcoming_bookings",
            lambda since, statuses: [make_booking("d-1", "approved", NOW), make_booking("d-2", "rejected", NOW)],
        )

        result = service.venue_staff_dashboard(now=NOW)

        assert result.pending_holds == []
        assert result.re_review_bookings == []

    def test_the_injected_now_reaches_both_reads_and_the_payload(self, queue):
        service.venue_staff_dashboard(now=NOW)
        assert queue["bookings"][0][0] == NOW
        assert queue["blocks"][0] == NOW

    def test_generated_at_is_the_cut_off_that_was_used(self, queue):
        assert service.venue_staff_dashboard(now=NOW).generated_at == NOW


class TestOpenEndedLiteral:
    """The `[since,)` literal is where "ends after now" is now decided."""

    def test_it_is_lower_bounded_and_unbounded_above(self):
        assert repository._open_ended_literal(NOW) == "[2026-09-19T12:00:00+08:00,)"

    def test_period_cannot_express_it(self):
        """Documents why this helper exists rather than reusing `_range_literal`."""
        with pytest.raises(ValueError):
            Period(starts_at=NOW, ends_at=NOW)


class TestEmbeddedVenueName:
    """PostgREST returns a to-one embed as a dict or a one-element list."""

    @pytest.mark.parametrize(
        "row",
        [{"venues": {"name": "Hall A"}}, {"venues": [{"name": "Hall A"}]}],
        ids=["dict", "list"],
    )
    def test_both_embed_shapes_yield_the_name(self, row):
        assert repository._embedded_venue_name(row) == "Hall A"

    @pytest.mark.parametrize("row", [{}, {"venues": None}, {"venues": []}], ids=["missing", "null", "empty"])
    def test_a_missing_embed_costs_a_label_not_the_request(self, row):
        assert repository._embedded_venue_name(row) == ""


def make_client_mock(table_rows: dict[str, list[dict]]) -> tuple[MagicMock, dict]:
    """A Supabase client stub that records the filters each query applied."""
    recorded: dict[str, dict] = {}

    def _table(name: str) -> MagicMock:
        query = MagicMock()
        calls = recorded.setdefault(name, {})

        def _overlaps(column, literal):
            calls["overlaps"] = (column, literal)
            return query

        def _in(column, values):
            calls["in_"] = (column, list(values))
            return query

        query.select.return_value = query
        query.overlaps.side_effect = _overlaps
        query.in_.side_effect = _in
        query.execute.side_effect = lambda: SimpleNamespace(data=table_rows.get(name, []))
        return query

    client = MagicMock()
    client.table.side_effect = _table
    return client, recorded


class TestCrossVenueReads:
    """The filter must run in Postgres: this queue spans every venue, so the
    per-venue helpers' "fetch everything and drop the past in Python" would be
    a full-table scan on each dashboard load."""

    @pytest.fixture()
    def blocks_client(self, monkeypatch):
        rows = [
            {
                "id": "c-2",
                "venue_id": HALL_B_ID,
                "blocked_period": '["2026-10-20 00:00:00+08","2026-10-22 00:00:00+08")',
                "reason": "safety",
                "notes": None,
                "venues": {"name": "Hall B"},
            },
            {
                "id": "c-1",
                "venue_id": HALL_A_ID,
                "blocked_period": '["2026-10-01 00:00:00+08","2026-10-15 00:00:00+08")',
                "reason": "renovation",
                "notes": "Floor restoration.",
                "venues": [{"name": "Hall A"}],
            },
        ]
        client, recorded = make_client_mock({"venue_blocks": rows})
        monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: client)
        return recorded

    def test_blocks_filter_on_the_open_ended_range_in_postgres(self, blocks_client):
        repository.list_all_upcoming_blocks(NOW)
        assert blocks_client["venue_blocks"]["overlaps"] == ("blocked_period", "[2026-09-19T12:00:00+08:00,)")

    def test_blocks_come_back_soonest_first_with_their_venue_named(self, blocks_client):
        blocks = repository.list_all_upcoming_blocks(NOW)
        assert [b.id for b in blocks] == ["c-1", "c-2"]
        assert [b.venue_name for b in blocks] == ["Hall A", "Hall B"]
        assert isinstance(blocks[0], VenueStaffBlock)

    @pytest.fixture()
    def bookings_client(self, monkeypatch):
        rows = [
            {
                "id": "d-2",
                "event_id": "e-102",
                "venue_id": HALL_A_ID,
                "occupied_period": '["2026-10-13 09:00:00+08","2026-10-13 12:00:00+08")',
                "status": "held",
                "created_at": "2026-08-28T16:15:00+08:00",
                "venues": {"name": "Hall A"},
            },
            {
                "id": "d-1",
                "event_id": "e-101",
                "venue_id": HALL_B_ID,
                "occupied_period": '["2026-10-10 13:00:00+08","2026-10-10 16:00:00+08")',
                "status": "re_review",
                "created_at": "2026-09-10T11:45:00+08:00",
                "venues": {"name": "Hall B"},
            },
        ]
        client, recorded = make_client_mock({"venue_bookings": rows})
        monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: client)
        return recorded

    def test_bookings_filter_on_both_status_and_the_open_ended_range(self, bookings_client):
        repository.list_all_upcoming_bookings(NOW, {"held", "re_review"})
        recorded = bookings_client["venue_bookings"]
        assert recorded["overlaps"] == ("occupied_period", "[2026-09-19T12:00:00+08:00,)")
        assert recorded["in_"] == ("status", ["held", "re_review"])

    def test_requested_at_is_read_from_created_at(self, bookings_client):
        """Oldest-first is meaningless without it, and no existing select asked for it."""
        bookings = repository.list_all_upcoming_bookings(NOW, {"held"})
        by_id = {b.id: b for b in bookings}
        assert by_id["d-2"].requested_at == datetime(2026, 8, 28, 16, 15, tzinfo=SGT)

    def test_bookings_are_sorted_by_period_and_name_their_venue(self, bookings_client):
        bookings = repository.list_all_upcoming_bookings(NOW, {"held", "re_review"})
        assert [b.id for b in bookings] == ["d-1", "d-2"]
        assert [b.venue_name for b in bookings] == ["Hall B", "Hall A"]

    def test_event_name_is_left_unset(self, bookings_client):
        bookings = repository.list_all_upcoming_bookings(NOW, {"held"})
        assert all(b.event_name is None for b in bookings)
