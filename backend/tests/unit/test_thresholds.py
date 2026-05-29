from decimal import Decimal

from app.services.thresholds import evaluate_threshold


def test_threshold_moves_to_critical_after_trigger_count() -> None:
    state = evaluate_threshold(
        value=Decimal("120"),
        warning_watts=Decimal("100"),
        critical_watts=Decimal("110"),
        current_state="normal",
        consecutive_trigger_count=0,
        consecutive_clear_count=0,
        trigger_count=1,
        clear_count=2,
    )

    assert state.current_state == "critical"
    assert state.consecutive_trigger_count == 1


def test_threshold_requires_clear_count_to_return_normal() -> None:
    first = evaluate_threshold(
        value=Decimal("90"),
        warning_watts=Decimal("100"),
        critical_watts=Decimal("110"),
        current_state="critical",
        consecutive_trigger_count=1,
        consecutive_clear_count=0,
        trigger_count=1,
        clear_count=2,
    )
    second = evaluate_threshold(
        value=Decimal("90"),
        warning_watts=Decimal("100"),
        critical_watts=Decimal("110"),
        current_state=first.current_state,
        consecutive_trigger_count=first.consecutive_trigger_count,
        consecutive_clear_count=first.consecutive_clear_count,
        trigger_count=1,
        clear_count=2,
    )

    assert first.current_state == "critical"
    assert second.current_state == "normal"
