# Power Monitoring Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a backend-first power monitoring dashboard with FastAPI, PostgreSQL, worker jobs, iLO collection, manual measurements, aggregates, kWh, thresholds, Excel import, and a minimal React frontend.

**Architecture:** The backend exposes REST APIs through FastAPI and keeps business logic in services behind repository interfaces. A separate worker container shares the backend codebase and runs iLO collection, aggregation, kWh, threshold, and recalculation jobs. The React frontend is a simple operational UI that validates the API flows and can be upgraded later.

**Tech Stack:** Python, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, PostgreSQL, pytest, React, TypeScript, Vite, Docker Compose.

---

## File Structure

Create this structure:

```text
backend/
  alembic/
  alembic.ini
  app/
    __init__.py
    api/
      __init__.py
      deps.py
      routes/
        __init__.py
        aggregates.py
        devices.py
        imports.py
        ilo.py
        kwh.py
        measurement_batches.py
        measurements.py
        overview.py
        phases.py
        racks.py
        settings.py
        thresholds.py
    core/
      __init__.py
      config.py
      database.py
      datetime.py
      encryption.py
      errors.py
      logging.py
      numeric.py
    integrations/
      __init__.py
      ilo/
        __init__.py
        auth.py
        client.py
        profiles.py
      snmp/
        __init__.py
        client.py
        profiles.py
    models/
      __init__.py
      base.py
      inventory.py
      ilo.py
      measurements.py
      power.py
      settings.py
      thresholds.py
      imports.py
    repositories/
      __init__.py
      aggregates.py
      devices.py
      imports.py
      ilo.py
      kwh.py
      measurements.py
      racks.py
      settings.py
      thresholds.py
    schemas/
      __init__.py
      aggregates.py
      common.py
      devices.py
      imports.py
      ilo.py
      kwh.py
      measurements.py
      overview.py
      racks.py
      settings.py
      thresholds.py
    services/
      __init__.py
      aggregates.py
      imports.py
      ilo_collection.py
      kwh.py
      measurements.py
      overview.py
      power_calculations.py
      representative_power.py
      snmp_collection.py
      thresholds.py
    workers/
      __init__.py
      jobs.py
      main.py
    main.py
  tests/
    conftest.py
    unit/
      test_kwh.py
      test_measurement_validation.py
      test_representative_power.py
      test_thresholds.py
    integration/
      test_ilo_client.py
frontend/
  package.json
  index.html
  src/
    api/
      client.ts
      types.ts
    components/
    pages/
      HomePage.tsx
      InventoryPage.tsx
      MeasurementInputPage.tsx
      RackDetailPage.tsx
      SettingsPage.tsx
      ThresholdPage.tsx
    App.tsx
    main.tsx
docker-compose.yml
.env.example
```

Conventions:

- Python type hints are required.
- API routers never access SQLAlchemy sessions directly except through service calls.
- Use `router -> service -> repository`.
- Calculation logic must be pure functions where practical.
- Use timezone-aware datetimes only; persist UTC.
- Use `Decimal` for amp, volt, power factor, watts, and kWh.
- API paths use kebab-case and plural nouns.

---

### Task 1: Backend Project Scaffold

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/main.py`
- Create: `backend/app/core/config.py`
- Create: `backend/app/core/database.py`
- Create: `backend/app/core/errors.py`
- Create: `backend/app/core/datetime.py`
- Create: `backend/app/core/numeric.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/unit/test_core_datetime.py`
- Create: `.env.example`

- [ ] **Step 1: Write failing datetime tests**

Create `backend/tests/unit/test_core_datetime.py`:

```python
from datetime import UTC, datetime

import pytest

from app.core.datetime import ensure_aware, to_utc


def test_ensure_aware_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        ensure_aware(datetime(2026, 5, 29, 12, 0, 0))


def test_to_utc_converts_aware_datetime() -> None:
    value = datetime(2026, 5, 29, 3, 0, 0, tzinfo=UTC)

    assert to_utc(value) == datetime(2026, 5, 29, 3, 0, 0, tzinfo=UTC)
```

- [ ] **Step 2: Create backend package and config**

Create `backend/pyproject.toml`:

```toml
[project]
name = "power-monitoring-backend"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "alembic>=1.13",
  "asyncpg>=0.29",
  "cryptography>=42.0",
  "fastapi>=0.111",
  "httpx>=0.27",
  "openpyxl>=3.1",
  "pydantic-settings>=2.2",
  "pydantic>=2.7",
  "sqlalchemy>=2.0",
  "uvicorn[standard]>=0.30",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.2",
  "pytest-asyncio>=0.23",
  "ruff>=0.5",
]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

Create `.env.example`:

```env
DATABASE_URL=postgresql+asyncpg://power:power@db:5432/power
SECRET_KEY=replace-with-fernet-compatible-secret
DEFAULT_VOLTAGE=220
DEFAULT_POWER_FACTOR=0.95
ILO_TIMEOUT_SECONDS=10
ILO_TLS_VERIFY=false
CARRY_FORWARD_MAX_HOURS=6
```

Create `backend/app/core/config.py`:

```python
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
```

Create `backend/app/core/datetime.py`:

```python
from datetime import UTC, datetime


def ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value


def to_utc(value: datetime) -> datetime:
    return ensure_aware(value).astimezone(UTC)
```

Create `backend/app/core/numeric.py`:

```python
from decimal import Decimal, ROUND_HALF_UP


WATT_DISPLAY_QUANT = Decimal("0.1")
KWH_DISPLAY_QUANT = Decimal("0.001")


def quantize_watts(value: Decimal) -> Decimal:
    return value.quantize(WATT_DISPLAY_QUANT, rounding=ROUND_HALF_UP)


def quantize_kwh(value: Decimal) -> Decimal:
    return value.quantize(KWH_DISPLAY_QUANT, rounding=ROUND_HALF_UP)
```

Create `backend/app/core/errors.py`:

```python
from typing import Any


class AppError(Exception):
    code = "APP_ERROR"

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ValidationAppError(AppError):
    code = "VALIDATION_ERROR"


class ExternalApiError(AppError):
    code = "EXTERNAL_API_ERROR"
```

Create `backend/app/core/database.py`:

```python
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
```

Create `backend/app/main.py`:

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.errors import AppError

app = FastAPI(title="Power Monitoring API")


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

Create empty `__init__.py` files in each package directory.

- [ ] **Step 3: Run tests**

Run:

```bash
cd backend
pytest tests/unit/test_core_datetime.py -v
```

Expected:

```text
2 passed
```

- [ ] **Step 4: Commit**

```bash
git add .env.example backend
git commit -m "chore: scaffold backend project"
```

---

### Task 2: SQLAlchemy Models and Alembic

**Files:**
- Create: `backend/app/models/base.py`
- Create: `backend/app/models/inventory.py`
- Create: `backend/app/models/ilo.py`
- Create: `backend/app/models/measurements.py`
- Create: `backend/app/models/power.py`
- Create: `backend/app/models/settings.py`
- Create: `backend/app/models/thresholds.py`
- Create: `backend/app/models/imports.py`
- Create: `backend/app/models/__init__.py`
- Create/modify: `backend/alembic.ini`
- Create/modify: `backend/alembic/env.py`
- Create: first Alembic revision

