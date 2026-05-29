from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.services.representative_power import CandidatePower, choose_device_representative

NOW = datetime(2026, 5, 29, 12, 0, tzinfo=UTC)


def test_device_representative_prefers_fresh_ilo() -> None:
    result = choose_device_representative(
        now=NOW,
        ilo=CandidatePower(Decimal("300"), NOW - timedelta(minutes=5), "collected_ilo"),
        measured=CandidatePower(Decimal("310"), NOW - timedelta(days=1), "measured_watts"),
        estimated=CandidatePower(Decimal("320"), NOW - timedelta(days=10), "estimated"),
        rated=CandidatePower(Decimal("400"), NOW - timedelta(days=100), "rated"),
    )

    assert result.watts == Decimal("300")
    assert result.source == "ilo"


def test_device_representative_ignores_stale_ilo() -> None:
    result = choose_device_representative(
        now=NOW,
        ilo=CandidatePower(Decimal("300"), NOW - timedelta(hours=2), "collected_ilo"),
        measured=CandidatePower(Decimal("310"), NOW - timedelta(days=1), "measured_watts"),
        estimated=None,
        rated=None,
    )

    assert result.watts == Decimal("310")
    assert result.source == "manual_measured"


def test_device_representative_uses_estimated_before_rated() -> None:
    result = choose_device_representative(
        now=NOW,
        ilo=None,
        measured=None,
        estimated=CandidatePower(Decimal("320"), NOW - timedelta(days=10), "estimated"),
        rated=CandidatePower(Decimal("400"), NOW - timedelta(days=100), "rated"),
    )

    assert result.watts == Decimal("320")
    assert result.source == "estimated"


def test_device_representative_rejects_naive_now() -> None:
    naive_now = datetime(2026, 5, 29, 12, 0)

    try:
        choose_device_representative(
            now=naive_now,
            ilo=None,
            measured=None,
            estimated=None,
            rated=None,
        )
    except ValueError as exc:
        assert "timezone-aware" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_device_representative_rejects_naive_candidate() -> None:
    try:
        choose_device_representative(
            now=NOW,
            ilo=None,
            measured=None,
            estimated=CandidatePower(Decimal("320"), datetime(2026, 5, 29, 12, 0), "estimated"),
            rated=None,
        )
    except ValueError as exc:
        assert "timezone-aware" in str(exc)
    else:
        raise AssertionError("expected ValueError")
