from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Threshold(TimestampMixin, Base):
    __tablename__ = "thresholds"

    id: Mapped[int] = mapped_column(primary_key=True)
    target_type: Mapped[str] = mapped_column(String(30), nullable=False)
    target_id: Mapped[int | None]
    basis: Mapped[str] = mapped_column(String(50), nullable=False)
    warning_watts: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    critical_watts: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    trigger_count: Mapped[int] = mapped_column(nullable=False, default=1)
    clear_count: Mapped[int] = mapped_column(nullable=False, default=2)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ThresholdState(TimestampMixin, Base):
    __tablename__ = "threshold_states"

    threshold_id: Mapped[int] = mapped_column(ForeignKey("thresholds.id"), primary_key=True)
    current_state: Mapped[str] = mapped_column(String(30), nullable=False)
    consecutive_trigger_count: Mapped[int] = mapped_column(nullable=False, default=0)
    consecutive_clear_count: Mapped[int] = mapped_column(nullable=False, default=0)
    last_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
