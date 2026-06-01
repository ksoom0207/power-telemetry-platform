from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.services import representative_power as rp
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


def test_rack_representative_prefers_rack_measured_value_over_device_sum() -> None:
    result = rp.resolve_rack_representative(
        rack_id=10,
        phase="R",
        rack_measurement=CandidatePower(
            Decimal("500"),
            NOW - timedelta(minutes=5),
            "measured_watts",
        ),
        devices=[
            rp.DeviceRepresentativePower(device_id=1, watts=Decimal("100"), source="ilo"),
            rp.DeviceRepresentativePower(
                device_id=2,
                watts=Decimal("200"),
                source="manual_measured",
            ),
        ],
    )

    assert result.entity_type == "rack"
    assert result.entity_id == 10
    assert result.phase == "R"
    assert result.watts == Decimal("500")
    assert result.source == "rack_measured"
    assert result.unknown_count == 0
    assert result.stale_count == 0


def test_rack_representative_falls_back_to_active_device_sum() -> None:
    result = rp.resolve_rack_representative(
        rack_id=10,
        phase="S",
        rack_measurement=None,
        devices=[
            rp.DeviceRepresentativePower(device_id=1, watts=Decimal("100"), source="ilo"),
            rp.DeviceRepresentativePower(
                device_id=2,
                watts=Decimal("200"),
                source="manual_measured",
            ),
            rp.DeviceRepresentativePower(
                device_id=3,
                watts=Decimal("999"),
                source="rated",
                active=False,
            ),
        ],
    )

    assert result.watts == Decimal("300")
    assert result.source == "representative"
    assert result.skipped_count == 1


def test_rack_representative_counts_stale_unknown_and_skipped_devices() -> None:
    result = rp.resolve_rack_representative(
        rack_id=10,
        phase="T",
        rack_measurement=None,
        devices=[
            rp.DeviceRepresentativePower(device_id=1, watts=Decimal("100"), source="ilo"),
            rp.DeviceRepresentativePower(device_id=2, watts=None, source="unknown"),
            rp.DeviceRepresentativePower(
                device_id=3,
                watts=Decimal("200"),
                source="ilo",
                stale=True,
            ),
            rp.DeviceRepresentativePower(
                device_id=4,
                watts=Decimal("300"),
                source="rated",
                active=False,
            ),
        ],
    )

    assert result.watts == Decimal("100")
    assert result.unknown_count == 1
    assert result.stale_count == 1
    assert result.skipped_count == 1


def test_phase_basis_resolver_supports_phase_main_rack_sum_max_and_default() -> None:
    racks = [
        rp.RepresentativePowerResult(
            entity_type="rack",
            entity_id=10,
            watts=Decimal("100"),
            source="representative",
            phase="R",
        ),
        rp.RepresentativePowerResult(
            entity_type="rack",
            entity_id=11,
            watts=Decimal("250"),
            source="rack_measured",
            phase="R",
        ),
    ]
    phase_main = {"R": CandidatePower(Decimal("300"), NOW, "phase_main")}

    by_phase_main = rp.resolve_phase_representative(
        phase="R",
        rack_results=racks,
        phase_main=phase_main,
        basis="phase_main",
    )
    by_rack_sum = rp.resolve_phase_representative(
        phase="R",
        rack_results=racks,
        phase_main=phase_main,
        basis="rack_sum",
    )
    by_max = rp.resolve_phase_representative(
        phase="R",
        rack_results=racks,
        phase_main=phase_main,
        basis="max",
    )
    by_default = rp.resolve_phase_representative(
        phase="R",
        rack_results=racks,
        phase_main=phase_main,
    )

    assert by_phase_main.watts == Decimal("300")
    assert by_phase_main.source == "phase_main"
    assert by_rack_sum.watts == Decimal("350")
    assert by_rack_sum.source == "representative"
    assert by_max.watts == Decimal("350")
    assert by_default.watts == by_max.watts


