from decimal import Decimal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(default="postgresql+asyncpg://power:power@localhost:5432/power")
    secret_key: str = Field(default="dev-secret-key")
    default_voltage: Decimal = Field(default=Decimal("220"))
    default_power_factor: Decimal = Field(default=Decimal("0.95"))
    ilo_timeout_seconds: int = Field(default=10)
    ilo_tls_verify: bool = Field(default=False)
    carry_forward_max_hours: int = Field(default=6)


settings = Settings()
