from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.errors import ValidationAppError
from app.schemas.measurements import PhaseMainMeasurementUpdate, RackMeasurementUpdate
from app.services.measurements import derive_watts_and_quality
from app.services.power_calculations import calculate_single_phase_watts, validate_watts_tolerance


def test_calculate_single_phase_watts() -> None:
    result = calculate_single_phase_watts(
        voltage=Decimal("220"),
        amp=Decimal("10"),
        power_factor=Decimal("0.95"),
    )

    assert result == Decimal("2090.00")


def test_validate_watts_tolerance_accepts_within_default_tolerance() -> None:
    result = validate_watts_tolerance(
        entered_watts=Decimal("2100"),
        calculated_watts=Decimal("2090"),
    )

    assert result.is_valid is True
    assert result.warning is None


def test_validate_watts_tolerance_warns_outside_default_tolerance() -> None:
    result = validate_watts_tolerance(
        entered_watts=Decimal("3000"),
        calculated_watts=Decimal("2090"),
    )

    assert result.is_valid is False
    assert result.warning == "WATTS_TOLERANCE_EXCEEDED"


def test_derive_watts_and_quality_calculates_with_default_pf() -> None:
    watts, quality, warning = derive_watts_and_quality(
        watts=None,
        voltage=Decimal("220"),
        amp=Decimal("10"),
        power_factor=Decimal("0.95"),
        voltage_source="default",
        power_factor_source="default",
    )

    assert watts == Decimal("2090.00")
    assert quality == "calculated_with_default_pf"
    assert warning is None


def test_derive_watts_and_quality_marks_watts_only_input_as_measured() -> None:
    watts, quality, warning = derive_watts_and_quality(
        watts=Decimal("500"),
        voltage=None,
        amp=None,
        power_factor=None,
        voltage_source="default",
        power_factor_source="default",
    )

    assert watts == Decimal("500")
    assert quality == "measured_watts"
    assert warning is None


def test_derive_watts_and_quality_keeps_entered_watts_as_measured_when_cross_checked() -> None:
    watts, quality, warning = derive_watts_and_quality(
        watts=Decimal("2100"),
        voltage=Decimal("220"),
        amp=Decimal("10"),
        power_factor=Decimal("0.95"),
        voltage_source="default",
        power_factor_source="default",
    )

    assert watts == Decimal("2100")
    assert quality == "measured_watts"
    assert warning is None


def test_derive_watts_and_quality_requires_confirmation_for_large_mismatch() -> None:
    with pytest.raises(ValidationAppError, match="watts tolerance exceeded"):
        derive_watts_and_quality(
            watts=Decimal("3000"),
            voltage=Decimal("220"),
            amp=Decimal("10"),
            power_factor=Decimal("0.95"),
            voltage_source="meter",
            power_factor_source="meter",
            confirmed=False,
        )


def test_derive_watts_and_quality_returns_warning_when_confirmed() -> None:
    watts, quality, warning = derive_watts_and_quality(
        watts=Decimal("3000"),
        voltage=Decimal("220"),
        amp=Decimal("10"),
        power_factor=Decimal("0.95"),
        voltage_source="meter",
        power_factor_source="meter",
        confirmed=True,
    )

    assert watts == Decimal("3000")
    assert quality == "measured_watts"
    assert warning is not None
    assert warning["code"] == "WATTS_TOLERANCE_EXCEEDED"


def test_derive_watts_and_quality_preserves_estimated_and_rated_quality() -> None:
    estimated = derive_watts_and_quality(
        watts=Decimal("700"),
        voltage=None,
        amp=None,
        power_factor=None,
        voltage_source="manual",
        power_factor_source="manual",
        value_type="estimated",
    )
    rated = derive_watts_and_quality(
        watts=Decimal("900"),
        voltage=None,
        amp=None,
        power_factor=None,
        voltage_source="manual",
        power_factor_source="manual",
        value_type="rated",
    )

    assert estimated == (Decimal("700"), "estimated", None)
    assert rated == (Decimal("900"), "rated", None)


def test_phase_main_update_schema_allows_only_phase_main_fields() -> None:
    payload = PhaseMainMeasurementUpdate(
        phase="R",
        measurement_point="phase_branch",
        amp=Decimal("80"),
        note="main branch measurement",
    )

    assert payload.amp == Decimal("80")


def test_phase_main_update_schema_rejects_rack_device_power_fields() -> None:
    with pytest.raises(ValidationError):
        PhaseMainMeasurementUpdate(
            amp=Decimal("80"),
            watts=Decimal("1000"),
            power_factor=Decimal("0.95"),
        )


def test_rack_update_schema_rejects_phase_field() -> None:
    with pytest.raises(ValidationError):
        RackMeasurementUpdate(phase="R", amp=Decimal("10"))
