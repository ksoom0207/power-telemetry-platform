from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.core.errors import ValidationAppError
from app.schemas.thresholds import ThresholdCreate, ThresholdUpdate
from app.services import thresholds as threshold_service
from app.services.thresholds import ThresholdEvaluation


@dataclass
class FakeSession:
    commits: int = 0

    async def commit(self) -> None:
        self.commits += 1


class FakeThresholdRepo:
    def __init__(self) -> None:
        self.created: dict[str, object] | None = None
        self.updated: tuple[int, dict[str, object]] | None = None
        self.state: dict[str, object] | None = None
        self.state_by_threshold: dict[int, dict[str, object]] = {}
        self.upserted_states: list[dict[str, object]] = []
        self.list_limit: int | None | object = object()
        self.threshold: dict[str, object] = {
            "id": 1,
            "target_type": "rack",
            "target_id": 1,
            "basis": "avg_watts",
            "warning_watts": Decimal("200"),
            "critical_watts": Decimal("300"),
            "trigger_count": 1,
            "clear_count": 2,
            "active": True,
        }

    async def create_threshold(
        self,
        _session: object,
        values: dict[str, object],
    ) -> dict[str, object]:
        self.created = values
        return {"id": 1, **values}

    async def update_threshold(
        self, _session: object, threshold_id: int, values: dict[str, object]
    ) -> dict[str, object]:
        self.updated = (threshold_id, values)
        self.threshold.update(values)
        return {**self.threshold, "id": threshold_id}

    async def get_threshold(self, _session: object, threshold_id: int) -> dict[str, object]:
        return {**self.threshold, "id": threshold_id}

    async def list_thresholds(
        self,
        _session: object,
        *,
        active: bool | None = True,
        target_type: str | None = None,
        target_id: int | None = None,
        limit: int | None = 100,
    ) -> list[dict[str, object]]:
        self.list_limit = limit
        rows = [self.threshold]
        if active is not None:
            rows = [row for row in rows if row["active"] is active]
        if target_type is not None:
            rows = [row for row in rows if row["target_type"] == target_type]
        if target_id is not None:
            rows = [row for row in rows if row["target_id"] == target_id]
        if limit is not None:
            rows = rows[:limit]
        return [{**row} for row in rows]

    async def get_threshold_state_or_none(
        self,
        _session: object,
        threshold_id: int,
    ) -> dict[str, object] | None:
        state = self.state_by_threshold.get(threshold_id)
        return None if state is None else {**state}

    async def deactivate_threshold(
        self,
        _session: object,
        threshold_id: int,
        values: dict[str, object],
    ) -> dict[str, object]:
        values = {"active": False, **values}
        self.updated = (threshold_id, values)
        self.threshold.update(values)
        return {**self.threshold, "id": threshold_id}

    async def upsert_threshold_state(
        self, _session: object, values: dict[str, object]
    ) -> dict[str, object]:
        self.state = values
        self.upserted_states.append(values)
        return values


class FakeAggregateRepo:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.list_limit: int | None | object = object()

    async def list_latest_power_aggregates(
        self,
        _session: object,
        *,
        period: str = "hour",
        period_start_to: datetime,
        limit: int | None = 1000,
    ) -> list[dict[str, object]]:
        self.list_limit = limit
        rows = [
            {**row}
            for row in self.rows
            if row["period"] == period and row["period_start"] <= period_start_to
        ]
        if limit is not None:
            rows = rows[:limit]
        return rows


@pytest.mark.asyncio
async def test_threshold_create_update_delete_validate_rules_and_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_repo = FakeThresholdRepo()
    monkeypatch.setattr(threshold_service, "threshold_repo", fake_repo)
    session = FakeSession()

    with pytest.raises(ValidationAppError):
        await threshold_service.create_threshold(
            session,
            ThresholdCreate(target_type="rack", target_id=1, basis="avg_watts"),
        )

    with pytest.raises(ValidationAppError):
        await threshold_service.create_threshold(
            session,
            ThresholdCreate(
                target_type="rack",
                target_id=1,
                basis="avg_watts",
                warning_watts=Decimal("200"),
                critical_watts=Decimal("100"),
            ),
        )

    created = await threshold_service.create_threshold(
        session,
        ThresholdCreate(
            target_type="rack",
            target_id=1,
            basis="avg_watts",
            warning_watts=Decimal("100"),
            critical_watts=Decimal("200"),
            trigger_count=2,
            clear_count=3,
        ),
    )
    updated = await threshold_service.update_threshold(
        session,
        1,
        ThresholdUpdate(warning_watts=Decimal("110"), trigger_count=1),
    )
    deleted = await threshold_service.deactivate_threshold(session, 1)

    assert created["warning_watts"] == Decimal("100")
    assert updated["warning_watts"] == Decimal("110")
    assert deleted["active"] is False
    assert fake_repo.updated is not None
    assert fake_repo.updated[1]["updated_at"].tzinfo == UTC
    assert session.commits == 3


