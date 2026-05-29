from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ThresholdEvaluation:
    current_state: str
    consecutive_trigger_count: int
    consecutive_clear_count: int


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
