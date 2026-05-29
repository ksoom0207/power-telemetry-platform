from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import measurement_batches, measurements
from app.core.errors import AppError

app = FastAPI(title="Power Monitoring API")

app.include_router(measurement_batches.router)
app.include_router(measurements.router)


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