def test_overall_basis_resolver_supports_rack_sum_phase_main_sum_max_and_default() -> None:
    racks = [
        rp.RepresentativePowerResult(
            entity_type="rack",
            entity_id=10,
            watts=Decimal("300"),
            source="representative",
            phase="R",
        ),
        rp.RepresentativePowerResult(
            entity_type="rack",
            entity_id=11,
            watts=Decimal("400"),
            source="representative",
            phase="S",
        ),
    ]
    phase_main = {
        "R": CandidatePower(Decimal("250"), NOW, "phase_main"),
        "S": CandidatePower(Decimal("300"), NOW, "phase_main"),
        "T": CandidatePower(Decimal("250"), NOW, "phase_main"),
    }

    by_rack_sum = rp.resolve_overall_representative(
        rack_results=racks,
        phase_main=phase_main,
        basis="rack_sum",
    )
    by_phase_main_sum = rp.resolve_overall_representative(
        rack_results=racks,
        phase_main=phase_main,
        basis="phase_main_sum",
    )
    by_max = rp.resolve_overall_representative(
        rack_results=racks,
        phase_main=phase_main,
        basis="max",
    )
    by_default = rp.resolve_overall_representative(rack_results=racks, phase_main=phase_main)

    assert by_rack_sum.watts == Decimal("700")
    assert by_rack_sum.source == "representative"
    assert by_phase_main_sum.watts == Decimal("800")
    assert by_phase_main_sum.source == "phase_main"
    assert by_max.watts == Decimal("800")
    assert by_default.watts == by_max.watts


def test_overall_phase_main_sum_requires_complete_rst_measurements() -> None:
    phase_main = {
        "R": CandidatePower(Decimal("100"), NOW, "phase_main"),
    }

    by_phase_main_sum = rp.resolve_overall_representative(
        rack_results=[],
        phase_main=phase_main,
        basis="phase_main_sum",
    )
    by_default = rp.resolve_overall_representative(
        rack_results=[],
        phase_main=phase_main,
    )

    assert by_phase_main_sum.watts is None
    assert by_phase_main_sum.source == "unknown"
    assert by_phase_main_sum.unknown_count == 2
    assert by_default.watts is None
    assert by_default.source == "unknown"
    assert by_default.unknown_count == 2


def test_overall_phase_main_sum_reports_single_missing_phase() -> None:
    phase_main = {
        "R": CandidatePower(Decimal("100"), NOW, "phase_main"),
        "S": CandidatePower(Decimal("200"), NOW, "phase_main"),
    }

    result = rp.resolve_overall_representative(
        rack_results=[],
        phase_main=phase_main,
        basis="phase_main_sum",
    )

    assert result.watts is None
    assert result.source == "unknown"
    assert result.unknown_count == 1


def test_phase_and_overall_entity_id_mapping_is_explicit() -> None:
    phase_main = {
        "R": CandidatePower(Decimal("100"), NOW, "phase_main"),
        "S": CandidatePower(Decimal("200"), NOW, "phase_main"),
        "T": CandidatePower(Decimal("300"), NOW, "phase_main"),
    }

    r_phase = rp.resolve_phase_representative(phase="R", rack_results=[], phase_main=phase_main)
    s_phase = rp.resolve_phase_representative(phase="S", rack_results=[], phase_main=phase_main)
    t_phase = rp.resolve_phase_representative(phase="T", rack_results=[], phase_main=phase_main)
    overall = rp.resolve_overall_representative(rack_results=[], phase_main=phase_main)

    assert (r_phase.entity_type, r_phase.entity_id) == ("phase", 1)
    assert (s_phase.entity_type, s_phase.entity_id) == ("phase", 2)
    assert (t_phase.entity_type, t_phase.entity_id) == ("phase", 3)
    assert (overall.entity_type, overall.entity_id) == ("overall", 0)
