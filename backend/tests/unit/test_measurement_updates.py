from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from app.core.errors import ValidationAppError
from app.schemas.measurements import (
    DevicePowerMeasurementUpdate,
    PhaseMainMeasurementUpdate,
    RackMeasurementUpdate,
)
from app.services import measurements as measurement_service


class FakeSession:
    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> None:
        self.committed = True


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

    session = FakeSession()
    result = await measurement_service.update_phase_main_measurement(
        session,
        measurement_id=10,
        payload=PhaseMainMeasurementUpdate(amp=Decimal("80")),
    )

    assert result["calculated_watts"] == Decimal("16720.00")
    assert captured["measurement_type"] == "phase-main"
    assert captured["measurement_id"] == 10
    assert captured["values"]["amp"] == Decimal("80")
    assert captured["values"]["quality"] == "calculated_with_default_pf"
    assert session.committed is True


@pytest.mark.asyncio
async def test_update_rack_measurement_recalculates_when_amps_change_without_watts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_get_measurement(
        _session: object,
        measurement_type: str,
        measurement_id: int,
    ) -> dict[str, Any]:
        assert measurement_type == "rack"
        assert measurement_id == 20
        return {
            "id": 20,
            "watts": Decimal("5000"),
            "voltage": Decimal("220"),
            "amp": Decimal("10"),
            "power_factor": Decimal("0.95"),
            "voltage_source": "default",
            "power_factor_source": "default",
            "quality": "measured_watts",
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
        return {"id": measurement_id, **values}

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

    session = FakeSession()
    result = await measurement_service.update_rack_measurement(
        session,
        measurement_id=20,
        payload=RackMeasurementUpdate(amp=Decimal("12")),
    )

    assert result["row"]["watts"] == Decimal("2508.00")
    assert result["row"]["quality"] == "calculated_with_default_pf"
    assert result["warnings"] == []
    assert captured["values"]["watts"] == Decimal("2508.00")
    assert captured["values"]["quality"] == "calculated_with_default_pf"
    assert session.committed is True


@pytest.mark.asyncio
async def test_update_device_power_measurement_recalculates_when_voltage_changes_without_watts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_get_measurement(
        _session: object,
        measurement_type: str,
        measurement_id: int,
    ) -> dict[str, Any]:
        assert measurement_type == "device-power"
        assert measurement_id == 30
        return {
            "id": 30,
            "watts": Decimal("5000"),
            "voltage": Decimal("220"),
            "amp": Decimal("10"),
            "power_factor": Decimal("0.95"),
            "voltage_source": "default",
            "power_factor_source": "default",
            "value_type": "measured",
            "quality": "measured_watts",
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
        return {"id": measurement_id, **values}

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

    result = await measurement_service.update_device_power_measurement(
        FakeSession(),
        measurement_id=30,
        payload=DevicePowerMeasurementUpdate(voltage=Decimal("230")),
    )

    assert result["row"]["watts"] == Decimal("2185.00")
    assert result["row"]["quality"] == "calculated_with_default_pf"
    assert result["warnings"] == []
    assert captured["values"]["watts"] == Decimal("2185.00")


@pytest.mark.asyncio
async def test_update_rack_measurement_preserves_power_fields_for_note_only_patch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_get_measurement(
        _session: object,
        measurement_type: str,
        measurement_id: int,
    ) -> dict[str, Any]:
        return {
            "id": measurement_id,
            "watts": Decimal("2090.00"),
            "voltage": Decimal("220"),
            "amp": Decimal("10"),
            "power_factor": Decimal("0.95"),
            "voltage_source": "default",
            "power_factor_source": "default",
            "quality": "calculated_with_default_pf",
        }

    async def fake_update_measurement(
        _session: object,
        measurement_type: str,
        measurement_id: int,
        values: dict[str, object],
    ) -> dict[str, object]:
        captured["values"] = values
        return {"id": measurement_id, **values}

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

    result = await measurement_service.update_rack_measurement(
        FakeSession(),
        measurement_id=40,
        payload=RackMeasurementUpdate(note="checked"),
    )

    assert result["row"]["watts"] == Decimal("2090.00")
    assert result["row"]["quality"] == "calculated_with_default_pf"
    assert result["warnings"] == []
    assert captured["values"]["note"] == "checked"
    assert captured["values"]["watts"] == Decimal("2090.00")
    assert captured["values"]["quality"] == "calculated_with_default_pf"


@pytest.mark.asyncio
async def test_update_device_power_measurement_returns_confirmed_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_measurement(
        _session: object,
        measurement_type: str,
        measurement_id: int,
    ) -> dict[str, Any]:
        return {
            "id": measurement_id,
            "watts": Decimal("2090.00"),
            "voltage": Decimal("220"),
            "amp": Decimal("10"),
            "power_factor": Decimal("0.95"),
            "voltage_source": "meter",
            "power_factor_source": "meter",
            "value_type": "estimated",
            "quality": "estimated",
        }

    async def fake_update_measurement(
        _session: object,
        measurement_type: str,
        measurement_id: int,
        values: dict[str, object],
    ) -> dict[str, object]:
        return {"id": measurement_id, **values}

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

    result = await measurement_service.update_device_power_measurement(
        FakeSession(),
        measurement_id=50,
        payload=DevicePowerMeasurementUpdate(watts=Decimal("3000"), confirmed=True),
    )

    assert result["row"]["watts"] == Decimal("3000")
    assert result["row"]["quality"] == "measured_watts"
    assert result["warnings"] == [
        {
            "code": "WATTS_TOLERANCE_EXCEEDED",
            "difference": "910.00",
            "tolerance": "300.00",
        }
    ]


@pytest.mark.asyncio
async def test_update_rack_measurement_recalculates_quality_when_pf_source_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_get_measurement(
        _session: object,
        measurement_type: str,
        measurement_id: int,
    ) -> dict[str, Any]:
        assert measurement_type == "rack"
        return {
            "id": measurement_id,
            "watts": Decimal("2090.00"),
            "voltage": Decimal("220"),
            "amp": Decimal("10"),
            "power_factor": Decimal("0.95"),
            "voltage_source": "meter",
            "power_factor_source": "meter",
            "quality": "calculated_with_measured_pf",
        }

    async def fake_update_measurement(
        _session: object,
        measurement_type: str,
        measurement_id: int,
        values: dict[str, object],
    ) -> dict[str, object]:
        captured["values"] = values
        return {"id": measurement_id, **values}

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

    result = await measurement_service.update_rack_measurement(
        FakeSession(),
        measurement_id=60,
        payload=RackMeasurementUpdate(power_factor_source="default"),
    )

    assert result["row"]["quality"] == "calculated_with_default_pf"
    assert result["warnings"] == []
    assert captured["values"]["watts"] == Decimal("2090.00")
    assert captured["values"]["quality"] == "calculated_with_default_pf"


@pytest.mark.asyncio
async def test_update_device_power_measurement_reclassifies_quality_when_value_type_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_get_measurement(
        _session: object,
        measurement_type: str,
        measurement_id: int,
    ) -> dict[str, Any]:
        assert measurement_type == "device-power"
        return {
            "id": measurement_id,
            "watts": Decimal("2090.00"),
            "voltage": Decimal("220"),
            "amp": Decimal("10"),
            "power_factor": Decimal("0.95"),
            "voltage_source": "default",
            "power_factor_source": "default",
            "value_type": "measured",
            "quality": "calculated_with_default_pf",
        }

    async def fake_update_measurement(
        _session: object,
        measurement_type: str,
        measurement_id: int,
        values: dict[str, object],
    ) -> dict[str, object]:
        captured["values"] = values
        return {"id": measurement_id, **values}

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

    result = await measurement_service.update_device_power_measurement(
        FakeSession(),
        measurement_id=70,
        payload=DevicePowerMeasurementUpdate(value_type="estimated"),
    )

    assert result["row"]["quality"] == "estimated"
    assert result["warnings"] == []
    assert captured["values"]["watts"] == Decimal("2090.00")
    assert captured["values"]["quality"] == "estimated"


@pytest.mark.asyncio
async def test_update_rack_measurement_rejects_numeric_change_when_recalculation_inputs_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_measurement(
        _session: object,
        measurement_type: str,
        measurement_id: int,
    ) -> dict[str, Any]:
        assert measurement_type == "rack"
        return {
            "id": measurement_id,
            "watts": Decimal("5000"),
            "voltage": None,
            "amp": Decimal("10"),
            "power_factor": Decimal("0.95"),
            "voltage_source": "default",
            "power_factor_source": "default",
            "quality": "measured_watts",
        }

    monkeypatch.setattr(
        measurement_service.measurement_repo,
        "get_measurement",
        fake_get_measurement,
    )

    with pytest.raises(ValidationAppError, match="watts or voltage/amp/power_factor is required"):
        await measurement_service.update_rack_measurement(
            FakeSession(),
            measurement_id=80,
            payload=RackMeasurementUpdate(amp=Decimal("12")),
        )


@pytest.mark.asyncio
async def test_update_device_power_measurement_keeps_watts_when_only_value_type_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_get_measurement(
        _session: object,
        measurement_type: str,
        measurement_id: int,
    ) -> dict[str, Any]:
        assert measurement_type == "device-power"
        return {
            "id": measurement_id,
            "watts": Decimal("5000"),
            "voltage": Decimal("220"),
            "amp": Decimal("10"),
            "power_factor": Decimal("0.95"),
            "voltage_source": "default",
            "power_factor_source": "default",
            "value_type": "measured",
            "quality": "measured_watts",
        }

    async def fake_update_measurement(
        _session: object,
        measurement_type: str,
        measurement_id: int,
        values: dict[str, object],
    ) -> dict[str, object]:
        captured["values"] = values
        return {"id": measurement_id, **values}

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

    result = await measurement_service.update_device_power_measurement(
        FakeSession(),
        measurement_id=90,
        payload=DevicePowerMeasurementUpdate(value_type="estimated"),
    )

    assert result["row"]["watts"] == Decimal("5000")
    assert result["row"]["quality"] == "estimated"
    assert captured["values"]["watts"] == Decimal("5000")
