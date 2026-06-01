from datetime import datetime

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.schemas.kwh import RackHourlyKwhRead, RackMonthlyKwhRead
from app.services import kwh as kwh_service

router = APIRouter(tags=["kwh"])


@router.get("/rack-hourly-kwh", response_model=list[RackHourlyKwhRead])
async def list_rack_hourly_kwh(
    session: DbSession,
    rack_id: int | None = None,
    hour_start_from: datetime | None = None,
    hour_start_to: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[dict[str, object]]:
    return await kwh_service.list_rack_hourly_kwh(
        session,
        rack_id=rack_id,
        hour_start_from=hour_start_from,
        hour_start_to=hour_start_to,
        limit=limit,
    )


@router.get("/rack-monthly-kwh", response_model=list[RackMonthlyKwhRead])
async def list_rack_monthly_kwh(
    session: DbSession,
    rack_id: int | None = None,
    month_from: datetime | None = None,
    month_to: datetime | None = None,
    needs_recalculation: bool | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[dict[str, object]]:
    return await kwh_service.list_rack_monthly_kwh(
        session,
        rack_id=rack_id,
        month_from=month_from,
        month_to=month_to,
        needs_recalculation=needs_recalculation,
        limit=limit,
    )
