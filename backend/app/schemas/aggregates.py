from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PowerAggregateUpsert(StrictBaseModel):
    entity_type: str = Field(min_length=1, max_length=30)
    entity_id: int
    source_type: str = Field(min_length=1, max_length=50)
    period: str = Field(min_length=1, max_length=20)
    period_start: datetime
    avg_watts: Decimal | None = None
    min_watts: Decimal | None = None
    max_watts: Decimal | None = None
    sample_count: int = Field(ge=0)
    coverage_percent: Decimal = Field(ge=0, le=100)
    unknown_count: int = Field(default=0, ge=0)
    stale_count: int = Field(default=0, ge=0)


class PowerAggregateRead(PowerAggregateUpsert):
    id: int
    created_at: datetime
    updated_at: datetime
