from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime import ensure_aware
from app.core.errors import ValidationAppError
from app.repositories import thresholds as threshold_repo
from app.schemas.thresholds import ThresholdCreate, ThresholdUpdate


@dataclass(frozen=True)
class ThresholdEvaluation:
    current_state: str
    consecutive_trigger_count: int
    consecutive_clear_count: int


def _target_state(
    *,
    value: Decimal,
    warning_watts: Decimal | None,
    critical_watts: Decimal | None,
) -> str:
    if critical_watts is not None and value >= critical_watts:
        return "critical"
    if warning_watts is not None and value >= warning_watts:
        return "warning"
    return "normal"


def evaluate_threshold(
    *,
    value: Decimal,
    warning_watts: Decimal | None,
    critical_watts: Decimal | None,
    current_state: str,
    consecutive_trigger_count: int,
    consecutive_clear_count: int,
    trigger_count: int,
    clear_count: int,
) -> ThresholdEvaluation:
    target = _target_state(value=value, warning_watts=warning_watts, critical_watts=critical_watts)

    if target != "normal":
        next_trigger_count = consecutive_trigger_count + 1
        if next_trigger_count >= trigger_count:
            return ThresholdEvaluation(
                current_state=target,
                consecutive_trigger_count=next_trigger_count,
                consecutive_clear_count=0,
            )
        return ThresholdEvaluation(
            current_state=current_state,
            consecutive_trigger_count=next_trigger_count,
            consecutive_clear_count=0,
        )

    next_clear_count = consecutive_clear_count + 1
    if current_state != "normal" and next_clear_count < clear_count:
        return ThresholdEvaluation(
            current_state=current_state,
            consecutive_trigger_count=consecutive_trigger_count,
            consecutive_clear_count=next_clear_count,
        )
    return ThresholdEvaluation(
        current_state="normal",
        consecutive_trigger_count=0,
        consecutive_clear_count=next_clear_count,
    )


def _now_utc() -> datetime:
    return datetime.now(tz=UTC)


def _with_timestamps(values: dict[str, object], *, create: bool) -> dict[str, object]:
    now = _now_utc()
    values["updated_at"] = now
    if create:
        values["created_at"] = now
    return values


def _validate_threshold_values(values: dict[str, object], *, partial: bool) -> None:
    warning = values.get("warning_watts")
    critical = values.get("critical_watts")
    trigger_count = values.get("trigger_count")
    clear_count = values.get("clear_count")

    if warning is None and critical is None:
        raise ValidationAppError("warning_watts or critical_watts is required")
    if isinstance(warning, Decimal) and isinstance(critical, Decimal) and critical < warning:
        raise ValidationAppError("critical_watts must be greater than or equal to warning_watts")
    if isinstance(trigger_count, int) and trigger_count < 1:
        raise ValidationAppError("trigger_count must be at least 1")
    if isinstance(clear_count, int) and clear_count < 1:
        raise ValidationAppError("clear_count must be at least 1")


async def list_thresholds(
    session: AsyncSession,
    *,
    active: bool | None = True,
    target_type: str | None = None,
    target_id: int | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    return await threshold_repo.list_thresholds(
        session,
        active=active,
        target_type=target_type,
        target_id=target_id,
        limit=limit,
    )


async def create_threshold(
    session: AsyncSession,
    payload: ThresholdCreate,
) -> dict[str, Any]:
    values = payload.model_dump()
    _validate_threshold_values(values, partial=False)
    row = await threshold_repo.create_threshold(
        session,
        _with_timestamps(values, create=True),
    )
    await session.commit()
    return row


async def update_threshold(
    session: AsyncSession,
    threshold_id: int,
    payload: ThresholdUpdate,
) -> dict[str, Any]:
    values = payload.model_dump(exclude_unset=True)
    current = await threshold_repo.get_threshold(session, threshold_id)
    _validate_threshold_values({**current, **values}, partial=True)
    row = await threshold_repo.update_threshold(
        session,
        threshold_id,
        _with_timestamps(values, create=False),
    )
    await session.commit()
    return row


async def deactivate_threshold(session: AsyncSession, threshold_id: int) -> dict[str, Any]:
    row = await threshold_repo.deactivate_threshold(
        session,
        threshold_id,
        _with_timestamps({}, create=False),
    )
    await session.commit()
    return row


async def list_threshold_states(
    session: AsyncSession,
    *,
    threshold_id: int | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    # TODO(Task 7.2): resolve threshold basis values and evaluate states on schedule.
    return await threshold_repo.list_threshold_states(
        session,
        threshold_id=threshold_id,
        limit=limit,
    )


async def upsert_threshold_state_from_evaluation(
    session: AsyncSession,
    *,
    threshold_id: int,
    evaluation: ThresholdEvaluation,
    evaluated_at: datetime,
) -> dict[str, Any]:
    ensure_aware(evaluated_at)
    now = _now_utc()
    row = await threshold_repo.upsert_threshold_state(
        session,
        {
            "threshold_id": threshold_id,
            "current_state": evaluation.current_state,
            "consecutive_trigger_count": evaluation.consecutive_trigger_count,
            "consecutive_clear_count": evaluation.consecutive_clear_count,
            "last_evaluated_at": evaluated_at,
            "created_at": now,
            "updated_at": now,
        },
    )
    await session.commit()
    return row
