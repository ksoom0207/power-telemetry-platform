from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IloCredentialUpsert(StrictBaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str | None = Field(default=None, min_length=1)
    auth_mode: str = "session_with_basic_fallback"
    tls_verify: bool = False
    timeout_seconds: int = Field(default=10, ge=1)


class IloCredentialRead(StrictBaseModel):
    id: int | None = None
    username: str | None = None
    auth_mode: str = "session_with_basic_fallback"
    tls_verify: bool = False
    timeout_seconds: int = 10
    password_configured: bool


class PowerDefaultsUpsert(StrictBaseModel):
    default_voltage: Decimal
    default_power_factor: Decimal
    carry_forward_max_hours: int = Field(default=6, ge=0)


class PowerDefaultsRead(PowerDefaultsUpsert):
    id: int | None = None
