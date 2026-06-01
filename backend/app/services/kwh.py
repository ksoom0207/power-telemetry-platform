from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime import ensure_aware
from app.core.errors import ValidationAppError
from app.repositories import kwh as kwh_repo


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
    row = await kwh_repo.upsert_rack_monthly_kwh(session, values)
    await session.commit()
    return row


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
