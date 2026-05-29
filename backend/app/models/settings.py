from decimal import Decimal

from sqlalchemy import Boolean, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class IloCredentialSetting(TimestampMixin, Base):
    __tablename__ = "ilo_credential_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_password: Mapped[str] = mapped_column(String(2048), nullable=False)
    auth_mode: Mapped[str] = mapped_column(String(50), nullable=False)
    tls_verify: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    timeout_seconds: Mapped[int] = mapped_column(nullable=False, default=10)


class PowerDefaultSetting(TimestampMixin, Base):
    __tablename__ = "power_default_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    default_voltage: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    default_power_factor: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    carry_forward_max_hours: Mapped[int] = mapped_column(nullable=False, default=6)
