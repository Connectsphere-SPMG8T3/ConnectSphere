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
            # d-4 was requested first but d-2 expires first.
            make_booking("d-2", "held", datetime(2026, 9, 3, 10, 30, tzinfo=SGT),
                         expires_at=datetime(2026, 9, 20, 9, tzinfo=SGT)),
            make_booking("d-4", "held", datetime(2026, 8, 28, 16, 15, tzinfo=SGT),
                         expires_at=datetime(2026, 9, 22, 9, tzinfo=SGT)),
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

    def test_holds_come_back_soonest_expiry_first_carrying_their_expiry(self, queue):
        # CR-99 (W7 CR-04): the hold nearest to expiring most needs a decision,
        # so expiry, not age, orders the queue.
        result = service.venue_staff_dashboard(now=NOW)
        assert [h.id for h in result.pending_holds] == ["d-2", "d-4"]
        assert result.pending_holds[0].expires_at == datetime(2026, 9, 20, 9, tzinfo=SGT)

    def test_equal_expiries_are_broken_by_id_so_the_order_is_stable(self, monkeypatch):
        """Two holds expiring in the same instant must not shuffle between loads."""
        same = datetime(2026, 9, 21, 10, 30, tzinfo=SGT)
        monkeypatch.setattr(repository, "list_venues", list)
        monkeypatch.setattr(repository, "list_all_upcoming_blocks", lambda since: [])
        monkeypatch.setattr(
            repository,
            "list_all_upcoming_bookings",
            lambda since, statuses: [
                make_booking("d-9", "held", NOW, expires_at=same),
                make_booking("d-1", "held", NOW, expires_at=same),
            ],
        )

        result = service.venue_staff_dashboard(now=NOW)

        assert [h.id for h in result.pending_holds] == ["d-1", "d-9"]

    def test_a_hold_past_its_expiry_is_left_out_before_the_job_reaches_it(self, monkeypatch):
        # CR-99 AC5: expired holds leave the queue; the job runs every minute,
        # so one can still read as held for up to that long.
        monkeypatch.setattr(repository, "list_venues", list)
        monkeypatch.setattr(repository, "list_all_upcoming_blocks", lambda since: [])
        monkeypatch.setattr(
            repository,
            "list_all_upcoming_bookings",
            lambda since, statuses: [
                make_booking("d-1", "held", NOW, expires_at=NOW),
                make_booking("d-2", "held", NOW, expires_at=NOW + timedelta(seconds=1)),
            ],
        )

        result = service.venue_staff_dashboard(now=NOW)

        assert [h.id for h in result.pending_holds] == ["d-2"]

    def test_affected_bookings_are_the_live_flagged_ones_that_have_not_ended(self, monkeypatch):
        # CR-95 AC9: venue staff need to find a booking whose venue became
        # unavailable, to restore it once the venue is free again.
        past = Period(starts_at=datetime(2026, 9, 1, 9, tzinfo=SGT), ends_at=datetime(2026, 9, 1, 12, tzinfo=SGT))
        bookings = [
            make_booking("a-2", "approved", datetime(2026, 9, 3, tzinfo=SGT), flag="affected",
                         period=Period(starts_at=datetime(2026, 10, 12, 9, tzinfo=SGT),
                                       ends_at=datetime(2026, 10, 12, 12, tzinfo=SGT))),
            make_booking("a-1", "held", datetime(2026, 9, 4, tzinfo=SGT), flag="affected",
                         expires_at=datetime(2026, 9, 30, 9, tzinfo=SGT)),
            make_booking("ended", "approved", datetime(2026, 8, 1, tzinfo=SGT), flag="affected", period=past),
            make_booking("other-flag", "approved", datetime(2026, 9, 5, tzinfo=SGT), flag="unsuitable"),
            make_booking("plain", "approved", datetime(2026, 9, 6, tzinfo=SGT)),
            make_booking("released", "released", datetime(2026, 9, 7, tzinfo=SGT), flag="affected"),
        ]
        monkeypatch.setattr(repository, "list_venues", list)
        monkeypatch.setattr(repository, "list_all_upcoming_blocks", lambda since: [])
        monkeypatch.setattr(repository, "list_all_upcoming_bookings", lambda since, statuses: bookings)

        result = service.venue_staff_dashboard(now=NOW)

        # Soonest event first.
        assert [b.id for b in result.affected_bookings] == ["a-1", "a-2"]
        assert result.affected_bookings[0].flag == "affected"

    def test_re_review_is_kept_out_of_the_holds_queue(self, queue):
        result = service.venue_staff_dashboard(now=NOW)
        assert [b.id for b in result.re_review_bookings] == ["d-5"]
        assert "d-5" not in [h.id for h in result.pending_holds]

    def test_it_asks_for_all_history_statuses(self, queue):
        service.venue_staff_dashboard(now=NOW)
        _, statuses = queue["bookings"][0]
        assert statuses == {"held", "re_review", "approved", "rejected", "expired"}

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

        def _select(columns):
            calls["select"] = columns
            return query

        def _overlaps(column, literal):
            calls["overlaps"] = (column, literal)
            return query

        def _in(column, values):
            calls["in_"] = (column, list(values))
            return query

        query.select.side_effect = _select
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
                "booked_period": '["2026-10-13 09:00:00+08","2026-10-13 12:00:00+08")',
                "status": "held",
                "created_at": "2026-08-28T16:15:00+08:00",
                "expires_at": "2026-09-04T16:15:00+08:00",
                "venues": {"name": "Hall A"},
            },
            {
                "id": "d-1",
                "event_id": "e-101",
                "venue_id": HALL_B_ID,
                "booked_period": '["2026-10-10 13:00:00+08","2026-10-10 16:00:00+08")',
                "status": "re_review",
                "created_at": "2026-09-10T11:45:00+08:00",
                "flag": "affected",
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

    def test_expires_at_is_read_and_absent_on_a_booking_without_one(self, bookings_client):
        bookings = repository.list_all_upcoming_bookings(NOW, {"held", "re_review"})
        by_id = {b.id: b for b in bookings}
        assert by_id["d-2"].expires_at == datetime(2026, 9, 4, 16, 15, tzinfo=SGT)
        assert by_id["d-1"].expires_at is None

    def test_bookings_are_sorted_by_period_and_name_their_venue(self, bookings_client):
        bookings = repository.list_all_upcoming_bookings(NOW, {"held", "re_review"})
        assert [b.id for b in bookings] == ["d-1", "d-2"]
        assert [b.venue_name for b in bookings] == ["Hall B", "Hall A"]

    def test_a_bookings_flag_is_read(self, bookings_client):
        bookings = repository.list_all_upcoming_bookings(NOW, {"held", "re_review"})
        by_id = {b.id: b for b in bookings}
        assert by_id["d-1"].flag == "affected"
        assert by_id["d-2"].flag is None

    def test_event_name_is_left_unset(self, bookings_client):
        bookings = repository.list_all_upcoming_bookings(NOW, {"held"})
        assert all(b.event_name is None for b in bookings)

    def test_the_venue_embed_names_its_foreign_key(self, bookings_client):
        """Regression: PostgREST rejected the whole query without this.

        `venue_bookings` has two foreign keys to `venues` — `venue_id` and the
        `suggested_venue_id` a rejection may carry — so a bare `venues(name)`
        is ambiguous and answers PGRST201 rather than picking one. Caught only
        by running against a real database, hence this guard.
        """
        repository.list_all_upcoming_bookings(NOW, {"held"})
        assert "venues!venue_bookings_venue_id_fkey(name)" in bookings_client["venue_bookings"]["select"]

    def test_the_block_embed_stays_unqualified(self, blocks_client):
        """`venue_blocks` has a single FK to `venues`, so it needs no hint."""
        repository.list_all_upcoming_blocks(NOW)
        assert "venues(name)" in blocks_client["venue_blocks"]["select"]


class TestRestorableAfterBlock:
    """SCRUM-54 AC5: the queue marks each booking a block no longer covers, from
    the computed column on the same read, so the dashboard costs no extra query."""

    @pytest.fixture()
    def rows(self, monkeypatch):
        base = {"event_id": "e-1", "venue_id": HALL_A_ID, "status": "approved", "flag": "affected",
                "booked_period": '["2026-10-13 09:00:00+08","2026-10-13 12:00:00+08")',
                "created_at": "2026-09-01T10:00:00+08:00", "venues": {"name": "Hall A"}}
        data = [{**base, "id": "free", "restorable_after_block": True},
                {**base, "id": "covered", "restorable_after_block": False}]
        client, recorded = make_client_mock({"venue_bookings": data})
        monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: client)
        return recorded

    def test_the_computed_column_is_selected_and_read(self, rows):
        bookings = {b.id: b for b in repository.list_all_upcoming_bookings(NOW, {"approved"})}
        assert "restorable_after_block" in rows["venue_bookings"]["select"]
        assert bookings["free"].restorable is True and bookings["covered"].restorable is False

    def test_a_row_without_it_is_not_restorable(self, monkeypatch):
        client, _ = make_client_mock({"venue_blocks": [], "venue_bookings": [{
            "id": "x", "event_id": "e-1", "venue_id": HALL_A_ID, "status": "held",
            "booked_period": '["2026-10-13 09:00:00+08","2026-10-13 12:00:00+08")',
            "created_at": "2026-09-01T10:00:00+08:00"}]})
        monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: client)
        [booking] = repository.list_all_upcoming_bookings(NOW, {"held"})
        assert booking.restorable is False
