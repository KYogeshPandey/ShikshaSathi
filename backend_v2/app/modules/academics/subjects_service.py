"""Subject orchestration and role-scoped reads."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.transaction import service_transaction
from app.modules.academics.errors import SubjectNotFoundError
from app.modules.academics.models import Subject
from app.modules.academics.repository import (
    ClassroomRepository,
    SubjectRepository,
)
from app.modules.academics.schemas import SubjectCreate, SubjectRead, SubjectUpdate
from app.modules.auth.authorization import require_related_resource
from app.modules.profiles.repository import StudentProfileRepository, TeacherProfileRepository
from app.modules.users.models import User, UserRole
from app.schemas.pagination import Page


class SubjectService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._subjects = SubjectRepository(session)
        self._teachers = TeacherProfileRepository(session)
        self._students = StudentProfileRepository(session)
        self._classrooms = ClassroomRepository(session)

    async def list_for_user(
        self,
        current_user: User,
        *,
        include_inactive: bool,
        limit: int,
        offset: int,
    ) -> Page[SubjectRead]:
        if current_user.role is UserRole.ADMIN:
            rows = await self._subjects.list(
                include_inactive=include_inactive, limit=limit, offset=offset
            )
            total = await self._subjects.count(include_inactive=include_inactive)
        elif current_user.role is UserRole.TEACHER:
            teacher_profile = await self._teachers.get_by_user_id(current_user.id)
            if teacher_profile is None or not teacher_profile.is_active:
                rows, total = [], 0
            else:
                rows = await self._subjects.list_for_teacher(
                    teacher_profile.id, limit=limit, offset=offset
                )
                total = await self._subjects.count_for_teacher(teacher_profile.id)
        else:
            student_profile = await self._students.get_by_user_id(current_user.id)
            classroom = (
                await self._classrooms.get_by_id(student_profile.classroom_id)
                if student_profile is not None and student_profile.classroom_id is not None
                else None
            )
            if (
                student_profile is None
                or not student_profile.is_active
                or classroom is None
                or not classroom.is_active
            ):
                rows, total = [], 0
            else:
                rows = await self._subjects.list_for_classroom(
                    classroom.id, limit=limit, offset=offset
                )
                total = await self._subjects.count_for_classroom(classroom.id)
        return Page[SubjectRead](
            items=[SubjectRead.model_validate(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_for_user(self, current_user: User, subject_id: uuid.UUID) -> Subject:
        subject = await self._subjects.get_by_id(subject_id)
        if subject is None:
            raise SubjectNotFoundError()
        if current_user.role is UserRole.ADMIN:
            return subject
        if not subject.is_active:
            raise SubjectNotFoundError()
        if current_user.role is UserRole.TEACHER:
            teacher_profile = await self._teachers.get_by_user_id(current_user.id)
            allowed = (
                await self._subjects.is_available_for_teacher(
                    subject_id=subject_id,
                    teacher_profile_id=teacher_profile.id,
                )
                if teacher_profile is not None and teacher_profile.is_active
                else False
            )
        else:
            student_profile = await self._students.get_by_user_id(current_user.id)
            classroom = (
                await self._classrooms.get_by_id(student_profile.classroom_id)
                if student_profile is not None and student_profile.classroom_id is not None
                else None
            )
            allowed = (
                await self._subjects.is_available_for_classroom(
                    subject_id=subject_id,
                    classroom_id=classroom.id,
                )
                if student_profile is not None
                and student_profile.is_active
                and classroom is not None
                and classroom.is_active
                else False
            )
        require_related_resource(
            resource_id=subject_id,
            allowed_ids={subject_id} if allowed else set(),
            not_found=SubjectNotFoundError,
        )
        return subject

    async def create(self, payload: SubjectCreate) -> Subject:
        async with service_transaction(self._session):
            return await self._subjects.create(**payload.model_dump())

    async def update(self, subject_id: uuid.UUID, payload: SubjectUpdate) -> Subject:
        async with service_transaction(self._session):
            subject = await self._subjects.get_by_id(subject_id)
            if subject is None:
                raise SubjectNotFoundError()
            return await self._subjects.update(subject, **payload.model_dump(exclude_unset=True))

    async def deactivate(self, subject_id: uuid.UUID) -> Subject:
        async with service_transaction(self._session):
            subject = await self._subjects.get_by_id(subject_id)
            if subject is None:
                raise SubjectNotFoundError()
            return await self._subjects.deactivate(subject)
