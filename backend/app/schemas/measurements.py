from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class MeasurementBatchCreate(BaseModel):
    client_batch_id: str | None = None
    operator_name: str = Field(min_length=1)
    measured_at: datetime
    note: str | None = None


class MeasurementBatchRead(BaseModel):
    id: int
    client_batch_id: str
    operator_name: str
    measured_at: datetime
    note: str | None
    source: str


class RackMeasurementCreate(BaseModel):
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


class RackMeasurementBulkCreate(BaseModel):
    batch_id: int
    rows: list[RackMeasurementCreate]


class DevicePowerCreate(BaseModel):
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


class DevicePowerBulkCreate(BaseModel):
    batch_id: int
    rows: list[DevicePowerCreate]


class PhaseMainMeasurementCreate(BaseModel):
    phase: str
    measurement_point: str = "phase_branch"
    amp: Decimal
    note: str | None = None


class PhaseMainMeasurementBulkCreate(BaseModel):
    batch_id: int
    rows: list[PhaseMainMeasurementCreate]


class MeasurementUpdate(BaseModel):
    watts: Decimal | None = None
    voltage: Decimal | None = None
    amp: Decimal | None = None
    power_factor: Decimal | None = None
    voltage_source: str | None = None
    power_factor_source: str | None = None
    note: str | None = None
    confirmed: bool = False


class BulkCreateResult(BaseModel):
    created_ids: list[int]
    warnings: list[dict[str, object]]
