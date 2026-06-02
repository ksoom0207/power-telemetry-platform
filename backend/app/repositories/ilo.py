from datetime import datetime
from typing import Any

from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime import ensure_aware
from app.core.errors import ValidationAppError
from app.models.ilo import CollectionRun, IloPowerSample


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


async def create_collection_run(
    session: AsyncSession,
    values: dict[str, object],
) -> dict[str, Any]:
    result = await session.execute(insert(CollectionRun).values(**values).returning(CollectionRun))
    return _row_to_dict(result.scalar_one())


async def update_collection_run(
    session: AsyncSession,
    collection_run_id: int,
    values: dict[str, object],
) -> dict[str, Any]:
    result = await session.execute(
        update(CollectionRun)
        .where(CollectionRun.id == collection_run_id)
        .values(**values)
        .returning(CollectionRun)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise ValidationAppError(
            "collection run not found",
            {"collection_run_id": collection_run_id},
        )
    return _row_to_dict(row)


async def create_power_sample(
    session: AsyncSession,
    values: dict[str, object],
) -> dict[str, Any]:
    result = await session.execute(
        insert(IloPowerSample).values(**values).returning(IloPowerSample)
    )
    return _row_to_dict(result.scalar_one())


async def list_power_samples(
    session: AsyncSession,
    *,
    limit: int = 100,
    collection_run_id: int | None = None,
) -> list[dict[str, Any]]:
    statement = select(IloPowerSample)
    if collection_run_id is not None:
        statement = statement.where(IloPowerSample.collection_run_id == collection_run_id)
    result = await session.execute(
        statement.order_by(IloPowerSample.measured_at.desc()).limit(limit)
    )
    return [_row_to_dict(row) for row in result.scalars().all()]


def build_latest_power_samples_by_device_statement(*, measured_at_to: datetime) -> Any:
    ensure_aware(measured_at_to)
    ranked = (
        select(
            IloPowerSample.id,
            IloPowerSample.device_id,
            IloPowerSample.collection_run_id,
            IloPowerSample.measured_at,
            IloPowerSample.average_watts,
            IloPowerSample.status,
            IloPowerSample.auth_method_used,
            IloPowerSample.profile_used,
            IloPowerSample.quality,
            func.row_number()
            .over(
                partition_by=IloPowerSample.device_id,
                order_by=(IloPowerSample.measured_at.desc(), IloPowerSample.id.desc()),
            )
            .label("row_number"),
        )
        .where(IloPowerSample.status == "success")
        .where(IloPowerSample.average_watts.is_not(None))
        .where(IloPowerSample.measured_at <= measured_at_to)
        .subquery()
    )
    return select(ranked).where(ranked.c.row_number == 1)


async def list_latest_power_samples_by_device(
    session: AsyncSession,
    measured_at_to: datetime,
) -> dict[int, dict[str, Any]]:
    result = await session.execute(
        build_latest_power_samples_by_device_statement(measured_at_to=measured_at_to)
    )
    rows: dict[int, dict[str, Any]] = {}
    for row in result.mappings().all():
        values = dict(row)
        values.pop("row_number", None)
        rows[int(values["device_id"])] = values
    return rows


async def list_collection_runs(session: AsyncSession, *, limit: int = 100) -> list[dict[str, Any]]:
    result = await session.execute(
        select(CollectionRun).order_by(CollectionRun.started_at.desc()).limit(limit)
    )
    return [_row_to_dict(row) for row in result.scalars().all()]


async def get_collection_run(
    session: AsyncSession,
    collection_run_id: int,
) -> dict[str, Any]:
    result = await session.execute(
        select(CollectionRun).where(CollectionRun.id == collection_run_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise ValidationAppError(
            "collection run not found",
            {"collection_run_id": collection_run_id},
        )
    return _row_to_dict(row)
