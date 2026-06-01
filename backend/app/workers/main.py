import asyncio
import logging

from app.core.database import AsyncSessionLocal
from app.workers.jobs import (
    run_aggregate_job,
    run_ilo_collect_job,
    run_kwh_job,
    run_recalculation_job,
    run_threshold_evaluation_job,
)

LOGGER = logging.getLogger(__name__)
WORKER_INTERVAL_SECONDS = 900


async def run_once() -> None:
    async with AsyncSessionLocal() as session:
        for job in (
            run_ilo_collect_job,
            run_aggregate_job,
            run_kwh_job,
            run_threshold_evaluation_job,
            run_recalculation_job,
        ):
            try:
                await job(session)
            except Exception:
                LOGGER.exception("worker job failed", extra={"job": job.__name__})


async def run_forever(interval_seconds: int = WORKER_INTERVAL_SECONDS) -> None:
    while True:
        await run_once()
        await asyncio.sleep(interval_seconds)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
