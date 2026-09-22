"""SQLAlchemy models for the equipment availability domain.

These models mirror the Supabase migration. The equipment domain deliberately
does not own the events table, so reservation.event_id remains an unlinked UUID.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import ENUM as PostgreSQLEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID

class Base(DeclarativeBase):
    pass


class EquipmentStatus(StrEnum):
    ACTIVE = "active"
    MAINTENANCE = "maintenance"
    RETIRED = "retired"


class ReservationStatus(StrEnum):
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


_SpecificationsType = JSON().with_variant(JSONB, "postgresql")
_EquipmentStatusType = String(20).with_variant(
    PostgreSQLEnum(
        EquipmentStatus,
        name="equipment_status",
        create_type=False,
        values_callable=lambda enum_type: [member.value for member in enum_type],
    ),
    "postgresql",
)
_ReservationStatusType = String(20).with_variant(
    PostgreSQLEnum(
        ReservationStatus,
        name="equipment_reservation_status",
        create_type=False,
        values_callable=lambda enum_type: [member.value for member in enum_type],
    ),
    "postgresql",
)


class Equipment(Base):
    __tablename__ = "equipment"

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    equipment_type: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    total_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[EquipmentStatus] = mapped_column(_EquipmentStatusType, nullable=False, default=EquipmentStatus.ACTIVE)
    specifications: Mapped[dict | None] = mapped_column(_SpecificationsType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    unavailability: Mapped[list[EquipmentUnavailability]] = relationship(back_populates="equipment")
    reservations: Mapped[list[EquipmentReservation]] = relationship(back_populates="equipment")


class EquipmentUnavailability(Base):
    __tablename__ = "equipment_unavailability"
    __table_args__ = (Index("ix_equipment_unavailability_equipment_range", "equipment_id", "start_at", "end_at"),)

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    equipment_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("equipment.id", ondelete="CASCADE"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    equipment: Mapped[Equipment] = relationship(back_populates="unavailability")


class EquipmentReservation(Base):
    __tablename__ = "equipment_reservations"
    __table_args__ = (Index("ix_equipment_reservations_equipment_range", "equipment_id", "start_at", "end_at"),)

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    equipment_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("equipment.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[ReservationStatus] = mapped_column(_ReservationStatusType, nullable=False, default=ReservationStatus.CONFIRMED)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    equipment: Mapped[Equipment] = relationship(back_populates="reservations")