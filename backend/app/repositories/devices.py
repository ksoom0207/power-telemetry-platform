from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationAppError
from app.models.inventory import Device


def _row_to_dict(row: Device) -> dict[str, Any]:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


async def list_devices(
    session: AsyncSession,
    *,
    include_inactive: bool = False,
    rack_id: int | None = None,
) -> list[dict[str, Any]]:
    statement = select(Device).order_by(Device.name)
    if not include_inactive:
        statement = statement.where(Device.active.is_(True))
    if rack_id is not None:
        statement = statement.where(Device.rack_id == rack_id)
    result = await session.execute(statement)
    return [_row_to_dict(row) for row in result.scalars().all()]


async def get_device(session: AsyncSession, device_id: int) -> dict[str, Any]:
    result = await session.execute(select(Device).where(Device.id == device_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise ValidationAppError("device not found", {"device_id": device_id})
    return _row_to_dict(row)


async def create_device(session: AsyncSession, values: dict[str, object]) -> dict[str, Any]:
    result = await session.execute(insert(Device).values(**values).returning(Device))
    return _row_to_dict(result.scalar_one())


async def update_device(
    session: AsyncSession,
    device_id: int,
    values: dict[str, object],
) -> dict[str, Any]:
    result = await session.execute(
        update(Device).where(Device.id == device_id).values(**values).returning(Device)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise ValidationAppError("device not found", {"device_id": device_id})
    return _row_to_dict(row)
