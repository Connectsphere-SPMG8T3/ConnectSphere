from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


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