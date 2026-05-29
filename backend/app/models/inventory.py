from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.measurements import ManualDevicePower, RackMeasurement


class Rack(TimestampMixin, Base):
    __tablename__ = "racks"
    __table_args__ = (UniqueConstraint("name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phase: Mapped[str] = mapped_column(String(1), nullable=False)
    voltage: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    circuit_name: Mapped[str | None] = mapped_column(String(255))
    capacity_amp: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    devices: Mapped[list["Device"]] = relationship(back_populates="rack")
    measurements: Mapped[list["RackMeasurement"]] = relationship(back_populates="rack")


class Device(TimestampMixin, Base):
    __tablename__ = "devices"
    __table_args__ = (UniqueConstraint("name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    rack_id: Mapped[int] = mapped_column(ForeignKey("racks.id"), nullable=False)
    device_type: Mapped[str] = mapped_column(String(50), nullable=False)
    u_position_start: Mapped[int | None]
    u_position_end: Mapped[int | None]
    has_ilo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ilo_host: Mapped[str | None] = mapped_column(String(255))
    ilo_profile: Mapped[str | None] = mapped_column(String(50))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    rack: Mapped[Rack] = relationship(back_populates="devices")
    manual_powers: Mapped[list["ManualDevicePower"]] = relationship(back_populates="device")
