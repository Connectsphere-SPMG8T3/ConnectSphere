from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.db.models import Base, Equipment, EquipmentReservation, EquipmentUnavailability, ReservationStatus
from app.db.session import get_db
from app.main import app
from app.modules.equipment.service import check_equipment_availability
from app.modules.equipment.schemas import EquipmentAvailabilityRequest


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _period():
    start = datetime(2026, 10, 15, 9, tzinfo=timezone.utc)
    return start, start + timedelta(hours=2)


def _equipment(db, quantity=10):
    item = Equipment(
        name="Projector",
        equipment_type="display",
        total_quantity=quantity,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(item)
    db.commit()
    return item


def _check(db, equipment_id, quantity):
    start, end = _period()
    return check_equipment_availability(
        db,
        start,
        end,
        EquipmentAvailabilityRequest(
            start_at=start,
            end_at=end,
            items=[{"equipment_id": equipment_id, "quantity_needed": quantity}],
        ).items,
    ).items[0]


def test_sufficient_stock_returns_available_quantity(db):
    item = _equipment(db, quantity=5)

    result = _check(db, item.id, 5)

    assert result.quantity_available == 5
    assert result.sufficient is True


def test_over_requested_stock_is_insufficient(db):
    item = _equipment(db, quantity=5)

    result = _check(db, item.id, 6)

    assert result.quantity_available == 5
    assert result.sufficient is False


def test_overlapping_confirmed_reservation_and_unavailability_reduce_stock(db):
    item = _equipment(db, quantity=10)
    start, end = _period()
    db.add(
        EquipmentReservation(
            equipment_id=item.id,
            event_id=uuid4(),
            quantity=3,
            start_at=start,
            end_at=end,
            status=ReservationStatus.CONFIRMED,
            created_at=start,
            updated_at=start,
        )
    )
    db.add(
        EquipmentUnavailability(
            equipment_id=item.id,
            quantity=2,
            start_at=start,
            end_at=end,
            created_at=start,
        )
    )
    db.commit()

    result = _check(db, item.id, 6)

    assert result.quantity_available == 5
    assert result.sufficient is False


def test_non_overlapping_reservation_does_not_reduce_stock(db):
    item = _equipment(db, quantity=5)
    start, end = _period()
    db.add(
        EquipmentReservation(
            equipment_id=item.id,
            event_id=uuid4(),
            quantity=5,
            start_at=end,
            end_at=end + timedelta(hours=2),
            status=ReservationStatus.CONFIRMED,
            created_at=start,
            updated_at=start,
        )
    )
    db.commit()

    result = _check(db, item.id, 5)

    assert result.quantity_available == 5
    assert result.sufficient is True


def test_unknown_equipment_is_insufficient(db):
    result = _check(db, uuid4(), 1)

    assert result.quantity_available == 0
    assert result.sufficient is False


def test_non_technical_support_role_is_forbidden(monkeypatch):
    user = CurrentUser(
        id=str(uuid4()),
        email="coordinator@connectsphere.dev",
        full_name="Coordinator",
        role="event_coordinator",
        access_token="test-token",
    )
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: iter([None])
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
        app.dependency_overrides.pop(get_db, None)