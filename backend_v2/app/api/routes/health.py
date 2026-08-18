"""Liveness and readiness endpoints.

- GET /health/live  — process is alive; never touches PostgreSQL.
- GET /health/ready — infrastructure is actually ready; runs a real
  ``SELECT 1`` against PostgreSQL and returns a sanitized HTTP 503 if
  that fails. This directly replaces the legacy app's shallow health
  check, which reported ``{"status": "ok"}`` even with MongoDB
  unreachable (docs/AUDIT.md §2.2).

Both endpoints are mounted unversioned (not under ``API_V1_PREFIX``) —
see app/api/router.py and app/main.py.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.db.session import require_database_ready
from app.schemas.health import LivenessResponse, ReadinessResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get(
    "/live",
    response_model=LivenessResponse,
    summary="Liveness probe",
    description="Confirms the FastAPI process itself is running. Never touches PostgreSQL.",
)
async def liveness() -> LivenessResponse:
    return LivenessResponse(status="alive")


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    description=(
        "Confirms required infrastructure is reachable by running a real "
        "`SELECT 1` against PostgreSQL. Returns HTTP 503 with the "
        "standard sanitized error envelope — never a raw database "
        "exception — if that check fails."
    ),
    responses={503: {"description": "Database is unavailable."}},
)
async def readiness(_: Annotated[None, Depends(require_database_ready)]) -> ReadinessResponse:
    return ReadinessResponse(status="ready", checks={"database": "ready"})
