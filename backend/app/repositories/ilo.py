from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

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
