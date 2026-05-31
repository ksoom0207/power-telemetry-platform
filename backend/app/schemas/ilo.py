from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IloStatusRead(StrictBaseModel):
    credential_configured: bool
    supported_profiles: list[str]
    target_count: int


class IloPowerSampleRead(StrictBaseModel):
    id: int
    device_id: int
    collection_run_id: int
    measured_at: datetime
    average_watts: Decimal | None
    status: str
    auth_method_used: str | None
    profile_used: str | None
    quality: str


class CollectionRunRead(StrictBaseModel):
    id: int
    started_at: datetime
    finished_at: datetime | None
    status: str
    triggered_by: str
    total_targets: int
    success_count: int
    failed_count: int


class CollectionRunDetail(CollectionRunRead):
    samples: list[IloPowerSampleRead]


class IloListQuery(StrictBaseModel):
    limit: int = Field(default=100, ge=1, le=1000)
