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
        return values


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
