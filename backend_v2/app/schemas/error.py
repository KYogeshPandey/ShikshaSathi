"""Standard error-response envelope shared by every exception handler.

See docs/ARCHITECTURE.md §7 and docs/HANDOVER_PHASE_1.md for the target
shape:

    {
      "error": {"code": "...", "message": "...", "details": {}},
      "request_id": "..."
    }

This directly replaces the legacy pattern of ad hoc per-route
``try/except`` blocks returning ``str(exception)`` to the client
(docs/AUDIT.md §2.4, §2.7).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str = Field(
        ...,
        description="Machine-readable error code, e.g. 'DATABASE_UNAVAILABLE'.",
    )
    message: str = Field(
        ...,
        description="Human-readable, client-safe error message. Never a raw exception.",
    )
    details: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Optional sanitized extra context (e.g. field-level validation "
            "errors). Never contains secrets, stack traces, or raw driver "
            "exception text."
        ),
    )


class ErrorResponse(BaseModel):
    error: ErrorDetail
    request_id: str = Field(
        ...,
        description=(
            "Correlation ID for this request; also present in the X-Request-ID response header."
        ),
    )
