from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.services.kwh import HourlyPowerPoint, build_hourly_kwh


def test_build_hourly_kwh_splits_actual_and_estimated() -> None:
    start = datetime(2026, 5, 1, 0, 0, tzinfo=UTC)
    points = [
        HourlyPowerPoint(hour_start=start, watts=Decimal("1000"), basis_source="rack_measured"),
        HourlyPowerPoint(
            hour_start=start + timedelta(hours=2),
            watts=Decimal("2000"),
            basis_source="device_sum",
        ),
    ]

    rows = build_hourly_kwh(
        start=start,
        hours=4,
        actual_points=points,
        carry_forward_max_hours=1,
    )

    assert rows[0].actual_kwh == Decimal("1")
    assert rows[0].estimated_kwh == Decimal("0")
    assert rows[1].actual_kwh == Decimal("0")
    assert rows[1].estimated_kwh == Decimal("1")
    assert rows[2].actual_kwh == Decimal("2")
    assert rows[3].estimated_kwh == Decimal("2")


def test_build_hourly_kwh_stops_after_carry_forward_cap() -> None:
    start = datetime(2026, 5, 1, 0, 0, tzinfo=UTC)
    points = [
        HourlyPowerPoint(hour_start=start, watts=Decimal("1000"), basis_source="rack_measured")
    ]

    rows = build_hourly_kwh(
        start=start,
        hours=4,
        actual_points=points,
        carry_forward_max_hours=1,
    )

    assert rows[0].coverage_state == "actual"
    assert rows[1].coverage_state == "estimated"
    assert rows[2].coverage_state == "missing"
    assert rows[3].coverage_state == "missing"


def test_build_hourly_kwh_rejects_naive_start() -> None:
    start = datetime(2026, 5, 1, 0, 0)

    try:
        build_hourly_kwh(
            start=start,
            hours=1,
            actual_points=[],
            carry_forward_max_hours=1,
        )
    except ValueError as exc:
        assert "timezone-aware" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_build_hourly_kwh_rejects_naive_power_point() -> None:
    start = datetime(2026, 5, 1, 0, 0, tzinfo=UTC)
    points = [
        HourlyPowerPoint(
            hour_start=datetime(2026, 5, 1, 0, 0),
            watts=Decimal("1000"),
            basis_source="rack_measured",
        )
    ]

    try:
        build_hourly_kwh(
            start=start,
            hours=1,
            actual_points=points,
            carry_forward_max_hours=1,
        )
    except ValueError as exc:
        assert "timezone-aware" in str(exc)
    else:
        raise AssertionError("expected ValueError")
