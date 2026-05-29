from decimal import Decimal

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
