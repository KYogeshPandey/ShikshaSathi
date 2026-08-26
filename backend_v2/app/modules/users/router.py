"""Admin-only user directory used by human-readable profile selectors."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.auth.dependencies import require_roles
from app.modules.users.models import User, UserRole
from app.modules.users.schemas import UserRead
from app.modules.users.service import UserDirectoryService
from app.schemas.pagination import Page

router = APIRouter(prefix="/users", tags=["users"])
AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
Session = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("", response_model=Page[UserRead])
async def list_users(
    _admin: AdminUser,
    session: Session,
    role: UserRole,
    include_inactive: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[UserRead]:
    return await UserDirectoryService(session).list_by_role(
        role,
        include_inactive=include_inactive,
        limit=limit,
        offset=offset,
    )
