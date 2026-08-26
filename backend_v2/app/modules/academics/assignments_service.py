"""Teacher-assignment management orchestration."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.transaction import service_transaction
from app.modules.academics.errors import (
    InactiveAcademicReferenceError,
    TeacherAssignmentNotFoundError,
    TeacherAssignmentReferenceError,
)
from app.modules.academics.models import TeacherAssignment
from app.modules.academics.repository import (
    ClassroomRepository,
    SubjectRepository,
    TeacherAssignmentRepository,
)
from app.modules.academics.schemas import (
    TeacherAssignmentCreate,
    TeacherAssignmentRead,
    TeacherAssignmentUpdate,
)
from app.modules.profiles.repository import TeacherProfileRepository
from app.modules.users.repository import UserRepository
from app.schemas.pagination import Page


class TeacherAssignmentService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._assignments = TeacherAssignmentRepository(session)
        self._teachers = TeacherProfileRepository(session)
        self._classrooms = ClassroomRepository(session)
        self._subjects = SubjectRepository(session)
        self._users = UserRepository(session)

    async def _validate_references(
        self, *, teacher_profile_id: uuid.UUID, classroom_id: uuid.UUID, subject_id: uuid.UUID
    ) -> None:
        teacher = await self._teachers.get_by_id(teacher_profile_id)
        classroom = await self._classrooms.get_by_id(classroom_id)
        subject = await self._subjects.get_by_id(subject_id)
        if teacher is None or classroom is None or subject is None:
            raise TeacherAssignmentReferenceError()
        user = await self._users.get_by_id(teacher.user_id)
        if (
            not teacher.is_active
            or user is None
            or not user.is_active
            or not classroom.is_active
            or not subject.is_active
        ):
            raise InactiveAcademicReferenceError()

    async def list(
        self,
        *,
        classroom_id: uuid.UUID | None = None,
        include_inactive: bool,
        limit: int,
        offset: int,
    ) -> Page[TeacherAssignmentRead]:
        rows = await self._assignments.list(
            classroom_id=classroom_id,
            include_inactive=include_inactive,
            limit=limit,
            offset=offset,
        )
        total = await self._assignments.count(
            classroom_id=classroom_id,
            include_inactive=include_inactive,
        )
        return Page[TeacherAssignmentRead](
            items=[TeacherAssignmentRead.model_validate(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get(self, assignment_id: uuid.UUID) -> TeacherAssignment:
        assignment = await self._assignments.get_by_id(assignment_id)
        if assignment is None:
            raise TeacherAssignmentNotFoundError()
        return assignment

    async def create(self, payload: TeacherAssignmentCreate) -> TeacherAssignment:
        async with service_transaction(self._session):
            await self._validate_references(**payload.model_dump())
            return await self._assignments.create(**payload.model_dump())

    async def update(
        self, assignment_id: uuid.UUID, payload: TeacherAssignmentUpdate
    ) -> TeacherAssignment:
        async with service_transaction(self._session):
            assignment = await self._assignments.get_by_id(assignment_id)
            if assignment is None:
                raise TeacherAssignmentNotFoundError()
            if payload.is_active:
                await self._validate_references(
                    teacher_profile_id=assignment.teacher_profile_id,
                    classroom_id=assignment.classroom_id,
                    subject_id=assignment.subject_id,
                )
            return await self._assignments.update(assignment, is_active=payload.is_active)

    async def deactivate(self, assignment_id: uuid.UUID) -> TeacherAssignment:
        async with service_transaction(self._session):
            assignment = await self._assignments.get_by_id(assignment_id)
            if assignment is None:
                raise TeacherAssignmentNotFoundError()
            return await self._assignments.deactivate(assignment)