- [ ] **Step 1: Create ORM base**

Create `backend/app/models/base.py`:

```python
from datetime import datetime

from sqlalchemy import DateTime, MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

- [ ] **Step 2: Create inventory models**

Create `backend/app/models/inventory.py`:

```python
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


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
```

- [ ] **Step 3: Create iLO models**

Create `backend/app/models/ilo.py`:

```python
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

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


class IloPowerSample(TimestampMixin, Base):
    __tablename__ = "ilo_power_samples"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), nullable=False)
    collection_run_id: Mapped[int] = mapped_column(ForeignKey("collection_runs.id"), nullable=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    average_watts: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    auth_method_used: Mapped[str | None] = mapped_column(String(30))
    profile_used: Mapped[str | None] = mapped_column(String(50))
    quality: Mapped[str] = mapped_column(String(50), nullable=False, default="collected_ilo")
```

- [ ] **Step 4: Create measurement models**

Create `backend/app/models/measurements.py`:

```python
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class MeasurementBatch(TimestampMixin, Base):
    __tablename__ = "measurement_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_batch_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    operator_name: Mapped[str] = mapped_column(String(255), nullable=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(String(1000))
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="web_bulk_input")


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
```

- [ ] **Step 5: Create power, settings, threshold, and import models**

Create `backend/app/models/power.py`:

```python
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
```

Create `backend/app/models/settings.py`:

```python
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
```

Create `backend/app/models/thresholds.py`:

```python
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
```

Create `backend/app/models/imports.py`:

```python
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ImportLog(TimestampMixin, Base):
    __tablename__ = "import_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_count: Mapped[int] = mapped_column(nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(nullable=False, default=0)
    failure_summary: Mapped[str | None] = mapped_column(String(4000))
```

Create `backend/app/models/__init__.py`:

```python
from app.models.base import Base
from app.models.ilo import CollectionRun, IloPowerSample
from app.models.imports import ImportLog
from app.models.inventory import Device, Rack
from app.models.measurements import (
    ManualDevicePower,
    MeasurementBatch,
    PhaseMainMeasurement,
    RackMeasurement,
)
from app.models.power import PowerAggregate, RackHourlyKwh, RackMonthlyKwh
from app.models.settings import IloCredentialSetting, PowerDefaultSetting
from app.models.thresholds import Threshold, ThresholdState

__all__ = [
    "Base",
    "CollectionRun",
    "Device",
    "IloCredentialSetting",
    "IloPowerSample",
    "ImportLog",
    "ManualDevicePower",
    "MeasurementBatch",
    "PhaseMainMeasurement",
    "PowerAggregate",
    "PowerDefaultSetting",
    "Rack",
    "RackHourlyKwh",
    "RackMeasurement",
    "RackMonthlyKwh",
    "Threshold",
    "ThresholdState",
]
```

- [ ] **Step 6: Configure Alembic and generate migration**

Run:

```bash
cd backend
alembic init alembic
```

Edit `backend/alembic/env.py` so `target_metadata = Base.metadata`:

```python
from app.core.config import settings
from app.models import Base

config.set_main_option("sqlalchemy.url", settings.database_url)
target_metadata = Base.metadata
```

Run:

```bash
cd backend
alembic revision --autogenerate -m "create initial schema"
```

Expected:

```text
Generating ...create_initial_schema.py
```

- [ ] **Step 7: Commit**

```bash
git add backend
git commit -m "feat: add database schema"
```

---

### Task 3: Pure Calculation Services

**Files:**
- Create: `backend/app/services/power_calculations.py`
- Create: `backend/app/services/representative_power.py`
- Create: `backend/app/services/kwh.py`
- Create: `backend/app/services/thresholds.py`
- Test: `backend/tests/unit/test_measurement_validation.py`
- Test: `backend/tests/unit/test_representative_power.py`
- Test: `backend/tests/unit/test_kwh.py`
- Test: `backend/tests/unit/test_thresholds.py`

- [ ] **Step 1: Write measurement validation tests**

Create `backend/tests/unit/test_measurement_validation.py`:

```python
from decimal import Decimal

from app.services.power_calculations import calculate_single_phase_watts, validate_watts_tolerance


def test_calculate_single_phase_watts() -> None:
    result = calculate_single_phase_watts(
        voltage=Decimal("220"),
        amp=Decimal("10"),
        power_factor=Decimal("0.95"),
    )

    assert result == Decimal("2090.00")


def test_validate_watts_tolerance_accepts_within_default_tolerance() -> None:
    result = validate_watts_tolerance(
        entered_watts=Decimal("2100"),
        calculated_watts=Decimal("2090"),
    )

    assert result.is_valid is True
    assert result.warning is None


def test_validate_watts_tolerance_warns_outside_default_tolerance() -> None:
    result = validate_watts_tolerance(
        entered_watts=Decimal("3000"),
        calculated_watts=Decimal("2090"),
    )

    assert result.is_valid is False
    assert result.warning == "WATTS_TOLERANCE_EXCEEDED"
```

- [ ] **Step 2: Implement measurement calculations**

Create `backend/app/services/power_calculations.py`:

```python
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ToleranceResult:
    is_valid: bool
    warning: str | None
    difference: Decimal
    tolerance: Decimal


def calculate_single_phase_watts(
    *,
    voltage: Decimal,
    amp: Decimal,
    power_factor: Decimal,
) -> Decimal:
    return voltage * amp * power_factor


def validate_watts_tolerance(
    *,
    entered_watts: Decimal,
    calculated_watts: Decimal,
    percent: Decimal = Decimal("0.10"),
    minimum_watts: Decimal = Decimal("100"),
) -> ToleranceResult:
    difference = abs(entered_watts - calculated_watts)
    tolerance = max(abs(entered_watts) * percent, minimum_watts)
    if difference > tolerance:
        return ToleranceResult(
            is_valid=False,
            warning="WATTS_TOLERANCE_EXCEEDED",
            difference=difference,
            tolerance=tolerance,
        )
    return ToleranceResult(is_valid=True, warning=None, difference=difference, tolerance=tolerance)
```

- [ ] **Step 3: Write representative power tests**

Create `backend/tests/unit/test_representative_power.py`:

```python
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.services.representative_power import CandidatePower, choose_device_representative


NOW = datetime(2026, 5, 29, 12, 0, tzinfo=UTC)


def test_device_representative_prefers_fresh_ilo() -> None:
    result = choose_device_representative(
        now=NOW,
        ilo=CandidatePower(Decimal("300"), NOW - timedelta(minutes=5), "collected_ilo"),
        measured=CandidatePower(Decimal("310"), NOW - timedelta(days=1), "measured_watts"),
        estimated=CandidatePower(Decimal("320"), NOW - timedelta(days=10), "estimated"),
        rated=CandidatePower(Decimal("400"), NOW - timedelta(days=100), "rated"),
    )

    assert result.watts == Decimal("300")
    assert result.source == "ilo"


