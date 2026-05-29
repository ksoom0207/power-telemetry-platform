from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ToleranceResult:
    is_valid: bool
    warning: str | None
    difference: Decimal
    tolerance: Decimal


def calculate_single_phase_watts(
    *,
    voltage: Decimal,
    amp: Decimal,
    power_factor: Decimal,
) -> Decimal:
    return voltage * amp * power_factor


def validate_watts_tolerance(
    *,
    entered_watts: Decimal,
    calculated_watts: Decimal,
    percent: Decimal = Decimal("0.10"),
    minimum_watts: Decimal = Decimal("100"),
) -> ToleranceResult:
    difference = abs(entered_watts - calculated_watts)
    tolerance = max(abs(entered_watts) * percent, minimum_watts)
    if difference > tolerance:
        return ToleranceResult(
            is_valid=False,
            warning="WATTS_TOLERANCE_EXCEEDED",
            difference=difference,
            tolerance=tolerance,
        )
    return ToleranceResult(is_valid=True, warning=None, difference=difference, tolerance=tolerance)
