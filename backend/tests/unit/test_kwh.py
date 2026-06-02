from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.core.errors import ValidationAppError
from app.services.kwh import (
    HourlyPowerPoint,
    build_hourly_kwh,
    count_hours,
    floor_to_hour,
    month_start,
    next_month_start,
)


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


def test_floor_to_hour_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        floor_to_hour(datetime(2026, 5, 1, 12, 34, 56))


def test_floor_to_hour_removes_minutes_seconds_and_microseconds() -> None:
    value = datetime(2026, 5, 1, 12, 34, 56, 789, tzinfo=UTC)

    assert floor_to_hour(value) == datetime(2026, 5, 1, 12, tzinfo=UTC)


def test_month_helpers_handle_year_boundary() -> None:
    value = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)

    assert month_start(value) == datetime(2026, 12, 1, tzinfo=UTC)
    assert next_month_start(month_start(value)) == datetime(2027, 1, 1, tzinfo=UTC)


def test_count_hours_uses_half_open_range() -> None:
    start = datetime(2026, 5, 1, 0, tzinfo=UTC)
    end = datetime(2026, 5, 2, 0, tzinfo=UTC)

    assert count_hours(start, end) == 24


def test_count_hours_rejects_non_hour_boundaries() -> None:
    start = datetime(2026, 5, 1, 0, 30, tzinfo=UTC)
    end = datetime(2026, 5, 1, 2, tzinfo=UTC)

    with pytest.raises(ValueError, match="hour boundaries"):
        count_hours(start, end)


def test_count_hours_rejects_empty_or_reversed_range() -> None:
    start = datetime(2026, 5, 1, 0, tzinfo=UTC)

    with pytest.raises(ValidationAppError, match="greater than"):
        count_hours(start, start)
    with pytest.raises(ValidationAppError, match="greater than"):
        count_hours(start, start - timedelta(hours=1))
