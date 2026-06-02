from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.dialects import postgresql

from app.repositories import aggregates as aggregate_repo
from app.repositories import ilo as ilo_repo
from app.repositories import kwh as kwh_repo
from app.repositories import measurements as measurement_repo
from app.repositories import thresholds as threshold_repo


def _compile(statement: object) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))


def test_power_aggregate_upsert_uses_expected_conflict_target() -> None:
    statement = aggregate_repo.build_upsert_power_aggregate_statement(
        {
            "entity_type": "rack",
            "entity_id": 1,
            "source_type": "representative",
            "period": "hour",
            "period_start": datetime(2026, 5, 1, tzinfo=UTC),
            "avg_watts": Decimal("100"),
            "min_watts": Decimal("90"),
            "max_watts": Decimal("110"),
            "sample_count": 3,
            "coverage_percent": Decimal("100"),
            "unknown_count": 0,
            "stale_count": 0,
            "created_at": datetime(2026, 5, 1, tzinfo=UTC),
            "updated_at": datetime(2026, 5, 1, tzinfo=UTC),
        }
    )

    compiled = _compile(statement)

    assert "ON CONFLICT" in compiled
    assert "entity_type, entity_id, source_type, period, period_start" in compiled


def test_kwh_hourly_and_monthly_upserts_use_expected_conflict_targets() -> None:
    now = datetime(2026, 5, 1, tzinfo=UTC)
    hourly = kwh_repo.build_upsert_rack_hourly_kwh_statement(
        {
            "rack_id": 1,
            "hour_start": now,
            "actual_kwh": Decimal("1"),
            "estimated_kwh": Decimal("0"),
            "basis_source": "rack_measured",
            "coverage_state": "actual",
            "created_at": now,
            "updated_at": now,
        }
    )
    monthly = kwh_repo.build_upsert_rack_monthly_kwh_statement(
        {
            "rack_id": 1,
            "month": now,
            "actual_kwh": Decimal("1"),
            "estimated_kwh": Decimal("1"),
            "coverage_percent": Decimal("100"),
            "estimated_hours": Decimal("0"),
            "carry_forward_max_hours": 6,
            "needs_recalculation": False,
            "created_at": now,
            "updated_at": now,
        }
    )

    compiled_hourly = _compile(hourly)
    compiled_monthly = _compile(monthly)

    assert "ON CONFLICT" in compiled_hourly
    assert "rack_id, hour_start" in compiled_hourly
    assert "ON CONFLICT" in compiled_monthly
    assert "rack_id, month" in compiled_monthly


def test_threshold_state_upsert_uses_threshold_id_conflict_target() -> None:
    now = datetime(2026, 5, 1, tzinfo=UTC)
    statement = threshold_repo.build_upsert_threshold_state_statement(
        {
            "threshold_id": 1,
            "current_state": "warning",
            "consecutive_trigger_count": 2,
            "consecutive_clear_count": 0,
            "last_evaluated_at": now,
            "created_at": now,
            "updated_at": now,
        }
    )

    compiled = _compile(statement)

    assert "ON CONFLICT" in compiled
    assert "threshold_id" in compiled


def test_latest_power_sample_query_filters_success_and_uses_latest_tiebreak() -> None:
    statement = ilo_repo.build_latest_power_samples_by_device_statement(
        measured_at_to=datetime(2026, 6, 2, tzinfo=UTC)
    )

    compiled = _compile(statement)

    assert "ilo_power_samples.status = " in compiled
    assert "ilo_power_samples.average_watts IS NOT NULL" in compiled
    assert "ilo_power_samples.measured_at <= " in compiled
    assert "PARTITION BY ilo_power_samples.device_id" in compiled
    assert "ORDER BY ilo_power_samples.measured_at DESC, ilo_power_samples.id DESC" in compiled


def test_latest_manual_measurement_queries_use_entity_tiebreaks() -> None:
    measured_at_to = datetime(2026, 6, 2, tzinfo=UTC)

    device = _compile(
        measurement_repo.build_latest_manual_device_power_by_device_statement(
            measured_at_to=measured_at_to
        )
    )
    rack = _compile(
        measurement_repo.build_latest_rack_measurements_by_rack_statement(
            measured_at_to=measured_at_to
        )
    )
    phase = _compile(
        measurement_repo.build_latest_phase_main_measurements_by_phase_statement(
            measured_at_to=measured_at_to
        )
    )

    assert "PARTITION BY manual_device_powers.device_id" in device
    assert "manual_device_powers.value_type = " in device
    assert "manual_device_powers.quality = " in device
    assert "ORDER BY manual_device_powers.measured_at DESC, manual_device_powers.id DESC" in device
    assert "PARTITION BY rack_measurements.rack_id" in rack
    assert "ORDER BY rack_measurements.measured_at DESC, rack_measurements.id DESC" in rack
    assert "PARTITION BY phase_main_measurements.phase" in phase
    assert (
        "ORDER BY phase_main_measurements.measured_at DESC, phase_main_measurements.id DESC"
        in phase
    )


@pytest.mark.asyncio
async def test_power_aggregate_upsert_rejects_naive_period_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.schemas.aggregates import PowerAggregateUpsert
    from app.services import aggregates as aggregate_service

    class FakeSession:
        async def commit(self) -> None:
            raise AssertionError("commit should not be called")

    async def fake_upsert(_session: object, _values: dict[str, object]) -> dict[str, object]:
        raise AssertionError("repository should not be called")

    monkeypatch.setattr(aggregate_service.aggregate_repo, "upsert_power_aggregate", fake_upsert)

    with pytest.raises(ValueError, match="timezone-aware"):
        await aggregate_service.upsert_power_aggregate(
            FakeSession(),
            PowerAggregateUpsert(
                entity_type="rack",
                entity_id=1,
                source_type="representative",
                period="hour",
                period_start=datetime(2026, 5, 1),
                avg_watts=Decimal("100"),
                sample_count=1,
                coverage_percent=Decimal("100"),
            ),
        )
