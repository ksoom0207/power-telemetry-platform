from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime import to_utc
from app.core.errors import ValidationAppError
from app.repositories import measurements as measurement_repo
from app.schemas.measurements import (
    DevicePowerBulkCreate,
    DevicePowerMeasurementUpdate,
    MeasurementBatchCreate,
    PhaseMainMeasurementBulkCreate,
    PhaseMainMeasurementUpdate,
    RackMeasurementBulkCreate,
    RackMeasurementUpdate,
)
from app.services.power_calculations import calculate_single_phase_watts, validate_watts_tolerance


@dataclass(frozen=True)
class PreparedMeasurement:
    values: dict[str, object]
    warning: dict[str, object] | None


def derive_watts_and_quality(
    *,
    watts: Decimal | None,
    voltage: Decimal | None,
    amp: Decimal | None,
    power_factor: Decimal | None,
    voltage_source: str,
    power_factor_source: str,
    value_type: str | None = None,
    confirmed: bool = False,
) -> tuple[Decimal, str, dict[str, object] | None]:
    warning: dict[str, object] | None = None
    entered_watts = watts is not None

    if watts is None and None not in (voltage, amp, power_factor):
        watts = calculate_single_phase_watts(
            voltage=voltage or Decimal("0"),
            amp=amp or Decimal("0"),
            power_factor=power_factor or Decimal("0"),
        )

    if watts is None:
        raise ValidationAppError("watts or voltage/amp/power_factor is required")

    if value_type == "estimated":
        return watts, "estimated", None
    if value_type == "rated":
        return watts, "rated", None

    if None not in (voltage, amp, power_factor):
        calculated = calculate_single_phase_watts(
            voltage=voltage or Decimal("0"),
            amp=amp or Decimal("0"),
            power_factor=power_factor or Decimal("0"),
        )
        result = validate_watts_tolerance(entered_watts=watts, calculated_watts=calculated)
        if not result.is_valid:
            warning = {
                "code": result.warning,
                "difference": str(result.difference),
                "tolerance": str(result.tolerance),
            }
            if not confirmed:
                raise ValidationAppError("watts tolerance exceeded", warning)

    if entered_watts:
        return watts, "measured_watts", warning
    if power_factor_source == "default":
        return watts, "calculated_with_default_pf", warning
    return watts, "calculated_with_measured_pf", warning


def _now_utc() -> datetime:
    return datetime.now(tz=UTC)


def _has_power_input(
    *,
    watts: Decimal | None,
    voltage: Decimal | None,
    amp: Decimal | None,
    power_factor: Decimal | None,
) -> bool:
    return any(value is not None for value in (watts, voltage, amp, power_factor))


async def create_measurement_batch(
    session: AsyncSession,
    payload: MeasurementBatchCreate,
) -> dict[str, object]:
    measured_at = to_utc(payload.measured_at)
    now = _now_utc()
    values = {
        "client_batch_id": payload.client_batch_id or str(uuid4()),
        "operator_name": payload.operator_name,
        "measured_at": measured_at,
        "note": payload.note,
        "source": "web_bulk_input",
        "created_at": now,
        "updated_at": now,
    }
    row = await measurement_repo.create_measurement_batch(session, values)
    await session.commit()
    return row


async def create_rack_measurements_bulk(
    session: AsyncSession,
    payload: RackMeasurementBulkCreate,
) -> dict[str, object]:
    batch = await measurement_repo.get_measurement_batch(session, payload.batch_id)
    warnings: list[dict[str, object]] = []
    rows: list[dict[str, object]] = []
    now = _now_utc()

    for index, row in enumerate(payload.rows):
        if not _has_power_input(
            watts=row.watts, voltage=row.voltage, amp=row.amp, power_factor=row.power_factor
        ):
            continue
        watts, quality, warning = derive_watts_and_quality(
            watts=row.watts,
            voltage=row.voltage,
            amp=row.amp,
            power_factor=row.power_factor,
            voltage_source=row.voltage_source,
            power_factor_source=row.power_factor_source,
            confirmed=row.confirmed,
        )
        if warning:
            warnings.append({"index": index, **warning})
        rows.append(
            {
                "batch_id": payload.batch_id,
                "rack_id": row.rack_id,
                "measurement_point": row.measurement_point,
                "watts": watts,
                "voltage": row.voltage,
                "amp": row.amp,
                "power_factor": row.power_factor,
                "voltage_source": row.voltage_source,
                "power_factor_source": row.power_factor_source,
                "quality": quality,
                "measured_at": batch["measured_at"],
                "operator_name": batch["operator_name"],
                "note": row.note,
                "created_at": now,
                "updated_at": now,
            }
        )

    created_ids = await measurement_repo.create_rack_measurements(session, rows)
    await session.commit()
    return {"created_ids": created_ids, "warnings": warnings}


