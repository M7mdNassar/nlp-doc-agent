from typing import Any


class AppError(Exception):
    """Base exception for all application errors."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class ValidationError(AppError):
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__("VALIDATION_ERROR", message, 400, details)


class NotFoundError(AppError):
    def __init__(self, resource: str, resource_id: str):
        super().__init__("NOT_FOUND", f"{resource} with ID {resource_id} not found.", 404)


class UnauthorizedError(AppError):
    def __init__(self, message: str = "Unauthorized"):
        super().__init__("UNAUTHORIZED", message, 401)


class InsufficientEvidenceError(AppError):
    def __init__(self, message: str = "Not enough evidence to answer the question."):
        super().__init__("INSUFFICIENT_EVIDENCE", message, 422)
