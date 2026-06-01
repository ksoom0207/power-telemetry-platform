from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.dialects import postgresql

from app.repositories import aggregates as aggregate_repo
from app.repositories import kwh as kwh_repo
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
