from sqlalchemy.ext.asyncio import AsyncSession

from app.services import ilo_collection
from app.services import thresholds as threshold_service


async def run_ilo_collect_job(session: AsyncSession) -> dict[str, object]:
    return await ilo_collection.collect_ilo_power(session, triggered_by="worker")


async def run_aggregate_job(_session: AsyncSession) -> dict[str, object]:
    # TODO(Task 7.2): calculate persisted power aggregates from representative power rows.
    return {"status": "skipped", "reason": "aggregate calculation pending Task 7.2"}


async def run_kwh_job(_session: AsyncSession) -> dict[str, object]:
    # TODO(Task 7.2): build kWh rows from resolved hourly rack power inputs.
    return {"status": "skipped", "reason": "kWh calculation pending Task 7.2"}


async def run_threshold_evaluation_job(session: AsyncSession) -> dict[str, object]:
    return await threshold_service.evaluate_active_thresholds(session)


async def run_recalculation_job(_session: AsyncSession) -> dict[str, object]:
    # TODO(Task 7.2): process months marked for recalculation.
    return {"status": "skipped", "reason": "recalculation pending Task 7.2"}