def test_device_representative_ignores_stale_ilo() -> None:
    result = choose_device_representative(
        now=NOW,
        ilo=CandidatePower(Decimal("300"), NOW - timedelta(hours=2), "collected_ilo"),
        measured=CandidatePower(Decimal("310"), NOW - timedelta(days=1), "measured_watts"),
        estimated=None,
        rated=None,
    )

    assert result.watts == Decimal("310")
    assert result.source == "manual_measured"


def test_device_representative_uses_estimated_before_rated() -> None:
    result = choose_device_representative(
        now=NOW,
        ilo=None,
        measured=None,
        estimated=CandidatePower(Decimal("320"), NOW - timedelta(days=10), "estimated"),
        rated=CandidatePower(Decimal("400"), NOW - timedelta(days=100), "rated"),
    )

    assert result.watts == Decimal("320")
    assert result.source == "estimated"
```

- [ ] **Step 4: Implement representative power service**

Create `backend/app/services/representative_power.py`:

```python
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal


@dataclass(frozen=True)
class CandidatePower:
    watts: Decimal
    measured_at: datetime
    quality: str


@dataclass(frozen=True)
class RepresentativePower:
    watts: Decimal | None
    source: str
    stale: bool


def _is_fresh(now: datetime, candidate: CandidatePower, max_age: timedelta) -> bool:
    return now - candidate.measured_at <= max_age


def choose_device_representative(
    *,
    now: datetime,
    ilo: CandidatePower | None,
    measured: CandidatePower | None,
    estimated: CandidatePower | None,
    rated: CandidatePower | None,
    ilo_freshness: timedelta = timedelta(minutes=30),
    measured_freshness: timedelta = timedelta(days=30),
) -> RepresentativePower:
    if ilo and _is_fresh(now, ilo, ilo_freshness):
        return RepresentativePower(watts=ilo.watts, source="ilo", stale=False)
    if measured and _is_fresh(now, measured, measured_freshness):
        return RepresentativePower(watts=measured.watts, source="manual_measured", stale=False)
    if estimated:
        return RepresentativePower(watts=estimated.watts, source="estimated", stale=False)
    if rated:
        return RepresentativePower(watts=rated.watts, source="rated", stale=False)
    return RepresentativePower(watts=None, source="unknown", stale=False)
```

- [ ] **Step 5: Write kWh tests**

Create `backend/tests/unit/test_kwh.py`:

```python
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.services.kwh import HourlyPowerPoint, build_hourly_kwh


def test_build_hourly_kwh_splits_actual_and_estimated() -> None:
    start = datetime(2026, 5, 1, 0, 0, tzinfo=UTC)
    points = [
        HourlyPowerPoint(hour_start=start, watts=Decimal("1000"), basis_source="rack_measured"),
        HourlyPowerPoint(hour_start=start + timedelta(hours=2), watts=Decimal("2000"), basis_source="device_sum"),
    ]

    rows = build_hourly_kwh(
        start=start,
        hours=4,
        actual_points=points,
        carry_forward_max_hours=1,
    )

    assert rows[0].actual_kwh == Decimal("1")
    assert rows[0].estimated_kwh == Decimal("0")
    assert rows[1].actual_kwh == Decimal("0")
    assert rows[1].estimated_kwh == Decimal("1")
    assert rows[2].actual_kwh == Decimal("2")
    assert rows[3].estimated_kwh == Decimal("2")


def test_build_hourly_kwh_stops_after_carry_forward_cap() -> None:
    start = datetime(2026, 5, 1, 0, 0, tzinfo=UTC)
    points = [HourlyPowerPoint(hour_start=start, watts=Decimal("1000"), basis_source="rack_measured")]

    rows = build_hourly_kwh(
        start=start,
        hours=4,
        actual_points=points,
        carry_forward_max_hours=1,
    )

    assert rows[0].coverage_state == "actual"
    assert rows[1].coverage_state == "estimated"
    assert rows[2].coverage_state == "missing"
    assert rows[3].coverage_state == "missing"
```

- [ ] **Step 6: Implement kWh service**

Create `backend/app/services/kwh.py`:

```python
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal


@dataclass(frozen=True)
class HourlyPowerPoint:
    hour_start: datetime
    watts: Decimal
    basis_source: str


@dataclass(frozen=True)
class HourlyKwhResult:
    hour_start: datetime
    actual_kwh: Decimal
    estimated_kwh: Decimal
    basis_source: str
    coverage_state: str


def build_hourly_kwh(
    *,
    start: datetime,
    hours: int,
    actual_points: list[HourlyPowerPoint],
    carry_forward_max_hours: int,
) -> list[HourlyKwhResult]:
    by_hour = {point.hour_start: point for point in actual_points}
    rows: list[HourlyKwhResult] = []
    last_actual: HourlyPowerPoint | None = None
    last_actual_index: int | None = None

    for index in range(hours):
        hour = start + timedelta(hours=index)
        point = by_hour.get(hour)
        if point is not None:
            last_actual = point
            last_actual_index = index
            rows.append(
                HourlyKwhResult(
                    hour_start=hour,
                    actual_kwh=point.watts / Decimal("1000"),
                    estimated_kwh=Decimal("0"),
                    basis_source=point.basis_source,
                    coverage_state="actual",
                )
            )
            continue

        if last_actual is not None and last_actual_index is not None:
            gap = index - last_actual_index
            if gap <= carry_forward_max_hours:
                rows.append(
                    HourlyKwhResult(
                        hour_start=hour,
                        actual_kwh=Decimal("0"),
                        estimated_kwh=last_actual.watts / Decimal("1000"),
                        basis_source="carry_forward",
                        coverage_state="estimated",
                    )
                )
                continue

        rows.append(
            HourlyKwhResult(
                hour_start=hour,
                actual_kwh=Decimal("0"),
                estimated_kwh=Decimal("0"),
                basis_source="carry_forward",
                coverage_state="missing",
            )
        )

    return rows
```

- [ ] **Step 7: Write threshold tests**

Create `backend/tests/unit/test_thresholds.py`:

```python
from decimal import Decimal

from app.services.thresholds import evaluate_threshold


def test_threshold_moves_to_critical_after_trigger_count() -> None:
    state = evaluate_threshold(
        value=Decimal("120"),
        warning_watts=Decimal("100"),
        critical_watts=Decimal("110"),
        current_state="normal",
        consecutive_trigger_count=0,
        consecutive_clear_count=0,
        trigger_count=1,
        clear_count=2,
    )

    assert state.current_state == "critical"
    assert state.consecutive_trigger_count == 1


def test_threshold_requires_clear_count_to_return_normal() -> None:
    first = evaluate_threshold(
        value=Decimal("90"),
        warning_watts=Decimal("100"),
        critical_watts=Decimal("110"),
        current_state="critical",
        consecutive_trigger_count=1,
        consecutive_clear_count=0,
        trigger_count=1,
        clear_count=2,
    )
    second = evaluate_threshold(
        value=Decimal("90"),
        warning_watts=Decimal("100"),
        critical_watts=Decimal("110"),
        current_state=first.current_state,
        consecutive_trigger_count=first.consecutive_trigger_count,
        consecutive_clear_count=first.consecutive_clear_count,
        trigger_count=1,
        clear_count=2,
    )

    assert first.current_state == "critical"
    assert second.current_state == "normal"
