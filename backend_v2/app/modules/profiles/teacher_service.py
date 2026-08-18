"""Teacher-profile management and private-profile authorization."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.transaction import service_transaction
from app.modules.auth.authorization import require_own_profile
from app.modules.profiles.errors import InactiveProfileUserError, TeacherProfileNotFoundError
from app.modules.profiles.models import TeacherProfile
from app.modules.profiles.repository import TeacherProfileRepository
from app.modules.profiles.schemas import (
    TeacherProfileCreate,
    TeacherProfileRead,
    TeacherProfileUpdate,
)
from app.modules.users.models import User, UserRole
from app.modules.users.repository import UserRepository
from app.schemas.pagination import Page


class TeacherProfileService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._profiles = TeacherProfileRepository(session)
        self._users = UserRepository(session)

    async def list(
        self, *, include_inactive: bool, limit: int, offset: int
    ) -> Page[TeacherProfileRead]:
        rows = await self._profiles.list(
            include_inactive=include_inactive, limit=limit, offset=offset
        )
        total = await self._profiles.count(include_inactive=include_inactive)
        return Page[TeacherProfileRead](
            items=[TeacherProfileRead.model_validate(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_for_user(
        self, current_user: User, profile_id: uuid.UUID | None = None
    ) -> TeacherProfile:
        if profile_id is None:
            profile = await self._profiles.get_by_user_id(current_user.id)
        else:
            profile = await self._profiles.get_by_id(profile_id)
        if profile is None:
            raise TeacherProfileNotFoundError()
        if current_user.role is not UserRole.ADMIN:
            require_own_profile(
                current_user=current_user,
                profile_user_id=profile.user_id,
                not_found=TeacherProfileNotFoundError,
            )
            if not profile.is_active:
                raise TeacherProfileNotFoundError()
        return profile

    async def create(self, payload: TeacherProfileCreate) -> TeacherProfile:
        async with service_transaction(self._session):
            user = await self._users.get_by_id(payload.user_id)
            if user is not None and not user.is_active:
                raise InactiveProfileUserError()
            return await self._profiles.create(**payload.model_dump())

    async def update(self, profile_id: uuid.UUID, payload: TeacherProfileUpdate) -> TeacherProfile:
        async with service_transaction(self._session):
            profile = await self._profiles.get_by_id(profile_id)
            if profile is None:
                raise TeacherProfileNotFoundError()
            if payload.is_active:
                user = await self._users.get_by_id(profile.user_id)
                if user is None or not user.is_active:
                    raise InactiveProfileUserError()
            return await self._profiles.update(profile, **payload.model_dump(exclude_unset=True))

    async def deactivate(self, profile_id: uuid.UUID) -> TeacherProfile:
        async with service_transaction(self._session):
            profile = await self._profiles.get_by_id(profile_id)
            if profile is None:
                raise TeacherProfileNotFoundError()
            return await self._profiles.deactivate(profile)
