"""Repositories for the academic domain.

Follows the same conventions as ``app.modules.users.repository``: thin,
single-aggregate (or single-association) data access, no unexpected
commits (callers own the transaction boundary and only ``flush()`` is
called here to surface a constraint violation), and integrity errors are
translated into stable, named domain errors rather than left as raw
``IntegrityError``s.
"""

from __future__ import annotations

import builtins
import uuid
from datetime import time

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.academics.errors import (
    ClassroomCodeAlreadyExistsError,
    DuplicateTeacherAssignmentError,
    InvalidTimetableSlotError,
    SubjectCodeAlreadyExistsError,
    TeacherAssignmentReferenceError,
    TimetableCollisionError,
    TimetableReferenceError,
)
from app.modules.academics.models import (
    Classroom,
    DayOfWeek,
    Subject,
    TeacherAssignment,
    TimetableEntry,
)
from app.modules.profiles.models import TeacherProfile
from app.modules.users.models import User

_CLASSROOM_CODE_CONSTRAINT = "uq_classrooms_code"
_SUBJECT_CODE_CONSTRAINT = "uq_subjects_code"
_TEACHER_ASSIGNMENT_UNIQUE_CONSTRAINT = "uq_teacher_assignments_teacher_classroom_subject"
_TIMETABLE_CLASSROOM_DAY_START_CONSTRAINT = "uq_timetable_entries_classroom_day_start"
_TIMETABLE_TEACHER_DAY_START_CONSTRAINT = "uq_timetable_entries_teacher_day_start"
_TIMETABLE_START_BEFORE_END_CONSTRAINT = "ck_timetable_entries_start_before_end"


def _constraint_name(exc: IntegrityError) -> str | None:
    """Best-effort extraction of the violated constraint's name.

    Same pattern as ``app.modules.users.repository._is_email_unique_violation``:
    check the driver exception's ``constraint_name`` attribute first, then
    fall back to matching the constraint name inside the stringified
    original exception (stable across asyncpg adapter patch versions).
    """
    candidates = (
        exc.orig,
        getattr(exc.orig, "__cause__", None),
        getattr(exc.orig, "__context__", None),
    )
    for candidate in candidates:
        name = getattr(candidate, "constraint_name", None)
        if name:
            return str(name)
    return None


def _matches_constraint(exc: IntegrityError, constraint_name: str) -> bool:
    name = _constraint_name(exc)
    if name == constraint_name:
        return True
    return constraint_name in str(exc.orig)


class ClassroomRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, classroom_id: uuid.UUID) -> Classroom | None:
        return await self._session.get(Classroom, classroom_id)

    async def get_by_code(self, code: str) -> Classroom | None:
        """Look up by code. ``code`` must already be normalized by the caller."""
        stmt = select(Classroom).where(Classroom.code == code)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(
        self, *, include_inactive: bool = False, limit: int = 50, offset: int = 0
    ) -> builtins.list[Classroom]:
        stmt = select(Classroom).order_by(Classroom.code).limit(limit).offset(offset)
        if not include_inactive:
            stmt = stmt.where(Classroom.is_active.is_(True))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, *, include_inactive: bool = False) -> int:
        stmt = select(func.count()).select_from(Classroom)
        if not include_inactive:
            stmt = stmt.where(Classroom.is_active.is_(True))
        return int((await self._session.execute(stmt)).scalar_one())

    async def list_for_teacher(
        self, teacher_profile_id: uuid.UUID, *, limit: int, offset: int
    ) -> builtins.list[Classroom]:
        stmt = (
            select(Classroom)
            .join(TeacherAssignment, TeacherAssignment.classroom_id == Classroom.id)
            .where(
                TeacherAssignment.teacher_profile_id == teacher_profile_id,
                TeacherAssignment.is_active.is_(True),
                Classroom.is_active.is_(True),
            )
            .distinct()
            .order_by(Classroom.code)
            .limit(limit)
            .offset(offset)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def count_for_teacher(self, teacher_profile_id: uuid.UUID) -> int:
        stmt = (
            select(func.count(func.distinct(Classroom.id)))
            .select_from(Classroom)
            .join(TeacherAssignment, TeacherAssignment.classroom_id == Classroom.id)
            .where(
                TeacherAssignment.teacher_profile_id == teacher_profile_id,
                TeacherAssignment.is_active.is_(True),
                Classroom.is_active.is_(True),
            )
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def list_ids_for_teacher(self, teacher_profile_id: uuid.UUID) -> builtins.list[uuid.UUID]:
        stmt = (
            select(Classroom.id)
            .join(TeacherAssignment, TeacherAssignment.classroom_id == Classroom.id)
            .where(
                TeacherAssignment.teacher_profile_id == teacher_profile_id,
                TeacherAssignment.is_active.is_(True),
                Classroom.is_active.is_(True),
            )
            .distinct()
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def create(
        self,
        *,
        name: str,
        code: str,
        grade_level: str | None = None,
        section: str | None = None,
    ) -> Classroom:
        classroom = Classroom(name=name, code=code, grade_level=grade_level, section=section)
        self._session.add(classroom)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            if _matches_constraint(exc, _CLASSROOM_CODE_CONSTRAINT):
                raise ClassroomCodeAlreadyExistsError() from exc
            raise
        return classroom

    async def update(self, classroom: Classroom, **changes: object) -> Classroom:
        for field, value in changes.items():
            setattr(classroom, field, value)
        await self._session.flush()
        await self._session.refresh(classroom)
        return classroom

    async def deactivate(self, classroom: Classroom) -> Classroom:
        classroom.is_active = False
        await self._session.flush()
        await self._session.refresh(classroom)
        return classroom


class SubjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, subject_id: uuid.UUID) -> Subject | None:
        return await self._session.get(Subject, subject_id)

    async def get_by_code(self, code: str) -> Subject | None:
        """Look up by code. ``code`` must already be normalized by the caller."""
        stmt = select(Subject).where(Subject.code == code)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(
        self, *, include_inactive: bool = False, limit: int = 50, offset: int = 0
    ) -> builtins.list[Subject]:
        stmt = select(Subject).order_by(Subject.code).limit(limit).offset(offset)
        if not include_inactive:
            stmt = stmt.where(Subject.is_active.is_(True))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, *, include_inactive: bool = False) -> int:
        stmt = select(func.count()).select_from(Subject)
        if not include_inactive:
            stmt = stmt.where(Subject.is_active.is_(True))
        return int((await self._session.execute(stmt)).scalar_one())

    async def list_for_teacher(
        self, teacher_profile_id: uuid.UUID, *, limit: int, offset: int
    ) -> builtins.list[Subject]:
        stmt = (
            select(Subject)
            .join(TeacherAssignment, TeacherAssignment.subject_id == Subject.id)
            .join(Classroom, Classroom.id == TeacherAssignment.classroom_id)
            .where(
                TeacherAssignment.teacher_profile_id == teacher_profile_id,
                TeacherAssignment.is_active.is_(True),
                Subject.is_active.is_(True),
                Classroom.is_active.is_(True),
            )
            .distinct()
            .order_by(Subject.code)
            .limit(limit)
            .offset(offset)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def count_for_teacher(self, teacher_profile_id: uuid.UUID) -> int:
        stmt = (
            select(func.count(func.distinct(Subject.id)))
            .select_from(Subject)
            .join(TeacherAssignment, TeacherAssignment.subject_id == Subject.id)
            .join(Classroom, Classroom.id == TeacherAssignment.classroom_id)
            .where(
                TeacherAssignment.teacher_profile_id == teacher_profile_id,
                TeacherAssignment.is_active.is_(True),
                Subject.is_active.is_(True),
                Classroom.is_active.is_(True),
            )
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def list_for_classroom(
        self, classroom_id: uuid.UUID, *, limit: int, offset: int
    ) -> builtins.list[Subject]:
        stmt = (
            select(Subject)
            .join(TeacherAssignment, TeacherAssignment.subject_id == Subject.id)
            .join(
                TeacherProfile,
                TeacherProfile.id == TeacherAssignment.teacher_profile_id,
            )
            .join(User, User.id == TeacherProfile.user_id)
            .where(
                TeacherAssignment.classroom_id == classroom_id,
                TeacherAssignment.is_active.is_(True),
                TeacherProfile.is_active.is_(True),
                User.is_active.is_(True),
                Subject.is_active.is_(True),
            )
            .distinct()
            .order_by(Subject.code)
            .limit(limit)
            .offset(offset)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def count_for_classroom(self, classroom_id: uuid.UUID) -> int:
        stmt = (
            select(func.count(func.distinct(Subject.id)))
            .select_from(Subject)
            .join(TeacherAssignment, TeacherAssignment.subject_id == Subject.id)
            .join(
                TeacherProfile,
                TeacherProfile.id == TeacherAssignment.teacher_profile_id,
            )
            .join(User, User.id == TeacherProfile.user_id)
            .where(
                TeacherAssignment.classroom_id == classroom_id,
                TeacherAssignment.is_active.is_(True),
                TeacherProfile.is_active.is_(True),
                User.is_active.is_(True),
                Subject.is_active.is_(True),
            )
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def is_available_for_teacher(
        self, *, subject_id: uuid.UUID, teacher_profile_id: uuid.UUID
    ) -> bool:
        stmt = (
            select(Subject.id)
            .join(TeacherAssignment, TeacherAssignment.subject_id == Subject.id)
            .join(Classroom, Classroom.id == TeacherAssignment.classroom_id)
            .where(
                Subject.id == subject_id,
                Subject.is_active.is_(True),
                TeacherAssignment.teacher_profile_id == teacher_profile_id,
                TeacherAssignment.is_active.is_(True),
                Classroom.is_active.is_(True),
            )
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def is_available_for_classroom(
        self, *, subject_id: uuid.UUID, classroom_id: uuid.UUID
    ) -> bool:
        stmt = (
            select(Subject.id)
            .join(TeacherAssignment, TeacherAssignment.subject_id == Subject.id)
            .join(
                TeacherProfile,
                TeacherProfile.id == TeacherAssignment.teacher_profile_id,
            )
            .join(User, User.id == TeacherProfile.user_id)
            .where(
                Subject.id == subject_id,
                Subject.is_active.is_(True),
                TeacherAssignment.classroom_id == classroom_id,
                TeacherAssignment.is_active.is_(True),
                TeacherProfile.is_active.is_(True),
                User.is_active.is_(True),
            )
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def create(self, *, name: str, code: str, is_elective: bool = False) -> Subject:
        subject = Subject(name=name, code=code, is_elective=is_elective)
        self._session.add(subject)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            if _matches_constraint(exc, _SUBJECT_CODE_CONSTRAINT):
                raise SubjectCodeAlreadyExistsError() from exc
            raise
        return subject

    async def update(self, subject: Subject, **changes: object) -> Subject:
        for field, value in changes.items():
            setattr(subject, field, value)
        await self._session.flush()
        await self._session.refresh(subject)
        return subject

    async def deactivate(self, subject: Subject) -> Subject:
        subject.is_active = False
        await self._session.flush()
        await self._session.refresh(subject)
        return subject


class TeacherAssignmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, assignment_id: uuid.UUID) -> TeacherAssignment | None:
        return await self._session.get(TeacherAssignment, assignment_id)

    async def list_by_teacher(
        self, teacher_profile_id: uuid.UUID, *, include_inactive: bool = False
    ) -> builtins.list[TeacherAssignment]:
        stmt = select(TeacherAssignment).where(
            TeacherAssignment.teacher_profile_id == teacher_profile_id
        )
        if not include_inactive:
            stmt = stmt.where(TeacherAssignment.is_active.is_(True))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_classroom(
        self, classroom_id: uuid.UUID, *, include_inactive: bool = False
    ) -> builtins.list[TeacherAssignment]:
        stmt = select(TeacherAssignment).where(TeacherAssignment.classroom_id == classroom_id)
        if not include_inactive:
            stmt = stmt.where(TeacherAssignment.is_active.is_(True))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list(
        self, *, include_inactive: bool = False, limit: int = 50, offset: int = 0
    ) -> builtins.list[TeacherAssignment]:
        stmt = (
            select(TeacherAssignment)
            .order_by(TeacherAssignment.created_at, TeacherAssignment.id)
            .limit(limit)
            .offset(offset)
        )
        if not include_inactive:
            stmt = stmt.where(TeacherAssignment.is_active.is_(True))
        return list((await self._session.execute(stmt)).scalars().all())

    async def count(self, *, include_inactive: bool = False) -> int:
        stmt = select(func.count()).select_from(TeacherAssignment)
        if not include_inactive:
            stmt = stmt.where(TeacherAssignment.is_active.is_(True))
        return int((await self._session.execute(stmt)).scalar_one())

    async def exists(
        self,
        *,
        teacher_profile_id: uuid.UUID,
        classroom_id: uuid.UUID,
        subject_id: uuid.UUID,
        active_only: bool = False,
    ) -> bool:
        stmt = select(TeacherAssignment.id).where(
            TeacherAssignment.teacher_profile_id == teacher_profile_id,
            TeacherAssignment.classroom_id == classroom_id,
            TeacherAssignment.subject_id == subject_id,
        )
        if active_only:
            stmt = stmt.where(TeacherAssignment.is_active.is_(True))
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def create(
        self,
        *,
        teacher_profile_id: uuid.UUID,
        classroom_id: uuid.UUID,
        subject_id: uuid.UUID,
    ) -> TeacherAssignment:
        """Create an assignment.

        Raises ``DuplicateTeacherAssignmentError`` on a repeated
        (teacher, classroom, subject) triple, or
        ``TeacherAssignmentReferenceError`` if any referenced id does not
        exist (a foreign-key violation) — both mapped from the raw
        ``IntegrityError`` rather than left to propagate.
        """
        assignment = TeacherAssignment(
            teacher_profile_id=teacher_profile_id,
            classroom_id=classroom_id,
            subject_id=subject_id,
        )
        self._session.add(assignment)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            if _matches_constraint(exc, _TEACHER_ASSIGNMENT_UNIQUE_CONSTRAINT):
                raise DuplicateTeacherAssignmentError() from exc
            if (
                "ForeignKeyViolationError" in str(type(exc.orig))
                or "foreign key" in str(exc.orig).lower()
            ):
                raise TeacherAssignmentReferenceError() from exc
            raise
        return assignment

    async def deactivate(self, assignment: TeacherAssignment) -> TeacherAssignment:
        assignment.is_active = False
        await self._session.flush()
        await self._session.refresh(assignment)
        return assignment

    async def update(self, assignment: TeacherAssignment, *, is_active: bool) -> TeacherAssignment:
        assignment.is_active = is_active
        await self._session.flush()
        await self._session.refresh(assignment)
        return assignment


class TimetableRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, entry_id: uuid.UUID) -> TimetableEntry | None:
        return await self._session.get(TimetableEntry, entry_id)

    async def list_by_classroom(
        self, classroom_id: uuid.UUID, *, limit: int | None = None, offset: int = 0
    ) -> builtins.list[TimetableEntry]:
        stmt = (
            select(TimetableEntry)
            .join(
                TeacherAssignment,
                and_(
                    TeacherAssignment.teacher_profile_id == TimetableEntry.teacher_profile_id,
                    TeacherAssignment.classroom_id == TimetableEntry.classroom_id,
                    TeacherAssignment.subject_id == TimetableEntry.subject_id,
                ),
            )
            .join(Classroom, Classroom.id == TimetableEntry.classroom_id)
            .join(Subject, Subject.id == TimetableEntry.subject_id)
            .join(TeacherProfile, TeacherProfile.id == TimetableEntry.teacher_profile_id)
            .join(User, User.id == TeacherProfile.user_id)
            .where(
                TimetableEntry.classroom_id == classroom_id,
                TimetableEntry.is_active.is_(True),
                TeacherAssignment.is_active.is_(True),
                Classroom.is_active.is_(True),
                Subject.is_active.is_(True),
                TeacherProfile.is_active.is_(True),
                User.is_active.is_(True),
            )
            .order_by(
                TimetableEntry.day_of_week,
                TimetableEntry.start_time,
                TimetableEntry.id,
            )
            .offset(offset)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_teacher(
        self, teacher_profile_id: uuid.UUID, *, limit: int | None = None, offset: int = 0
    ) -> builtins.list[TimetableEntry]:
        stmt = (
            select(TimetableEntry)
            .join(
                TeacherAssignment,
                and_(
                    TeacherAssignment.teacher_profile_id == TimetableEntry.teacher_profile_id,
                    TeacherAssignment.classroom_id == TimetableEntry.classroom_id,
                    TeacherAssignment.subject_id == TimetableEntry.subject_id,
                ),
            )
            .join(Classroom, Classroom.id == TimetableEntry.classroom_id)
            .join(Subject, Subject.id == TimetableEntry.subject_id)
            .join(TeacherProfile, TeacherProfile.id == TimetableEntry.teacher_profile_id)
            .join(User, User.id == TeacherProfile.user_id)
            .where(
                TimetableEntry.teacher_profile_id == teacher_profile_id,
                TimetableEntry.is_active.is_(True),
                TeacherAssignment.is_active.is_(True),
                Classroom.is_active.is_(True),
                Subject.is_active.is_(True),
                TeacherProfile.is_active.is_(True),
                User.is_active.is_(True),
            )
            .order_by(
                TimetableEntry.day_of_week,
                TimetableEntry.start_time,
                TimetableEntry.id,
            )
            .offset(offset)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list(
        self, *, include_inactive: bool = False, limit: int = 50, offset: int = 0
    ) -> builtins.list[TimetableEntry]:
        stmt = (
            select(TimetableEntry)
            .order_by(
                TimetableEntry.day_of_week,
                TimetableEntry.start_time,
                TimetableEntry.id,
            )
            .limit(limit)
            .offset(offset)
        )
        if not include_inactive:
            stmt = stmt.where(TimetableEntry.is_active.is_(True))
        return list((await self._session.execute(stmt)).scalars().all())

    async def count(self, *, include_inactive: bool = False) -> int:
        stmt = select(func.count()).select_from(TimetableEntry)
        if not include_inactive:
            stmt = stmt.where(TimetableEntry.is_active.is_(True))
        return int((await self._session.execute(stmt)).scalar_one())

    async def count_by_classroom(self, classroom_id: uuid.UUID) -> int:
        stmt = (
            select(func.count(func.distinct(TimetableEntry.id)))
            .select_from(TimetableEntry)
            .join(
                TeacherAssignment,
                and_(
                    TeacherAssignment.teacher_profile_id == TimetableEntry.teacher_profile_id,
                    TeacherAssignment.classroom_id == TimetableEntry.classroom_id,
                    TeacherAssignment.subject_id == TimetableEntry.subject_id,
                ),
            )
            .join(Classroom, Classroom.id == TimetableEntry.classroom_id)
            .join(Subject, Subject.id == TimetableEntry.subject_id)
            .join(TeacherProfile, TeacherProfile.id == TimetableEntry.teacher_profile_id)
            .join(User, User.id == TeacherProfile.user_id)
            .where(
                TimetableEntry.classroom_id == classroom_id,
                TimetableEntry.is_active.is_(True),
                TeacherAssignment.is_active.is_(True),
                Classroom.is_active.is_(True),
                Subject.is_active.is_(True),
                TeacherProfile.is_active.is_(True),
                User.is_active.is_(True),
            )
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def count_by_teacher(self, teacher_profile_id: uuid.UUID) -> int:
        stmt = (
            select(func.count(func.distinct(TimetableEntry.id)))
            .select_from(TimetableEntry)
            .join(
                TeacherAssignment,
                and_(
                    TeacherAssignment.teacher_profile_id == TimetableEntry.teacher_profile_id,
                    TeacherAssignment.classroom_id == TimetableEntry.classroom_id,
                    TeacherAssignment.subject_id == TimetableEntry.subject_id,
                ),
            )
            .join(Classroom, Classroom.id == TimetableEntry.classroom_id)
            .join(Subject, Subject.id == TimetableEntry.subject_id)
            .join(TeacherProfile, TeacherProfile.id == TimetableEntry.teacher_profile_id)
            .join(User, User.id == TeacherProfile.user_id)
            .where(
                TimetableEntry.teacher_profile_id == teacher_profile_id,
                TimetableEntry.is_active.is_(True),
                TeacherAssignment.is_active.is_(True),
                Classroom.is_active.is_(True),
                Subject.is_active.is_(True),
                TeacherProfile.is_active.is_(True),
                User.is_active.is_(True),
            )
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def create(
        self,
        *,
        classroom_id: uuid.UUID,
        subject_id: uuid.UUID,
        teacher_profile_id: uuid.UUID,
        day_of_week: DayOfWeek,
        start_time: time,
        end_time: time,
    ) -> TimetableEntry:
        """Create a timetable entry.

        Raises ``InvalidTimetableSlotError`` if ``start_time >=
        end_time`` (re-checked here even though the Pydantic schema
        already validates it, and the DB CHECK constraint validates it a
        third time — belt-and-suspenders, since this repository method can
        be called directly in tests/scripts bypassing the schema),
        ``TimetableCollisionError`` on an exact classroom/teacher + day +
        start-time collision, or ``TimetableReferenceError`` if any
        referenced id does not exist.
        """
        if start_time >= end_time:
            raise InvalidTimetableSlotError()

        entry = TimetableEntry(
            classroom_id=classroom_id,
            subject_id=subject_id,
            teacher_profile_id=teacher_profile_id,
            day_of_week=day_of_week,
            start_time=start_time,
            end_time=end_time,
        )
        self._session.add(entry)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            if _matches_constraint(
                exc, _TIMETABLE_CLASSROOM_DAY_START_CONSTRAINT
            ) or _matches_constraint(exc, _TIMETABLE_TEACHER_DAY_START_CONSTRAINT):
                raise TimetableCollisionError() from exc
            if _matches_constraint(exc, _TIMETABLE_START_BEFORE_END_CONSTRAINT):
                raise InvalidTimetableSlotError() from exc
            if "foreign key" in str(exc.orig).lower():
                raise TimetableReferenceError() from exc
            raise
        await self._session.refresh(entry)
        return entry

    async def deactivate(self, entry: TimetableEntry) -> TimetableEntry:
        entry.is_active = False
        await self._session.flush()
        await self._session.refresh(entry)
        return entry

    async def update(self, entry: TimetableEntry, **changes: object) -> TimetableEntry:
        start_time = changes.get("start_time", entry.start_time)
        end_time = changes.get("end_time", entry.end_time)
        if not isinstance(start_time, time) or not isinstance(end_time, time):
            raise InvalidTimetableSlotError()
        if start_time >= end_time:
            raise InvalidTimetableSlotError()
        for field, value in changes.items():
            setattr(entry, field, value)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            if _matches_constraint(
                exc, _TIMETABLE_CLASSROOM_DAY_START_CONSTRAINT
            ) or _matches_constraint(exc, _TIMETABLE_TEACHER_DAY_START_CONSTRAINT):
                raise TimetableCollisionError() from exc
            if _matches_constraint(exc, _TIMETABLE_START_BEFORE_END_CONSTRAINT):
                raise InvalidTimetableSlotError() from exc
            if "foreign key" in str(exc.orig).lower():
                raise TimetableReferenceError() from exc
            raise
        await self._session.refresh(entry)
        return entry