```

- [ ] **Step 8: Implement threshold service**

Create `backend/app/services/thresholds.py`:

```python
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ThresholdEvaluation:
    current_state: str
    consecutive_trigger_count: int
    consecutive_clear_count: int


def _target_state(
    *,
    value: Decimal,
    warning_watts: Decimal | None,
    critical_watts: Decimal | None,
) -> str:
    if critical_watts is not None and value >= critical_watts:
        return "critical"
    if warning_watts is not None and value >= warning_watts:
        return "warning"
    return "normal"


def evaluate_threshold(
    *,
    value: Decimal,
    warning_watts: Decimal | None,
    critical_watts: Decimal | None,
    current_state: str,
    consecutive_trigger_count: int,
    consecutive_clear_count: int,
    trigger_count: int,
    clear_count: int,
) -> ThresholdEvaluation:
    target = _target_state(value=value, warning_watts=warning_watts, critical_watts=critical_watts)

    if target != "normal":
        next_trigger_count = consecutive_trigger_count + 1
        if next_trigger_count >= trigger_count:
            return ThresholdEvaluation(
                current_state=target,
                consecutive_trigger_count=next_trigger_count,
                consecutive_clear_count=0,
            )
        return ThresholdEvaluation(
            current_state=current_state,
            consecutive_trigger_count=next_trigger_count,
            consecutive_clear_count=0,
        )

    next_clear_count = consecutive_clear_count + 1
    if current_state != "normal" and next_clear_count < clear_count:
        return ThresholdEvaluation(
            current_state=current_state,
            consecutive_trigger_count=consecutive_trigger_count,
            consecutive_clear_count=next_clear_count,
        )
    return ThresholdEvaluation(
        current_state="normal",
        consecutive_trigger_count=0,
        consecutive_clear_count=next_clear_count,
    )
```

- [ ] **Step 9: Run calculation tests**

Run:

```bash
cd backend
pytest tests/unit -v
```

Expected:

```text
all tests passed
```

- [ ] **Step 10: Commit**

```bash
git add backend/app/services backend/tests/unit
git commit -m "feat: add power calculation services"
```

---

### Task 4: Measurement Batch and Measurement APIs

**Files:**
- Create: `backend/app/schemas/measurements.py`
- Create: `backend/app/repositories/measurements.py`
- Create: `backend/app/services/measurements.py`
- Create: `backend/app/api/routes/measurement_batches.py`
- Create: `backend/app/api/routes/measurements.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/unit/test_measurement_validation.py`

- [ ] **Step 1: Define measurement schemas**

Create `backend/app/schemas/measurements.py`:

```python
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


class BulkCreateResult(BaseModel):
    created_ids: list[int]
    warnings: list[dict[str, object]]
```

- [ ] **Step 2: Implement measurement service**

Create `backend/app/services/measurements.py`:

```python
from decimal import Decimal

from app.core.errors import ValidationAppError
from app.services.power_calculations import calculate_single_phase_watts, validate_watts_tolerance


def derive_watts_and_quality(
    *,
    watts: Decimal | None,
    voltage: Decimal | None,
    amp: Decimal | None,
    power_factor: Decimal | None,
    voltage_source: str,
    power_factor_source: str,
    value_type: str | None = None,
    confirmed: bool = False,
) -> tuple[Decimal, str, dict[str, object] | None]:
    warning: dict[str, object] | None = None

    if watts is None and None not in (voltage, amp, power_factor):
        watts = calculate_single_phase_watts(
            voltage=voltage or Decimal("0"),
            amp=amp or Decimal("0"),
            power_factor=power_factor or Decimal("0"),
        )

    if watts is None:
        raise ValidationAppError("watts or voltage/amp/power_factor is required")

    if value_type == "estimated":
        return watts, "estimated", None
    if value_type == "rated":
        return watts, "rated", None

    if None not in (voltage, amp, power_factor):
        calculated = calculate_single_phase_watts(
            voltage=voltage or Decimal("0"),
            amp=amp or Decimal("0"),
            power_factor=power_factor or Decimal("0"),
        )
        result = validate_watts_tolerance(entered_watts=watts, calculated_watts=calculated)
        if not result.is_valid:
            warning = {
                "code": result.warning,
                "difference": str(result.difference),
                "tolerance": str(result.tolerance),
            }
            if not confirmed:
                raise ValidationAppError("watts tolerance exceeded", warning)

    if power_factor_source == "default":
        return watts, "calculated_with_default_pf", warning
    if watts is not None and amp is None:
        return watts, "measured_watts", warning
    return watts, "calculated_with_measured_pf", warning
```

- [ ] **Step 3: Implement repository and routes**

Create repository methods in `backend/app/repositories/measurements.py` for creating batches and inserting bulk rows. Use SQLAlchemy `insert()` and `returning()` for IDs.

Create routes:

```text
POST /measurement-batches
POST /rack-measurements/bulk
POST /device-power-measurements/bulk
POST /phase-main-measurements/bulk
PATCH /rack-measurements/{measurement_id}
DELETE /rack-measurements/{measurement_id}
PATCH /device-power-measurements/{measurement_id}
DELETE /device-power-measurements/{measurement_id}
PATCH /phase-main-measurements/{measurement_id}
DELETE /phase-main-measurements/{measurement_id}
```

For deletes, physically delete the row and mark the affected month for recalculation.

- [ ] **Step 4: Include routers in app**

Modify `backend/app/main.py`:

```python
from app.api.routes import measurement_batches, measurements

app.include_router(measurement_batches.router)
app.include_router(measurements.router)
```

- [ ] **Step 5: Run tests**

Run:

```bash
cd backend
pytest tests/unit/test_measurement_validation.py -v
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit**

```bash
git add backend/app backend/tests
git commit -m "feat: add measurement APIs"
```

---

### Task 5: Inventory and Settings APIs

**Files:**
- Create: `backend/app/schemas/racks.py`
- Create: `backend/app/schemas/devices.py`
- Create: `backend/app/schemas/settings.py`
- Create: `backend/app/repositories/racks.py`
- Create: `backend/app/repositories/devices.py`
- Create: `backend/app/repositories/settings.py`
- Create: `backend/app/api/routes/racks.py`
- Create: `backend/app/api/routes/devices.py`
- Create: `backend/app/api/routes/settings.py`
- Create: `backend/app/core/encryption.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Implement encryption helper**

Create `backend/app/core/encryption.py`:

```python
import base64
import hashlib

from cryptography.fernet import Fernet

