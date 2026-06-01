from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import Select, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.power import RackHourlyKwh, RackMonthlyKwh


def _row_to_dict(row: RackHourlyKwh | RackMonthlyKwh) -> dict[str, Any]:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def build_upsert_rack_hourly_kwh_statement(values: dict[str, object]) -> Any:
    statement = insert(RackHourlyKwh).values(**values)
    update_values = {
        column.name: getattr(statement.excluded, column.name)
        for column in RackHourlyKwh.__table__.columns
        if column.name not in {"id", "created_at", "rack_id", "hour_start"}
    }
    return statement.on_conflict_do_update(
        index_elements=[RackHourlyKwh.rack_id, RackHourlyKwh.hour_start],
        set_=update_values,
    ).returning(RackHourlyKwh)


def build_upsert_rack_monthly_kwh_statement(values: dict[str, object]) -> Any:
    statement = insert(RackMonthlyKwh).values(**values)
    update_values = {
        column.name: getattr(statement.excluded, column.name)
        for column in RackMonthlyKwh.__table__.columns
        if column.name not in {"id", "created_at", "rack_id", "month"}
    }
    return statement.on_conflict_do_update(
        index_elements=[RackMonthlyKwh.rack_id, RackMonthlyKwh.month],
        set_=update_values,
    ).returning(RackMonthlyKwh)


async def upsert_rack_hourly_kwh(
    session: AsyncSession,
    values: dict[str, object],
) -> dict[str, Any]:
    result = await session.execute(build_upsert_rack_hourly_kwh_statement(values))
    return _row_to_dict(result.scalar_one())


async def upsert_rack_monthly_kwh(
    session: AsyncSession,
    values: dict[str, object],
) -> dict[str, Any]:
    result = await session.execute(build_upsert_rack_monthly_kwh_statement(values))
    return _row_to_dict(result.scalar_one())


async def list_rack_hourly_kwh(
    session: AsyncSession,
    *,
    rack_id: int | None = None,
    hour_start_from: datetime | None = None,
    hour_start_to: datetime | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    statement: Select[tuple[RackHourlyKwh]] = select(RackHourlyKwh)
    if rack_id is not None:
        statement = statement.where(RackHourlyKwh.rack_id == rack_id)
    if hour_start_from is not None:
        statement = statement.where(RackHourlyKwh.hour_start >= hour_start_from)
    if hour_start_to is not None:
        statement = statement.where(RackHourlyKwh.hour_start < hour_start_to)
    statement = statement.order_by(RackHourlyKwh.hour_start.desc()).limit(limit)
    result = await session.execute(statement)
    return [_row_to_dict(row) for row in result.scalars().all()]


async def list_rack_monthly_kwh(
    session: AsyncSession,
    *,
    rack_id: int | None = None,
    month_from: datetime | None = None,
    month_to: datetime | None = None,
    needs_recalculation: bool | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    statement: Select[tuple[RackMonthlyKwh]] = select(RackMonthlyKwh)
    if rack_id is not None:
        statement = statement.where(RackMonthlyKwh.rack_id == rack_id)
    if month_from is not None:
        statement = statement.where(RackMonthlyKwh.month >= month_from)
    if month_to is not None:
        statement = statement.where(RackMonthlyKwh.month < month_to)
    if needs_recalculation is not None:
        statement = statement.where(RackMonthlyKwh.needs_recalculation.is_(needs_recalculation))
    statement = statement.order_by(RackMonthlyKwh.month.desc()).limit(limit)
    result = await session.execute(statement)
    return [_row_to_dict(row) for row in result.scalars().all()]


async def mark_month_for_recalculation(
    session: AsyncSession,
    *,
    rack_id: int,
    month: datetime,
) -> None:
    await session.execute(
        update(RackMonthlyKwh)
        .where(RackMonthlyKwh.rack_id == rack_id, RackMonthlyKwh.month == month)
        .values(needs_recalculation=True)
    )


async def list_months_needing_recalculation(
    session: AsyncSession,
    *,
    limit: int = 100,
) -> list[dict[str, Any]]:
    return await list_rack_monthly_kwh(session, needs_recalculation=True, limit=limit)


async def clear_month_recalculation(
    session: AsyncSession,
    *,
    rack_id: int,
    month: datetime,
) -> None:
    await session.execute(
        update(RackMonthlyKwh)
        .where(RackMonthlyKwh.rack_id == rack_id, RackMonthlyKwh.month == month)
        .values(needs_recalculation=False)
    )


async def upsert_rack_hourly_kwh_rows(
    session: AsyncSession,
    rows: Sequence[dict[str, object]],
) -> list[dict[str, Any]]:
    return [await upsert_rack_hourly_kwh(session, row) for row in rows]
