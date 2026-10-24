"""Equipment availability checking (SCRUM-23) and the inventory/maintenance
reads behind the Technical Support dashboard (SCRUM-73).

The repository is patched, so these run offline; the availability rules
themselves are exercised directly. `TestOverlapFilter` covers the one piece the
repository still owns — that "overlaps this window" is pushed to PostgREST with
the half-open bounds the schema stores.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.security import CurrentUser, get_current_user
from app.main import app
from app.modules.equipment import repository, service
from app.modules.equipment.repository import AvailabilityRow, CommitmentRow, EquipmentRow, MaintenanceRow
from app.modules.equipment.schemas import EquipmentAvailabilityRequest

START = datetime(2026, 10, 15, 9, tzinfo=timezone.utc)
END = START + timedelta(hours=2)
PROJECTOR = str(uuid4())


def _overlaps(row: CommitmentRow, start_at: datetime, end_at: datetime) -> bool:
    """The same half-open predicate `repository._overlapping` asks PostgREST for."""
    return row.start_at < end_at and row.end_at > start_at


@pytest.fixture()
def repo(monkeypatch):
    """A fake repository holding rows in memory.

    It applies the window and id filters itself so the service sees exactly
    what the real repository would return for the same data.
    """

    state = {"equipment": [], "reservations": [], "unavailability": [], "maintenance": []}

    def _scoped(rows, start_at, end_at, equipment_ids):
        ids = None if equipment_ids is None else {str(i) for i in equipment_ids}
        return [
            row
            for row in rows
            if (ids is None or row.equipment_id in ids)
            and (start_at is None or end_at is None or _overlaps(row, start_at, end_at))
        ]

    monkeypatch.setattr(
        repository,
        "list_equipment",
        lambda equipment_ids=None: [
            row
            for row in state["equipment"]
            if equipment_ids is None or row.id in {str(i) for i in equipment_ids}
        ],
    )
    monkeypatch.setattr(
        repository,
        "list_reservations",
        lambda start_at=None, end_at=None, equipment_ids=None: _scoped(
            state["reservations"], start_at, end_at, equipment_ids
        ),
    )
    monkeypatch.setattr(
        repository,
        "list_unavailability",
        lambda start_at=None, end_at=None, equipment_ids=None: _scoped(
            state["unavailability"], start_at, end_at, equipment_ids
        ),
    )
    monkeypatch.setattr(repository, "list_maintenance", lambda: state["maintenance"])

    def availability(equipment_ids, start_at, end_at):
        """Stands in for `public.equipment_availability`: the peak concurrent
        commitment inside the window, never a plain sum (§6.16 AV-R2, D45)."""
        def peak(rows, equipment_id):
            rows = [row for row in _scoped(rows, start_at, end_at, [equipment_id])]
            moments = {start_at} | {row.start_at for row in rows if row.start_at > start_at}
            return max((sum(row.quantity for row in rows if row.start_at <= at < row.end_at) for at in moments), default=0)

        result = []
        for row in state["equipment"]:
            if row.id not in {str(i) for i in equipment_ids}:
                continue
            outage, reserved = peak(state["unavailability"], row.id), peak(state["reservations"], row.id)
            result.append(AvailabilityRow(
                equipment_id=row.id, total_quantity=row.total_quantity, outage_quantity=outage,
                reserved_quantity=reserved, free_quantity=max(0, row.total_quantity - outage - reserved),
            ))
        return result

    monkeypatch.setattr(repository, "availability", availability)
    return state


def _equipment(repo, quantity=10, equipment_id=PROJECTOR, name="Projector"):
    repo["equipment"].append(EquipmentRow(id=equipment_id, name=name, total_quantity=quantity))
    return equipment_id


def _commitment(equipment_id, quantity, start_at=START, end_at=END):
    return CommitmentRow(equipment_id=equipment_id, quantity=quantity, start_at=start_at, end_at=end_at)


def _check(equipment_id, quantity):
    return service.check_equipment_availability(
        START,
        END,
        EquipmentAvailabilityRequest(
            start_at=START,
            end_at=END,
            items=[{"equipment_id": equipment_id, "quantity_needed": quantity}],
        ).items,
    ).items[0]


class TestAvailability:
    def test_sufficient_stock_returns_available_quantity(self, repo):
        item = _equipment(repo, quantity=5)

        result = _check(item, 5)

        assert result.quantity_available == 5
        assert result.sufficient is True

    def test_over_requested_stock_is_insufficient(self, repo):
        item = _equipment(repo, quantity=5)

        result = _check(item, 6)

        assert result.quantity_available == 5
        assert result.sufficient is False

    def test_overlapping_reservation_and_unavailability_reduce_stock(self, repo):
        item = _equipment(repo, quantity=10)
        repo["reservations"].append(_commitment(item, 3))
        repo["unavailability"].append(_commitment(item, 2))

        result = _check(item, 6)

        assert result.quantity_available == 5
        assert result.sufficient is False

    def test_non_overlapping_reservation_does_not_reduce_stock(self, repo):
        item = _equipment(repo, quantity=5)
        later = END + timedelta(hours=1)
        repo["reservations"].append(_commitment(item, 5, start_at=later, end_at=later + timedelta(hours=2)))

        result = _check(item, 5)

        assert result.quantity_available == 5
        assert result.sufficient is True

    def test_a_reservation_ending_as_the_window_opens_does_not_clash(self, repo):
        """Equipment has no turnaround time (QA-126), so back-to-back is fine."""
        item = _equipment(repo, quantity=4)
        repo["reservations"].append(_commitment(item, 4, start_at=START - timedelta(hours=2), end_at=START))

        result = _check(item, 4)

        assert result.quantity_available == 4
        assert result.sufficient is True

    def test_unknown_equipment_is_insufficient(self, repo):
        result = _check(str(uuid4()), 1)

        assert result.quantity_available == 0
        assert result.sufficient is False
        assert result.name == "Unknown equipment"

    def test_stock_never_reports_below_zero(self, repo):
        item = _equipment(repo, quantity=2)
        repo["reservations"].append(_commitment(item, 5))

        result = _check(item, 1)

        assert result.quantity_available == 0

    def test_reservations_that_do_not_overlap_each_other_count_once(self, repo):
        """D45, §6.16: 10 at the window's start and 10 after it are never 20 at once."""
        item = _equipment(repo, quantity=20)
        middle = START + timedelta(hours=1)
        repo["reservations"].append(_commitment(item, 10, start_at=START, end_at=middle))
        repo["reservations"].append(_commitment(item, 10, start_at=middle, end_at=END))

        assert _check(item, 10).quantity_available == 10

    def test_the_check_asks_the_database_for_the_window_and_items(self, repo, monkeypatch):
        item = _equipment(repo, quantity=4)
        seen = {}

        def availability(equipment_ids, start_at, end_at):
            seen["args"] = (set(equipment_ids), start_at, end_at)
            return [AvailabilityRow(item, 4, 0, 1, 3)]

        monkeypatch.setattr(repository, "availability", availability)

        assert _check(item, 3).quantity_available == 3
        assert seen["args"] == ({item}, START, END)