async def create_device_power_measurements_bulk(
    session: AsyncSession,
    payload: DevicePowerBulkCreate,
) -> dict[str, object]:
    batch = await measurement_repo.get_measurement_batch(session, payload.batch_id)
    warnings: list[dict[str, object]] = []
    rows: list[dict[str, object]] = []
    now = _now_utc()

    for index, row in enumerate(payload.rows):
        if not _has_power_input(
            watts=row.watts, voltage=row.voltage, amp=row.amp, power_factor=row.power_factor
        ):
            continue
        watts, quality, warning = derive_watts_and_quality(
            watts=row.watts,
            voltage=row.voltage,
            amp=row.amp,
            power_factor=row.power_factor,
            voltage_source=row.voltage_source,
            power_factor_source=row.power_factor_source,
            value_type=row.value_type,
            confirmed=row.confirmed,
        )
        if warning:
            warnings.append({"index": index, **warning})
        rows.append(
            {
                "batch_id": payload.batch_id,
                "device_id": row.device_id,
                "measurement_point": row.measurement_point,
                "value_type": row.value_type,
                "watts": watts,
                "voltage": row.voltage,
                "amp": row.amp,
                "power_factor": row.power_factor,
                "voltage_source": row.voltage_source,
                "power_factor_source": row.power_factor_source,
                "quality": quality,
                "measured_at": batch["measured_at"],
                "operator_name": batch["operator_name"],
                "note": row.note,
                "created_at": now,
                "updated_at": now,
            }
        )

    created_ids = await measurement_repo.create_device_power_measurements(session, rows)
    await session.commit()
    return {"created_ids": created_ids, "warnings": warnings}


async def create_phase_main_measurements_bulk(
    session: AsyncSession,
    payload: PhaseMainMeasurementBulkCreate,
    *,
    default_voltage: Decimal,
    default_power_factor: Decimal,
) -> dict[str, object]:
    batch = await measurement_repo.get_measurement_batch(session, payload.batch_id)
    rows: list[dict[str, object]] = []
    now = _now_utc()

    for row in payload.rows:
        calculated_watts = calculate_single_phase_watts(
            voltage=default_voltage,
            amp=row.amp,
            power_factor=default_power_factor,
        )
        rows.append(
            {
                "batch_id": payload.batch_id,
                "phase": row.phase,
                "measurement_point": row.measurement_point,
                "amp": row.amp,
                "voltage_default_used": default_voltage,
                "power_factor_default_used": default_power_factor,
                "voltage_source": "default",
                "power_factor_source": "default",
                "quality": "calculated_with_default_pf",
                "calculated_watts": calculated_watts,
                "measured_at": batch["measured_at"],
                "operator_name": batch["operator_name"],
                "note": row.note,
                "created_at": now,
                "updated_at": now,
            }
        )

    created_ids = await measurement_repo.create_phase_main_measurements(session, rows)
    await session.commit()
    return {"created_ids": created_ids, "warnings": []}


async def update_rack_measurement(
    session: AsyncSession,
    *,
    measurement_id: int,
    payload: RackMeasurementUpdate,
) -> dict[str, object]:
    current = await measurement_repo.get_measurement(session, "rack", measurement_id)
    values = payload.model_dump(exclude_unset=True, exclude={"confirmed"})
    merged = {**current, **values}

    watts, quality, _warning = derive_watts_and_quality(
        watts=merged.get("watts"),
        voltage=merged.get("voltage"),
        amp=merged.get("amp"),
        power_factor=merged.get("power_factor"),
        voltage_source=merged.get("voltage_source") or "default",
        power_factor_source=merged.get("power_factor_source") or "default",
        confirmed=payload.confirmed,
    )
    values["watts"] = watts
    values["quality"] = quality

    values["updated_at"] = _now_utc()
    row = await measurement_repo.update_measurement(
        session,
        "rack",
        measurement_id,
        values,
    )
    await session.commit()
    return row


async def update_device_power_measurement(
    session: AsyncSession,
    *,
    measurement_id: int,
    payload: DevicePowerMeasurementUpdate,
) -> dict[str, object]:
    current = await measurement_repo.get_measurement(session, "device-power", measurement_id)
    values = payload.model_dump(exclude_unset=True, exclude={"confirmed"})
    merged = {**current, **values}

    watts, quality, _warning = derive_watts_and_quality(
        watts=merged.get("watts"),
        voltage=merged.get("voltage"),
        amp=merged.get("amp"),
        power_factor=merged.get("power_factor"),
        voltage_source=merged.get("voltage_source") or "default",
        power_factor_source=merged.get("power_factor_source") or "default",
        value_type=merged.get("value_type"),
        confirmed=payload.confirmed,
    )
    values["watts"] = watts
    values["quality"] = quality
    values["updated_at"] = _now_utc()
    row = await measurement_repo.update_measurement(
        session,
        "device-power",
        measurement_id,
        values,
    )
    await session.commit()
    return row


async def update_phase_main_measurement(
    session: AsyncSession,
    *,
    measurement_id: int,
    payload: PhaseMainMeasurementUpdate,
) -> dict[str, object]:
    current = await measurement_repo.get_measurement(session, "phase-main", measurement_id)
    values = payload.model_dump(exclude_unset=True)
    merged = {**current, **values}
    amp = merged.get("amp")
    voltage = merged.get("voltage_default_used")
    power_factor = merged.get("power_factor_default_used")
    if not (
        isinstance(amp, Decimal)
        and isinstance(voltage, Decimal)
        and isinstance(power_factor, Decimal)
    ):
        raise ValidationAppError("phase-main measurement cannot be recalculated")

    values["calculated_watts"] = calculate_single_phase_watts(
        voltage=voltage,
        amp=amp,
        power_factor=power_factor,
    )
    values["quality"] = "calculated_with_default_pf"
    values["updated_at"] = _now_utc()
    row = await measurement_repo.update_measurement(
        session,
        "phase-main",
        measurement_id,
        values,
    )
    await session.commit()
    return row


async def delete_measurement(
    session: AsyncSession,
    *,
    measurement_type: str,
    measurement_id: int,
) -> None:
    await measurement_repo.delete_measurement(session, measurement_type, measurement_id)
    await session.commit()
