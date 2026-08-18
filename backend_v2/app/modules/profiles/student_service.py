"""Student-profile management and classroom membership orchestration."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.transaction import service_transaction
from app.modules.academics.repository import ClassroomRepository
from app.modules.auth.authorization import require_own_profile
from app.modules.profiles.errors import (
    ClassroomMembershipReferenceError,
    InactiveClassroomMembershipError,
    InactiveProfileUserError,
    InvalidClassroomMembershipError,
    StudentProfileNotFoundError,
)
from app.modules.profiles.models import StudentProfile
from app.modules.profiles.repository import StudentProfileRepository
from app.modules.profiles.schemas import (
    StudentProfileCreate,
    StudentProfileRead,
    StudentProfileUpdate,
)
from app.modules.users.models import User, UserRole
from app.modules.users.repository import UserRepository
from app.schemas.pagination import Page


class StudentProfileService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._profiles = StudentProfileRepository(session)
        self._classrooms = ClassroomRepository(session)
        self._users = UserRepository(session)

    async def _validate_classroom(self, classroom_id: uuid.UUID | None) -> None:
        if classroom_id is None:
            return
        classroom = await self._classrooms.get_by_id(classroom_id)
        if classroom is None:
            raise ClassroomMembershipReferenceError()
        if not classroom.is_active:
            raise InactiveClassroomMembershipError()

    async def list(
        self, *, include_inactive: bool, limit: int, offset: int
    ) -> Page[StudentProfileRead]:
        rows = await self._profiles.list(
            include_inactive=include_inactive, limit=limit, offset=offset
        )
        total = await self._profiles.count(include_inactive=include_inactive)
        return Page[StudentProfileRead](
            items=[StudentProfileRead.model_validate(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_for_user(
        self, current_user: User, profile_id: uuid.UUID | None = None
    ) -> StudentProfile:
        if profile_id is None:
            profile = await self._profiles.get_by_user_id(current_user.id)
        else:
            profile = await self._profiles.get_by_id(profile_id)
        if profile is None:
            raise StudentProfileNotFoundError()
        if current_user.role is not UserRole.ADMIN:
            require_own_profile(
                current_user=current_user,
                profile_user_id=profile.user_id,
                not_found=StudentProfileNotFoundError,
            )
            if not profile.is_active:
                raise StudentProfileNotFoundError()
        return profile

    async def create(self, payload: StudentProfileCreate) -> StudentProfile:
        async with service_transaction(self._session):
            user = await self._users.get_by_id(payload.user_id)
            if user is not None and not user.is_active:
                raise InactiveProfileUserError()
            await self._validate_classroom(payload.classroom_id)
            return await self._profiles.create(**payload.model_dump())

    async def update(self, profile_id: uuid.UUID, payload: StudentProfileUpdate) -> StudentProfile:
        async with service_transaction(self._session):
            profile = await self._profiles.get_by_id(profile_id)
            if profile is None:
                raise StudentProfileNotFoundError()
            changes = payload.model_dump(exclude_unset=True)
            if changes.get("is_active"):
                user = await self._users.get_by_id(profile.user_id)
                if user is None or not user.is_active:
                    raise InactiveProfileUserError()
            if "classroom_id" in changes:
                classroom_id = changes["classroom_id"]
                assert isinstance(classroom_id, uuid.UUID) or classroom_id is None
                await self._validate_classroom(classroom_id)
                if classroom_id is None and "roll_number" not in changes:
                    changes["roll_number"] = None
            resulting_classroom_id = changes.get("classroom_id", profile.classroom_id)
            resulting_roll_number = changes.get("roll_number", profile.roll_number)
            if resulting_classroom_id is None and resulting_roll_number is not None:
                raise InvalidClassroomMembershipError()
            if changes.get("is_active") and isinstance(resulting_classroom_id, uuid.UUID):
                await self._validate_classroom(resulting_classroom_id)
            return await self._profiles.update(profile, **changes)

    async def deactivate(self, profile_id: uuid.UUID) -> StudentProfile:
        async with service_transaction(self._session):
            profile = await self._profiles.get_by_id(profile_id)
            if profile is None:
                raise StudentProfileNotFoundError()
            return await self._profiles.deactivate(profile)