from app.core.config import settings


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
```

- [ ] **Step 2: Implement rack/device CRUD**

Create schemas and repositories for:

```text
GET /racks
POST /racks
GET /racks/{rack_id}
PATCH /racks/{rack_id}
DELETE /racks/{rack_id} -> active=false
GET /devices
POST /devices
GET /devices/{device_id}
PATCH /devices/{device_id}
DELETE /devices/{device_id} -> active=false
```

Validation rules:

- Rack phase must be one of `R`, `S`, `T`.
- Rack name and device name are unique.
- Device `u_position_start <= u_position_end` when both are present.
- Device with `has_ilo=true` must have `ilo_host` and `ilo_profile`.

- [ ] **Step 3: Implement settings APIs**

Create:

```text
GET /settings/ilo-credential
PUT /settings/ilo-credential
GET /settings/power-defaults
PUT /settings/power-defaults
```

Rules:

- Store iLO password encrypted.
- Never return decrypted password from GET.
- Return `password_configured: true/false`.

- [ ] **Step 4: Include routers and run smoke test**

Modify `backend/app/main.py` to include racks, devices, and settings routers.

Run:

```bash
cd backend
pytest tests/unit -v
```

Expected:

```text
passed
```

- [ ] **Step 5: Commit**

```bash
git add backend/app
git commit -m "feat: add inventory and settings APIs"
```

---

### Task 6: iLO Client, Profiles, and Collection Job

**Files:**
- Create: `backend/app/integrations/ilo/auth.py`
- Create: `backend/app/integrations/ilo/client.py`
- Create: `backend/app/integrations/ilo/profiles.py`
- Create: `backend/app/services/ilo_collection.py`
- Create: `backend/app/repositories/ilo.py`
- Create: `backend/app/schemas/ilo.py`
- Create: `backend/app/api/routes/ilo.py`
- Test: `backend/tests/integration/test_ilo_client.py`

- [ ] **Step 1: Write iLO client mock tests**

Create `backend/tests/integration/test_ilo_client.py`:

```python
from decimal import Decimal

import httpx
import pytest

from app.integrations.ilo.client import IloClient
from app.integrations.ilo.profiles import read_average_watts


@pytest.mark.asyncio
async def test_read_average_watts_from_power_control() -> None:
    payload = {
        "PowerControl": [
            {
                "PowerMetrics": {
                    "AverageConsumedWatts": 321
                }
            }
        ]
    }

    assert read_average_watts(payload) == Decimal("321")


@pytest.mark.asyncio
async def test_ilo_client_uses_session_token() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/redfish/v1/SessionService/Sessions":
            return httpx.Response(201, headers={"X-Auth-Token": "token"})
        if request.url.path == "/redfish/v1/Chassis/1/Power":
            assert request.headers["X-Auth-Token"] == "token"
            return httpx.Response(200, json={"PowerControl": [{"PowerMetrics": {"AverageConsumedWatts": 321}}]})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = IloClient(base_url="https://ilo.local", username="u", password="p", transport=transport)

    result = await client.collect_average_watts(profile="ilo5-redfish")

    assert result.average_watts == Decimal("321")
    assert result.auth_method == "session"
```

- [ ] **Step 2: Implement iLO profile reader**

Create `backend/app/integrations/ilo/profiles.py`:

```python
from decimal import Decimal
from typing import Any


PROFILE_POWER_PATHS = {
    "ilo4-redfish": "/redfish/v1/Chassis/1/Power",
    "ilo5-redfish": "/redfish/v1/Chassis/1/Power",
    "ilo6-redfish": "/redfish/v1/Chassis/1/Power",
    "legacy-hpe-rest": "/redfish/v1/Chassis/1/Power",
}


def read_average_watts(payload: dict[str, Any]) -> Decimal:
    controls = payload.get("PowerControl") or []
    for control in controls:
        metrics = control.get("PowerMetrics") or {}
        value = metrics.get("AverageConsumedWatts")
        if value is not None:
            return Decimal(str(value))
    raise ValueError("AverageConsumedWatts not found")
```

- [ ] **Step 3: Implement iLO client**

Create `backend/app/integrations/ilo/client.py`:

```python
from dataclasses import dataclass
from decimal import Decimal

import httpx

from app.core.errors import ExternalApiError
from app.integrations.ilo.profiles import PROFILE_POWER_PATHS, read_average_watts


@dataclass(frozen=True)
class IloCollectResult:
    average_watts: Decimal
    auth_method: str


class IloClient:
    def __init__(
        self,
        *,
        base_url: str,
        username: str,
        password: str,
        timeout: float = 10,
        verify: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout
        self.verify = verify
        self.transport = transport

    async def collect_average_watts(self, *, profile: str) -> IloCollectResult:
        path = PROFILE_POWER_PATHS[profile]
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            verify=self.verify,
            transport=self.transport,
        ) as client:
            token = await self._try_session(client)
            if token is not None:
                response = await client.get(path, headers={"X-Auth-Token": token})
                response.raise_for_status()
                return IloCollectResult(read_average_watts(response.json()), "session")

            response = await client.get(path, auth=(self.username, self.password))
            response.raise_for_status()
            return IloCollectResult(read_average_watts(response.json()), "basic")

    async def _try_session(self, client: httpx.AsyncClient) -> str | None:
        try:
            response = await client.post(
                "/redfish/v1/SessionService/Sessions",
                json={"UserName": self.username, "Password": self.password},
            )
            if response.status_code not in (200, 201):
                return None
            return response.headers.get("X-Auth-Token")
        except httpx.HTTPError as exc:
            raise ExternalApiError("iLO session request failed", {"reason": str(exc)}) from exc
```

- [ ] **Step 4: Implement collection service**

Create `backend/app/services/ilo_collection.py`:

```python
from datetime import UTC, datetime

from app.integrations.ilo.client import IloClient


async def collect_device_power(
    *,
    ilo_host: str,
    profile: str,
    username: str,
    password: str,
    timeout_seconds: int,
    tls_verify: bool,
) -> tuple[str, object]:
    client = IloClient(
        base_url=f"https://{ilo_host}",
        username=username,
        password=password,
        timeout=timeout_seconds,
        verify=tls_verify,
    )
    result = await client.collect_average_watts(profile=profile)
    return result.auth_method, result.average_watts


def now_utc() -> datetime:
    return datetime.now(tz=UTC)