@pytest.mark.asyncio
async def test_threshold_update_validates_against_existing_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_repo = FakeThresholdRepo()
    monkeypatch.setattr(threshold_service, "threshold_repo", fake_repo)

    with pytest.raises(ValidationAppError, match="critical_watts"):
        await threshold_service.update_threshold(
            FakeSession(),
            1,
            ThresholdUpdate(critical_watts=Decimal("100")),
        )

    assert fake_repo.updated is None


@pytest.mark.asyncio
async def test_threshold_update_rejects_clearing_all_threshold_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_repo = FakeThresholdRepo()
    monkeypatch.setattr(threshold_service, "threshold_repo", fake_repo)

    with pytest.raises(ValidationAppError, match="warning_watts or critical_watts"):
        await threshold_service.update_threshold(
            FakeSession(),
            1,
            ThresholdUpdate(warning_watts=None, critical_watts=None),
        )

    assert fake_repo.updated is None


@pytest.mark.asyncio
async def test_threshold_state_upsert_stores_hysteresis_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_repo = FakeThresholdRepo()
    monkeypatch.setattr(threshold_service, "threshold_repo", fake_repo)
    session = FakeSession()
    evaluated_at = datetime(2026, 5, 1, tzinfo=UTC)

    row = await threshold_service.upsert_threshold_state_from_evaluation(
        session,
        threshold_id=9,
        evaluation=ThresholdEvaluation(
            current_state="critical",
            consecutive_trigger_count=2,
            consecutive_clear_count=0,
        ),
        evaluated_at=evaluated_at,
    )

    assert row["threshold_id"] == 9
    assert row["current_state"] == "critical"
    assert row["consecutive_trigger_count"] == 2
    assert row["last_evaluated_at"] == evaluated_at
    assert session.commits == 1


@pytest.mark.asyncio
async def test_threshold_state_upsert_rejects_naive_evaluated_at(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_repo = FakeThresholdRepo()
    monkeypatch.setattr(threshold_service, "threshold_repo", fake_repo)

    with pytest.raises(ValueError, match="timezone-aware"):
        await threshold_service.upsert_threshold_state_from_evaluation(
            FakeSession(),
            threshold_id=9,
            evaluation=ThresholdEvaluation(
                current_state="critical",
                consecutive_trigger_count=2,
                consecutive_clear_count=0,
            ),
            evaluated_at=datetime(2026, 5, 1),
        )

    assert fake_repo.state is None


@pytest.mark.asyncio
async def test_scheduled_threshold_evaluation_continues_existing_hysteresis_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluated_at = datetime(2026, 5, 1, 12, tzinfo=UTC)
    threshold_repo = FakeThresholdRepo()
    threshold_repo.threshold = {
        **threshold_repo.threshold,
        "id": 7,
        "warning_watts": Decimal("100"),
        "critical_watts": Decimal("200"),
        "trigger_count": 2,
        "clear_count": 2,
    }
    threshold_repo.state_by_threshold[7] = {
        "threshold_id": 7,
        "current_state": "normal",
        "consecutive_trigger_count": 1,
        "consecutive_clear_count": 0,
        "last_evaluated_at": datetime(2026, 5, 1, 11, tzinfo=UTC),
    }
    aggregate_repo = FakeAggregateRepo(
        [
            {
                "entity_type": "rack",
                "entity_id": 1,
                "source_type": "representative",
                "period": "hour",
                "period_start": evaluated_at,
                "avg_watts": Decimal("150"),
                "min_watts": Decimal("150"),
                "max_watts": Decimal("150"),
                "sample_count": 1,
                "coverage_percent": Decimal("100"),
                "unknown_count": 0,
                "stale_count": 0,
            }
        ]
    )
    monkeypatch.setattr(threshold_service, "threshold_repo", threshold_repo)
    monkeypatch.setattr(threshold_service, "aggregate_repo", aggregate_repo)

    result = await threshold_service.evaluate_active_thresholds(
        FakeSession(),
        evaluated_at=evaluated_at,
    )

    assert result == {"status": "success", "processed_count": 1, "skipped_count": 0}
    assert threshold_repo.upserted_states[0]["current_state"] == "warning"
    assert threshold_repo.upserted_states[0]["consecutive_trigger_count"] == 2
    assert threshold_repo.upserted_states[0]["last_evaluated_at"] == evaluated_at
    assert threshold_repo.list_limit is None
    assert aggregate_repo.list_limit is None


@pytest.mark.asyncio
async def test_scheduled_threshold_evaluation_skips_missing_basis_without_upsert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    threshold_repo = FakeThresholdRepo()
    aggregate_repo = FakeAggregateRepo([])
    monkeypatch.setattr(threshold_service, "threshold_repo", threshold_repo)
    monkeypatch.setattr(threshold_service, "aggregate_repo", aggregate_repo)

    result = await threshold_service.evaluate_active_thresholds(
        FakeSession(),
        evaluated_at=datetime(2026, 5, 1, 12, tzinfo=UTC),
    )

    assert result == {"status": "success", "processed_count": 0, "skipped_count": 1}
    assert threshold_repo.upserted_states == []
