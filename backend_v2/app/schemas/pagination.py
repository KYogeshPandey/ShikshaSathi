"""Shared offset-pagination response model."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Page[ItemT](BaseModel):
    items: list[ItemT]
    total: int = Field(..., ge=0)
    limit: int = Field(..., ge=1, le=100)
    offset: int = Field(..., ge=0)
