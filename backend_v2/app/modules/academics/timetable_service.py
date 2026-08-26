"""Timetable management and assignment-based access."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.transaction import service_transaction
from app.modules.academics.errors import (
    InactiveAcademicReferenceError,
    TimetableAssignmentRequiredError,
    TimetableEntryNotFoundError,
    TimetableReferenceError,
)
from app.modules.academics.models import TimetableEntry
from app.modules.academics.repository import (
    ClassroomRepository,
    SubjectRepository,
    TeacherAssignmentRepository,
    TimetableRepository,
)
from app.modules.academics.schemas import (
    TimetableEntryCreate,
    TimetableEntryRead,
    TimetableEntryUpdate,
)
from app.modules.auth.authorization import require_related_resource
from app.modules.profiles.repository import StudentProfileRepository, TeacherProfileRepository
from app.modules.users.models import User, UserRole
from app.modules.users.repository import UserRepository
from app.schemas.pagination import Page


class TimetableService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._timetable = TimetableRepository(session)
        self._assignments = TeacherAssignmentRepository(session)
        self._classrooms = ClassroomRepository(session)
        self._subjects = SubjectRepository(session)
        self._teachers = TeacherProfileRepository(session)
        self._students = StudentProfileRepository(session)
        self._users = UserRepository(session)

    async def _validate_references(
        self, *, classroom_id: uuid.UUID, subject_id: uuid.UUID, teacher_profile_id: uuid.UUID
    ) -> None:
        classroom = await self._classrooms.get_by_id(classroom_id)
        subject = await self._subjects.get_by_id(subject_id)
        teacher = await self._teachers.get_by_id(teacher_profile_id)
        if classroom is None or subject is None or teacher is None:
            raise TimetableReferenceError()
        teacher_user = await self._users.get_by_id(teacher.user_id)
        if (
            not classroom.is_active
            or not subject.is_active
            or not teacher.is_active
            or teacher_user is None
            or not teacher_user.is_active
        ):
            raise InactiveAcademicReferenceError()
        if not await self._assignments.exists(
            classroom_id=classroom_id,
            subject_id=subject_id,
            teacher_profile_id=teacher_profile_id,
            active_only=True,
        ):
            raise TimetableAssignmentRequiredError()

    async def list_for_user(
        self,
        current_user: User,
        *,
        classroom_id: uuid.UUID | None = None,
        include_inactive: bool,
        limit: int,
        offset: int,
    ) -> Page[TimetableEntryRead]:
        if current_user.role is UserRole.ADMIN:
            rows = await self._timetable.list(
                classroom_id=classroom_id,
                include_inactive=include_inactive,
                limit=limit,
                offset=offset,
            )
            total = await self._timetable.count(
                classroom_id=classroom_id,
                include_inactive=include_inactive,
            )
        elif current_user.role is UserRole.TEACHER:
            teacher_profile = await self._teachers.get_by_user_id(current_user.id)
            if teacher_profile is None or not teacher_profile.is_active:
                rows, total = [], 0
            else:
                rows = await self._timetable.list_by_teacher(
                    teacher_profile.id, limit=limit, offset=offset
                )
                total = await self._timetable.count_by_teacher(teacher_profile.id)
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
                rows = await self._timetable.list_by_classroom(
                    classroom.id, limit=limit, offset=offset
                )
                total = await self._timetable.count_by_classroom(classroom.id)
        return Page[TimetableEntryRead](
            items=[TimetableEntryRead.model_validate(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_for_user(self, current_user: User, entry_id: uuid.UUID) -> TimetableEntry:
        entry = await self._timetable.get_by_id(entry_id)
        if entry is None:
            raise TimetableEntryNotFoundError()
        if current_user.role is UserRole.ADMIN:
            return entry
        if not entry.is_active:
            raise TimetableEntryNotFoundError()
        entry_classroom = await self._classrooms.get_by_id(entry.classroom_id)
        entry_subject = await self._subjects.get_by_id(entry.subject_id)
        entry_teacher = await self._teachers.get_by_id(entry.teacher_profile_id)
        entry_teacher_user = (
            await self._users.get_by_id(entry_teacher.user_id)
            if entry_teacher is not None
            else None
        )
        if (
            entry_classroom is None
            or not entry_classroom.is_active
            or entry_subject is None
            or not entry_subject.is_active
            or entry_teacher is None
            or not entry_teacher.is_active
            or entry_teacher_user is None
            or not entry_teacher_user.is_active
        ):
            raise TimetableEntryNotFoundError()
        if current_user.role is UserRole.TEACHER:
            teacher_profile = await self._teachers.get_by_user_id(current_user.id)
            has_assignment = (
                await self._assignments.exists(
                    teacher_profile_id=entry.teacher_profile_id,
                    classroom_id=entry.classroom_id,
                    subject_id=entry.subject_id,
                    active_only=True,
                )
                if teacher_profile is not None
                else False
            )
            allowed = (
                {entry.id}
                if teacher_profile is not None
                and teacher_profile.is_active
                and entry.teacher_profile_id == teacher_profile.id
                and has_assignment
                else set()
            )
        else:
            student_profile = await self._students.get_by_user_id(current_user.id)
            classroom = (
                await self._classrooms.get_by_id(student_profile.classroom_id)
                if student_profile is not None and student_profile.classroom_id is not None
                else None
            )
            has_assignment = await self._assignments.exists(
                teacher_profile_id=entry.teacher_profile_id,
                classroom_id=entry.classroom_id,
                subject_id=entry.subject_id,
                active_only=True,
            )
            allowed = (
                {entry.id}
                if student_profile is not None
                and student_profile.is_active
                and classroom is not None
                and classroom.is_active
                and classroom.id == entry.classroom_id
                and has_assignment
                else set()
            )
        require_related_resource(
            resource_id=entry_id,
            allowed_ids=allowed,
            not_found=TimetableEntryNotFoundError,
        )
        return entry

    async def create(self, payload: TimetableEntryCreate) -> TimetableEntry:
        async with service_transaction(self._session):
            await self._validate_references(
                classroom_id=payload.classroom_id,
                subject_id=payload.subject_id,
                teacher_profile_id=payload.teacher_profile_id,
            )
            return await self._timetable.create(**payload.model_dump())

    async def update(self, entry_id: uuid.UUID, payload: TimetableEntryUpdate) -> TimetableEntry:
        async with service_transaction(self._session):
            entry = await self._timetable.get_by_id(entry_id)
            if entry is None:
                raise TimetableEntryNotFoundError()
            changes = payload.model_dump(exclude_unset=True)
            classroom_id = changes.get("classroom_id", entry.classroom_id)
            subject_id = changes.get("subject_id", entry.subject_id)
            teacher_profile_id = changes.get("teacher_profile_id", entry.teacher_profile_id)
            assert isinstance(classroom_id, uuid.UUID)
            assert isinstance(subject_id, uuid.UUID)
            assert isinstance(teacher_profile_id, uuid.UUID)
            if changes.get("is_active", entry.is_active):
                await self._validate_references(
                    classroom_id=classroom_id,
                    subject_id=subject_id,
                    teacher_profile_id=teacher_profile_id,
                )
            return await self._timetable.update(entry, **changes)

    async def deactivate(self, entry_id: uuid.UUID) -> TimetableEntry:
        async with service_transaction(self._session):
            entry = await self._timetable.get_by_id(entry_id)
            if entry is None:
                raise TimetableEntryNotFoundError()
            return await self._timetable.deactivate(entry)
