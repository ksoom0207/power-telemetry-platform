from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ThresholdCreate(StrictBaseModel):
    target_type: str = Field(min_length=1, max_length=30)
    target_id: int | None = None
    basis: str = Field(min_length=1, max_length=50)
    warning_watts: Decimal | None = None
    critical_watts: Decimal | None = None
    trigger_count: int = Field(default=1, ge=1)
    clear_count: int = Field(default=2, ge=1)
    active: bool = True


class ThresholdUpdate(StrictBaseModel):
    target_type: str | None = Field(default=None, min_length=1, max_length=30)
    target_id: int | None = None
    basis: str | None = Field(default=None, min_length=1, max_length=50)
    warning_watts: Decimal | None = None
    critical_watts: Decimal | None = None
    trigger_count: int | None = Field(default=None, ge=1)
    clear_count: int | None = Field(default=None, ge=1)
    active: bool | None = None


class ThresholdRead(StrictBaseModel):
    id: int
    target_type: str
    target_id: int | None
    basis: str
    warning_watts: Decimal | None
    critical_watts: Decimal | None
    trigger_count: int
    clear_count: int
    active: bool
    created_at: datetime
    updated_at: datetime


class ThresholdStateRead(StrictBaseModel):
    threshold_id: int
    current_state: str
    consecutive_trigger_count: int
    consecutive_clear_count: int
    last_evaluated_at: datetime | None
    created_at: datetime
    updated_at: datetime
