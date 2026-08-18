"""Database-backed tests for the ``academics`` domain.

Uses the ``db_session`` fixture (app/tests/conftest.py), which requires
a reachable Phase 3-migrated PostgreSQL test database and skips
gracefully if one is not available.
"""

from __future__ import annotations

import uuid
from datetime import time

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.academics.errors import (
    ClassroomCodeAlreadyExistsError,
    DuplicateTeacherAssignmentError,
    SubjectCodeAlreadyExistsError,
    TeacherAssignmentReferenceError,
    TimetableCollisionError,
    TimetableReferenceError,
)
from app.modules.academics.models import Classroom, DayOfWeek, Subject
from app.modules.academics.normalization import normalize_code, normalize_name
from app.modules.academics.repository import (
    ClassroomRepository,
    SubjectRepository,
    TeacherAssignmentRepository,
    TimetableRepository,
)
from app.modules.auth.security import hash_password
from app.modules.profiles.repository import TeacherProfileRepository
from app.modules.users.models import UserRole
from app.modules.users.normalization import normalize_email
from app.modules.users.repository import UserRepository


async def _create_classroom(
    session: AsyncSession, *, name: str = "Grade 8 - Section A", code: str = "Grade 8 A"
) -> Classroom:
    classroom = await ClassroomRepository(session).create(
        name=normalize_name(name), code=normalize_code(code)
    )
    await session.commit()
    return classroom


async def _create_subject(
    session: AsyncSession, *, name: str = "Mathematics", code: str = "Mathematics"
) -> Subject:
    subject = await SubjectRepository(session).create(
        name=normalize_name(name), code=normalize_code(code)
    )
    await session.commit()
    return subject


async def _create_teacher_profile(session: AsyncSession, *, email: str) -> uuid.UUID:
    user = await UserRepository(session).create(
        email=normalize_email(email),
        password_hash=hash_password("a-strong-real-password-1"),
        full_name="Test Teacher",
        role=UserRole.TEACHER,
        is_active=True,
    )
    profile = await TeacherProfileRepository(session).create(user_id=user.id)
    await session.commit()
    return profile.id


# --- Classrooms --------------------------------------------------------


async def test_create_classroom_normalizes_code(db_session: AsyncSession) -> None:
    classroom = await _create_classroom(db_session, name="  Grade  9   B ", code="Grade 9 B")
    assert classroom.name == "Grade 9 B"
    assert classroom.code == "grade_9_b"


async def test_duplicate_classroom_code_is_rejected(db_session: AsyncSession) -> None:
    await _create_classroom(db_session, code="dup-classroom")
    with pytest.raises(ClassroomCodeAlreadyExistsError):
        await _create_classroom(db_session, name="Different Name", code="dup-classroom")


async def test_get_classroom_by_normalized_code(db_session: AsyncSession) -> None:
    created = await _create_classroom(db_session, code="lookup-classroom")
    fetched = await ClassroomRepository(db_session).get_by_code(normalize_code("lookup-classroom"))
    assert fetched is not None
    assert fetched.id == created.id


# --- Subjects ------------------------------------------------------------


async def test_create_subject_normalizes_code(db_session: AsyncSession) -> None:
    subject = await _create_subject(db_session, name="  Computer   Science ", code="CompSci 101")
    assert subject.name == "Computer Science"
    assert subject.code == "compsci_101"


async def test_duplicate_subject_code_is_rejected(db_session: AsyncSession) -> None:
    await _create_subject(db_session, code="dup-subject")
    with pytest.raises(SubjectCodeAlreadyExistsError):
        await _create_subject(db_session, name="Different Subject", code="dup-subject")


# --- Teacher assignments ---------------------------------------------------


async def test_teacher_assignment_create_and_exists(db_session: AsyncSession) -> None:
    teacher_profile_id = await _create_teacher_profile(db_session, email="assign1@example.com")
    classroom = await _create_classroom(db_session, code="assign-classroom-1")
    subject = await _create_subject(db_session, code="assign-subject-1")

    repo = TeacherAssignmentRepository(db_session)
    assignment = await repo.create(
        teacher_profile_id=teacher_profile_id,
        classroom_id=classroom.id,
        subject_id=subject.id,
    )
    await db_session.commit()

    assert assignment.teacher_profile_id == teacher_profile_id
    assert await repo.exists(
        teacher_profile_id=teacher_profile_id,
        classroom_id=classroom.id,
        subject_id=subject.id,
    )


