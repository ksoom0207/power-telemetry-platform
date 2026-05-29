from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationAppError
from app.models.measurements import (
    ManualDevicePower,
    MeasurementBatch,
    PhaseMainMeasurement,
    RackMeasurement,
)

MEASUREMENT_MODELS = {
    "rack": RackMeasurement,
    "device-power": ManualDevicePower,
    "phase-main": PhaseMainMeasurement,
}


async def create_measurement_batch(
    session: AsyncSession,
    values: dict[str, object],
) -> dict[str, object]:
    result = await session.execute(
        insert(MeasurementBatch)
        .values(**values)
        .returning(
            MeasurementBatch.id,
            MeasurementBatch.client_batch_id,
            MeasurementBatch.operator_name,
            MeasurementBatch.measured_at,
            MeasurementBatch.note,
            MeasurementBatch.source,
        )
    )
    return dict(result.mappings().one())


async def get_measurement_batch(session: AsyncSession, batch_id: int) -> dict[str, Any]:
    result = await session.execute(
        select(
            MeasurementBatch.id,
            MeasurementBatch.client_batch_id,
            MeasurementBatch.operator_name,
            MeasurementBatch.measured_at,
            MeasurementBatch.note,
            MeasurementBatch.source,
        ).where(MeasurementBatch.id == batch_id)
    )
    row = result.mappings().one_or_none()
    if row is None:
        raise ValidationAppError("measurement batch not found", {"batch_id": batch_id})
    return dict(row)


async def _insert_many_returning_ids(
    session: AsyncSession,
    model: type,
    rows: Sequence[dict[str, object]],
) -> list[int]:
    if not rows:
        return []
    result = await session.execute(insert(model).values(list(rows)).returning(model.id))
    return list(result.scalars().all())


async def create_rack_measurements(
    session: AsyncSession,
    rows: Sequence[dict[str, object]],
) -> list[int]:
    return await _insert_many_returning_ids(session, RackMeasurement, rows)


async def create_device_power_measurements(
    session: AsyncSession,
    rows: Sequence[dict[str, object]],
) -> list[int]:
    return await _insert_many_returning_ids(session, ManualDevicePower, rows)


async def create_phase_main_measurements(
    session: AsyncSession,
    rows: Sequence[dict[str, object]],
) -> list[int]:
    return await _insert_many_returning_ids(session, PhaseMainMeasurement, rows)


def _model_for_type(measurement_type: str) -> type:
    model = MEASUREMENT_MODELS.get(measurement_type)
    if model is None:
        raise ValidationAppError("unknown measurement type", {"measurement_type": measurement_type})
    return model


async def update_measurement(
    session: AsyncSession,
    measurement_type: str,
    measurement_id: int,
    values: dict[str, object],
) -> dict[str, object]:
    model = _model_for_type(measurement_type)
    result = await session.execute(
        update(model).where(model.id == measurement_id).values(**values).returning(model)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise ValidationAppError("measurement not found", {"measurement_id": measurement_id})
    return {
        column.name: getattr(row, column.name)
        for column in row.__table__.columns
    }


async def get_measurement(
    session: AsyncSession,
    measurement_type: str,
    measurement_id: int,
) -> dict[str, Any]:
    model = _model_for_type(measurement_type)
    result = await session.execute(select(model).where(model.id == measurement_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise ValidationAppError("measurement not found", {"measurement_id": measurement_id})
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


async def delete_measurement(
    session: AsyncSession,
    measurement_type: str,
    measurement_id: int,
) -> None:
    model = _model_for_type(measurement_type)
    result = await session.execute(delete(model).where(model.id == measurement_id))
    if result.rowcount == 0:
        raise ValidationAppError("measurement not found", {"measurement_id": measurement_id})
