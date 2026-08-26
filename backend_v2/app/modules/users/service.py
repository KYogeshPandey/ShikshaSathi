"""Admin-facing, credential-free user directory for profile selectors."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import UserRole
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import UserRead
from app.schemas.pagination import Page


class UserDirectoryService:
    def __init__(self, session: AsyncSession) -> None:
        self._users = UserRepository(session)

    async def list_by_role(
        self,
        role: UserRole,
        *,
        include_inactive: bool,
        limit: int,
        offset: int,
    ) -> Page[UserRead]:
        rows = await self._users.list_by_role(
            role,
            include_inactive=include_inactive,
            limit=limit,
            offset=offset,
        )
        total = await self._users.count_by_role(role, include_inactive=include_inactive)
        return Page[UserRead](
            items=[UserRead.model_validate(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )
