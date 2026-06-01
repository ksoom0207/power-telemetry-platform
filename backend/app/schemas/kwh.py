from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RackHourlyKwhRead(StrictBaseModel):
    id: int
    rack_id: int
    hour_start: datetime
    actual_kwh: Decimal
    estimated_kwh: Decimal
    basis_source: str
    coverage_state: str
    created_at: datetime
    updated_at: datetime


class RackMonthlyKwhRead(StrictBaseModel):
    id: int
    rack_id: int
    month: datetime
    actual_kwh: Decimal
    estimated_kwh: Decimal
    coverage_percent: Decimal
    estimated_hours: Decimal
    carry_forward_max_hours: int
    needs_recalculation: bool
    created_at: datetime
    updated_at: datetime
