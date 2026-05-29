from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from app.schemas.measurements import PhaseMainMeasurementUpdate
from app.services import measurements as measurement_service


@pytest.mark.asyncio
async def test_update_phase_main_measurement_recalculates_watts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_get_measurement(
        _session: object,
        measurement_type: str,
        measurement_id: int,
    ) -> dict[str, Any]:
        assert measurement_type == "phase-main"
        assert measurement_id == 10
        return {
            "id": 10,
            "amp": Decimal("70"),
            "voltage_default_used": Decimal("220"),
            "power_factor_default_used": Decimal("0.95"),
            "calculated_watts": Decimal("14630.00"),
            "measured_at": datetime(2026, 5, 29, 0, 0, tzinfo=UTC),
        }

    async def fake_update_measurement(
        _session: object,
        measurement_type: str,
        measurement_id: int,
        values: dict[str, object],
    ) -> dict[str, object]:
        captured["measurement_type"] = measurement_type
        captured["measurement_id"] = measurement_id
        captured["values"] = values
        return values

    async def fake_commit() -> None:
        captured["committed"] = True

    class FakeSession:
        commit = staticmethod(fake_commit)

    monkeypatch.setattr(
        measurement_service.measurement_repo,
        "get_measurement",
        fake_get_measurement,
    )
    monkeypatch.setattr(
        measurement_service.measurement_repo,
        "update_measurement",
        fake_update_measurement,
    )

    result = await measurement_service.update_phase_main_measurement(
        FakeSession(),
        measurement_id=10,
        payload=PhaseMainMeasurementUpdate(amp=Decimal("80")),
    )

    assert result["calculated_watts"] == Decimal("16720.00")
    assert captured["measurement_type"] == "phase-main"
    assert captured["measurement_id"] == 10
    assert captured["values"]["amp"] == Decimal("80")
    assert captured["values"]["quality"] == "calculated_with_default_pf"
    assert captured["committed"] is True
