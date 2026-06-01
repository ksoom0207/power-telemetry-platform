from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime import ensure_aware
from app.core.errors import ValidationAppError
from app.repositories import aggregates as aggregate_repo
from app.schemas.aggregates import PowerAggregateUpsert
from app.services.representative_power import RepresentativePowerResult

AGGREGATE_SOURCE_TYPES = {
    "representative",
    "ilo",
    "rack_measured",
    "device_manual",
    "phase_main",
}


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


def _source_type(source: str) -> str:
    if source == "manual_measured":
        return "device_manual"
    if source == "unknown":
        return "representative"
    if source not in AGGREGATE_SOURCE_TYPES:
        raise ValidationAppError(f"unsupported aggregate source_type: {source}")
    return source


def _period_end(period: str, period_start: datetime) -> datetime:
    if period == "day":
        return period_start + timedelta(days=1)
    if period == "month":
        if period_start.month == 12:
            return period_start.replace(year=period_start.year + 1, month=1)
        return period_start.replace(month=period_start.month + 1)
    raise ValidationAppError("period must be one of day, month")


def _row_dict(row: PowerAggregateUpsert | dict[str, object]) -> dict[str, object]:
    if isinstance(row, PowerAggregateUpsert):
        return row.model_dump()
    return dict(row)


def _aggregate_group(
    rows: list[dict[str, object]],
    *,
    period: str,
    period_start: datetime,
) -> PowerAggregateUpsert:
    first = rows[0]
    total_samples = sum(int(row["sample_count"]) for row in rows)
    known_rows = [
        row
        for row in rows
        if row.get("avg_watts") is not None and int(row["sample_count"]) > 0
    ]
    avg_watts: Decimal | None = None
    min_watts: Decimal | None = None
    max_watts: Decimal | None = None
    if known_rows and total_samples > 0:
        weighted_total = Decimal("0")
        for row in known_rows:
            weighted_total += row["avg_watts"] * int(row["sample_count"])  # type: ignore[operator]
        avg_watts = weighted_total / Decimal(total_samples)
        min_values = [row["min_watts"] for row in known_rows if row.get("min_watts") is not None]
        max_values = [row["max_watts"] for row in known_rows if row.get("max_watts") is not None]
        min_watts = min(min_values) if min_values else None
        max_watts = max(max_values) if max_values else None

    coverage_total = Decimal("0")
    for row in rows:
        coverage_total += row["coverage_percent"]  # type: ignore[operator]

    return PowerAggregateUpsert(
        entity_type=str(first["entity_type"]),
        entity_id=int(first["entity_id"]),
        source_type=str(first["source_type"]),
        period=period,
        period_start=period_start,
        avg_watts=avg_watts,
        min_watts=min_watts,
        max_watts=max_watts,
        sample_count=total_samples,
        coverage_percent=coverage_total / Decimal(len(rows)),
        unknown_count=sum(int(row["unknown_count"]) for row in rows),
        stale_count=sum(int(row["stale_count"]) for row in rows),
    )


def build_hourly_power_aggregate_rows(
    *,
    period_start: datetime,
    results: list[RepresentativePowerResult],
) -> list[PowerAggregateUpsert]:
    ensure_aware(period_start)
    rows: list[PowerAggregateUpsert] = []
    for result in results:
        if result.entity_id is None:
            raise ValidationAppError("entity_id is required for power aggregate upsert")
        known = result.watts is not None and not result.stale
        rows.append(
            PowerAggregateUpsert(
                entity_type=result.entity_type,
                entity_id=result.entity_id,
                source_type=_source_type(result.source),
                period="hour",
                period_start=period_start,
                avg_watts=result.watts if known else None,
                min_watts=result.watts if known else None,
                max_watts=result.watts if known else None,
                sample_count=1 if known else 0,
                coverage_percent=Decimal("100") if known else Decimal("0"),
                unknown_count=result.unknown_count,
                stale_count=result.stale_count + (1 if result.stale else 0),
            )
        )
    return rows


def rollup_hourly_power_aggregate_rows(
    *,
    period: str,
    period_start: datetime,
    hourly_rows: list[PowerAggregateUpsert | dict[str, object]],
) -> list[PowerAggregateUpsert]:
    ensure_aware(period_start)
    end = _period_end(period, period_start)
    groups: dict[tuple[str, int, str], list[dict[str, object]]] = {}
    for hourly_row in hourly_rows:
        row = _row_dict(hourly_row)
        if row.get("period") != "hour":
            continue
        row_period_start = row.get("period_start")
        if not isinstance(row_period_start, datetime):
            raise ValidationAppError("period_start is required for power aggregate rollup")
        ensure_aware(row_period_start)
        if not period_start <= row_period_start < end:
            continue
        entity_id = row.get("entity_id")
        if entity_id is None:
            raise ValidationAppError("entity_id is required for power aggregate rollup")
        key = (str(row["entity_type"]), int(entity_id), str(row["source_type"]))
        groups.setdefault(key, []).append(row)

    return [
        _aggregate_group(rows, period=period, period_start=period_start)
        for rows in groups.values()
    ]


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
