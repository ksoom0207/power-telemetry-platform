from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime import ensure_aware
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


def _latest_statement(model: type, partition_column: object, *, measured_at_to: datetime) -> Any:
    ensure_aware(measured_at_to)
    ranked = (
        select(
            *model.__table__.columns,
            func.row_number()
            .over(
                partition_by=partition_column,
                order_by=(model.measured_at.desc(), model.id.desc()),
            )
            .label("row_number"),
        )
        .where(model.measured_at <= measured_at_to)
        .subquery()
    )
    return select(ranked).where(ranked.c.row_number == 1)


def build_latest_manual_device_power_by_device_statement(*, measured_at_to: datetime) -> Any:
    ensure_aware(measured_at_to)
    ranked = (
        select(
            *ManualDevicePower.__table__.columns,
            func.row_number()
            .over(
                partition_by=ManualDevicePower.device_id,
                order_by=(ManualDevicePower.measured_at.desc(), ManualDevicePower.id.desc()),
            )
            .label("row_number"),
        )
        .where(ManualDevicePower.measured_at <= measured_at_to)
        .where(
            or_(
                ManualDevicePower.value_type == "measured",
                ManualDevicePower.quality == "measured_watts",
            )
        )
        .subquery()
    )
    return select(ranked).where(ranked.c.row_number == 1)


def build_latest_rack_measurements_by_rack_statement(*, measured_at_to: datetime) -> Any:
    return _latest_statement(
        RackMeasurement,
        RackMeasurement.rack_id,
        measured_at_to=measured_at_to,
    )


def build_latest_phase_main_measurements_by_phase_statement(*, measured_at_to: datetime) -> Any:
    return _latest_statement(
        PhaseMainMeasurement,
        PhaseMainMeasurement.phase,
        measured_at_to=measured_at_to,
    )


def _mapped_latest_rows(rows: Sequence[dict[str, Any]], key: str) -> dict[Any, dict[str, Any]]:
    latest: dict[Any, dict[str, Any]] = {}
    for row in rows:
        row.pop("row_number", None)
        latest[row[key]] = row
    return latest


async def list_latest_manual_device_power_by_device(
    session: AsyncSession,
    measured_at_to: datetime,
) -> dict[int, dict[str, Any]]:
    result = await session.execute(
        build_latest_manual_device_power_by_device_statement(measured_at_to=measured_at_to)
    )
    return {
        int(key): row
        for key, row in _mapped_latest_rows(
            [dict(row) for row in result.mappings().all()],
            "device_id",
        ).items()
    }


async def list_latest_rack_measurements_by_rack(
    session: AsyncSession,
    measured_at_to: datetime,
) -> dict[int, dict[str, Any]]:
    result = await session.execute(
        build_latest_rack_measurements_by_rack_statement(measured_at_to=measured_at_to)
    )
    return {
        int(key): row
        for key, row in _mapped_latest_rows(
            [dict(row) for row in result.mappings().all()],
            "rack_id",
        ).items()
    }


async def list_latest_phase_main_measurements_by_phase(
    session: AsyncSession,
    measured_at_to: datetime,
) -> dict[str, dict[str, Any]]:
    result = await session.execute(
        build_latest_phase_main_measurements_by_phase_statement(measured_at_to=measured_at_to)
    )
    return {
        str(key): row
        for key, row in _mapped_latest_rows(
            [dict(row) for row in result.mappings().all()],
            "phase",
        ).items()
    }


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
