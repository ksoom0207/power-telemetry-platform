from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime import ensure_aware, to_utc
from app.core.errors import ValidationAppError
from app.repositories import aggregates as aggregate_repo
from app.repositories import devices as device_repo
from app.repositories import ilo as ilo_repo
from app.repositories import measurements as measurement_repo
from app.repositories import racks as rack_repo
from app.schemas.aggregates import PowerAggregateUpsert
from app.services.representative_power import (
    CandidatePower,
    DeviceRepresentativePower,
    RepresentativePowerResult,
    choose_device_representative,
    resolve_overall_representative,
    resolve_phase_representative,
    resolve_rack_representative,
)

AGGREGATE_SOURCE_TYPES = {
    "representative",
    "ilo",
    "rack_measured",
    "device_manual",
    "phase_main",
}


def _now_utc() -> datetime:
    return datetime.now(tz=UTC)


def _with_timestamps(values: dict[str, object], *, create: bool) -> dict[str, object]:
    now = _now_utc()
    values["updated_at"] = now
    if create:
        values["created_at"] = now
    return values


def floor_to_hour(value: datetime) -> datetime:
    return ensure_aware(value).replace(minute=0, second=0, microsecond=0)


def _validate_upsert_values(values: dict[str, object]) -> None:
    if values.get("entity_id") is None:
        raise ValidationAppError("entity_id is required for power aggregate upsert")
    period_start = values.get("period_start")
    if isinstance(period_start, datetime):
        ensure_aware(period_start)
    coverage = values.get("coverage_percent")
    if isinstance(coverage, Decimal) and not Decimal("0") <= coverage <= Decimal("100"):
        raise ValidationAppError("coverage_percent must be between 0 and 100")


def _source_type(source: str) -> str:
    if source == "manual_measured":
        return "device_manual"
    if source == "unknown":
        return "representative"
    if source not in AGGREGATE_SOURCE_TYPES:
        raise ValidationAppError(f"unsupported aggregate source_type: {source}")
    return source


def _candidate(
    row: dict[str, object] | None,
    *,
    watts_field: str,
    quality_default: str,
) -> CandidatePower | None:
    if row is None:
        return None
    watts = row.get(watts_field)
    measured_at = row.get("measured_at")
    if not isinstance(watts, Decimal) or not isinstance(measured_at, datetime):
        return None
    return CandidatePower(
        watts=watts,
        measured_at=measured_at,
        quality=str(row.get("quality") or quality_default),
    )


def _has_stale_device_candidate(
    now: datetime,
    *,
    ilo: CandidatePower | None,
    measured: CandidatePower | None,
) -> bool:
    if ilo is not None and now - ilo.measured_at > timedelta(minutes=30):
        return True
    if measured is not None and now - measured.measured_at > timedelta(days=30):
        return True
    return False


