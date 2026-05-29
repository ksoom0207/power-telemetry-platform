from fastapi import APIRouter

from app.api.deps import DbSession
from app.schemas.settings import (
    IloCredentialRead,
    IloCredentialUpsert,
    PowerDefaultsRead,
    PowerDefaultsUpsert,
)
from app.services import settings as settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/ilo-credential", response_model=IloCredentialRead)
async def get_ilo_credential(session: DbSession) -> dict[str, object]:
    return await settings_service.get_ilo_credential(session)


@router.put("/ilo-credential", response_model=IloCredentialRead)
async def upsert_ilo_credential(
    payload: IloCredentialUpsert,
    session: DbSession,
) -> dict[str, object]:
    return await settings_service.upsert_ilo_credential(session, payload)


@router.get("/power-defaults", response_model=PowerDefaultsRead)
async def get_power_defaults(session: DbSession) -> dict[str, object]:
    return await settings_service.get_power_defaults(session)


@router.put("/power-defaults", response_model=PowerDefaultsRead)
async def upsert_power_defaults(
    payload: PowerDefaultsUpsert,
    session: DbSession,
) -> dict[str, object]:
    return await settings_service.upsert_power_defaults(session, payload)
