from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.schemas.ilo import (
    CollectionRunDetail,
    CollectionRunRead,
    IloPowerSampleRead,
    IloStatusRead,
)
from app.services import ilo_collection

router = APIRouter(prefix="/ilo", tags=["ilo"])


@router.get("/status", response_model=IloStatusRead)
async def get_status(session: DbSession) -> dict[str, object]:
    return await ilo_collection.get_ilo_status(session)


@router.post("/collect", response_model=CollectionRunRead)
async def collect(session: DbSession) -> dict[str, object]:
    return await ilo_collection.collect_ilo_power(session)


@router.get("/samples", response_model=list[IloPowerSampleRead])
async def list_samples(
    session: DbSession,
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[dict[str, object]]:
    return await ilo_collection.list_ilo_samples(session, limit=limit)


@router.get("/collection-runs", response_model=list[CollectionRunRead])
async def list_collection_runs(
    session: DbSession,
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[dict[str, object]]:
    return await ilo_collection.list_collection_runs(session, limit=limit)


@router.get("/collection-runs/{collection_run_id}", response_model=CollectionRunDetail)
async def get_collection_run(
    collection_run_id: int,
    session: DbSession,
) -> dict[str, object]:
    return await ilo_collection.get_collection_run(session, collection_run_id)
