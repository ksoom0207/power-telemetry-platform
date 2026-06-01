from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from app.core.datetime import ensure_aware

PHASE_ENTITY_IDS = {"R": 1, "S": 2, "T": 3}
OVERALL_ENTITY_ID = 0


@dataclass(frozen=True)
class CandidatePower:
    watts: Decimal
    measured_at: datetime
    quality: str


@dataclass(frozen=True)
class RepresentativePower:
    watts: Decimal | None
    source: str
    stale: bool


@dataclass(frozen=True)
class DeviceRepresentativePower:
    device_id: int
    watts: Decimal | None
    source: str
    stale: bool = False
    active: bool = True
    measured_at: datetime | None = None


@dataclass(frozen=True)
class RepresentativePowerResult:
    entity_type: str
    entity_id: int
    watts: Decimal | None
    source: str
    stale: bool = False
    phase: str | None = None
    unknown_count: int = 0
    stale_count: int = 0
    skipped_count: int = 0


def _is_fresh(now: datetime, candidate: CandidatePower, max_age: timedelta) -> bool:
    ensure_aware(now)
    ensure_aware(candidate.measured_at)
    return now - candidate.measured_at <= max_age


def _ensure_candidate_datetimes(*candidates: CandidatePower | None) -> None:
    for candidate in candidates:
        if candidate is not None:
            ensure_aware(candidate.measured_at)


def _ensure_device_datetimes(devices: list[DeviceRepresentativePower]) -> None:
    for device in devices:
        if device.measured_at is not None:
            ensure_aware(device.measured_at)


def _validate_phase(phase: str) -> None:
    if phase not in PHASE_ENTITY_IDS:
        raise ValueError("phase must be one of R, S, T")


def _candidate_for_phase(
    phase: str,
    phase_main: dict[str, CandidatePower | None],
) -> CandidatePower | None:
    candidate = phase_main.get(phase)
    _ensure_candidate_datetimes(candidate)
    return candidate


