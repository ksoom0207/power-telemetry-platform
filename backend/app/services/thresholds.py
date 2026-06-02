from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime import ensure_aware
from app.core.errors import ValidationAppError
from app.repositories import aggregates as aggregate_repo
from app.repositories import thresholds as threshold_repo
from app.schemas.thresholds import ThresholdCreate, ThresholdUpdate


@dataclass(frozen=True)
class ThresholdEvaluation:
    current_state: str
    consecutive_trigger_count: int
    consecutive_clear_count: int


@dataclass(frozen=True)
class ThresholdBasisResolution:
    value: Decimal | None
    skipped: bool
    reason: str | None = None


PHASE_ENTITY_IDS = {"R": 1, "S": 2, "T": 3}
PHASE_IDS = frozenset(PHASE_ENTITY_IDS.values())
RACK_REPRESENTATIVE_SOURCE_TYPES = {"representative", "rack_measured"}
DEVICE_REPRESENTATIVE_SOURCE_TYPES = {"representative", "ilo", "device_manual"}


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


def _decimal_or_none(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _value_from_row(row: dict[str, Any], field: str = "avg_watts") -> Decimal | None:
    return _decimal_or_none(row.get(field))


def _basis_value_field(basis: str) -> str:
    if basis in {"avg_watts", "min_watts", "max_watts"}:
        return basis
    return "avg_watts"


def _latest_rows(
    aggregate_rows: list[dict[str, Any]],
    *,
    evaluated_at: datetime,
) -> list[dict[str, Any]]:
    latest: dict[tuple[str, int | None, str], dict[str, Any]] = {}
    for row in sorted(
        aggregate_rows,
        key=lambda aggregate: aggregate.get("period_start") or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    ):
        period_start = row.get("period_start")
        if not isinstance(period_start, datetime):
            continue
        ensure_aware(period_start)
        if period_start > evaluated_at:
            continue
        key = (
            str(row.get("entity_type")),
            row.get("entity_id"),
            str(row.get("source_type")),
        )
        latest.setdefault(key, row)
    return list(latest.values())


def _find_value(
    rows: list[dict[str, Any]],
    *,
    entity_type: str,
    entity_id: int | None,
    source_type: str,
    field: str = "avg_watts",
) -> Decimal | None:
    for row in rows:
        if (
            row.get("entity_type") == entity_type
            and row.get("entity_id") == entity_id
            and row.get("source_type") == source_type
        ):
            return _value_from_row(row, field)
    return None


def _find_representative_value(
    rows: list[dict[str, Any]],
    *,
    entity_type: str,
    entity_id: int | None,
    field: str = "avg_watts",
) -> Decimal | None:
    if entity_type == "rack":
        source_types = RACK_REPRESENTATIVE_SOURCE_TYPES
    elif entity_type == "device":
        source_types = DEVICE_REPRESENTATIVE_SOURCE_TYPES
    else:
        source_types = {"representative"}

    values = [
        _value_from_row(row, field)
        for row in rows
        if (
            row.get("entity_type") == entity_type
            and row.get("entity_id") == entity_id
            and row.get("source_type") in source_types
        )
    ]
    return next((value for value in values if value is not None), None)


def _sum_values(values: list[Decimal | None]) -> Decimal | None:
    if not values or any(value is None for value in values):
        return None
    return sum((value for value in values if value is not None), Decimal("0"))


def _rack_sum(rows: list[dict[str, Any]], *, phase_id: int | None = None) -> Decimal | None:
    rack_rows = [
        row
        for row in rows
        if (
            row.get("entity_type") == "rack"
            and row.get("source_type") in RACK_REPRESENTATIVE_SOURCE_TYPES
        )
    ]
    if phase_id is not None and any("phase" in row for row in rack_rows):
        phase_by_id = {value: key for key, value in PHASE_ENTITY_IDS.items()}
        phase = phase_by_id.get(phase_id)
        rack_rows = [row for row in rack_rows if row.get("phase") == phase]
    return _sum_values([_value_from_row(row) for row in rack_rows])


def _phase_main_value(rows: list[dict[str, Any]], phase_id: int) -> Decimal | None:
    return _find_value(
        rows,
        entity_type="phase",
        entity_id=phase_id,
        source_type="phase_main",
    )


def _phase_rack_sum_value(rows: list[dict[str, Any]], phase_id: int) -> Decimal | None:
    persisted = _find_value(
        rows,
        entity_type="phase",
        entity_id=phase_id,
        source_type="representative",
    )
    if persisted is not None:
        return persisted
    return _rack_sum(rows, phase_id=phase_id)


def _phase_main_sum(rows: list[dict[str, Any]]) -> Decimal | None:
    return _sum_values([_phase_main_value(rows, phase_id) for phase_id in sorted(PHASE_IDS)])


def _resolved(value: Decimal | None, reason: str) -> ThresholdBasisResolution:
    if value is None:
        return ThresholdBasisResolution(value=None, skipped=True, reason=reason)
    return ThresholdBasisResolution(value=value, skipped=False)


def resolve_threshold_basis_from_aggregates(
    threshold: dict[str, Any],
    aggregate_rows: list[dict[str, Any]],
    *,
    evaluated_at: datetime,
) -> ThresholdBasisResolution:
    ensure_aware(evaluated_at)
    rows = _latest_rows(aggregate_rows, evaluated_at=evaluated_at)
    target_type = str(threshold["target_type"])
    target_id = threshold.get("target_id")
    basis = str(threshold.get("basis") or "max")

    if target_type in {"rack", "device"}:
        value = _find_representative_value(
            rows,
            entity_type=target_type,
            entity_id=int(target_id) if target_id is not None else None,
            field=_basis_value_field(basis),
        )
        return _resolved(value, "missing representative aggregate")

    if target_type == "phase":
        if target_id is None:
            return _resolved(None, "missing phase target_id")
        phase_id = int(target_id)
        if basis == "phase_main":
            return _resolved(_phase_main_value(rows, phase_id), "missing phase_main aggregate")
        rack_sum = _phase_rack_sum_value(rows, phase_id)
        if basis == "rack_sum":
            return _resolved(rack_sum, "missing rack_sum aggregate")
        phase_main = _phase_main_value(rows, phase_id)
        return _resolved(
            max(value for value in [phase_main, rack_sum] if value is not None)
            if phase_main is not None or rack_sum is not None
            else None,
            "missing phase max aggregate",
        )

    if target_type == "overall":
        rack_sum = _find_value(
            rows,
            entity_type="overall",
            entity_id=int(target_id) if target_id is not None else 0,
            source_type="representative",
        )
        if rack_sum is None:
            rack_sum = _rack_sum(rows)
        if basis == "rack_sum":
            return _resolved(rack_sum, "missing overall rack_sum aggregate")
        phase_main_sum = _phase_main_sum(rows)
        if basis == "phase_main_sum":
            return _resolved(phase_main_sum, "missing overall phase_main_sum aggregate")
        return _resolved(
            max(value for value in [rack_sum, phase_main_sum] if value is not None)
            if rack_sum is not None or phase_main_sum is not None
            else None,
            "missing overall max aggregate",
        )

    return _resolved(None, "unsupported threshold target_type")


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


async def evaluate_active_thresholds(
    session: AsyncSession,
    *,
    evaluated_at: datetime | None = None,
) -> dict[str, object]:
    evaluated_at = evaluated_at or _now_utc()
    ensure_aware(evaluated_at)
    active_thresholds = await threshold_repo.list_thresholds(session, active=True, limit=None)
    aggregate_rows = await aggregate_repo.list_latest_power_aggregates(
        session,
        period="hour",
        period_start_to=evaluated_at,
        limit=None,
    )

    processed_count = 0
    skipped_count = 0
    for threshold in active_thresholds:
        basis = resolve_threshold_basis_from_aggregates(
            threshold,
            aggregate_rows,
            evaluated_at=evaluated_at,
        )
        if basis.skipped or basis.value is None:
            skipped_count += 1
            continue

        existing_state = await threshold_repo.get_threshold_state_or_none(
            session,
            int(threshold["id"]),
        )
        previous_state = existing_state or {
            "current_state": "normal",
            "consecutive_trigger_count": 0,
            "consecutive_clear_count": 0,
        }
        evaluation = evaluate_threshold(
            value=basis.value,
            warning_watts=threshold.get("warning_watts"),
            critical_watts=threshold.get("critical_watts"),
            current_state=str(previous_state["current_state"]),
            consecutive_trigger_count=int(previous_state["consecutive_trigger_count"]),
            consecutive_clear_count=int(previous_state["consecutive_clear_count"]),
            trigger_count=int(threshold["trigger_count"]),
            clear_count=int(threshold["clear_count"]),
        )
        await upsert_threshold_state_from_evaluation(
            session,
            threshold_id=int(threshold["id"]),
            evaluation=evaluation,
            evaluated_at=evaluated_at,
        )
        processed_count += 1

    return {
        "status": "success",
        "processed_count": processed_count,
        "skipped_count": skipped_count,
    }
