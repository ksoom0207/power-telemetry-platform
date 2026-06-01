from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime import ensure_aware
from app.core.errors import ValidationAppError
from app.repositories import aggregates as aggregate_repo
from app.schemas.aggregates import PowerAggregateUpsert


def _now_utc() -> datetime:
    return datetime.now(tz=UTC)


def _with_timestamps(values: dict[str, object], *, create: bool) -> dict[str, object]:
    now = _now_utc()
    values["updated_at"] = now
    if create:
        values["created_at"] = now
    return values


def _validate_upsert_values(values: dict[str, object]) -> None:
    if values.get("entity_id") is None:
        raise ValidationAppError("entity_id is required for power aggregate upsert")
    period_start = values.get("period_start")
    if isinstance(period_start, datetime):
        ensure_aware(period_start)
    coverage = values.get("coverage_percent")
    if isinstance(coverage, Decimal) and not Decimal("0") <= coverage <= Decimal("100"):
        raise ValidationAppError("coverage_percent must be between 0 and 100")


async def upsert_power_aggregate(
    session: AsyncSession,
    payload: PowerAggregateUpsert,
) -> dict[str, Any]:
    values = payload.model_dump()
    _validate_upsert_values(values)
    row = await aggregate_repo.upsert_power_aggregate(
        session,
        _with_timestamps(values, create=True),
    )
    await session.commit()
    return row


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
    # TODO(Task 7.2): calculate and refresh aggregate rows from representative power inputs.
    return await aggregate_repo.list_power_aggregates(
        session,
        entity_type=entity_type,
        entity_id=entity_id,
        source_type=source_type,
        period=period,
        period_start_from=period_start_from,
        period_start_to=period_start_to,
        limit=limit,
    )