def build_representative_power_results(
    *,
    now: datetime,
    racks: list[dict[str, object]],
    devices: list[dict[str, object]],
    ilo_by_device: dict[int, dict[str, object]],
    manual_device_by_device: dict[int, dict[str, object]],
    rack_measurements_by_rack: dict[int, dict[str, object]],
    phase_main_by_phase: dict[str, dict[str, object]],
    phase_basis: str = "max",
    overall_basis: str = "max",
) -> list[RepresentativePowerResult]:
    now = to_utc(now)
    device_results: list[RepresentativePowerResult] = []
    device_power_by_id: dict[int, DeviceRepresentativePower] = {}
    for device in devices:
        if device.get("active", True) is not True:
            continue
        device_id = int(device["id"])
        ilo_candidate = _candidate(
            ilo_by_device.get(device_id),
            watts_field="average_watts",
            quality_default="collected_ilo",
        )
        manual_candidate = _candidate(
            manual_device_by_device.get(device_id),
            watts_field="watts",
            quality_default="manual_measured",
        )
        representative = choose_device_representative(
            now=now,
            ilo=ilo_candidate,
            measured=manual_candidate,
            estimated=None,
            rated=None,
        )
        stale = representative.stale
        if representative.watts is None:
            stale = _has_stale_device_candidate(
                now,
                ilo=ilo_candidate,
                measured=manual_candidate,
            )
        device_power = DeviceRepresentativePower(
            device_id=device_id,
            watts=representative.watts,
            source=representative.source,
            stale=stale,
            active=True,
        )
        device_power_by_id[device_id] = device_power
        device_results.append(
            RepresentativePowerResult(
                entity_type="device",
                entity_id=device_id,
                watts=representative.watts,
                source=representative.source,
                stale=stale,
                unknown_count=1 if representative.watts is None else 0,
                stale_count=1 if stale else 0,
            )
        )

    devices_by_rack: dict[int, list[DeviceRepresentativePower]] = {}
    for device in devices:
        rack_id = int(device["rack_id"])
        device_id = int(device["id"])
        device_power = device_power_by_id.get(device_id)
        if device_power is None:
            device_power = DeviceRepresentativePower(
                device_id=device_id,
                watts=None,
                source="unknown",
                active=False,
            )
        devices_by_rack.setdefault(rack_id, []).append(device_power)

    active_racks = [rack for rack in racks if rack.get("active", True) is True]
    rack_results = [
        resolve_rack_representative(
            rack_id=int(rack["id"]),
            phase=str(rack["phase"]),
            rack_measurement=_candidate(
                rack_measurements_by_rack.get(int(rack["id"])),
                watts_field="watts",
                quality_default="manual_measured",
            ),
            devices=devices_by_rack.get(int(rack["id"]), []),
        )
        for rack in active_racks
    ]

    phase_main = {
        phase: _candidate(
            phase_main_by_phase.get(phase),
            watts_field="calculated_watts",
            quality_default="manual_measured",
        )
        for phase in ("R", "S", "T")
    }
    phase_results = [
        resolve_phase_representative(
            phase=phase,
            rack_results=rack_results,
            phase_main=phase_main,
            basis=phase_basis,
        )
        for phase in ("R", "S", "T")
    ]
    overall_result = resolve_overall_representative(
        rack_results=rack_results,
        phase_main=phase_main,
        basis=overall_basis,
    )
    return [*device_results, *rack_results, *phase_results, overall_result]


def _period_end(period: str, period_start: datetime) -> datetime:
    if period == "day":
        return period_start + timedelta(days=1)
    if period == "month":
        if period_start.month == 12:
            return period_start.replace(year=period_start.year + 1, month=1)
        return period_start.replace(month=period_start.month + 1)
    raise ValidationAppError("period must be one of day, month")


def _row_dict(row: PowerAggregateUpsert | dict[str, object]) -> dict[str, object]:
    if isinstance(row, PowerAggregateUpsert):
        return row.model_dump()
    return dict(row)


def _aggregate_group(
    rows: list[dict[str, object]],
    *,
    period: str,
    period_start: datetime,
) -> PowerAggregateUpsert:
    first = rows[0]
    total_samples = sum(int(row["sample_count"]) for row in rows)
    known_rows = [
        row
        for row in rows
        if row.get("avg_watts") is not None and int(row["sample_count"]) > 0
    ]
    avg_watts: Decimal | None = None
    min_watts: Decimal | None = None
    max_watts: Decimal | None = None
    if known_rows and total_samples > 0:
        weighted_total = Decimal("0")
        for row in known_rows:
            weighted_total += row["avg_watts"] * int(row["sample_count"])  # type: ignore[operator]
        avg_watts = weighted_total / Decimal(total_samples)
        min_values = [row["min_watts"] for row in known_rows if row.get("min_watts") is not None]
        max_values = [row["max_watts"] for row in known_rows if row.get("max_watts") is not None]
        min_watts = min(min_values) if min_values else None
        max_watts = max(max_values) if max_values else None

    coverage_total = Decimal("0")
    for row in rows:
        coverage_total += row["coverage_percent"]  # type: ignore[operator]

    return PowerAggregateUpsert(
        entity_type=str(first["entity_type"]),
        entity_id=int(first["entity_id"]),
        source_type=str(first["source_type"]),
        period=period,
        period_start=period_start,
        avg_watts=avg_watts,
        min_watts=min_watts,
        max_watts=max_watts,
        sample_count=total_samples,
        coverage_percent=coverage_total / Decimal(len(rows)),
        unknown_count=sum(int(row["unknown_count"]) for row in rows),
        stale_count=sum(int(row["stale_count"]) for row in rows),
    )


def build_hourly_power_aggregate_rows(
    *,
    period_start: datetime,
    results: list[RepresentativePowerResult],
) -> list[PowerAggregateUpsert]:
    ensure_aware(period_start)
    rows: list[PowerAggregateUpsert] = []
    for result in results:
        if result.entity_id is None:
            raise ValidationAppError("entity_id is required for power aggregate upsert")
        known = result.watts is not None and not result.stale
        rows.append(
            PowerAggregateUpsert(
                entity_type=result.entity_type,
                entity_id=result.entity_id,
                source_type=_source_type(result.source),
                period="hour",
                period_start=period_start,
                avg_watts=result.watts if known else None,
                min_watts=result.watts if known else None,
                max_watts=result.watts if known else None,
                sample_count=1 if known else 0,
                coverage_percent=Decimal("100") if known else Decimal("0"),
                unknown_count=result.unknown_count,
                stale_count=result.stale_count + (1 if result.stale else 0),
            )
        )
    return rows


