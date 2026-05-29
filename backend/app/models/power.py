from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class PowerAggregate(TimestampMixin, Base):
    __tablename__ = "power_aggregates"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "source_type", "period", "period_start"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[int | None]
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    period: Mapped[str] = mapped_column(String(20), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    avg_watts: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    min_watts: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    max_watts: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    sample_count: Mapped[int] = mapped_column(nullable=False, default=0)
    coverage_percent: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    unknown_count: Mapped[int] = mapped_column(nullable=False, default=0)
    stale_count: Mapped[int] = mapped_column(nullable=False, default=0)


class RackHourlyKwh(TimestampMixin, Base):
    __tablename__ = "rack_hourly_kwh"
    __table_args__ = (UniqueConstraint("rack_id", "hour_start"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    rack_id: Mapped[int] = mapped_column(nullable=False)
    hour_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actual_kwh: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    estimated_kwh: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    basis_source: Mapped[str] = mapped_column(String(30), nullable=False)
    coverage_state: Mapped[str] = mapped_column(String(30), nullable=False)


class RackMonthlyKwh(TimestampMixin, Base):
    __tablename__ = "rack_monthly_kwh"
    __table_args__ = (UniqueConstraint("rack_id", "month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    rack_id: Mapped[int] = mapped_column(nullable=False)
    month: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actual_kwh: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    estimated_kwh: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    coverage_percent: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    estimated_hours: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    carry_forward_max_hours: Mapped[int] = mapped_column(nullable=False)
    needs_recalculation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