```

- [ ] **Step 5: Add iLO routes**

Add:

```text
GET /ilo/status
POST /ilo/collect
GET /ilo/samples
GET /ilo/collection-runs
GET /ilo/collection-runs/{collection_run_id}
```

`POST /ilo/collect` should create a manual `CollectionRun` and collect active iLO-enabled devices.

- [ ] **Step 6: Run tests**

Run:

```bash
cd backend
pytest tests/integration/test_ilo_client.py -v
```

Expected:

```text
passed
```

- [ ] **Step 7: Commit**

```bash
git add backend/app backend/tests/integration
git commit -m "feat: add ilo collection"
```

---

### Task 7: Aggregates, kWh, Threshold Worker Jobs

**Files:**
- Create: `backend/app/repositories/aggregates.py`
- Create: `backend/app/repositories/kwh.py`
- Create: `backend/app/repositories/thresholds.py`
- Create: `backend/app/services/aggregates.py`
- Modify: `backend/app/services/kwh.py`
- Modify: `backend/app/services/thresholds.py`
- Create: `backend/app/workers/jobs.py`
- Create: `backend/app/workers/main.py`
- Create: `backend/app/api/routes/aggregates.py`
- Create: `backend/app/api/routes/kwh.py`
- Create: `backend/app/api/routes/thresholds.py`

- [ ] **Step 1: Implement aggregate upsert repositories**

Create repository functions:

```text
upsert_power_aggregate(...)
upsert_rack_hourly_kwh(...)
upsert_rack_monthly_kwh(...)
mark_month_for_recalculation(...)
list_months_needing_recalculation(...)
```

Use PostgreSQL `ON CONFLICT DO UPDATE` through SQLAlchemy dialect insert.

- [ ] **Step 2: Implement aggregate service**

Create `backend/app/services/aggregates.py` with functions:

```text
build_hourly_representative_aggregates(period_start)
build_daily_aggregates(day_start)
build_monthly_aggregates(month_start)
```

Rules:

- Use representative and source-specific values.
- Preserve `unknown_count`, `stale_count`, and `coverage_percent`.
- Upsert aggregates.

- [ ] **Step 3: Implement kWh persistence service**

Use `build_hourly_kwh()` from Task 3 to create hourly rows, then sum monthly:

```text
actual_kwh = sum(hourly.actual_kwh)
estimated_kwh = sum(hourly.actual_kwh + hourly.estimated_kwh)
coverage_percent = actual_hour_count / total_hours * 100
estimated_hours = count(coverage_state == "estimated")
```

- [ ] **Step 4: Implement threshold API and evaluation job**

Routes:

```text
GET /thresholds
POST /thresholds
PATCH /thresholds/{threshold_id}
DELETE /thresholds/{threshold_id}
GET /threshold-states
```

Job:

```text
evaluate_thresholds()
```

Rules:

- Device basis uses device representative power.
- Rack basis uses rack representative power.
- Phase basis supports `phase_main`, `rack_sum`, and `max`.
- Overall basis supports `rack_sum`, `phase_main_sum`, and `max`.

- [ ] **Step 5: Implement worker entrypoint**

Create `backend/app/workers/jobs.py`:

```python
async def run_ilo_collect_job() -> None:
    ...


async def run_aggregate_job() -> None:
    ...


async def run_kwh_job() -> None:
    ...


async def run_threshold_evaluation_job() -> None:
    ...


async def run_recalculation_job() -> None:
    ...
```

Create `backend/app/workers/main.py`:

```python
import asyncio

from app.workers.jobs import (
    run_aggregate_job,
    run_ilo_collect_job,
    run_kwh_job,
    run_recalculation_job,
    run_threshold_evaluation_job,
)


async def main() -> None:
    while True:
        await run_ilo_collect_job()
        await run_aggregate_job()
        await run_kwh_job()
        await run_threshold_evaluation_job()
        await run_recalculation_job()
        await asyncio.sleep(900)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 6: Run tests**

Run:

```bash
cd backend
pytest tests/unit/test_kwh.py tests/unit/test_thresholds.py -v
```

Expected:

```text
passed
```

- [ ] **Step 7: Commit**

```bash
git add backend/app
git commit -m "feat: add aggregate and worker jobs"
```

---

### Task 8: Overview, Rack Detail, and Phase APIs

**Files:**
- Create: `backend/app/schemas/overview.py`
- Create: `backend/app/services/overview.py`
- Create: `backend/app/api/routes/overview.py`
- Create: `backend/app/api/routes/phases.py`
- Modify: `backend/app/api/routes/racks.py`

- [ ] **Step 1: Implement overview service**

Create `backend/app/services/overview.py` to return:

```text
rack_cards:
  rack_id
  rack_name
  representative_watts
  representative_source
  threshold_state
  data_confidence_state
  phase
  monthly_actual_kwh
  monthly_estimated_kwh
  coverage_percent
overall:
  rack_sum_watts
  phase_main_sum_watts
  known_rack_count
  unknown_rack_count
  known_device_count
  unknown_device_count
  coverage_percent
phases:
  phase
  phase_main_watts
  rack_sum_watts
  difference_watts
  imbalance_percent
  known_rack_count
  unknown_rack_count
  stale_rack_count
```

- [ ] **Step 2: Add overview and phase routes**

Routes:

```text
GET /overview
GET /phases/summary
GET /phases/{phase}/measurements
```

- [ ] **Step 3: Add rack detail routes**

Ensure:

```text
GET /racks/{rack_id}/summary
GET /racks/{rack_id}/trend
GET /racks/{rack_id}/devices
GET /racks/{rack_id}/measurements
```

Trend default:

- Last 7 days.
- Representative power only unless source query parameter is supplied.

- [ ] **Step 4: Commit**

```bash
git add backend/app
git commit -m "feat: add overview and rack detail APIs"
```

---

### Task 9: Excel Import

**Files:**
- Create: `backend/app/schemas/imports.py`
- Create: `backend/app/repositories/imports.py`
- Create: `backend/app/services/imports.py`
- Create: `backend/app/api/routes/imports.py`
- Test: `backend/tests/unit/test_imports.py`

- [ ] **Step 1: Define template columns**

Rack sheet columns:

```text
name
phase
voltage
circuit_name
capacity_amp
active
```

Device sheet columns:

```text
name
rack_name
device_type
u_position_start
u_position_end
has_ilo
ilo_host
ilo_profile
active
```

- [ ] **Step 2: Implement template download**

`GET /imports/template` returns an `.xlsx` file with two sheets:

- `racks`
- `devices`

- [ ] **Step 3: Implement import parser**

Rules:

- Match racks by unique rack name.
- Match devices by unique device name.
- Create or update only.
- Do not delete missing records.
- Do not import thresholds.
- Do not store original file.
- Store `ImportLog` with file name and counts.

- [ ] **Step 4: Write parser test**

Create `backend/tests/unit/test_imports.py` with an in-memory workbook containing one rack and one device. Assert parsed records have expected names and rack linkage by name.

- [ ] **Step 5: Add route and run tests**

Run:

