"""Features 15-17: what equipment stock reports and what a request records.

`test_equipment_availability.py` covers the availability rules; these tests pin the sums,
the window handling and the arguments the mocked repository would otherwise hide.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import (
    CoordinatorNotEligibleError,
    EquipmentNotInCatalogueError,
    EquipmentRequestNotAllowedError,
    NotificationNotFoundError,
)
from app.modules.equipment import repository, service
from app.modules.equipment.schemas import EquipmentCheckItem, EquipmentRequestCreate, EquipmentRequestItem
from app.modules.equipment.service import event_technical_history

START = datetime(2031, 5, 1, 9, tzinfo=timezone.utc)
END = START + timedelta(hours=2)
EVENT_ID = str(uuid4())
COORDINATOR_ID = str(uuid4())
PROJECTOR = str(uuid4())
SPEAKER = str(uuid4())


def _equipment(equipment_id=PROJECTOR, total=10, status="active", name="Projector"):
    return SimpleNamespace(id=equipment_id, name=name, total_quantity=total, status=status, storage_location="Store A")


def _commitment(quantity, equipment_id=PROJECTOR):
    return SimpleNamespace(equipment_id=equipment_id, quantity=quantity)


def _window(equipment_id=PROJECTOR, reserved=0, outage=0, free=0):
    return SimpleNamespace(
        equipment_id=equipment_id, reserved_quantity=reserved, outage_quantity=outage, free_quantity=free,
    )


class TestInventory:
    @pytest.fixture()
    def stock(self, monkeypatch):
        calls = SimpleNamespace(window=[])
        monkeypatch.setattr(repository, "list_equipment", lambda ids=None: [_equipment()])
        monkeypatch.setattr(repository, "list_reservations", lambda: [])
        monkeypatch.setattr(repository, "list_unavailability", lambda: [])

        def availability(ids, start_at, end_at):
            calls.window.append((list(ids), start_at, end_at))
            return []

        monkeypatch.setattr(repository, "availability", availability)
        return calls

    def test_commitments_on_one_item_add_up(self, monkeypatch, stock):
        monkeypatch.setattr(repository, "list_reservations", lambda: [_commitment(2), _commitment(3)])
        monkeypatch.setattr(repository, "list_unavailability", lambda: [_commitment(1)])

        [item] = service.get_equipment_inventory().items

        assert (item.reserved_quantity, item.maintenance_quantity, item.net_available) == (5, 1, 4)

    def test_an_item_nothing_has_committed_shows_all_its_stock(self, stock):
        [item] = service.get_equipment_inventory().items

        assert (item.reserved_quantity, item.maintenance_quantity, item.net_available) == (0, 0, 10)

    @pytest.mark.parametrize(("start_at", "end_at"), [(START, None), (None, END)], ids=["start only", "end only"])
    def test_a_lone_start_or_end_is_ignored(self, stock, start_at, end_at):
        service.get_equipment_inventory(start_at, end_at)

        assert stock.window == []

    def test_a_window_asks_for_that_equipment_and_period(self, stock):
        service.get_equipment_inventory(START, END)

        assert stock.window == [([PROJECTOR], START, END)]

    def test_an_item_with_no_row_in_the_window_shows_all_its_stock(self, stock):
        [item] = service.get_equipment_inventory(START, END).items

        assert (item.reserved_quantity, item.maintenance_quantity, item.net_available) == (0, 0, 10)

    def test_stock_never_reads_below_nothing(self, monkeypatch, stock):
        monkeypatch.setattr(repository, "list_reservations", lambda: [_commitment(10)])

        [item] = service.get_equipment_inventory().items

        assert item.net_available == 0


class TestAvailabilityCheck:
    def _check(self, monkeypatch, equipment, free, item_id=PROJECTOR):
        listed = []
        monkeypatch.setattr(repository, "list_equipment", lambda ids=None: listed.append(ids) or equipment)
        monkeypatch.setattr(repository, "availability", lambda ids, start_at, end_at: free)
        result = service.check_equipment_availability(
            START, END, [EquipmentCheckItem(equipment_id=item_id, quantity_needed=2)]
        )
        assert listed == [{item_id}]
        return result.items[0]

    def test_an_item_absent_from_the_window_has_none_free(self, monkeypatch):
        item = self._check(monkeypatch, [_equipment()], [])

        assert (item.name, item.quantity_available, item.sufficient) == ("Projector", 0, False)

    def test_an_item_not_in_the_catalogue_is_unknown_even_if_stock_is_reported(self, monkeypatch):
        item = self._check(monkeypatch, [], [_window(free=5)])

        assert (item.name, item.quantity_available, item.quantity_missing) == ("Unknown equipment", 0, 2)

    def test_the_endpoint_returns_the_check(self, client, auth_headers, authenticate_as, monkeypatch):
        authenticate_as("tech_support")
        monkeypatch.setattr(repository, "list_equipment", lambda ids=None: [_equipment()])
        monkeypatch.setattr(repository, "availability", lambda ids, start_at, end_at: [_window(free=5)])

        response = client.post("/api/v1/equipment/availability/check", headers=auth_headers, json={
            "start_at": START.isoformat(), "end_at": END.isoformat(),
            "items": [{"equipment_id": PROJECTOR, "quantity_needed": 2}],
        })

        assert response.status_code == 200
        assert response.json()["sufficient"] is True

    def test_a_window_that_ends_at_its_start_is_refused(self, client, auth_headers, authenticate_as):
        authenticate_as("tech_support")

        response = client.post("/api/v1/equipment/availability/check", headers=auth_headers, json={
            "start_at": START.isoformat(), "end_at": START.isoformat(),
            "items": [{"equipment_id": PROJECTOR, "quantity_needed": 2}],
        })

        assert response.status_code == 422
        assert "end_at must be later than start_at" in str(response.json())


class TestShortfalls:
    @staticmethod
    def _line(line_id, status="reserved", needs_re_review_since=None, quantity=5):
        return {"id": line_id, "equipment_id": PROJECTOR, "status": status, "quantity": quantity,
                "needs_re_review_since": needs_re_review_since, "equipment": {"name": "Projector"}}

    def _shortfalls(self, monkeypatch, lines, free=2):
        calls = SimpleNamespace(listed=[], free=[])
        monkeypatch.setattr(repository, "list_event_requests", lambda event_id: calls.listed.append(event_id) or lines)
        monkeypatch.setattr(
            repository, "line_free_quantity", lambda *args: calls.free.append(args) or free,
        )
        return service.shortfalls(EVENT_ID, START, END), calls

    def test_a_reserved_line_the_new_time_leaves_short_is_listed(self, monkeypatch):
        short, calls = self._shortfalls(monkeypatch, [self._line("line-1")])

        assert calls.listed == [EVENT_ID]
        assert calls.free == [("line-1", PROJECTOR, START, END)]
        assert [(row["line_id"], row["needed"], row["free"]) for row in short] == [("line-1", 5, 2)]

    def test_lines_already_with_someone_are_skipped_and_the_rest_still_checked(self, monkeypatch):
        short, _ = self._shortfalls(monkeypatch, [
            self._line("pending", status="pending"),
            self._line("reviewing", needs_re_review_since="2031-04-01T00:00:00+00:00"),
            self._line("reserved"),
        ])

        assert [row["line_id"] for row in short] == ["reserved"]

    def test_a_list_embed_is_read_as_one_equipment_row(self, monkeypatch):
        line = {**self._line("line-1"), "equipment": [{"name": "Speaker"}, {"name": "Unused"}]}
        short, _ = self._shortfalls(monkeypatch, [line])

        assert "Speaker" in short[0]["label"]

    def test_an_empty_list_embed_has_no_equipment(self):
        assert service._one([]) is None


class TestSubmitRequest:
    @pytest.fixture()
    def planning(self, monkeypatch):
        calls = SimpleNamespace(catalogue=[], status="planning", outcome="ok", rows=[])
        monkeypatch.setattr(
            service.events_service, "assigned_event", lambda event_id, coordinator_id: {"status": calls.status},
        )

        def list_catalogue(ids):
            calls.catalogue.append(list(ids))
            return [{"id": PROJECTOR, "name": "Projector"}, {"id": SPEAKER, "name": "Speaker"}]

        monkeypatch.setattr(repository, "list_catalogue", list_catalogue)
        monkeypatch.setattr(repository, "submit_request", lambda *args: (calls.outcome, calls.rows))
        return calls

    @staticmethod
    def _body(*equipment_ids, requirements=None):
        return EquipmentRequestCreate(event_id=EVENT_ID, items=[
            EquipmentRequestItem(equipment_id=equipment_id, quantity=1, technical_requirements=requirements)
            for equipment_id in equipment_ids
        ])

    @staticmethod
    def _row(equipment_id):
        return {
            "id": str(uuid4()), "submission_id": str(uuid4()), "event_id": EVENT_ID, "equipment_id": equipment_id,
            "quantity": 1, "status": "pending", "created_at": START.isoformat(),
        }

    def test_lines_come_back_in_the_order_listed_and_name_the_requester(self, planning):
        planning.rows = [self._row(SPEAKER), self._row(PROJECTOR)]

        lines = service.submit_request(COORDINATOR_ID, "Sam Lee", self._body(PROJECTOR, SPEAKER)).lines

        assert planning.catalogue == [[PROJECTOR, SPEAKER]]
        assert [line.equipment_name for line in lines] == ["Projector", "Speaker"]
        assert lines[0].requested_by.full_name == "Sam Lee"
        assert str(lines[0].requested_by.id) == COORDINATOR_ID

    def test_each_item_missing_from_the_catalogue_is_named_by_its_position(self, planning):
        with pytest.raises(EquipmentNotInCatalogueError) as error:
            service.submit_request(COORDINATOR_ID, "Sam Lee", self._body(PROJECTOR, str(uuid4()), str(uuid4())))

        assert error.value.status_code == 422
        assert error.value.detail == [
            {"loc": ["body", "items", index, "equipment_id"], "msg": "This item is not in the equipment catalogue.",
             "type": "not_in_catalogue"}
            for index in (1, 2)
        ]

    def test_a_batch_the_database_refused_points_at_the_items(self):
        assert EquipmentNotInCatalogueError().detail[0]["loc"] == ["body", "items"]

    def test_one_line_edit_points_at_its_own_field(self):
        assert EquipmentNotInCatalogueError(loc=["body", "equipment_id"]).detail[0]["loc"] == ["body", "equipment_id"]

    @pytest.mark.parametrize(
        ("outcome", "message"),
        [("returned", service.RETURNED_MESSAGE), ("not_planning", "This event is no longer in planning. Reload.")],
    )
    def test_the_database_refusing_the_event_is_explained(self, planning, outcome, message):
        planning.outcome = outcome

        with pytest.raises(EquipmentRequestNotAllowedError) as error:
            service.submit_request(COORDINATOR_ID, "Sam Lee", self._body(PROJECTOR))

        assert error.value.detail == message

    def test_a_returned_event_is_refused_before_the_catalogue_is_read(self, planning):
        planning.status = "returned"

        with pytest.raises(EquipmentRequestNotAllowedError) as error:
            service.submit_request(COORDINATOR_ID, "Sam Lee", self._body(PROJECTOR))

        assert error.value.detail == service.RETURNED_MESSAGE
        assert planning.catalogue == []

    def test_an_unknown_outcome_is_an_error_not_a_success(self, planning):
        planning.outcome = "surprise"

        with pytest.raises(RuntimeError, match="surprise"):
            service.submit_request(COORDINATOR_ID, "Sam Lee", self._body(PROJECTOR))

    def test_no_technical_requirements_stay_empty(self):
        assert self._body(PROJECTOR).items[0].technical_requirements is None


class TestEventHistory:
    """conftest.py stubs `service.event_technical_history`; the import above is the real one."""

    def test_each_entry_names_the_line_and_who_acted(self, monkeypatch):
        reads = []
        monkeypatch.setattr(repository, "list_technical_history", lambda event_id: reads.append(event_id) or [{
            "id": "history-1", "action": "reserved", "created_at": START.isoformat(), "detail": "Done",
            "actor": {"id": COORDINATOR_ID, "full_name": "Tess Tan"},
            "line": {"quantity": 2, "equipment": {"name": "Projector"}},
        }])

        [entry] = event_technical_history(EVENT_ID)

        assert reads == [EVENT_ID]
        assert (entry["id"], entry["action"], entry["detail"], entry["at"]) == ("history-1", "reserved", "Done", START)
        assert "Projector" in entry["line_label"]
        assert entry["actor"]["full_name"] == "Tess Tan"

    def test_an_automatic_entry_has_no_actor(self, monkeypatch):
        monkeypatch.setattr(repository, "list_technical_history", lambda event_id: [
            {"id": "history-2", "action": "released", "created_at": START.isoformat(), "actor": None},
        ])

        assert event_technical_history(EVENT_ID)[0]["actor"] is None


class TestRefusalStatuses:
    def test_a_person_who_is_not_a_coordinator_is_a_validation_error(self):
        assert CoordinatorNotEligibleError().status_code == 422

    def test_a_notification_the_caller_cannot_see_is_not_found(self):
        assert NotificationNotFoundError().status_code == 404
