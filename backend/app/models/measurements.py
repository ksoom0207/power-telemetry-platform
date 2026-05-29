from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.inventory import Device, Rack


class MeasurementBatch(TimestampMixin, Base):
    __tablename__ = "measurement_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_batch_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    operator_name: Mapped[str] = mapped_column(String(255), nullable=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(String(1000))
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="web_bulk_input")

    rack_measurements: Mapped[list[RackMeasurement]] = relationship(back_populates="batch")
    manual_device_powers: Mapped[list[ManualDevicePower]] = relationship(back_populates="batch")
    phase_main_measurements: Mapped[list[PhaseMainMeasurement]] = relationship(
        back_populates="batch"
    )


class RackMeasurement(TimestampMixin, Base):
    __tablename__ = "rack_measurements"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("measurement_batches.id"), nullable=False)
    rack_id: Mapped[int] = mapped_column(ForeignKey("racks.id"), nullable=False)
    measurement_point: Mapped[str] = mapped_column(String(50), nullable=False)
    watts: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    voltage: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    amp: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    power_factor: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    voltage_source: Mapped[str] = mapped_column(String(30), nullable=False)
    power_factor_source: Mapped[str] = mapped_column(String(30), nullable=False)
    quality: Mapped[str] = mapped_column(String(50), nullable=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    operator_name: Mapped[str] = mapped_column(String(255), nullable=False)
    note: Mapped[str | None] = mapped_column(String(1000))

    batch: Mapped[MeasurementBatch] = relationship(back_populates="rack_measurements")
    rack: Mapped[Rack] = relationship(back_populates="measurements")


class ManualDevicePower(TimestampMixin, Base):
    __tablename__ = "manual_device_powers"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("measurement_batches.id"))
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), nullable=False)
    measurement_point: Mapped[str] = mapped_column(String(50), nullable=False)
    value_type: Mapped[str] = mapped_column(String(30), nullable=False)
    watts: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    voltage: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    amp: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    power_factor: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    voltage_source: Mapped[str] = mapped_column(String(30), nullable=False)
    power_factor_source: Mapped[str] = mapped_column(String(30), nullable=False)
    quality: Mapped[str] = mapped_column(String(50), nullable=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    operator_name: Mapped[str] = mapped_column(String(255), nullable=False)
    note: Mapped[str | None] = mapped_column(String(1000))

    batch: Mapped[MeasurementBatch | None] = relationship(back_populates="manual_device_powers")
    device: Mapped[Device] = relationship(back_populates="manual_powers")


class PhaseMainMeasurement(TimestampMixin, Base):
    __tablename__ = "phase_main_measurements"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("measurement_batches.id"), nullable=False)
    phase: Mapped[str] = mapped_column(String(1), nullable=False)
    measurement_point: Mapped[str] = mapped_column(String(50), nullable=False)
    amp: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    voltage_default_used: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    power_factor_default_used: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    voltage_source: Mapped[str] = mapped_column(String(30), nullable=False)
    power_factor_source: Mapped[str] = mapped_column(String(30), nullable=False)
    quality: Mapped[str] = mapped_column(String(50), nullable=False)
    calculated_watts: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    operator_name: Mapped[str] = mapped_column(String(255), nullable=False)
    note: Mapped[str | None] = mapped_column(String(1000))

    batch: Mapped[MeasurementBatch] = relationship(back_populates="phase_main_measurements")
