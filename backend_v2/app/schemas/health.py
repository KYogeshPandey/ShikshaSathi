"""Response schemas for the liveness/readiness/root endpoints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LivenessResponse(BaseModel):
    status: Literal["alive"] = Field(
        default="alive",
        description="Always 'alive' when this endpoint responds at all.",
    )


class ReadinessResponse(BaseModel):
    status: Literal["ready"] = Field(
        default="ready",
        description="'ready' only when every check below passed.",
    )
    checks: dict[str, str] = Field(
        ...,
        description="Per-dependency status, e.g. {'database': 'ready'}.",
    )


class RootResponse(BaseModel):
    name: str = Field(..., description="Application name.")
    version: str = Field(..., description="Application version.")
    docs: str = Field(..., description="Path to the interactive OpenAPI docs.")
    health: dict[str, str] = Field(..., description="Paths to the liveness and readiness checks.")
