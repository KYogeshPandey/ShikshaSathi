"""Classroom orchestration and object-level authorization."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.transaction import service_transaction
from app.modules.academics.errors import ClassroomNotFoundError
from app.modules.academics.models import Classroom
from app.modules.academics.repository import ClassroomRepository
from app.modules.academics.schemas import ClassroomCreate, ClassroomRead, ClassroomUpdate
from app.modules.auth.authorization import require_related_resource
from app.modules.profiles.repository import StudentProfileRepository, TeacherProfileRepository
from app.modules.users.models import User, UserRole
from app.schemas.pagination import Page


class ClassroomService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._classrooms = ClassroomRepository(session)
        self._teachers = TeacherProfileRepository(session)
        self._students = StudentProfileRepository(session)

    async def list_for_user(
        self,
        current_user: User,
        *,
        include_inactive: bool,
        limit: int,
        offset: int,
    ) -> Page[ClassroomRead]:
        if current_user.role is UserRole.ADMIN:
            rows = await self._classrooms.list(
                include_inactive=include_inactive, limit=limit, offset=offset
            )
            total = await self._classrooms.count(include_inactive=include_inactive)
        elif current_user.role is UserRole.TEACHER:
            teacher_profile = await self._teachers.get_by_user_id(current_user.id)
            if teacher_profile is None or not teacher_profile.is_active:
                rows, total = [], 0
            else:
                rows = await self._classrooms.list_for_teacher(
                    teacher_profile.id, limit=limit, offset=offset
                )
                total = await self._classrooms.count_for_teacher(teacher_profile.id)
        else:
            student_profile = await self._students.get_by_user_id(current_user.id)
            classroom = (
                await self._classrooms.get_by_id(student_profile.classroom_id)
                if student_profile is not None
                and student_profile.is_active
                and student_profile.classroom_id is not None
                else None
            )
            rows = (
                [classroom] if classroom is not None and classroom.is_active and offset == 0 else []
            )
            total = 1 if classroom is not None and classroom.is_active else 0
        return Page[ClassroomRead](
            items=[ClassroomRead.model_validate(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_for_user(self, current_user: User, classroom_id: uuid.UUID) -> Classroom:
        classroom = await self._classrooms.get_by_id(classroom_id)
        if classroom is None:
            raise ClassroomNotFoundError()
        if current_user.role is UserRole.ADMIN:
            return classroom
        if not classroom.is_active:
            raise ClassroomNotFoundError()
        if current_user.role is UserRole.TEACHER:
            teacher_profile = await self._teachers.get_by_user_id(current_user.id)
            allowed = (
                set(await self._classrooms.list_ids_for_teacher(teacher_profile.id))
                if teacher_profile is not None and teacher_profile.is_active
                else set()
            )
        else:
            student_profile = await self._students.get_by_user_id(current_user.id)
            allowed = (
                {student_profile.classroom_id}
                if student_profile is not None
                and student_profile.is_active
                and student_profile.classroom_id is not None
                else set()
            )
        require_related_resource(
            resource_id=classroom_id,
            allowed_ids=allowed,
            not_found=ClassroomNotFoundError,
        )
        return classroom

    async def create(self, payload: ClassroomCreate) -> Classroom:
        async with service_transaction(self._session):
            return await self._classrooms.create(**payload.model_dump())

    async def update(self, classroom_id: uuid.UUID, payload: ClassroomUpdate) -> Classroom:
        async with service_transaction(self._session):
            classroom = await self._classrooms.get_by_id(classroom_id)
            if classroom is None:
                raise ClassroomNotFoundError()
            return await self._classrooms.update(
                classroom, **payload.model_dump(exclude_unset=True)
            )

    async def deactivate(self, classroom_id: uuid.UUID) -> Classroom:
        async with service_transaction(self._session):
            classroom = await self._classrooms.get_by_id(classroom_id)
            if classroom is None:
                raise ClassroomNotFoundError()
            return await self._classrooms.deactivate(classroom)