class TestInventory:
    def test_every_equipment_type_is_listed_with_its_breakdown(self, repo):
        item = _equipment(repo, quantity=10)
        repo["reservations"].append(_commitment(item, 3))
        repo["unavailability"].append(_commitment(item, 2))

        row = service.get_equipment_inventory(START, END).items[0]

        assert (row.total_quantity, row.reserved_quantity, row.maintenance_quantity) == (10, 3, 2)
        assert row.net_available == 5

    def test_a_window_reports_its_worst_moment(self, repo):
        """D45: the inventory over a window agrees with the availability check."""
        item = _equipment(repo, quantity=20)
        middle = START + timedelta(hours=1)
        repo["reservations"].append(_commitment(item, 10, start_at=START, end_at=middle))
        repo["reservations"].append(_commitment(item, 10, start_at=middle, end_at=END))

        row = service.get_equipment_inventory(START, END).items[0]

        assert (row.reserved_quantity, row.net_available) == (10, 10)

    def test_without_a_window_every_commitment_counts(self, repo):
        item = _equipment(repo, quantity=10)
        far_off = START + timedelta(days=30)
        repo["reservations"].append(_commitment(item, 4, start_at=far_off, end_at=far_off + timedelta(hours=1)))

        row = service.get_equipment_inventory().items[0]

        assert row.reserved_quantity == 4

    def test_a_lone_start_is_ignored_rather_than_half_applied(self, repo):
        item = _equipment(repo, quantity=10)
        repo["reservations"].append(_commitment(item, 4))

        row = service.get_equipment_inventory(START, None).items[0]

        assert row.reserved_quantity == 4


