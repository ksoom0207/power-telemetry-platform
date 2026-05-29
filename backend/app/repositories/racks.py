from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationAppError
from app.models.inventory import Rack


def _row_to_dict(row: Rack) -> dict[str, Any]:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


async def list_racks(
    session: AsyncSession,
    *,
    include_inactive: bool = False,
) -> list[dict[str, Any]]:
    statement = select(Rack).order_by(Rack.name)
    if not include_inactive:
        statement = statement.where(Rack.active.is_(True))
    result = await session.execute(statement)
    return [_row_to_dict(row) for row in result.scalars().all()]


async def get_rack(session: AsyncSession, rack_id: int) -> dict[str, Any]:
    result = await session.execute(select(Rack).where(Rack.id == rack_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise ValidationAppError("rack not found", {"rack_id": rack_id})
    return _row_to_dict(row)


async def create_rack(session: AsyncSession, values: dict[str, object]) -> dict[str, Any]:
    result = await session.execute(insert(Rack).values(**values).returning(Rack))
    return _row_to_dict(result.scalar_one())


async def update_rack(
    session: AsyncSession,
    rack_id: int,
    values: dict[str, object],
) -> dict[str, Any]:
    result = await session.execute(
        update(Rack).where(Rack.id == rack_id).values(**values).returning(Rack)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise ValidationAppError("rack not found", {"rack_id": rack_id})
    return _row_to_dict(row)