```bash
cd backend
pytest tests/unit/test_imports.py -v
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit**

```bash
git add backend/app backend/tests/unit/test_imports.py
git commit -m "feat: add excel inventory import"
```

---

### Task 10: Minimal React Frontend

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/types.ts`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/pages/HomePage.tsx`
- Create: `frontend/src/pages/RackDetailPage.tsx`
- Create: `frontend/src/pages/MeasurementInputPage.tsx`
- Create: `frontend/src/pages/InventoryPage.tsx`
- Create: `frontend/src/pages/ThresholdPage.tsx`
- Create: `frontend/src/pages/SettingsPage.tsx`

- [ ] **Step 1: Create frontend package**

Create `frontend/package.json`:

```json
{
  "scripts": {
    "dev": "vite --host 0.0.0.0",
    "build": "tsc && vite build",
    "preview": "vite preview --host 0.0.0.0"
  },
  "dependencies": {
    "@tanstack/react-query": "^5.0.0",
    "@vitejs/plugin-react": "^4.0.0",
    "vite": "^5.0.0",
    "typescript": "^5.0.0",
    "react": "^18.2.0",
    "react-dom": "^18.2.0"
  },
  "devDependencies": {}
}
```

- [ ] **Step 2: Create API client**

Create `frontend/src/api/client.ts`:

```typescript
const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(`GET ${path} failed`);
  }
  return response.json() as Promise<T>;
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`POST ${path} failed`);
  }
  return response.json() as Promise<T>;
}
```

- [ ] **Step 3: Create basic pages**

Implement pages:

- Home shows `/overview` rack cards.
- Rack detail shows summary/trend placeholder from API.
- Measurement input creates batch then calls three bulk endpoints.
- Inventory lists racks/devices.
- Threshold page lists threshold states.
- Settings page edits iLO credential and power defaults.

Keep styling simple. Use table/grid layouts and status badges.

- [ ] **Step 4: Run frontend build**

Run:

```bash
cd frontend
npm install
npm run build
```

Expected:

```text
built successfully
```

- [ ] **Step 5: Commit**

```bash
git add frontend
git commit -m "feat: add minimal react frontend"
```

---

### Task 11: Docker Compose and Local Verification

**Files:**
- Create: `backend/Dockerfile`
- Create: `frontend/Dockerfile`
- Create: `docker-compose.yml`
- Modify: `.env.example`
- Create: `README.md`

- [ ] **Step 1: Create backend Dockerfile**

Create `backend/Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir ".[dev]"
COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Create frontend Dockerfile**

Create `frontend/Dockerfile`:

```dockerfile
FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
```

- [ ] **Step 3: Create docker-compose.yml**

Create `docker-compose.yml`:

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: power
      POSTGRES_PASSWORD: power
      POSTGRES_DB: power
    volumes:
      - postgres-data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  backend:
    build: ./backend
    env_file: .env
    depends_on:
      - db
    ports:
      - "8000:8000"

  worker:
    build: ./backend
    env_file: .env
    depends_on:
      - db
    command: ["python", "-m", "app.workers.main"]

  frontend:
    build: ./frontend
    depends_on:
      - backend
    ports:
      - "3000:80"

volumes:
  postgres-data:
```

- [ ] **Step 4: Create README**

Create `README.md` with:

```markdown
# Power Monitoring Dashboard

## Run

```bash
cp .env.example .env
docker compose up --build
```

Backend: http://localhost:8000/health

Frontend: http://localhost:3000
```

- [ ] **Step 5: Verify**

Run:

```bash
docker compose up --build
```

Expected:

```text
backend starts
worker starts
frontend starts
db starts
GET http://localhost:8000/health returns {"status":"ok"}
```

- [ ] **Step 6: Commit**

```bash
git add README.md docker-compose.yml backend/Dockerfile frontend/Dockerfile .env.example
git commit -m "chore: add docker compose deployment"
```

---

### Task 12: SNMP Schema and Settings

**Files:**
- Modify: `backend/app/models/inventory.py`
- Modify: `backend/app/models/settings.py`
- Create: `backend/app/models/snmp.py`
- Modify: `backend/app/models/ilo.py`
- Modify: `backend/app/models/__init__.py`
- Create: Alembic revision for SNMP fields/tables
- Modify: `backend/app/api/routes/settings.py`
- Modify: `backend/app/schemas/settings.py`

- [ ] **Step 1: Extend Device with SNMP fields**

Modify `backend/app/models/inventory.py` `Device`:

```python
has_snmp: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
snmp_host: Mapped[str | None] = mapped_column(String(255))
snmp_profile: Mapped[str | None] = mapped_column(String(80))
```

Validation rule for device create/update:

```text
If has_snmp=true, snmp_host and snmp_profile are required.
```

- [ ] **Step 2: Add SNMP credential settings**

Modify `backend/app/models/settings.py`:

```python
class SnmpCredentialSetting(TimestampMixin, Base):
    __tablename__ = "snmp_credential_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    community_encrypted: Mapped[str | None] = mapped_column(String(2048))
    username: Mapped[str | None] = mapped_column(String(255))
    auth_protocol: Mapped[str | None] = mapped_column(String(50))
    auth_password_encrypted: Mapped[str | None] = mapped_column(String(2048))
    privacy_protocol: Mapped[str | None] = mapped_column(String(50))
    privacy_password_encrypted: Mapped[str | None] = mapped_column(String(2048))
    timeout_seconds: Mapped[int] = mapped_column(nullable=False, default=5)
    retries: Mapped[int] = mapped_column(nullable=False, default=1)
