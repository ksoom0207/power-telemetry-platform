from fastapi import APIRouter

from app.api.deps import DbSession
from app.schemas.measurements import MeasurementBatchCreate, MeasurementBatchRead
from app.services import measurements as measurement_service

router = APIRouter(prefix="/measurement-batches", tags=["measurement-batches"])


@router.post("", response_model=MeasurementBatchRead)
async def create_measurement_batch(
    payload: MeasurementBatchCreate,
    session: DbSession,
) -> dict[str, object]:
    return await measurement_service.create_measurement_batch(session, payload)
