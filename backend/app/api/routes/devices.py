from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.schemas.devices import DeviceCreate, DeviceRead, DeviceUpdate
from app.services import inventory

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=list[DeviceRead])
async def list_devices(
    session: DbSession,
    include_inactive: bool = Query(default=False),
    rack_id: int | None = Query(default=None),
) -> list[dict[str, object]]:
    return await inventory.list_devices(
        session,
        include_inactive=include_inactive,
        rack_id=rack_id,
    )


@router.post("", response_model=DeviceRead)
async def create_device(payload: DeviceCreate, session: DbSession) -> dict[str, object]:
    return await inventory.create_device(session, payload)


@router.get("/{device_id}", response_model=DeviceRead)
async def get_device(device_id: int, session: DbSession) -> dict[str, object]:
    return await inventory.get_device(session, device_id)


@router.patch("/{device_id}", response_model=DeviceRead)
async def update_device(
    device_id: int,
    payload: DeviceUpdate,
    session: DbSession,
) -> dict[str, object]:
    return await inventory.update_device(session, device_id, payload)


@router.delete("/{device_id}", status_code=204)
async def delete_device(device_id: int, session: DbSession) -> None:
    await inventory.deactivate_device(session, device_id)
