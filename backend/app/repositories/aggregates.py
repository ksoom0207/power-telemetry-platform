from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import Select, and_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationAppError
from app.models.inventory import Rack
from app.models.power import PowerAggregate

AGGREGATE_CONFLICT_COLUMNS = [
    "entity_type",
    "entity_id",
    "source_type",
    "period",
    "period_start",
]


def _row_to_dict(row: PowerAggregate) -> dict[str, Any]:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def build_upsert_power_aggregate_statement(values: dict[str, object]) -> Any:
    if values.get("entity_id") is None:
        raise ValidationAppError("entity_id is required for power aggregate upsert")
    statement = insert(PowerAggregate).values(**values)
    update_values = {
        column.name: getattr(statement.excluded, column.name)
        for column in PowerAggregate.__table__.columns
        if column.name not in {"id", "created_at", *AGGREGATE_CONFLICT_COLUMNS}
    }
    return statement.on_conflict_do_update(
        index_elements=[
            PowerAggregate.entity_type,
            PowerAggregate.entity_id,
            PowerAggregate.source_type,
            PowerAggregate.period,
            PowerAggregate.period_start,
        ],
        set_=update_values,
    ).returning(PowerAggregate)


async def upsert_power_aggregate(
    session: AsyncSession,
    values: dict[str, object],
) -> dict[str, Any]:
    result = await session.execute(build_upsert_power_aggregate_statement(values))
    return _row_to_dict(result.scalar_one())


async def list_power_aggregates(
    session: AsyncSession,
    *,
    entity_type: str | None = None,
    entity_id: int | None = None,
    source_type: str | None = None,
    period: str | None = None,
    period_start_from: datetime | None = None,
    period_start_to: datetime | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    statement: Select[tuple[PowerAggregate]] = select(PowerAggregate)
    if entity_type is not None:
        statement = statement.where(PowerAggregate.entity_type == entity_type)
    if entity_id is not None:
        statement = statement.where(PowerAggregate.entity_id == entity_id)
    if source_type is not None:
        statement = statement.where(PowerAggregate.source_type == source_type)
    if period is not None:
        statement = statement.where(PowerAggregate.period == period)
    if period_start_from is not None:
        statement = statement.where(PowerAggregate.period_start >= period_start_from)
    if period_start_to is not None:
        statement = statement.where(PowerAggregate.period_start < period_start_to)
    statement = statement.order_by(PowerAggregate.period_start.desc()).limit(limit)
    result = await session.execute(statement)
    return [_row_to_dict(row) for row in result.scalars().all()]


async def list_rack_hourly_power_aggregates(
    session: AsyncSession,
    *,
    period_start_from: datetime,
    period_start_to: datetime,
    rack_id: int | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    statement: Select[tuple[PowerAggregate]] = (
        select(PowerAggregate)
        .where(PowerAggregate.entity_type == "rack")
        .where(PowerAggregate.period == "hour")
        .where(PowerAggregate.period_start >= period_start_from)
        .where(PowerAggregate.period_start < period_start_to)
    )
    if rack_id is not None:
        statement = statement.where(PowerAggregate.entity_id == rack_id)
    statement = statement.order_by(
        PowerAggregate.entity_id.asc(),
        PowerAggregate.period_start.asc(),
    )
    if limit is not None:
        statement = statement.limit(limit)
    result = await session.execute(statement)
    return [_row_to_dict(row) for row in result.scalars().all()]


async def list_latest_power_aggregates(
    session: AsyncSession,
    *,
    period: str = "hour",
    period_start_to: datetime,
    limit: int | None = 1000,
) -> list[dict[str, Any]]:
    statement = (
        select(PowerAggregate, Rack.phase)
        .outerjoin(
            Rack,
            and_(PowerAggregate.entity_type == "rack", PowerAggregate.entity_id == Rack.id),
        )
        .where(PowerAggregate.period == period)
        .where(PowerAggregate.period_start <= period_start_to)
        .order_by(PowerAggregate.period_start.desc())
    )
    if limit is not None:
        statement = statement.limit(limit)
    result = await session.execute(statement)
    rows = []
    for aggregate, phase in result.all():
        row = _row_to_dict(aggregate)
        if phase is not None:
            row["phase"] = phase
        rows.append(row)
    latest: dict[tuple[str, int | None, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row["entity_type"]),
            row["entity_id"],
            str(row["source_type"]),
        )
        latest.setdefault(key, row)
    return list(latest.values())


async def upsert_power_aggregates(
    session: AsyncSession,
    rows: Sequence[dict[str, object]],
) -> list[dict[str, Any]]:
    return [await upsert_power_aggregate(session, row) for row in rows]
