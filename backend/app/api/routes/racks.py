from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.schemas.racks import RackCreate, RackRead, RackUpdate
from app.services import inventory

router = APIRouter(prefix="/racks", tags=["racks"])


@router.get("", response_model=list[RackRead])
async def list_racks(
    session: DbSession,
    include_inactive: bool = Query(default=False),
) -> list[dict[str, object]]:
    return await inventory.list_racks(session, include_inactive=include_inactive)


@router.post("", response_model=RackRead)
async def create_rack(payload: RackCreate, session: DbSession) -> dict[str, object]:
    return await inventory.create_rack(session, payload)


@router.get("/{rack_id}", response_model=RackRead)
async def get_rack(rack_id: int, session: DbSession) -> dict[str, object]:
    return await inventory.get_rack(session, rack_id)


@router.patch("/{rack_id}", response_model=RackRead)
async def update_rack(
    rack_id: int,
    payload: RackUpdate,
    session: DbSession,
) -> dict[str, object]:
    return await inventory.update_rack(session, rack_id, payload)


@router.delete("/{rack_id}", status_code=204)
async def delete_rack(rack_id: int, session: DbSession) -> None:
    await inventory.deactivate_rack(session, rack_id)
