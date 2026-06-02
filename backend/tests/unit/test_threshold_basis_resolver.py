from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.services import thresholds

NOW = datetime(2026, 5, 1, 12, tzinfo=UTC)


def _aggregate(
    *,
    entity_type: str,
    entity_id: int,
    source_type: str,
    avg_watts: Decimal | None,
) -> dict[str, object]:
    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "source_type": source_type,
        "period": "hour",
        "period_start": NOW,
        "avg_watts": avg_watts,
        "min_watts": avg_watts,
        "max_watts": avg_watts,
        "sample_count": 1 if avg_watts is not None else 0,
        "coverage_percent": Decimal("100") if avg_watts is not None else Decimal("0"),
        "unknown_count": 0,
        "stale_count": 0,
    }


def _threshold(target_type: str, target_id: int | None, basis: str) -> dict[str, object]:
    return {
        "id": 1,
        "target_type": target_type,
        "target_id": target_id,
        "basis": basis,
    }


def test_rack_and_device_thresholds_resolve_representative_aggregate_value() -> None:
    rows = [
        _aggregate(
            entity_type="rack",
            entity_id=10,
            source_type="representative",
            avg_watts=Decimal("125.250"),
        ),
        _aggregate(
            entity_type="device",
            entity_id=20,
            source_type="representative",
            avg_watts=Decimal("75.500"),
        ),
    ]

    rack = thresholds.resolve_threshold_basis_from_aggregates(
        _threshold("rack", 10, "avg_watts"),
        rows,
        evaluated_at=NOW,
    )
    device = thresholds.resolve_threshold_basis_from_aggregates(
        _threshold("device", 20, "avg_watts"),
        rows,
        evaluated_at=NOW,
    )

    assert rack.value == Decimal("125.250")
    assert rack.skipped is False
    assert device.value == Decimal("75.500")
    assert device.skipped is False


def test_rack_and_device_thresholds_resolve_persisted_representative_source_types() -> None:
    rows = [
        _aggregate(
            entity_type="rack",
            entity_id=10,
            source_type="rack_measured",
            avg_watts=Decimal("125.250"),
        ),
        _aggregate(
            entity_type="device",
            entity_id=20,
            source_type="device_manual",
            avg_watts=Decimal("75.500"),
        ),
        _aggregate(
            entity_type="device",
            entity_id=21,
            source_type="ilo",
            avg_watts=Decimal("90.250"),
        ),
    ]

    rack = thresholds.resolve_threshold_basis_from_aggregates(
        _threshold("rack", 10, "avg_watts"),
        rows,
        evaluated_at=NOW,
    )
    manual_device = thresholds.resolve_threshold_basis_from_aggregates(
        _threshold("device", 20, "avg_watts"),
        rows,
        evaluated_at=NOW,
    )
    ilo_device = thresholds.resolve_threshold_basis_from_aggregates(
        _threshold("device", 21, "avg_watts"),
        rows,
        evaluated_at=NOW,
    )

    assert rack.value == Decimal("125.250")
    assert rack.skipped is False
    assert manual_device.value == Decimal("75.500")
    assert manual_device.skipped is False
    assert ilo_device.value == Decimal("90.250")
    assert ilo_device.skipped is False


def test_phase_basis_supports_phase_main_rack_sum_max_and_default_max() -> None:
    rows = [
        _aggregate(
            entity_type="rack",
            entity_id=10,
            source_type="rack_measured",
            avg_watts=Decimal("100"),
        ),
        _aggregate(
            entity_type="rack",
            entity_id=11,
            source_type="representative",
            avg_watts=Decimal("250"),
        ),
        _aggregate(
            entity_type="phase",
            entity_id=1,
            source_type="phase_main",
            avg_watts=Decimal("300"),
        ),
    ]

    phase_main = thresholds.resolve_threshold_basis_from_aggregates(
        _threshold("phase", 1, "phase_main"),
        rows,
        evaluated_at=NOW,
    )
    rack_sum = thresholds.resolve_threshold_basis_from_aggregates(
        _threshold("phase", 1, "rack_sum"),
        rows,
        evaluated_at=NOW,
    )
    max_basis = thresholds.resolve_threshold_basis_from_aggregates(
        _threshold("phase", 1, "max"),
        rows,
        evaluated_at=NOW,
    )
    default_basis = thresholds.resolve_threshold_basis_from_aggregates(
        _threshold("phase", 1, "not-a-known-basis"),
        rows,
        evaluated_at=NOW,
    )

    assert phase_main.value == Decimal("300")
    assert rack_sum.value == Decimal("350")
    assert max_basis.value == Decimal("350")
    assert default_basis.value == max_basis.value


def test_overall_basis_supports_rack_sum_phase_main_sum_max_and_default_max() -> None:
    rows = [
        _aggregate(
            entity_type="rack",
            entity_id=10,
            source_type="rack_measured",
            avg_watts=Decimal("300"),
        ),
        _aggregate(
            entity_type="rack",
            entity_id=11,
            source_type="representative",
            avg_watts=Decimal("400"),
        ),
        _aggregate(
            entity_type="phase",
            entity_id=1,
            source_type="phase_main",
            avg_watts=Decimal("250"),
        ),
        _aggregate(
            entity_type="phase",
            entity_id=2,
            source_type="phase_main",
            avg_watts=Decimal("300"),
        ),
        _aggregate(
            entity_type="phase",
            entity_id=3,
            source_type="phase_main",
            avg_watts=Decimal("250"),
        ),
    ]

    rack_sum = thresholds.resolve_threshold_basis_from_aggregates(
        _threshold("overall", 0, "rack_sum"),
        rows,
        evaluated_at=NOW,
    )
    phase_main_sum = thresholds.resolve_threshold_basis_from_aggregates(
        _threshold("overall", 0, "phase_main_sum"),
        rows,
        evaluated_at=NOW,
    )
    max_basis = thresholds.resolve_threshold_basis_from_aggregates(
        _threshold("overall", 0, "max"),
        rows,
        evaluated_at=NOW,
    )
    default_basis = thresholds.resolve_threshold_basis_from_aggregates(
        _threshold("overall", 0, "unknown"),
        rows,
        evaluated_at=NOW,
    )

    assert rack_sum.value == Decimal("700")
    assert phase_main_sum.value == Decimal("800")
    assert max_basis.value == Decimal("800")
    assert default_basis.value == max_basis.value


def test_missing_basis_value_returns_skipped_resolution_not_normal_clear() -> None:
    result = thresholds.resolve_threshold_basis_from_aggregates(
        _threshold("rack", 10, "avg_watts"),
        [],
        evaluated_at=NOW,
    )

    assert result.value is None
    assert result.skipped is True


def test_threshold_basis_resolution_rejects_naive_evaluated_at() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        thresholds.resolve_threshold_basis_from_aggregates(
            _threshold("rack", 10, "avg_watts"),
            [],
            evaluated_at=datetime(2026, 5, 1, 12),
        )
