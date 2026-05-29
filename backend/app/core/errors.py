from typing import Any


class AppError(Exception):
    code = "APP_ERROR"

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ValidationAppError(AppError):
    code = "VALIDATION_ERROR"


class ExternalApiError(AppError):
    code = "EXTERNAL_API_ERROR"
