from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


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
        return self


class ItemAvailabilityResult(BaseModel):
    equipment_id: UUID
    name: str
    quantity_needed: int
    quantity_available: int
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
    requested_by: Requester | None
    created_at: datetime


class EquipmentRequestLinesResponse(BaseModel):
    lines: list[EquipmentRequestLine]


class PendingEquipmentLine(EquipmentRequestLine):
    event_name: str
    event_starts_at: datetime | None


class PendingEquipmentLinesResponse(BaseModel):
    lines: list[PendingEquipmentLine]
