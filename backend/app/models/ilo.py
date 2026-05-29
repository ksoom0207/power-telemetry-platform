from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class CollectionRun(TimestampMixin, Base):
    __tablename__ = "collection_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    triggered_by: Mapped[str] = mapped_column(String(30), nullable=False)
    total_targets: Mapped[int] = mapped_column(nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(nullable=False, default=0)

    ilo_samples: Mapped[list["IloPowerSample"]] = relationship(back_populates="collection_run")


class IloPowerSample(TimestampMixin, Base):
    __tablename__ = "ilo_power_samples"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), nullable=False)
    collection_run_id: Mapped[int] = mapped_column(
        ForeignKey("collection_runs.id"), nullable=False
    )
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    average_watts: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    auth_method_used: Mapped[str | None] = mapped_column(String(30))
    profile_used: Mapped[str | None] = mapped_column(String(50))
    quality: Mapped[str] = mapped_column(String(50), nullable=False, default="collected_ilo")

    collection_run: Mapped[CollectionRun] = relationship(back_populates="ilo_samples")
