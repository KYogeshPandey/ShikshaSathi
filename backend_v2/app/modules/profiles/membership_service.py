"""Student classroom-membership assignment orchestration."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.transaction import service_transaction
from app.modules.academics.repository import ClassroomRepository
from app.modules.profiles.errors import (
    ClassroomMembershipReferenceError,
    InactiveClassroomMembershipError,
    StudentProfileNotFoundError,
)
from app.modules.profiles.models import StudentProfile
from app.modules.profiles.repository import StudentProfileRepository
from app.modules.profiles.schemas import StudentClassroomMembershipUpdate


class StudentClassroomMembershipService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._profiles = StudentProfileRepository(session)
        self._classrooms = ClassroomRepository(session)

    async def _validate_classroom(self, classroom_id: uuid.UUID | None) -> None:
        if classroom_id is None:
            return
        classroom = await self._classrooms.get_by_id(classroom_id)
        if classroom is None:
            raise ClassroomMembershipReferenceError()
        if not classroom.is_active:
            raise InactiveClassroomMembershipError()

    async def assign(
        self, profile_id: uuid.UUID, payload: StudentClassroomMembershipUpdate
    ) -> StudentProfile:
        async with service_transaction(self._session):
            profile = await self._profiles.get_by_id(profile_id)
            if profile is None:
                raise StudentProfileNotFoundError()
            await self._validate_classroom(payload.classroom_id)
            return await self._profiles.assign_classroom(
                profile,
                classroom_id=payload.classroom_id,
                roll_number=payload.roll_number,
            )
