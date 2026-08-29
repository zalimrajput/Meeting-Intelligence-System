"""Global error handling and AppError custom exception."""

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

logger = logging.getLogger(__name__)


class AppError(Exception):
    """
    Standard application error carrying HTTP status code, machine-readable
    error code, human-readable message, and optional contextual details.
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | list[Any] | None = None,
        error_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = error_code or code
        self.message = message
        self.details = details or {}


CustomAppException = AppError


def format_error_envelope(code: str, message: str, details: Any = None) -> dict[str, Any]:
    """Helper to produce the standardized API error envelope per rules.md 4.2."""
    return {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "details": details if details is not None else {},
        },
    }


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Handles explicit AppError instances thrown throughout services and controllers."""
    logger.warning(
        "AppError caught [%s - %s]: %s (path: %s)",
        exc.status_code,
        exc.code,
        exc.message,
        request.url.path,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=format_error_envelope(exc.code, exc.message, exc.details),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Transforms Pydantic validation errors into the standard API error response envelope."""
    formatted_errors: list[dict[str, Any]] = []
    for err in exc.errors():
        field_loc = ".".join(str(item) for item in err.get("loc", []) if item != "body")
        formatted_errors.append(
            {
                "field": field_loc or "body",
                "message": err.get("msg", "Invalid value"),
                "type": err.get("type", "value_error"),
            }
        )

    logger.warning("Validation error on %s: %s", request.url.path, formatted_errors)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=format_error_envelope(
            code="VALIDATION_ERROR",
            message="Request validation failed. Please check the provided data.",
            details={"errors": formatted_errors},
        ),
    )


async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Handles Slowapi rate limit exceeded exceptions."""
    logger.warning(
        "Rate limit exceeded on %s from %s",
        request.url.path,
        request.client.host if request.client else "unknown",
    )
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content=format_error_envelope(
            code="RATE_LIMIT_EXCEEDED",
            message="Too many requests. Please slow down and try again.",
            details={"limit": str(exc.detail)},
        ),
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Catches standard FastAPI/Starlette HTTPExceptions and formats them."""
    code = "HTTP_ERROR"
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        code = "UNAUTHORIZED"
    elif exc.status_code == status.HTTP_403_FORBIDDEN:
        code = "FORBIDDEN"
    elif exc.status_code == status.HTTP_404_NOT_FOUND:
        code = "NOT_FOUND"

    return JSONResponse(
        status_code=exc.status_code,
        content=format_error_envelope(
            code=code,
            message=str(exc.detail),
            details={},
        ),
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all handler for unhandled server exceptions.
    Logs the full traceback internally and returns a clean, safe envelope without leaking traces.
    """
    logger.critical(
        "Unhandled exception on %s: %s",
        request.url.path,
        str(exc),
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=format_error_envelope(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected error occurred. Please try again later.",
            details={},
        ),
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register all global error handlers onto the FastAPI application."""
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
