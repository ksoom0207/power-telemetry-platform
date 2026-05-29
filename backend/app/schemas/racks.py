from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RackBase(StrictBaseModel):
    name: str = Field(min_length=1, max_length=255)
    phase: str
    voltage: Decimal
    circuit_name: str | None = None
    capacity_amp: Decimal | None = None
    active: bool = True

    @field_validator("phase")
    @classmethod
    def validate_phase(cls, value: str) -> str:
        if value not in {"R", "S", "T"}:
            raise ValueError("phase must be one of R, S, T")
        return value


class RackCreate(RackBase):
    pass


class RackUpdate(StrictBaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    phase: str | None = None
    voltage: Decimal | None = None
    circuit_name: str | None = None
    capacity_amp: Decimal | None = None
    active: bool | None = None

    @field_validator("phase")
    @classmethod
    def validate_phase(cls, value: str | None) -> str | None:
        if value is not None and value not in {"R", "S", "T"}:
            raise ValueError("phase must be one of R, S, T")
        return value


class RackRead(RackBase):
    id: int
