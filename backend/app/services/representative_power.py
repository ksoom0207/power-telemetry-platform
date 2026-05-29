from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from app.core.datetime import ensure_aware


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


def _is_fresh(now: datetime, candidate: CandidatePower, max_age: timedelta) -> bool:
    ensure_aware(now)
    ensure_aware(candidate.measured_at)
    return now - candidate.measured_at <= max_age


def _ensure_candidate_datetimes(*candidates: CandidatePower | None) -> None:
    for candidate in candidates:
        if candidate is not None:
            ensure_aware(candidate.measured_at)


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