```

Rules:

- Support SNMP v2c and v3 in the schema.
- Initial UI configures one common SNMP credential profile.
- Encrypt community and SNMP v3 secrets.
- Never return decrypted secrets from GET.

- [ ] **Step 3: Add SNMP sample model and collection run type**

Create `backend/app/models/snmp.py`:

```python
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class SnmpPowerSample(TimestampMixin, Base):
    __tablename__ = "snmp_power_samples"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), nullable=False)
    collection_run_id: Mapped[int] = mapped_column(ForeignKey("collection_runs.id"), nullable=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    watts: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    profile_used: Mapped[str | None] = mapped_column(String(80))
    oid_used: Mapped[str | None] = mapped_column(String(255))
    quality: Mapped[str] = mapped_column(String(50), nullable=False, default="collected_snmp")
```

Modify `CollectionRun` in `backend/app/models/ilo.py`:

```python
collector_type: Mapped[str] = mapped_column(String(30), nullable=False, default="ilo")
```

Valid collector types:

```text
ilo
snmp
```

- [ ] **Step 4: Export models and generate migration**

Modify `backend/app/models/__init__.py` to export:

```python
from app.models.settings import SnmpCredentialSetting
from app.models.snmp import SnmpPowerSample
```

Run:

```bash
cd backend
alembic revision --autogenerate -m "add snmp collection schema"
```

Expected:

```text
Generating ...add_snmp_collection_schema.py
```

- [ ] **Step 5: Add SNMP credential settings API**

Add:

```text
GET /settings/snmp-credential
PUT /settings/snmp-credential
```

Response rule:

```text
Return secret_configured booleans. Never return decrypted community, auth password, or privacy password values.
```

- [ ] **Step 6: Commit**

```bash
git add backend/app backend/alembic
git commit -m "feat: add snmp schema and settings"
```

---

### Task 13: SNMP Client, Profiles, and Collection Job

**Files:**
- Modify: `backend/pyproject.toml`
- Create: `backend/app/integrations/snmp/__init__.py`
- Create: `backend/app/integrations/snmp/client.py`
- Create: `backend/app/integrations/snmp/profiles.py`
- Create: `backend/app/services/snmp_collection.py`
- Create: `backend/app/repositories/snmp.py`
- Create: `backend/app/schemas/snmp.py`
- Create: `backend/app/api/routes/snmp.py`
- Modify: `backend/app/workers/jobs.py`
- Modify: `backend/app/workers/main.py`
- Test: `backend/tests/integration/test_snmp_client.py`

- [ ] **Step 1: Add SNMP dependency**

Modify `backend/pyproject.toml` dependencies:

```toml
"pysnmp>=7.1",
```

- [ ] **Step 2: Define SNMP profiles**

Create `backend/app/integrations/snmp/profiles.py`:

```python
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class SnmpPowerProfile:
    name: str
    watts_oid: str | None
    scale: Decimal = Decimal("1")
    description: str = ""


SNMP_POWER_PROFILES: dict[str, SnmpPowerProfile] = {
    "generic-entity-sensor": SnmpPowerProfile(
        name="generic-entity-sensor",
        watts_oid=None,
        description="ENTITY-SENSOR-MIB based profile; device-specific sensor mapping required",
    ),
    "custom-watts-oid": SnmpPowerProfile(
        name="custom-watts-oid",
        watts_oid=None,
        description="Device-specific watts OID supplied by configuration",
    ),
}
```

SNMP rule:

```text
Many network devices do not expose total consumed watts through a common OID.
Profiles must be explicit. If a profile cannot return watts, store status=failed and watts=null.
```

- [ ] **Step 3: Write SNMP client helper test**

Create `backend/tests/integration/test_snmp_client.py`:

```python
from decimal import Decimal

from app.integrations.snmp.client import parse_snmp_decimal


def test_parse_snmp_decimal_applies_scale() -> None:
    assert parse_snmp_decimal("1234", Decimal("0.1")) == Decimal("123.4")
```

- [ ] **Step 4: Implement SNMP client helpers**

Create `backend/app/integrations/snmp/client.py`:

```python
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class SnmpGetResult:
    oid: str
    value: str


def parse_snmp_decimal(value: str | int, scale: Decimal) -> Decimal:
    return Decimal(str(value)) * scale
```

Add the async SNMP GET wrapper with `pysnmp` in this file during implementation.

Rules:

- Convert timeout and protocol failures into typed external API errors.
- Do not log SNMP community or SNMP v3 secrets.

- [ ] **Step 5: Implement SNMP collection service**

Create `backend/app/services/snmp_collection.py`:

```python
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class SnmpCollectResult:
    watts: Decimal
    oid_used: str
```

Collection rules:

- Load active devices with `has_snmp=true`.
- Use `device.snmp_profile`.
- Read common SNMP credential setting.
- Create `CollectionRun(collector_type="snmp")`.
- Insert one `SnmpPowerSample` per target.
- On failure, insert row with `watts=null`, `status=failed`.

- [ ] **Step 6: Add SNMP APIs**

Add:

```text
GET /snmp/status
POST /snmp/collect
GET /snmp/samples
GET /snmp/profiles
```

`POST /snmp/collect` triggers a manual SNMP collection run.

- [ ] **Step 7: Add worker job**

Modify `backend/app/workers/jobs.py`:

```python
async def run_snmp_collect_job() -> None:
    ...
```

Modify `backend/app/workers/main.py` loop:

```python
await run_ilo_collect_job()
await run_snmp_collect_job()
await run_aggregate_job()
```

Default interval:

```text
SNMP collection follows the same 15-minute worker loop as iLO.
```

- [ ] **Step 8: Run tests**

Run:

```bash
cd backend
pytest tests/integration/test_snmp_client.py -v
```

Expected:

```text
passed
```

- [ ] **Step 9: Commit**

```bash
git add backend/app backend/tests/integration/test_snmp_client.py backend/pyproject.toml
git commit -m "feat: add snmp collection"
```

---

### Task 14: SNMP Representative Power and UI Integration

**Files:**
- Modify: `backend/app/services/representative_power.py`
- Modify: `backend/tests/unit/test_representative_power.py`
- Modify: `backend/app/services/overview.py`
- Modify: `backend/app/services/aggregates.py`
- Modify: `frontend/src/pages/InventoryPage.tsx`
- Modify: `frontend/src/pages/SettingsPage.tsx`
- Modify: `frontend/src/api/types.ts`

- [ ] **Step 1: Update representative priority test**

Modify `backend/tests/unit/test_representative_power.py`:

```python
def test_device_representative_uses_fresh_snmp_after_ilo() -> None:
    result = choose_device_representative(
        now=NOW,
        ilo=None,
        snmp=CandidatePower(Decimal("280"), NOW - timedelta(minutes=10), "collected_snmp"),
        measured=CandidatePower(Decimal("310"), NOW - timedelta(days=1), "measured_watts"),
        estimated=None,
        rated=None,
    )

    assert result.watts == Decimal("280")
    assert result.source == "snmp"
```

- [ ] **Step 2: Update representative service**

Modify `choose_device_representative()` signature:

```python
def choose_device_representative(
    *,
    now: datetime,
    ilo: CandidatePower | None,
    snmp: CandidatePower | None,
    measured: CandidatePower | None,
    estimated: CandidatePower | None,
    rated: CandidatePower | None,
    ilo_freshness: timedelta = timedelta(minutes=30),
    snmp_freshness: timedelta = timedelta(minutes=30),
    measured_freshness: timedelta = timedelta(days=30),
) -> RepresentativePower:
```

Priority:

```text
1. fresh iLO
2. fresh SNMP
3. fresh manual measured
4. estimated
5. rated
6. null
```

- [ ] **Step 3: Update overview and aggregate source types**

Add source type:

```text
snmp
```

Rules:

- Device summaries show `representative_source=snmp` when SNMP wins.
- Rack device-sum can include SNMP values.
- Aggregates can store `source_type=snmp`.

- [ ] **Step 4: Update frontend inventory/settings**

Inventory device form fields:

```text
has_snmp
snmp_host
snmp_profile
```

Settings page fields:

```text
SNMP credential version
community configured flag
timeout
retries
```

Do not display decrypted SNMP secrets.

- [ ] **Step 5: Run tests**

Run:

```bash
cd backend
pytest tests/unit/test_representative_power.py -v
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit**

```bash
git add backend frontend
git commit -m "feat: integrate snmp representative power"
```

---

## Self-Review

Spec coverage:

- HPE iLO collection: Task 6.
- iLO 4/5/6 profiles: Task 6.
- Rack/device inventory: Task 5.
- Manual rack/device/phase measurements: Task 4.
- Measurement batch: Task 4.
- Measurement quality/source/freshness: Tasks 2, 3, 4, 8.
- CollectionRun: Tasks 2 and 6.
- Aggregates/kWh/coverage/carry-forward cap: Tasks 3 and 7.
- Thresholds: Tasks 3 and 7.
- Overview/rack/phase APIs: Task 8.
- Excel import: Task 9.
- Minimal frontend: Task 10.
- Docker Compose: Task 11.
- SNMP schema/settings: Task 12.
- SNMP collection: Task 13.
- SNMP representative power integration: Task 14.

Known scope intentionally deferred:

- Login/authorization.
- Slack/Teams external notification.
- PDU automatic collection.
- Electricity billing.
- CSV upload.
- Rack floor-plan.
- WebSocket/SSE.

Implementation risk notes:

- Task 2 is broad because the schema is central. Do not proceed to API work until migrations are generated and reviewed.
- Task 7 requires careful repository upsert code. Keep pure kWh/threshold functions from Task 3 unchanged and test them before adding DB persistence.
- Task 10 is intentionally simple. Do not polish UI beyond basic operational use until backend flows are verified.
