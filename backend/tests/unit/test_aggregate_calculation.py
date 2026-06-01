from datetime import UTC, datetime
from decimal import Decimal

from app.services import aggregates
from app.services import representative_power as rp

HOUR = datetime(2026, 5, 1, 12, tzinfo=UTC)
DAY = datetime(2026, 5, 1, tzinfo=UTC)
NEXT_DAY = datetime(2026, 5, 2, tzinfo=UTC)
MONTH = datetime(2026, 5, 1, tzinfo=UTC)
NEXT_MONTH = datetime(2026, 6, 1, tzinfo=UTC)


def test_hourly_aggregate_rows_use_representative_entity_ids_and_source_types() -> None:
    results = [
        rp.RepresentativePowerResult(
            entity_type="rack",
            entity_id=7,
            watts=Decimal("100"),
            source="rack_measured",
        ),
        rp.RepresentativePowerResult(
            entity_type="phase",
            entity_id=1,
            watts=Decimal("300"),
            source="phase_main",
        ),
        rp.RepresentativePowerResult(
            entity_type="overall",
            entity_id=0,
            watts=Decimal("900"),
            source="representative",
        ),
    ]

    rows = aggregates.build_hourly_power_aggregate_rows(period_start=HOUR, results=results)

    dumped = [row.model_dump() for row in rows]
    assert [(row["entity_type"], row["entity_id"], row["source_type"]) for row in dumped] == [
        ("rack", 7, "rack_measured"),
        ("phase", 1, "phase_main"),
        ("overall", 0, "representative"),
    ]
    assert all(row["period"] == "hour" for row in dumped)
    assert all(row["period_start"] == HOUR for row in dumped)
    assert dumped[0]["avg_watts"] == Decimal("100")
    assert dumped[0]["min_watts"] == Decimal("100")
    assert dumped[0]["max_watts"] == Decimal("100")
    assert dumped[0]["sample_count"] == 1
    assert dumped[0]["coverage_percent"] == Decimal("100")


def test_hourly_aggregate_rows_preserve_unknown_and_stale_counts() -> None:
    rows = aggregates.build_hourly_power_aggregate_rows(
        period_start=HOUR,
        results=[
            rp.RepresentativePowerResult(
                entity_type="rack",
                entity_id=7,
                watts=None,
                source="representative",
                unknown_count=2,
                stale_count=1,
            )
        ],
    )

    row = rows[0].model_dump()
    assert row["avg_watts"] is None
    assert row["sample_count"] == 0
    assert row["coverage_percent"] == Decimal("0")
    assert row["unknown_count"] == 2
    assert row["stale_count"] == 1


def test_daily_rollup_uses_half_open_period_range_and_sums_counts() -> None:
    hourly_rows = [
        _hourly_row(HOUR, avg=Decimal("100"), coverage=Decimal("100"), unknown=1, stale=0),
        _hourly_row(
            HOUR.replace(hour=13),
            avg=Decimal("300"),
            coverage=Decimal("50"),
            unknown=0,
            stale=2,
        ),
        _hourly_row(NEXT_DAY, avg=Decimal("999"), coverage=Decimal("100"), unknown=9, stale=9),
    ]

    rows = aggregates.rollup_hourly_power_aggregate_rows(
        period="day",
        period_start=DAY,
        hourly_rows=hourly_rows,
    )

    assert len(rows) == 1
    row = rows[0].model_dump()
    assert row["period"] == "day"
    assert row["period_start"] == DAY
    assert row["avg_watts"] == Decimal("200")
    assert row["min_watts"] == Decimal("100")
    assert row["max_watts"] == Decimal("300")
    assert row["sample_count"] == 2
    assert row["coverage_percent"] == Decimal("75")
    assert row["unknown_count"] == 1
    assert row["stale_count"] == 2


def test_monthly_rollup_uses_half_open_period_range() -> None:
    hourly_rows = [
        _hourly_row(datetime(2026, 5, 31, 23, tzinfo=UTC), avg=Decimal("400")),
        _hourly_row(NEXT_MONTH, avg=Decimal("999")),
    ]

    rows = aggregates.rollup_hourly_power_aggregate_rows(
        period="month",
        period_start=MONTH,
        hourly_rows=hourly_rows,
    )

    assert len(rows) == 1
    row = rows[0].model_dump()
    assert row["period"] == "month"
    assert row["period_start"] == MONTH
    assert row["avg_watts"] == Decimal("400")
    assert row["sample_count"] == 1


def _hourly_row(
    period_start: datetime,
    *,
    avg: Decimal,
    coverage: Decimal = Decimal("100"),
    unknown: int = 0,
    stale: int = 0,
):
    return aggregates.PowerAggregateUpsert(
        entity_type="rack",
        entity_id=7,
        source_type="representative",
        period="hour",
        period_start=period_start,
        avg_watts=avg,
        min_watts=avg,
        max_watts=avg,
        sample_count=1,
        coverage_percent=coverage,
        unknown_count=unknown,
        stale_count=stale,
    )
