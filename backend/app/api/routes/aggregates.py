from datetime import datetime

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.schemas.aggregates import PowerAggregateRead
from app.services import aggregates as aggregate_service

router = APIRouter(tags=["aggregates"])


@router.get("/aggregates", response_model=list[PowerAggregateRead])
async def list_power_aggregates(
    session: DbSession,
    entity_type: str | None = None,
    entity_id: int | None = None,
    source_type: str | None = None,
    period: str | None = None,
    period_start_from: datetime | None = None,
    period_start_to: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[dict[str, object]]:
    return await aggregate_service.list_power_aggregates(
        session,
        entity_type=entity_type,
        entity_id=entity_id,
        source_type=source_type,
        period=period,
        period_start_from=period_start_from,
        period_start_to=period_start_to,
        limit=limit,
    )
