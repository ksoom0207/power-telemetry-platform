from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MeasurementBatchCreate(StrictBaseModel):
    client_batch_id: str | None = None
    operator_name: str = Field(min_length=1)
    measured_at: datetime
    note: str | None = None


class MeasurementBatchRead(StrictBaseModel):
    id: int
    client_batch_id: str
    operator_name: str
    measured_at: datetime
    note: str | None
    source: str


class RackMeasurementCreate(StrictBaseModel):
    rack_id: int
    measurement_point: str = "rack_input"
    watts: Decimal | None = None
    voltage: Decimal | None = None
    amp: Decimal | None = None
    power_factor: Decimal | None = None
    voltage_source: str = "default"
    power_factor_source: str = "default"
    note: str | None = None
    confirmed: bool = False


class RackMeasurementBulkCreate(StrictBaseModel):
    batch_id: int
    rows: list[RackMeasurementCreate]


class DevicePowerCreate(StrictBaseModel):
    device_id: int
    measurement_point: str = "device_power_cord"
    value_type: str
    watts: Decimal | None = None
    voltage: Decimal | None = None
    amp: Decimal | None = None
    power_factor: Decimal | None = None
    voltage_source: str = "default"
    power_factor_source: str = "default"
    note: str | None = None
    confirmed: bool = False


class DevicePowerBulkCreate(StrictBaseModel):
    batch_id: int
    rows: list[DevicePowerCreate]


class PhaseMainMeasurementCreate(StrictBaseModel):
    phase: Literal["R", "S", "T"]
    measurement_point: str = "phase_branch"
    amp: Decimal
    note: str | None = None


class PhaseMainMeasurementBulkCreate(StrictBaseModel):
    batch_id: int
    rows: list[PhaseMainMeasurementCreate]


class RackMeasurementUpdate(StrictBaseModel):
    watts: Decimal | None = None
    voltage: Decimal | None = None
    amp: Decimal | None = None
    power_factor: Decimal | None = None
    voltage_source: str | None = None
    power_factor_source: str | None = None
    note: str | None = None
    confirmed: bool = False


class DevicePowerMeasurementUpdate(RackMeasurementUpdate):
    value_type: str | None = None


class PhaseMainMeasurementUpdate(StrictBaseModel):
    phase: Literal["R", "S", "T"] | None = None
    measurement_point: str | None = None
    amp: Decimal | None = None
    note: str | None = None


class BulkCreateResult(StrictBaseModel):
    created_ids: list[int]
    warnings: list[dict[str, object]]


class MeasurementUpdateResult(StrictBaseModel):
    row: dict[str, object]
    warnings: list[dict[str, object]]