def _known_decimal_sum(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    total = Decimal("0")
    for value in values:
        total += value
    return total


def _sum_rack_results(
    rack_results: list[RepresentativePowerResult],
    *,
    phase: str | None = None,
) -> tuple[Decimal | None, int, int, int]:
    values: list[Decimal] = []
    unknown_count = 0
    stale_count = 0
    skipped_count = 0
    for result in rack_results:
        if result.entity_type != "rack":
            continue
        if phase is not None and result.phase != phase:
            continue
        unknown_count += result.unknown_count
        stale_count += result.stale_count
        skipped_count += result.skipped_count
        if result.stale:
            stale_count += 1
            continue
        if result.watts is None:
            unknown_count += 1
            continue
        values.append(result.watts)
    return _known_decimal_sum(values), unknown_count, stale_count, skipped_count


def _phase_main_sum(
    phase_main: dict[str, CandidatePower | None],
) -> tuple[Decimal | None, int]:
    values: list[Decimal] = []
    unknown_count = 0
    for phase in PHASE_ENTITY_IDS:
        candidate = _candidate_for_phase(phase, phase_main)
        if candidate is None:
            unknown_count += 1
            continue
        values.append(candidate.watts)
    if unknown_count:
        return None, unknown_count
    return _known_decimal_sum(values), 0


def _unknown_result(
    entity_type: str,
    entity_id: int,
    *,
    phase: str | None = None,
) -> RepresentativePowerResult:
    return RepresentativePowerResult(
        entity_type=entity_type,
        entity_id=entity_id,
        watts=None,
        source="unknown",
        phase=phase,
        unknown_count=1,
    )


def choose_device_representative(
    *,
    now: datetime,
    ilo: CandidatePower | None,
    measured: CandidatePower | None,
    estimated: CandidatePower | None,
    rated: CandidatePower | None,
    ilo_freshness: timedelta = timedelta(minutes=30),
    measured_freshness: timedelta = timedelta(days=30),
) -> RepresentativePower:
    ensure_aware(now)
    _ensure_candidate_datetimes(ilo, measured, estimated, rated)
    if ilo and _is_fresh(now, ilo, ilo_freshness):
        return RepresentativePower(watts=ilo.watts, source="ilo", stale=False)
    if measured and _is_fresh(now, measured, measured_freshness):
        return RepresentativePower(watts=measured.watts, source="manual_measured", stale=False)
    if estimated:
        return RepresentativePower(watts=estimated.watts, source="estimated", stale=False)
    if rated:
        return RepresentativePower(watts=rated.watts, source="rated", stale=False)
    return RepresentativePower(watts=None, source="unknown", stale=False)


def resolve_rack_representative(
    *,
    rack_id: int,
    phase: str,
    rack_measurement: CandidatePower | None,
    devices: list[DeviceRepresentativePower],
) -> RepresentativePowerResult:
    _validate_phase(phase)
    _ensure_candidate_datetimes(rack_measurement)
    _ensure_device_datetimes(devices)
    if rack_measurement is not None:
        return RepresentativePowerResult(
            entity_type="rack",
            entity_id=rack_id,
            watts=rack_measurement.watts,
            source="rack_measured",
            phase=phase,
        )

    values: list[Decimal] = []
    unknown_count = 0
    stale_count = 0
    skipped_count = 0
    for device in devices:
        if not device.active:
            skipped_count += 1
            continue
        if device.stale:
            stale_count += 1
            continue
        if device.watts is None:
            unknown_count += 1
            continue
        values.append(device.watts)

    watts = _known_decimal_sum(values)
    if watts is None:
        return RepresentativePowerResult(
            entity_type="rack",
            entity_id=rack_id,
            watts=None,
            source="unknown",
            phase=phase,
            unknown_count=unknown_count or 1,
            stale_count=stale_count,
            skipped_count=skipped_count,
        )
    return RepresentativePowerResult(
        entity_type="rack",
        entity_id=rack_id,
        watts=watts,
        source="representative",
        phase=phase,
        unknown_count=unknown_count,
        stale_count=stale_count,
        skipped_count=skipped_count,
    )


def resolve_phase_representative(
    *,
    phase: str,
    rack_results: list[RepresentativePowerResult],
    phase_main: dict[str, CandidatePower | None],
    basis: str = "max",
) -> RepresentativePowerResult:
    _validate_phase(phase)
    if basis not in {"phase_main", "rack_sum", "max"}:
        raise ValueError("basis must be one of phase_main, rack_sum, max")

    phase_candidate = _candidate_for_phase(phase, phase_main)
    rack_sum, unknown_count, stale_count, skipped_count = _sum_rack_results(
        rack_results,
        phase=phase,
    )
    phase_watts = phase_candidate.watts if phase_candidate is not None else None
    entity_id = PHASE_ENTITY_IDS[phase]

    if basis == "phase_main":
        if phase_watts is None:
            return _unknown_result("phase", entity_id, phase=phase)
        return RepresentativePowerResult(
            entity_type="phase",
            entity_id=entity_id,
            watts=phase_watts,
            source="phase_main",
            phase=phase,
        )

    if basis == "rack_sum":
        if rack_sum is None:
            return RepresentativePowerResult(
                entity_type="phase",
                entity_id=entity_id,
                watts=None,
                source="unknown",
                phase=phase,
                unknown_count=unknown_count or 1,
                stale_count=stale_count,
                skipped_count=skipped_count,
            )
        return RepresentativePowerResult(
            entity_type="phase",
            entity_id=entity_id,
            watts=rack_sum,
            source="representative",
            phase=phase,
            unknown_count=unknown_count,
            stale_count=stale_count,
            skipped_count=skipped_count,
        )

    if phase_watts is None and rack_sum is None:
        return RepresentativePowerResult(
            entity_type="phase",
            entity_id=entity_id,
            watts=None,
            source="unknown",
            phase=phase,
            unknown_count=unknown_count or 1,
            stale_count=stale_count,
            skipped_count=skipped_count,
        )
    if rack_sum is None or (phase_watts is not None and phase_watts >= rack_sum):
        return RepresentativePowerResult(
            entity_type="phase",
            entity_id=entity_id,
            watts=phase_watts,
            source="phase_main",
            phase=phase,
        )
    return RepresentativePowerResult(
        entity_type="phase",
        entity_id=entity_id,
        watts=rack_sum,
        source="representative",
        phase=phase,
        unknown_count=unknown_count,
        stale_count=stale_count,
        skipped_count=skipped_count,
    )


def resolve_overall_representative(
    *,
    rack_results: list[RepresentativePowerResult],
    phase_main: dict[str, CandidatePower | None],
    basis: str = "max",
) -> RepresentativePowerResult:
    if basis not in {"rack_sum", "phase_main_sum", "max"}:
        raise ValueError("basis must be one of rack_sum, phase_main_sum, max")

    rack_sum, unknown_count, stale_count, skipped_count = _sum_rack_results(rack_results)
    main_sum, phase_main_unknown_count = _phase_main_sum(phase_main)

    if basis == "rack_sum":
        if rack_sum is None:
            return RepresentativePowerResult(
                entity_type="overall",
                entity_id=OVERALL_ENTITY_ID,
                watts=None,
                source="unknown",
                unknown_count=unknown_count or 1,
                stale_count=stale_count,
                skipped_count=skipped_count,
            )
        return RepresentativePowerResult(
            entity_type="overall",
            entity_id=OVERALL_ENTITY_ID,
            watts=rack_sum,
            source="representative",
            unknown_count=unknown_count,
            stale_count=stale_count,
            skipped_count=skipped_count,
        )

    if basis == "phase_main_sum":
        if main_sum is None:
            return RepresentativePowerResult(
                entity_type="overall",
                entity_id=OVERALL_ENTITY_ID,
                watts=None,
                source="unknown",
                unknown_count=phase_main_unknown_count or 1,
            )
        return RepresentativePowerResult(
            entity_type="overall",
            entity_id=OVERALL_ENTITY_ID,
            watts=main_sum,
            source="phase_main",
        )

    if rack_sum is None and main_sum is None:
        return RepresentativePowerResult(
            entity_type="overall",
            entity_id=OVERALL_ENTITY_ID,
            watts=None,
            source="unknown",
            unknown_count=unknown_count + phase_main_unknown_count or 1,
            stale_count=stale_count,
            skipped_count=skipped_count,
        )
    if rack_sum is None or (main_sum is not None and main_sum >= rack_sum):
        return RepresentativePowerResult(
            entity_type="overall",
            entity_id=OVERALL_ENTITY_ID,
            watts=main_sum,
            source="phase_main",
        )
    return RepresentativePowerResult(
        entity_type="overall",
        entity_id=OVERALL_ENTITY_ID,
        watts=rack_sum,
        source="representative",
        unknown_count=unknown_count,
        stale_count=stale_count,
        skipped_count=skipped_count,
    )
