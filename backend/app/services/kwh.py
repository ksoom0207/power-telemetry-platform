from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.datetime import ensure_aware
from app.core.errors import ValidationAppError
from app.repositories import aggregates as aggregates_repo
from app.repositories import kwh as kwh_repo

SOURCE_PRECEDENCE = {
    "rack_measured": 0,
    "representative": 1,
    "ilo": 2,
    "device_manual": 3,
}


@dataclass(frozen=True)
class HourlyPowerPoint:
    hour_start: datetime
    watts: Decimal
    basis_source: str


@dataclass(frozen=True)
class HourlyKwhResult:
    hour_start: datetime
    actual_kwh: Decimal
    estimated_kwh: Decimal
    basis_source: str
    coverage_state: str


def floor_to_hour(value: datetime) -> datetime:
    ensure_aware(value)
    return value.replace(minute=0, second=0, microsecond=0)


def month_start(value: datetime) -> datetime:
    ensure_aware(value)
    return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def next_month_start(value: datetime) -> datetime:
    start = month_start(value)
    if start.month == 12:
        return start.replace(year=start.year + 1, month=1)
    return start.replace(month=start.month + 1)


def count_hours(start: datetime, end: datetime) -> int:
    ensure_aware(start)
    ensure_aware(end)
    if floor_to_hour(start) != start or floor_to_hour(end) != end:
        raise ValueError("datetime range must use hour boundaries")
    if end <= start:
        raise ValidationAppError("end must be greater than start")
    seconds = (end - start).total_seconds()
    if seconds % 3600 != 0:
        raise ValueError("datetime range must contain whole hours")
    return int(seconds // 3600)


def build_hourly_kwh(
    *,
    start: datetime,
    hours: int,
    actual_points: list[HourlyPowerPoint],
    carry_forward_max_hours: int,
) -> list[HourlyKwhResult]:
    ensure_aware(start)
    for point in actual_points:
        ensure_aware(point.hour_start)
    by_hour = {point.hour_start: point for point in actual_points}
    rows: list[HourlyKwhResult] = []
    last_actual: HourlyPowerPoint | None = None
    last_actual_index: int | None = None

    for index in range(hours):
        hour = start + timedelta(hours=index)
        point = by_hour.get(hour)
        if point is not None:
            last_actual = point
            last_actual_index = index
            rows.append(
                HourlyKwhResult(
                    hour_start=hour,
                    actual_kwh=point.watts / Decimal("1000"),
                    estimated_kwh=Decimal("0"),
                    basis_source=point.basis_source,
                    coverage_state="actual",
                )
            )
            continue

        if last_actual is not None and last_actual_index is not None:
            gap = index - last_actual_index
            if gap <= carry_forward_max_hours:
                rows.append(
                    HourlyKwhResult(
                        hour_start=hour,
                        actual_kwh=Decimal("0"),
                        estimated_kwh=last_actual.watts / Decimal("1000"),
                        basis_source="carry_forward",
                        coverage_state="estimated",
                    )
                )
                continue

        rows.append(
            HourlyKwhResult(
                hour_start=hour,
                actual_kwh=Decimal("0"),
                estimated_kwh=Decimal("0"),
                basis_source="carry_forward",
                coverage_state="missing",
            )
        )

    return rows


def _source_rank(source_type: str) -> tuple[int, str]:
    return (SOURCE_PRECEDENCE.get(source_type, len(SOURCE_PRECEDENCE)), source_type)


def _actual_points_from_aggregates(
    rows: list[dict[str, object]],
) -> dict[int, list[HourlyPowerPoint]]:
    selected: dict[tuple[int, datetime], dict[str, object]] = {}
    for row in rows:
        avg_watts = row.get("avg_watts")
        sample_count = row.get("sample_count")
        period_start = row.get("period_start")
        rack_id = row.get("entity_id")
        source_type = str(row.get("source_type"))
        if avg_watts is None or not isinstance(avg_watts, Decimal):
            continue
        if not isinstance(sample_count, int) or sample_count <= 0:
            continue
        if not isinstance(period_start, datetime) or not isinstance(rack_id, int):
            continue
        ensure_aware(period_start)
        key = (rack_id, period_start)
        current = selected.get(key)
        if current is None or _source_rank(source_type) < _source_rank(str(current["source_type"])):
            selected[key] = row

    points_by_rack: dict[int, list[HourlyPowerPoint]] = {}
    for (rack_id, period_start), row in selected.items():
        points_by_rack.setdefault(rack_id, []).append(
            HourlyPowerPoint(
                hour_start=period_start,
                watts=row["avg_watts"],  # type: ignore[arg-type]
                basis_source=str(row["source_type"]),
            )
        )

    for points in points_by_rack.values():
        points.sort(key=lambda point: point.hour_start)
    return points_by_rack


def _rack_ids_from_aggregates(rows: list[dict[str, object]]) -> list[int]:
    rack_ids = {
        rack_id
        for rack_id in (row.get("entity_id") for row in rows)
        if isinstance(rack_id, int)
    }
    return sorted(rack_ids)


def _months_in_range(start: datetime, end: datetime) -> list[datetime]:
    ensure_aware(start)
    ensure_aware(end)
    months: list[datetime] = []
    current = month_start(start)
    while current < end:
        months.append(current)
        current = next_month_start(current)
    return months


def _now_utc() -> datetime:
    return datetime.now(tz=UTC)


def hourly_kwh_result_to_row(
    *,
    rack_id: int,
    result: HourlyKwhResult,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> dict[str, object]:
    now = _now_utc()
    return {
        "rack_id": rack_id,
        "hour_start": result.hour_start,
        "actual_kwh": result.actual_kwh,
        "estimated_kwh": result.estimated_kwh,
        "basis_source": result.basis_source,
        "coverage_state": result.coverage_state,
        "created_at": created_at or now,
        "updated_at": updated_at or now,
    }


def hourly_kwh_results_to_rows(
    *,
    rack_id: int,
    results: list[HourlyKwhResult],
) -> list[dict[str, object]]:
    now = _now_utc()
    return [
        hourly_kwh_result_to_row(
            rack_id=rack_id,
            result=result,
            created_at=now,
            updated_at=now,
        )
        for result in results
    ]


def build_monthly_kwh_summary(
    *,
    rack_id: int,
    month: datetime,
    hourly_rows: list[HourlyKwhResult] | list[dict[str, object]],
    total_hours: int,
    carry_forward_max_hours: int,
) -> dict[str, object]:
    ensure_aware(month)
    if total_hours < 1:
        raise ValidationAppError("total_hours must be at least 1")

    actual_kwh = Decimal("0")
    estimated_total_kwh = Decimal("0")
    actual_hour_count = 0
    estimated_hours = 0

    for row in hourly_rows:
        if isinstance(row, HourlyKwhResult):
            row_actual_kwh = row.actual_kwh
            row_estimated_kwh = row.estimated_kwh
            coverage_state = row.coverage_state
        else:
            row_actual_kwh = row["actual_kwh"]
            row_estimated_kwh = row["estimated_kwh"]
            coverage_state = row["coverage_state"]
            has_decimal_kwh = isinstance(row_actual_kwh, Decimal) and isinstance(
                row_estimated_kwh, Decimal
            )
            if not has_decimal_kwh:
                raise ValidationAppError("hourly kWh values must be Decimal")
            if not isinstance(coverage_state, str):
                raise ValidationAppError("coverage_state must be a string")

        actual_kwh += row_actual_kwh
        estimated_total_kwh += row_actual_kwh + row_estimated_kwh
        if coverage_state == "actual":
            actual_hour_count += 1
        if coverage_state == "estimated":
            estimated_hours += 1

    coverage_ratio = Decimal(actual_hour_count) / Decimal(total_hours) * Decimal("100")
    coverage_percent = coverage_ratio.quantize(Decimal("0.001"))
    return {
        "rack_id": rack_id,
        "month": month,
        "actual_kwh": actual_kwh,
        "estimated_kwh": estimated_total_kwh,
        "coverage_percent": coverage_percent,
        "estimated_hours": Decimal(estimated_hours),
        "carry_forward_max_hours": carry_forward_max_hours,
        "needs_recalculation": False,
    }


async def persist_rack_hourly_kwh_results(
    session: AsyncSession,
    *,
    rack_id: int,
    results: list[HourlyKwhResult],
) -> list[dict[str, Any]]:
    rows = hourly_kwh_results_to_rows(rack_id=rack_id, results=results)
    persisted = await kwh_repo.upsert_rack_hourly_kwh_rows(session, rows)
    await session.commit()
    return persisted


async def upsert_rack_monthly_kwh_from_hourly(
    session: AsyncSession,
    *,
    rack_id: int,
    month: datetime,
    hourly_rows: list[HourlyKwhResult] | list[dict[str, object]],
    total_hours: int,
    carry_forward_max_hours: int,
) -> dict[str, Any]:
    now = _now_utc()
    values = build_monthly_kwh_summary(
        rack_id=rack_id,
        month=month,
        hourly_rows=hourly_rows,
        total_hours=total_hours,
        carry_forward_max_hours=carry_forward_max_hours,
    )
    values["created_at"] = now
    values["updated_at"] = now
    row = await kwh_repo.upsert_rack_monthly_kwh(session, values=values)
    await session.commit()
    return row


async def refresh_monthly_kwh_from_persisted_hourly(
    session: AsyncSession,
    *,
    rack_id: int,
    month: datetime,
    carry_forward_max_hours: int,
) -> dict[str, Any]:
    month = month_start(month)
    end = next_month_start(month)
    total_hours = count_hours(month, end)
    hourly_rows = await kwh_repo.list_rack_hourly_kwh(
        session,
        rack_id=rack_id,
        hour_start_from=month,
        hour_start_to=end,
        limit=total_hours,
    )
    now = _now_utc()
    values = build_monthly_kwh_summary(
        rack_id=rack_id,
        month=month,
        hourly_rows=hourly_rows,
        total_hours=total_hours,
        carry_forward_max_hours=carry_forward_max_hours,
    )
    values["created_at"] = now
    values["updated_at"] = now
    row = await kwh_repo.upsert_rack_monthly_kwh(session, values=values)
    await session.commit()
    return row


async def refresh_rack_kwh_for_range(
    session: AsyncSession,
    *,
    rack_id: int,
    start: datetime,
    end: datetime,
    carry_forward_max_hours: int,
    aggregate_rows: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    hours = count_hours(start, end)
    if aggregate_rows is None:
        aggregate_rows = await aggregates_repo.list_rack_hourly_power_aggregates(
            session,
            period_start_from=start,
            period_start_to=end,
            rack_id=rack_id,
            limit=None,
        )
    points = _actual_points_from_aggregates(aggregate_rows).get(rack_id, [])
    results = build_hourly_kwh(
        start=start,
        hours=hours,
        actual_points=points,
        carry_forward_max_hours=carry_forward_max_hours,
    )
    hourly_rows = hourly_kwh_results_to_rows(rack_id=rack_id, results=results)
    await kwh_repo.upsert_rack_hourly_kwh_rows(session, rows=hourly_rows)

    monthly_count = 0
    for month in _months_in_range(start, end):
        month_end = next_month_start(month)
        month_hours = count_hours(month, month_end)
        persisted_hourly = await kwh_repo.list_rack_hourly_kwh(
            session,
            rack_id=rack_id,
            hour_start_from=month,
            hour_start_to=month_end,
            limit=month_hours,
        )
        now = _now_utc()
        values = build_monthly_kwh_summary(
            rack_id=rack_id,
            month=month,
            hourly_rows=persisted_hourly,
            total_hours=month_hours,
            carry_forward_max_hours=carry_forward_max_hours,
        )
        values["created_at"] = now
        values["updated_at"] = now
        await kwh_repo.upsert_rack_monthly_kwh(session, values=values)
        monthly_count += 1

    await session.commit()
    return {"rack_id": rack_id, "hourly_count": len(hourly_rows), "monthly_count": monthly_count}


async def refresh_kwh_for_range(
    session: AsyncSession,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    rack_id: int | None = None,
    carry_forward_max_hours: int | None = None,
) -> dict[str, object]:
    if end is None:
        end = floor_to_hour(_now_utc())
    else:
        ensure_aware(end)
    if start is None:
        start = end - timedelta(hours=1)
    else:
        ensure_aware(start)
    carry_forward_max_hours = (
        settings.carry_forward_max_hours
        if carry_forward_max_hours is None
        else carry_forward_max_hours
    )
    count_hours(start, end)

    aggregate_rows = await aggregates_repo.list_rack_hourly_power_aggregates(
        session,
        period_start_from=start,
        period_start_to=end,
        rack_id=rack_id,
        limit=None,
    )
    rack_ids = _rack_ids_from_aggregates(aggregate_rows)
    if rack_id is not None and rack_id not in rack_ids:
        rack_ids = [rack_id]

    results = [
        await refresh_rack_kwh_for_range(
            session,
            rack_id=current_rack_id,
            start=start,
            end=end,
            carry_forward_max_hours=carry_forward_max_hours,
            aggregate_rows=[
                row for row in aggregate_rows if row.get("entity_id") == current_rack_id
            ],
        )
        for current_rack_id in rack_ids
    ]
    return {"status": "success", "rack_count": len(results), "racks": results}


async def process_kwh_recalculations(
    session: AsyncSession,
    *,
    limit: int = 100,
    carry_forward_max_hours: int | None = None,
) -> dict[str, object]:
    carry_forward_max_hours = (
        settings.carry_forward_max_hours
        if carry_forward_max_hours is None
        else carry_forward_max_hours
    )
    months = await kwh_repo.list_months_needing_recalculation(session, limit=limit)
    processed = 0
    for row in months:
        rack_id = row["rack_id"]
        month = row["month"]
        if not isinstance(rack_id, int) or not isinstance(month, datetime):
            continue
        ensure_aware(month)
        await refresh_monthly_kwh_from_persisted_hourly(
            session,
            rack_id=rack_id,
            month=month,
            carry_forward_max_hours=carry_forward_max_hours,
        )
        await kwh_repo.clear_month_recalculation(session, rack_id=rack_id, month=month_start(month))
        await session.commit()
        processed += 1
    return {"status": "success", "processed_count": processed}


async def list_rack_hourly_kwh(
    session: AsyncSession,
    *,
    rack_id: int | None = None,
    hour_start_from: datetime | None = None,
    hour_start_to: datetime | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    return await kwh_repo.list_rack_hourly_kwh(
        session,
        rack_id=rack_id,
        hour_start_from=hour_start_from,
        hour_start_to=hour_start_to,
        limit=limit,
    )


async def list_rack_monthly_kwh(
    session: AsyncSession,
    *,
    rack_id: int | None = None,
    month_from: datetime | None = None,
    month_to: datetime | None = None,
    needs_recalculation: bool | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    return await kwh_repo.list_rack_monthly_kwh(
        session,
        rack_id=rack_id,
        month_from=month_from,
        month_to=month_to,
        needs_recalculation=needs_recalculation,
        limit=limit,
    )