def rollup_hourly_power_aggregate_rows(
    *,
    period: str,
    period_start: datetime,
    hourly_rows: list[PowerAggregateUpsert | dict[str, object]],
) -> list[PowerAggregateUpsert]:
    ensure_aware(period_start)
    end = _period_end(period, period_start)
    groups: dict[tuple[str, int, str], list[dict[str, object]]] = {}
    for hourly_row in hourly_rows:
        row = _row_dict(hourly_row)
        if row.get("period") != "hour":
            continue
        row_period_start = row.get("period_start")
        if not isinstance(row_period_start, datetime):
            raise ValidationAppError("period_start is required for power aggregate rollup")
        ensure_aware(row_period_start)
        if not period_start <= row_period_start < end:
            continue
        entity_id = row.get("entity_id")
        if entity_id is None:
            raise ValidationAppError("entity_id is required for power aggregate rollup")
        key = (str(row["entity_type"]), int(entity_id), str(row["source_type"]))
        groups.setdefault(key, []).append(row)

    return [
        _aggregate_group(rows, period=period, period_start=period_start)
        for rows in groups.values()
    ]


async def upsert_power_aggregate(
    session: AsyncSession,
    payload: PowerAggregateUpsert,
) -> dict[str, Any]:
    values = payload.model_dump()
    _validate_upsert_values(values)
    row = await aggregate_repo.upsert_power_aggregate(
        session,
        _with_timestamps(values, create=True),
    )
    await session.commit()
    return row


async def list_power_aggregates(
    session: AsyncSession,
    *,
    entity_type: str | None = None,
    entity_id: int | None = None,
    source_type: str | None = None,
    period: str | None = None,
    period_start_from: datetime | None = None,
    period_start_to: datetime | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    # TODO(Task 7.2): calculate and refresh aggregate rows from representative power inputs.
    return await aggregate_repo.list_power_aggregates(
        session,
        entity_type=entity_type,
        entity_id=entity_id,
        source_type=source_type,
        period=period,
        period_start_from=period_start_from,
        period_start_to=period_start_to,
        limit=limit,
    )


async def refresh_power_aggregates(
    session: AsyncSession,
    now: datetime | None = None,
    phase_basis: str = "max",
    overall_basis: str = "max",
) -> dict[str, object]:
    measured_at_to = to_utc(now or _now_utc())
    period_start = floor_to_hour(measured_at_to)
    racks = await rack_repo.list_racks(session)
    devices = await device_repo.list_devices(session)
    ilo_by_device = await ilo_repo.list_latest_power_samples_by_device(
        session,
        measured_at_to,
    )
    manual_device_by_device = await measurement_repo.list_latest_manual_device_power_by_device(
        session,
        measured_at_to,
    )
    rack_measurements_by_rack = await measurement_repo.list_latest_rack_measurements_by_rack(
        session,
        measured_at_to,
    )
    phase_main_by_phase = await measurement_repo.list_latest_phase_main_measurements_by_phase(
        session,
        measured_at_to,
    )

    results = build_representative_power_results(
        now=measured_at_to,
        racks=racks,
        devices=devices,
        ilo_by_device=ilo_by_device,
        manual_device_by_device=manual_device_by_device,
        rack_measurements_by_rack=rack_measurements_by_rack,
        phase_main_by_phase=phase_main_by_phase,
        phase_basis=phase_basis,
        overall_basis=overall_basis,
    )
    rows = build_hourly_power_aggregate_rows(period_start=period_start, results=results)
    upserted_count = 0
    for row in rows:
        await aggregate_repo.upsert_power_aggregate(
            session,
            _with_timestamps(row.model_dump(), create=True),
        )
        upserted_count += 1
    await session.commit()
    return {
        "status": "success",
        "period": "hour",
        "period_start": period_start,
        "upserted_count": upserted_count,
        "unknown_count": sum(result.unknown_count for result in results),
        "stale_count": sum(result.stale_count + (1 if result.stale else 0) for result in results),
        "skipped_count": sum(result.skipped_count for result in results),
    }
