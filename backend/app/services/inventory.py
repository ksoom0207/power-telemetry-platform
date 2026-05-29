from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationAppError
from app.repositories import devices as device_repo
from app.repositories import racks as rack_repo
from app.schemas.devices import DeviceCreate, DeviceUpdate
from app.schemas.racks import RackCreate, RackUpdate


def _now_utc() -> datetime:
    return datetime.now(tz=UTC)


def _with_timestamps(values: dict[str, object], *, create: bool) -> dict[str, object]:
    now = _now_utc()
    values["updated_at"] = now
    if create:
        values["created_at"] = now
    return values


async def list_racks(
    session: AsyncSession,
    *,
    include_inactive: bool = False,
) -> list[dict[str, object]]:
    return await rack_repo.list_racks(session, include_inactive=include_inactive)


async def get_rack(session: AsyncSession, rack_id: int) -> dict[str, object]:
    return await rack_repo.get_rack(session, rack_id)


async def create_rack(session: AsyncSession, payload: RackCreate) -> dict[str, object]:
    try:
        row = await rack_repo.create_rack(
            session,
            _with_timestamps(payload.model_dump(), create=True),
        )
        await session.commit()
        return row
    except IntegrityError as exc:
        await session.rollback()
        raise ValidationAppError("rack name already exists") from exc


async def update_rack(
    session: AsyncSession,
    rack_id: int,
    payload: RackUpdate,
) -> dict[str, object]:
    try:
        row = await rack_repo.update_rack(
            session,
            rack_id,
            _with_timestamps(payload.model_dump(exclude_unset=True), create=False),
        )
        await session.commit()
        return row
    except IntegrityError as exc:
        await session.rollback()
        raise ValidationAppError("rack name already exists") from exc


async def deactivate_rack(session: AsyncSession, rack_id: int) -> None:
    await rack_repo.update_rack(
        session,
        rack_id,
        _with_timestamps({"active": False}, create=False),
    )
    await session.commit()


async def list_devices(
    session: AsyncSession,
    *,
    include_inactive: bool = False,
    rack_id: int | None = None,
) -> list[dict[str, object]]:
    return await device_repo.list_devices(
        session,
        include_inactive=include_inactive,
        rack_id=rack_id,
    )


async def get_device(session: AsyncSession, device_id: int) -> dict[str, object]:
    return await device_repo.get_device(session, device_id)


async def create_device(session: AsyncSession, payload: DeviceCreate) -> dict[str, object]:
    try:
        row = await device_repo.create_device(
            session,
            _with_timestamps(payload.model_dump(), create=True),
        )
        await session.commit()
        return row
    except IntegrityError as exc:
        await session.rollback()
        raise ValidationAppError("device name already exists") from exc


async def update_device(
    session: AsyncSession,
    device_id: int,
    payload: DeviceUpdate,
) -> dict[str, object]:
    current = await device_repo.get_device(session, device_id)
    merged = {**current, **payload.model_dump(exclude_unset=True)}
    validated = DeviceCreate.model_validate(
        {
            key: merged[key]
            for key in (
                "name",
                "rack_id",
                "device_type",
                "u_position_start",
                "u_position_end",
                "has_ilo",
                "ilo_host",
                "ilo_profile",
                "active",
            )
        }
    )
    try:
        row = await device_repo.update_device(
            session,
            device_id,
            _with_timestamps(validated.model_dump(exclude_unset=True), create=False),
        )
        await session.commit()
        return row
    except IntegrityError as exc:
        await session.rollback()
        raise ValidationAppError("device name already exists") from exc


async def deactivate_device(session: AsyncSession, device_id: int) -> None:
    await device_repo.update_device(
        session,
        device_id,
        _with_timestamps({"active": False}, create=False),
    )
    await session.commit()
