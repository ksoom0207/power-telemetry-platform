from typing import Any

from sqlalchemy import Select, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationAppError
from app.models.thresholds import Threshold, ThresholdState


def _row_to_dict(row: Threshold | ThresholdState) -> dict[str, Any]:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


async def list_thresholds(
    session: AsyncSession,
    *,
    active: bool | None = True,
    target_type: str | None = None,
    target_id: int | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    statement: Select[tuple[Threshold]] = select(Threshold)
    if active is not None:
        statement = statement.where(Threshold.active.is_(active))
    if target_type is not None:
        statement = statement.where(Threshold.target_type == target_type)
    if target_id is not None:
        statement = statement.where(Threshold.target_id == target_id)
    statement = statement.order_by(Threshold.id).limit(limit)
    result = await session.execute(statement)
    return [_row_to_dict(row) for row in result.scalars().all()]


async def get_threshold(session: AsyncSession, threshold_id: int) -> dict[str, Any]:
    result = await session.execute(select(Threshold).where(Threshold.id == threshold_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise ValidationAppError("threshold not found", {"threshold_id": threshold_id})
    return _row_to_dict(row)


async def create_threshold(session: AsyncSession, values: dict[str, object]) -> dict[str, Any]:
    result = await session.execute(insert(Threshold).values(**values).returning(Threshold))
    return _row_to_dict(result.scalar_one())


async def update_threshold(
    session: AsyncSession,
    threshold_id: int,
    values: dict[str, object],
) -> dict[str, Any]:
    result = await session.execute(
        update(Threshold).where(Threshold.id == threshold_id).values(**values).returning(Threshold)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise ValidationAppError("threshold not found", {"threshold_id": threshold_id})
    return _row_to_dict(row)


async def deactivate_threshold(
    session: AsyncSession,
    threshold_id: int,
    values: dict[str, object],
) -> dict[str, Any]:
    return await update_threshold(session, threshold_id, {"active": False, **values})


async def list_threshold_states(
    session: AsyncSession,
    *,
    threshold_id: int | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    statement: Select[tuple[ThresholdState]] = select(ThresholdState)
    if threshold_id is not None:
        statement = statement.where(ThresholdState.threshold_id == threshold_id)
    statement = statement.order_by(ThresholdState.threshold_id).limit(limit)
    result = await session.execute(statement)
    return [_row_to_dict(row) for row in result.scalars().all()]


async def get_threshold_state(session: AsyncSession, threshold_id: int) -> dict[str, Any]:
    result = await session.execute(
        select(ThresholdState).where(ThresholdState.threshold_id == threshold_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise ValidationAppError("threshold state not found", {"threshold_id": threshold_id})
    return _row_to_dict(row)


def build_upsert_threshold_state_statement(values: dict[str, object]) -> Any:
    statement = pg_insert(ThresholdState).values(**values)
    update_values = {
        column.name: getattr(statement.excluded, column.name)
        for column in ThresholdState.__table__.columns
        if column.name not in {"threshold_id", "created_at"}
    }
    return statement.on_conflict_do_update(
        index_elements=[ThresholdState.threshold_id],
        set_=update_values,
    ).returning(ThresholdState)


async def upsert_threshold_state(
    session: AsyncSession,
    values: dict[str, object],
) -> dict[str, Any]:
    result = await session.execute(build_upsert_threshold_state_statement(values))
    return _row_to_dict(result.scalar_one())
