from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.services import kwh as kwh_service
from app.services.kwh import HourlyKwhResult, HourlyPowerPoint, build_hourly_kwh


def test_monthly_summary_uses_hourly_rows_for_actual_estimated_split() -> None:
    start = datetime(2026, 5, 1, tzinfo=UTC)
    rows = [
        HourlyKwhResult(
            hour_start=start,
            actual_kwh=Decimal("1.5"),
            estimated_kwh=Decimal("0"),
            basis_source="rack_measured",
            coverage_state="actual",
        ),
        HourlyKwhResult(
            hour_start=start + timedelta(hours=1),
            actual_kwh=Decimal("0"),
            estimated_kwh=Decimal("1.5"),
            basis_source="carry_forward",
            coverage_state="estimated",
        ),
        HourlyKwhResult(
            hour_start=start + timedelta(hours=2),
            actual_kwh=Decimal("0"),
            estimated_kwh=Decimal("0"),
            basis_source="carry_forward",
            coverage_state="missing",
        ),
    ]

    summary = kwh_service.build_monthly_kwh_summary(
        rack_id=7,
        month=start,
        hourly_rows=rows,
        total_hours=3,
        carry_forward_max_hours=1,
    )

    assert summary["actual_kwh"] == Decimal("1.5")
    assert summary["estimated_kwh"] == Decimal("3.0")
    assert summary["coverage_percent"] == Decimal("33.333")
    assert summary["estimated_hours"] == Decimal("1")


def test_carry_forward_cap_missing_rows_do_not_create_estimated_kwh_beyond_cap() -> None:
    start = datetime(2026, 5, 1, tzinfo=UTC)

    hourly = build_hourly_kwh(
        start=start,
        hours=4,
        actual_points=[
            HourlyPowerPoint(
                hour_start=start,
                watts=Decimal("1000"),
                basis_source="rack_measured",
            )
        ],
        carry_forward_max_hours=1,
    )
    summary = kwh_service.build_monthly_kwh_summary(
        rack_id=7,
        month=start,
        hourly_rows=hourly,
        total_hours=4,
        carry_forward_max_hours=1,
    )

    assert [row.coverage_state for row in hourly] == ["actual", "estimated", "missing", "missing"]
    assert summary["actual_kwh"] == Decimal("1")
    assert summary["estimated_kwh"] == Decimal("2")
    assert summary["estimated_hours"] == Decimal("1")
