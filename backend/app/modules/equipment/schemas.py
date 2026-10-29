from datetime import datetime
from enum import Enum
from typing import Annotated, Literal
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


# SCRUM-44: the statuses a line can be changed or removed from. A released line
# has already left the request.
LiveLineStatus = Literal["pending", "reserved", "re_review", "rejected"]


class EquipmentLineUpdate(EquipmentRequestItem):
    """SCRUM-44 AC2: a line's new item, quantity and requirements, with the same
    rules as submitting it (SCRUM-45). `expected_status` is the status the
    coordinator saw, so a reservation that lands first refuses the edit (AC6)."""

    expected_status: LiveLineStatus


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
    # Story 37: why an approved time change marked it Needs re-review; null once sent.
    needs_re_review_reason: str | None = None
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


class PreparationStage(str, Enum):
    """CR-110 AC2, RD-R2: the stages named in the M3 meeting, shared with venue
    preparation (CR-109). Any stage can follow any other [Assumption]."""

    not_started = "not_started"
    in_preparation = "in_preparation"
    in_progress = "in_progress"
    completed = "completed"


class TechnicalPreparationRequest(LineNoteRequest):
    """CR-110 AC2: the event's stage, with the same internal note rules as a line (24 AC12)."""

    stage: PreparationStage


class TechnicalPreparationUpdated(BaseModel):
    stage: PreparationStage
    note: str | None
    # Preparation after the first update on a Confirmed event (AC3).
    event_status: str


class TechnicalPreparationStage(BaseModel):
    """CR-110 AC4: what the organiser sees; never the note (AUTH-R2)."""

    stage: PreparationStage
    updated_at: datetime | None


class TechnicalPreparation(TechnicalPreparationStage):
    """CR-110 AC2, AC4: Technical Support's and the assigned coordinator's view."""

    note: str | None
    updated_by_name: str | None


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
    # D70: the line the entry is about, or null for the event's own entries, so a
    # line under re-review can say what put it there.
    request_id: UUID | None = None
    line_label: str | None
    from_status: str | None
    to_status: str | None
    detail: str | None
    actor_name: str | None
    created_at: datetime


class TechnicalHistoryResponse(BaseModel):
    """SCRUM-44 AC8: an event's equipment history for its assigned coordinator,
    where a removed line stays visible."""

    history: list[TechnicalHistoryEntry]


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
    technical_preparation: TechnicalPreparation
    lines: list[EquipmentRequestLine]
    history: list[TechnicalHistoryEntry]
    # Story 37 Q21: the approved change a line under re-review is checked against.
    re_review_changes: dict | None = None


EquipmentRequestLinesResponse.model_rebuild()
