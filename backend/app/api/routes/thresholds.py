from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.schemas.thresholds import (
    ThresholdCreate,
    ThresholdRead,
    ThresholdStateRead,
    ThresholdUpdate,
)
from app.services import thresholds as threshold_service

router = APIRouter(tags=["thresholds"])


@router.get("/thresholds", response_model=list[ThresholdRead])
async def list_thresholds(
    session: DbSession,
    active: bool | None = True,
    target_type: str | None = None,
    target_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[dict[str, object]]:
    return await threshold_service.list_thresholds(
        session,
        active=active,
        target_type=target_type,
        target_id=target_id,
        limit=limit,
    )


@router.post("/thresholds", response_model=ThresholdRead)
async def create_threshold(
    payload: ThresholdCreate,
    session: DbSession,
) -> dict[str, object]:
    return await threshold_service.create_threshold(session, payload)


@router.patch("/thresholds/{threshold_id}", response_model=ThresholdRead)
async def update_threshold(
    threshold_id: int,
    payload: ThresholdUpdate,
    session: DbSession,
) -> dict[str, object]:
    return await threshold_service.update_threshold(session, threshold_id, payload)


@router.delete("/thresholds/{threshold_id}", response_model=ThresholdRead)
async def deactivate_threshold(
    threshold_id: int,
    session: DbSession,
) -> dict[str, object]:
    return await threshold_service.deactivate_threshold(session, threshold_id)


@router.get("/threshold-states", response_model=list[ThresholdStateRead])
async def list_threshold_states(
    session: DbSession,
    threshold_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[dict[str, object]]:
    return await threshold_service.list_threshold_states(
        session,
        threshold_id=threshold_id,
        limit=limit,
    )
