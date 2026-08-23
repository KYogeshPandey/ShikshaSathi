"""Authenticated, identity-derived dashboard analytics endpoint."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.analytics.schemas import (
    AnalyticsOverviewResponse,
    AnalyticsWindowDays,
)
from app.modules.analytics.service import AnalyticsService
from app.modules.auth.dependencies import get_current_active_user
from app.modules.users.models import User

router = APIRouter(prefix="/analytics", tags=["analytics"])

CurrentUser = Annotated[User, Depends(get_current_active_user)]
Session = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/overview", response_model=AnalyticsOverviewResponse)
async def get_analytics_overview(
    current_user: CurrentUser,
    session: Session,
    days: Annotated[AnalyticsWindowDays, Query()] = AnalyticsWindowDays.SEVEN,
    date_to: date | None = None,
) -> AnalyticsOverviewResponse:
    """Return bounded analytics derived only from the caller's role and identity."""
    return await AnalyticsService(session).overview(
        current_user,
        days=days,
        date_to=date_to or date.today(),
    )


__all__ = ["router"]
