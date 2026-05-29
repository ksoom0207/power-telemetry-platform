from fastapi import APIRouter

from app.api.deps import DbSession
from app.core.config import settings
from app.schemas.measurements import (
    BulkCreateResult,
    DevicePowerBulkCreate,
    DevicePowerMeasurementUpdate,
    MeasurementUpdateResult,
    PhaseMainMeasurementBulkCreate,
    PhaseMainMeasurementUpdate,
    RackMeasurementBulkCreate,
    RackMeasurementUpdate,
)
from app.services import measurements as measurement_service

router = APIRouter(tags=["measurements"])


@router.post("/rack-measurements/bulk", response_model=BulkCreateResult)
async def create_rack_measurements_bulk(
    payload: RackMeasurementBulkCreate,
    session: DbSession,
) -> dict[str, object]:
    return await measurement_service.create_rack_measurements_bulk(session, payload)


@router.post("/device-power-measurements/bulk", response_model=BulkCreateResult)
async def create_device_power_measurements_bulk(
    payload: DevicePowerBulkCreate,
    session: DbSession,
) -> dict[str, object]:
    return await measurement_service.create_device_power_measurements_bulk(session, payload)


@router.post("/phase-main-measurements/bulk", response_model=BulkCreateResult)
async def create_phase_main_measurements_bulk(
    payload: PhaseMainMeasurementBulkCreate,
    session: DbSession,
) -> dict[str, object]:
    return await measurement_service.create_phase_main_measurements_bulk(
        session,
        payload,
        default_voltage=settings.default_voltage,
        default_power_factor=settings.default_power_factor,
    )


@router.patch("/rack-measurements/{measurement_id}", response_model=MeasurementUpdateResult)
async def update_rack_measurement(
    measurement_id: int,
    payload: RackMeasurementUpdate,
    session: DbSession,
) -> dict[str, object]:
    return await measurement_service.update_rack_measurement(
        session,
        measurement_id=measurement_id,
        payload=payload,
    )


@router.delete("/rack-measurements/{measurement_id}", status_code=204)
async def delete_rack_measurement(measurement_id: int, session: DbSession) -> None:
    await measurement_service.delete_measurement(
        session,
        measurement_type="rack",
        measurement_id=measurement_id,
    )


@router.patch("/device-power-measurements/{measurement_id}", response_model=MeasurementUpdateResult)
async def update_device_power_measurement(
    measurement_id: int,
    payload: DevicePowerMeasurementUpdate,
    session: DbSession,
) -> dict[str, object]:
    return await measurement_service.update_device_power_measurement(
        session,
        measurement_id=measurement_id,
        payload=payload,
    )


@router.delete("/device-power-measurements/{measurement_id}", status_code=204)
async def delete_device_power_measurement(measurement_id: int, session: DbSession) -> None:
    await measurement_service.delete_measurement(
        session,
        measurement_type="device-power",
        measurement_id=measurement_id,
    )


@router.patch("/phase-main-measurements/{measurement_id}")
async def update_phase_main_measurement(
    measurement_id: int,
    payload: PhaseMainMeasurementUpdate,
    session: DbSession,
) -> dict[str, object]:
    return await measurement_service.update_phase_main_measurement(
        session,
        measurement_id=measurement_id,
        payload=payload,
    )


@router.delete("/phase-main-measurements/{measurement_id}", status_code=204)
async def delete_phase_main_measurement(measurement_id: int, session: DbSession) -> None:
    await measurement_service.delete_measurement(
        session,
        measurement_type="phase-main",
        measurement_id=measurement_id,
    )
