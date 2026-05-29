from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settings import IloCredentialSetting, PowerDefaultSetting


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


async def get_ilo_credential(session: AsyncSession) -> dict[str, Any] | None:
    result = await session.execute(select(IloCredentialSetting).order_by(IloCredentialSetting.id))
    row = result.scalars().first()
    return _row_to_dict(row) if row else None


async def upsert_ilo_credential(session: AsyncSession, values: dict[str, object]) -> dict[str, Any]:
    current = await get_ilo_credential(session)
    if current is None:
        result = await session.execute(
            insert(IloCredentialSetting).values(**values).returning(IloCredentialSetting)
        )
    else:
        result = await session.execute(
            update(IloCredentialSetting)
            .where(IloCredentialSetting.id == current["id"])
            .values(**values)
            .returning(IloCredentialSetting)
        )
    return _row_to_dict(result.scalar_one())


async def get_power_defaults(session: AsyncSession) -> dict[str, Any] | None:
    result = await session.execute(select(PowerDefaultSetting).order_by(PowerDefaultSetting.id))
    row = result.scalars().first()
    return _row_to_dict(row) if row else None


async def upsert_power_defaults(session: AsyncSession, values: dict[str, object]) -> dict[str, Any]:
    current = await get_power_defaults(session)
    if current is None:
        result = await session.execute(
            insert(PowerDefaultSetting).values(**values).returning(PowerDefaultSetting)
        )
    else:
        result = await session.execute(
            update(PowerDefaultSetting)
            .where(PowerDefaultSetting.id == current["id"])
            .values(**values)
            .returning(PowerDefaultSetting)
        )
    return _row_to_dict(result.scalar_one())
