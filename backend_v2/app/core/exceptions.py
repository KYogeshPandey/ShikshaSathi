"""Application-defined exceptions and centralized exception handlers.

Every handler here returns the standard envelope defined in
app/schemas/error.py and never leaks a stack trace, a raw database/driver
exception, or a secret value to the client. This directly replaces the
legacy pattern of ad hoc ``try/except`` blocks per route that returned
``str(exception)`` straight into the JSON response body (docs/AUDIT.md
§2.4, §2.7).

Registered in app/main.py via ``EXCEPTION_HANDLERS``:

- ``AppError``               -> application-defined, client-facing errors
- ``RequestValidationError`` -> FastAPI/Pydantic request validation errors
- ``StarletteHTTPException`` -> any HTTPException, including framework 404s
- ``Exception``              -> catch-all: sanitized 500, never re-raised
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas.error import ErrorDetail, ErrorResponse

logger = structlog.get_logger(__name__)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or "unknown"


def _request_id_header(request: Request) -> str:
    return getattr(request.state, "request_id_header", None) or "X-Request-ID"


def _envelope(
    request: Request,
    *,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return ErrorResponse(
        error=ErrorDetail(code=code, message=message, details=details or {}),
        request_id=_request_id(request),
    ).model_dump()


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build every API error with the same envelope and request-ID header."""
    response_headers = dict(headers or {})
    response_headers[_request_id_header(request)] = _request_id(request)
    return JSONResponse(
        status_code=status_code,
        content=_envelope(request, code=code, message=message, details=details),
        headers=response_headers,
    )


class AppError(Exception):
    """Base class for application-defined, client-facing errors.

    Anything raised as (or wrapped into) an ``AppError`` is treated as an
    *expected* failure mode: it carries a stable ``code``, a safe public
    ``message``, an appropriate HTTP status, and optional sanitized
    ``details``. It is not a substitute for server-side logging of the
    real cause when one exists — see ``DatabaseUnavailableError``.
    """

    code: str = "APPLICATION_ERROR"
    status_code: int = status.HTTP_400_BAD_REQUEST

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class DatabaseUnavailableError(AppError):
    """Raised when GET /health/ready's database check fails.

    Deliberately carries no information about the underlying driver
    exception, host, credentials, or connection string — see
    app/db/session.py's ``require_database_ready``.
    """

    code = "DATABASE_UNAVAILABLE"
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    def __init__(self) -> None:
        super().__init__("The database is temporarily unavailable.")


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return _error_response(
        request,
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # Only `loc` and `msg` are surfaced — deliberately not pydantic's
    # `input`/`ctx` keys, which can echo back the client's raw submitted
    # value (potentially sensitive in a future phase's request bodies).
    sanitized_errors = [
        {
            "field": ".".join(str(part) for part in error.get("loc", []) if part != "body"),
            "message": error.get("msg", "Invalid value."),
        }
        for error in exc.errors()
    ]
    return _error_response(
        request,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code="VALIDATION_ERROR",
        message="The request could not be validated.",
        details={"errors": sanitized_errors},
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return _error_response(
        request,
        status_code=exc.status_code,
        code=f"HTTP_{exc.status_code}",
        message=str(exc.detail) if exc.detail else "An HTTP error occurred.",
        headers=dict(exc.headers or {}),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Full detail goes to the server-side structured log only; the client
    # only ever receives a generic, stable message. This is the direct
    # fix for docs/AUDIT.md §2.4's "both decorators return str(e) ...
    # directly in the JSON response body" finding.
    logger.exception(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        exc_type=type(exc).__name__,
    )
    return _error_response(
        request,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="INTERNAL_SERVER_ERROR",
        message="An unexpected error occurred. Please try again later.",
    )


EXCEPTION_HANDLERS: dict[Any, Any] = {
    AppError: app_error_handler,
    RequestValidationError: validation_exception_handler,
    StarletteHTTPException: http_exception_handler,
    Exception: unhandled_exception_handler,
}