class TestMaintenance:
    def _record(self, start_at, end_at):
        return MaintenanceRow(
            id=str(uuid4()),
            equipment_id=PROJECTOR,
            equipment_name="Projector",
            start_at=start_at,
            end_at=end_at,
            reason="Lens calibration",
        )

    def test_a_future_window_is_scheduled(self, repo):
        now = datetime.now(timezone.utc)
        repo["maintenance"].append(self._record(now + timedelta(days=1), now + timedelta(days=2)))

        assert service.get_equipment_maintenance().items[0].status == "SCHEDULED"

    def test_a_window_under_way_is_in_progress(self, repo):
        now = datetime.now(timezone.utc)
        repo["maintenance"].append(self._record(now - timedelta(hours=1), now + timedelta(hours=1)))

        assert service.get_equipment_maintenance().items[0].status == "IN_PROGRESS"

    def test_a_finished_window_is_completed_and_still_listed(self, repo):
        now = datetime.now(timezone.utc)
        repo["maintenance"].append(self._record(now - timedelta(days=2), now - timedelta(days=1)))

        items = service.get_equipment_maintenance().items

        assert len(items) == 1
        assert items[0].status == "COMPLETED"

    def test_the_record_carries_its_equipment_name_and_reason(self, repo):
        now = datetime.now(timezone.utc)
        repo["maintenance"].append(self._record(now + timedelta(days=1), now + timedelta(days=2)))

        item = service.get_equipment_maintenance().items[0]

        assert item.equipment_name == "Projector"
        assert item.reason == "Lens calibration"


class TestOverlapFilter:
    """The overlap moved from SQL into PostgREST filters, so pin the bounds."""

    def _captured_query(self, monkeypatch):
        query = MagicMock()
        for method in ("select", "in_", "lt", "gt", "order"):
            getattr(query, method).return_value = query
        query.execute.return_value = MagicMock(data=[])
        client = MagicMock()
        client.table.return_value = query
        monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: client)
        return query

    def test_reservations_are_filtered_half_open_on_both_ends(self, monkeypatch):
        query = self._captured_query(monkeypatch)

        repository.list_reservations(START, END, [PROJECTOR])

        # start_at < window end AND end_at > window start: a row touching only
        # the boundary is excluded at both ends.
        query.lt.assert_called_once_with("start_at", END.isoformat())
        query.gt.assert_called_once_with("end_at", START.isoformat())

    def test_only_occupying_statuses_are_requested(self, monkeypatch):
        query = self._captured_query(monkeypatch)

        repository.list_reservations(START, END)

        assert query.in_.call_args_list[0].args == ("status", ["confirmed"])

    def test_no_window_means_no_time_filter(self, monkeypatch):
        query = self._captured_query(monkeypatch)

        repository.list_reservations()

        query.lt.assert_not_called()
        query.gt.assert_not_called()

    def test_an_empty_id_list_short_circuits_instead_of_querying(self, monkeypatch):
        query = self._captured_query(monkeypatch)

        assert repository.list_equipment([]) == []
        query.execute.assert_not_called()


def test_non_technical_support_role_is_forbidden():
    user = CurrentUser(
        id=str(uuid4()),
        email="coordinator@connectsphere.dev",
        full_name="Coordinator",
        role="event_coordinator",
        session_id=str(uuid4()),
        access_token="test-token",
    )
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/equipment/availability/check",
                json={
                    "start_at": "2026-10-15T09:00:00Z",
                    "end_at": "2026-10-15T11:00:00Z",
                    "items": [{"equipment_id": str(uuid4()), "quantity_needed": 1}],
                },
            )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


class TestReopenedAvailability:
    """23-R: condition uses outages; location is reference data; shortage is explicit."""

    @pytest.mark.parametrize("needed, missing", [(2, 0), (5, 0), (8, 3)])
    def test_reports_missing_units_without_negative_surplus(self, repo, needed, missing):
        item = _equipment(repo, quantity=7)
        repo["unavailability"].append(_commitment(item, 2))

        result = _check(item, needed)

        assert result.quantity_needed == needed
        assert result.quantity_available == 5
        assert result.quantity_missing == missing
        assert result.sufficient is (missing == 0)

    @pytest.mark.parametrize("location", ["Store A, level 2", "Different venue store", None])
    def test_location_is_returned_without_changing_availability(self, repo, monkeypatch, location):
        from types import SimpleNamespace

        item = _equipment(repo, quantity=7)
        repo["unavailability"].append(_commitment(item, 2))
        monkeypatch.setattr(repository, "list_equipment", lambda ids: [
            SimpleNamespace(id=item, name="Projector", total_quantity=7, storage_location=location),
        ])

        result = _check(item, 6)

        assert result.storage_location == location
        assert result.quantity_available == 5
        assert result.quantity_missing == 1

    def test_unknown_item_has_no_location_and_all_units_missing(self, repo):
        result = _check(str(uuid4()), 3)

        assert result.storage_location is None
        assert result.quantity_missing == 3

    def test_repository_reads_storage_location(self, monkeypatch):
        query = MagicMock()
        query.select.return_value = query
        query.order.return_value = query
        query.execute.return_value = MagicMock(data=[{
            "id": PROJECTOR, "name": "Projector", "total_quantity": 7,
            "storage_location": "Store A",
        }])
        client = MagicMock()
        client.table.return_value = query
        monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: client)

        assert repository.list_equipment()[0].storage_location == "Store A"
        assert "storage_location" in query.select.call_args.args[0]
