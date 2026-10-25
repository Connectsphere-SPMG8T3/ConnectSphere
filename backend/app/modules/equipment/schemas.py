from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, StrictBool, field_validator, model_validator


class EquipmentCheckItem(BaseModel):
    equipment_id: UUID
    quantity_needed: int = Field(gt=0)


class EquipmentAvailabilityRequest(BaseModel):
    start_at: datetime
    end_at: datetime
    items: list[EquipmentCheckItem] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_period(self) -> "EquipmentAvailabilityRequest":
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be later than start_at")
        if len({item.equipment_id for item in self.items}) != len(self.items):
            raise ValueError("Each item can appear once in a check; combine the quantities.")
        return self


class ItemAvailabilityResult(BaseModel):
    equipment_id: UUID
    name: str
    storage_location: str | None = None
    quantity_needed: int
    quantity_available: int
    quantity_missing: int
    sufficient: bool


class EquipmentAvailabilityResponse(BaseModel):
    sufficient: bool
    items: list[ItemAvailabilityResult]


class EquipmentInventoryItem(BaseModel):
    equipment_id: UUID
    name: str
    total_quantity: int
    reserved_quantity: int
    maintenance_quantity: int
    net_available: int


class EquipmentInventoryResponse(BaseModel):
    items: list[EquipmentInventoryItem]


class EquipmentMaintenanceItem(BaseModel):
    maintenance_id: UUID
    equipment_id: UUID
    equipment_name: str
    start_at: datetime
    end_at: datetime
    reason: str | None = None
    status: str


class EquipmentMaintenanceResponse(BaseModel):
    items: list[EquipmentMaintenanceItem]


# --- SCRUM-45 equipment request lines (REQUIREMENTS 6.15) ---------------------

# Postgres `integer`: anything larger couldn't be stored, so it is refused here.
MAX_QUANTITY = 2_147_483_647
# [Assumption] REQUIREMENTS 9: a bound on one submission, generous for a single event.
MAX_ITEMS_PER_SUBMISSION = 50
TECHNICAL_REQUIREMENTS_MAX_LENGTH = 1000


class CatalogueItem(BaseModel):
    equipment_id: UUID
    name: str
    equipment_type: str
    total_quantity: int


class CatalogueResponse(BaseModel):
    items: list[CatalogueItem]


class EquipmentRequestItem(BaseModel):
    equipment_id: UUID
    # Strict: "2", 2.0 and true are not whole numbers the coordinator typed.
    quantity: Annotated[int, Field(strict=True, ge=1, le=MAX_QUANTITY)]
    technical_requirements: str | None = Field(default=None, max_length=TECHNICAL_REQUIREMENTS_MAX_LENGTH)

    @field_validator("technical_requirements")
    @classmethod
    def blank_is_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class EquipmentRequestCreate(BaseModel):
    event_id: UUID
    items: list[EquipmentRequestItem] = Field(min_length=1, max_length=MAX_ITEMS_PER_SUBMISSION)

    @model_validator(mode="after")
    def one_line_per_item(self) -> "EquipmentRequestCreate":
        # [Assumption] REQUIREMENTS 9: one line per item in a submission, so tech
        # support decide on one quantity rather than two lines for the same thing.
        seen = set()
        for item in self.items:
            if item.equipment_id in seen:
                raise ValueError("Each item can appear once in a request; combine the quantities.")
            seen.add(item.equipment_id)
        return self


class Requester(BaseModel):
    id: UUID
    full_name: str


class EquipmentRequestLine(BaseModel):
    id: UUID
    submission_id: UUID
    event_id: UUID
    equipment_id: UUID
    equipment_name: str
    quantity: int
    technical_requirements: str | None
    status: str
    # SCRUM-24 AC9: internal, so only tech support and the assigned coordinator
    # ever receive a line (AC12).
    technical_notes: str | None = None
    not_available_reason: str | None = None
    requested_by: Requester | None
    created_at: datetime


class EquipmentRequestLinesResponse(BaseModel):
    lines: list[EquipmentRequestLine]
    # SCRUM-24 AC9-AC11, on the coordinator's event view only.
    technical_status: str | None = None
    exit_confirmation: "ExitConfirmation | None" = None


class PendingEquipmentLine(EquipmentRequestLine):
    event_name: str
    event_starts_at: datetime | None
    # Tech support sort their requests by type (REQUIREMENTS §6.15).
    equipment_type: str | None = None


class PendingEquipmentLinesResponse(BaseModel):
    lines: list[PendingEquipmentLine]


# --- SCRUM-24 reservation ------------------------------------------------------

NOT_AVAILABLE_REASON_MAX_LENGTH = 500
TECHNICAL_NOTES_MAX_LENGTH = 2000


class NotAvailableRequest(BaseModel):
    """AC3, AC9: a reason is required (EQ-R3)."""

    reason: str = Field(max_length=NOT_AVAILABLE_REASON_MAX_LENGTH)

    @field_validator("reason")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Give a reason the line is not available.")
        return value


class LineNoteRequest(BaseModel):
    """AC9: internal notes; blank clears them."""

    note: str | None = Field(default=None, max_length=TECHNICAL_NOTES_MAX_LENGTH)

    @field_validator("note")
    @classmethod
    def blank_is_none(cls, value: str | None) -> str | None:
        return (value or "").strip() or None


class ExitConfirmationRequest(BaseModel):
    """AC10: tick or untick "Equipment does not block exits or walkways"."""

    confirmed: StrictBool


class LineActionResponse(BaseModel):
    line_id: UUID
    status: str
    free_quantity: int | None = None


class ExitConfirmation(BaseModel):
    """Who ticked "Equipment does not block exits or walkways", and when (AC10).
    Shared with the safety review page (CR-103 AC3)."""

    confirmed_by_name: str | None
    confirmed_at: datetime


class TechnicalHistoryEntry(BaseModel):
    action: str
    line_label: str | None
    from_status: str | None
    to_status: str | None
    detail: str | None
    actor_name: str | None
    created_at: datetime


class TechnicalEvent(BaseModel):
    id: UUID
    name: str
    status: str
    starts_at: datetime | None
    ends_at: datetime | None
    coordinator_name: str | None


class TechnicalEventResponse(BaseModel):
    """Technical Support's view of one event's equipment (AC9-AC13)."""

    event: TechnicalEvent
    technical_status: str
    exit_confirmation: ExitConfirmation | None
    lines: list[EquipmentRequestLine]
    history: list[TechnicalHistoryEntry]


EquipmentRequestLinesResponse.model_rebuild()
