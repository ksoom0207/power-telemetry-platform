from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from app.core.datetime import ensure_aware


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