async def test_duplicate_teacher_assignment_is_rejected(db_session: AsyncSession) -> None:
    teacher_profile_id = await _create_teacher_profile(db_session, email="assign2@example.com")
    classroom = await _create_classroom(db_session, code="assign-classroom-2")
    subject = await _create_subject(db_session, code="assign-subject-2")

    repo = TeacherAssignmentRepository(db_session)
    await repo.create(
        teacher_profile_id=teacher_profile_id,
        classroom_id=classroom.id,
        subject_id=subject.id,
    )
    await db_session.commit()

    with pytest.raises(DuplicateTeacherAssignmentError):
        await repo.create(
            teacher_profile_id=teacher_profile_id,
            classroom_id=classroom.id,
            subject_id=subject.id,
        )


async def test_teacher_assignment_missing_related_record_is_rejected(
    db_session: AsyncSession,
) -> None:
    teacher_profile_id = await _create_teacher_profile(db_session, email="assign3@example.com")
    classroom = await _create_classroom(db_session, code="assign-classroom-3")

    with pytest.raises(TeacherAssignmentReferenceError):
        await TeacherAssignmentRepository(db_session).create(
            teacher_profile_id=teacher_profile_id,
            classroom_id=classroom.id,
            subject_id=uuid.uuid4(),
        )


# --- Timetable -------------------------------------------------------------


async def test_timetable_entry_create(db_session: AsyncSession) -> None:
    teacher_profile_id = await _create_teacher_profile(db_session, email="tt1@example.com")
    classroom = await _create_classroom(db_session, code="tt-classroom-1")
    subject = await _create_subject(db_session, code="tt-subject-1")

    entry = await TimetableRepository(db_session).create(
        classroom_id=classroom.id,
        subject_id=subject.id,
        teacher_profile_id=teacher_profile_id,
        day_of_week=DayOfWeek.MONDAY,
        start_time=time(9, 0),
        end_time=time(10, 0),
    )
    await db_session.commit()

    assert entry.day_of_week is DayOfWeek.MONDAY


async def test_timetable_entry_same_classroom_same_slot_collides(
    db_session: AsyncSession,
) -> None:
    teacher_profile_id = await _create_teacher_profile(db_session, email="tt2@example.com")
    other_teacher_profile_id = await _create_teacher_profile(db_session, email="tt3@example.com")
    classroom = await _create_classroom(db_session, code="tt-classroom-2")
    subject = await _create_subject(db_session, code="tt-subject-2")
    other_subject = await _create_subject(db_session, code="tt-subject-2b")

    repo = TimetableRepository(db_session)
    await repo.create(
        classroom_id=classroom.id,
        subject_id=subject.id,
        teacher_profile_id=teacher_profile_id,
        day_of_week=DayOfWeek.TUESDAY,
        start_time=time(9, 0),
        end_time=time(10, 0),
    )
    await db_session.commit()

    # Same classroom, same day, same start time, but a different
    # teacher/subject: still a collision under the Stage 1 rule (see
    # app/modules/academics/models.py's TimetableEntry docstring).
    with pytest.raises(TimetableCollisionError):
        await repo.create(
            classroom_id=classroom.id,
            subject_id=other_subject.id,
            teacher_profile_id=other_teacher_profile_id,
            day_of_week=DayOfWeek.TUESDAY,
            start_time=time(9, 0),
            end_time=time(10, 30),
        )


async def test_timetable_entry_same_teacher_same_slot_different_classroom_collides(
    db_session: AsyncSession,
) -> None:
    teacher_profile_id = await _create_teacher_profile(db_session, email="tt4@example.com")
    classroom_a = await _create_classroom(db_session, code="tt-classroom-3a")
    classroom_b = await _create_classroom(db_session, code="tt-classroom-3b")
    subject = await _create_subject(db_session, code="tt-subject-3")

    repo = TimetableRepository(db_session)
    await repo.create(
        classroom_id=classroom_a.id,
        subject_id=subject.id,
        teacher_profile_id=teacher_profile_id,
        day_of_week=DayOfWeek.WEDNESDAY,
        start_time=time(11, 0),
        end_time=time(12, 0),
    )
    await db_session.commit()

    # A teacher cannot be in two classrooms at the same day/start-time,
    # even if the classroom differs.
    with pytest.raises(TimetableCollisionError):
        await repo.create(
            classroom_id=classroom_b.id,
            subject_id=subject.id,
            teacher_profile_id=teacher_profile_id,
            day_of_week=DayOfWeek.WEDNESDAY,
            start_time=time(11, 0),
            end_time=time(12, 0),
        )


async def test_timetable_entry_missing_related_record_is_rejected(
    db_session: AsyncSession,
) -> None:
    teacher_profile_id = await _create_teacher_profile(db_session, email="tt5@example.com")
    subject = await _create_subject(db_session, code="tt-subject-5")

    with pytest.raises(TimetableReferenceError):
        await TimetableRepository(db_session).create(
            classroom_id=uuid.uuid4(),
            subject_id=subject.id,
            teacher_profile_id=teacher_profile_id,
            day_of_week=DayOfWeek.THURSDAY,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
