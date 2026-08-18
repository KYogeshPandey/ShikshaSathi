"""Database-backed tests for ``app.modules.attendance.repository.AttendanceRepository``.

Uses the ``db_session`` fixture (app/tests/conftest.py), which requires a
reachable Phase 4-migrated PostgreSQL test database and skips gracefully
if one is not available. Mirrors the conventions in
``app.tests.test_academics_repository`` (direct repository calls, no
HTTP, explicit ``session.commit()`` between setup steps).
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.academics.repository import ClassroomRepository, SubjectRepository
from app.modules.attendance.errors import AttendanceRecordAlreadyExistsError
from app.modules.attendance.models import AttendanceStatus
from app.modules.attendance.repository import AttendanceRepository
from app.modules.auth.security import hash_password
from app.modules.profiles.repository import StudentProfileRepository
from app.modules.users.models import UserRole
from app.modules.users.normalization import normalize_email
from app.modules.users.repository import UserRepository

_PASSWORD = "a-strong-real-password-1"


async def _create_user(session: AsyncSession, *, email: str, role: UserRole) -> uuid.UUID:
    user = await UserRepository(session).create(
        email=normalize_email(email),
        password_hash=hash_password(_PASSWORD),
        full_name=f"{role.value.title()} Attendance Test",
        role=role,
        is_active=True,
    )
    await session.commit()
    return user.id


async def _create_classroom(session: AsyncSession, *, code: str) -> uuid.UUID:
    classroom = await ClassroomRepository(session).create(name=code.title(), code=code)
    await session.commit()
    return classroom.id


async def _create_subject(session: AsyncSession, *, code: str) -> uuid.UUID:
    subject = await SubjectRepository(session).create(name=code.title(), code=code)
    await session.commit()
    return subject.id


async def _create_student_profile(
    session: AsyncSession, *, email: str, classroom_id: uuid.UUID, roll_number: str
) -> uuid.UUID:
    user_id = await _create_user(session, email=email, role=UserRole.STUDENT)
    profile = await StudentProfileRepository(session).create(
        user_id=user_id, classroom_id=classroom_id, roll_number=roll_number
    )
    await session.commit()
    return profile.id


class _Fixture:
    def __init__(
        self,
        *,
        classroom_id: uuid.UUID,
        subject_id: uuid.UUID,
        teacher_user_id: uuid.UUID,
        student_a_id: uuid.UUID,
        student_b_id: uuid.UUID,
    ) -> None:
        self.classroom_id = classroom_id
        self.subject_id = subject_id
        self.teacher_user_id = teacher_user_id
        self.student_a_id = student_a_id
        self.student_b_id = student_b_id


async def _seed(session: AsyncSession, *, suffix: str) -> _Fixture:
    classroom_id = await _create_classroom(session, code=f"att-classroom-{suffix}")
    subject_id = await _create_subject(session, code=f"att-subject-{suffix}")
    teacher_user_id = await _create_user(
        session, email=f"att-teacher-{suffix}@example.com", role=UserRole.TEACHER
    )
    student_a_id = await _create_student_profile(
        session,
        email=f"att-student-a-{suffix}@example.com",
        classroom_id=classroom_id,
        roll_number="01",
    )
    student_b_id = await _create_student_profile(
        session,
        email=f"att-student-b-{suffix}@example.com",
        classroom_id=classroom_id,
        roll_number="02",
    )
    return _Fixture(
        classroom_id=classroom_id,
        subject_id=subject_id,
        teacher_user_id=teacher_user_id,
        student_a_id=student_a_id,
        student_b_id=student_b_id,
    )


# --- create / get -----------------------------------------------------------


async def test_create_and_get_by_id(db_session: AsyncSession) -> None:
    fx = await _seed(db_session, suffix="create-get")
    repo = AttendanceRepository(db_session)
    record = await repo.create(
        student_profile_id=fx.student_a_id,
        classroom_id=fx.classroom_id,
        subject_id=fx.subject_id,
        attendance_date=date(2026, 7, 1),
        status=AttendanceStatus.PRESENT,
        marked_by_user_id=fx.teacher_user_id,
        remarks="on time",
    )
    await db_session.commit()

    fetched = await repo.get_by_id(record.id)
    assert fetched is not None
    assert fetched.status is AttendanceStatus.PRESENT
    assert fetched.remarks == "on time"
    assert fetched.marked_by_user_id == fx.teacher_user_id


async def test_get_by_unique_key_round_trips(db_session: AsyncSession) -> None:
    fx = await _seed(db_session, suffix="unique-key")
    repo = AttendanceRepository(db_session)
    created = await repo.create(
        student_profile_id=fx.student_a_id,
        classroom_id=fx.classroom_id,
        subject_id=fx.subject_id,
        attendance_date=date(2026, 7, 2),
        status=AttendanceStatus.ABSENT,
        marked_by_user_id=fx.teacher_user_id,
    )
    await db_session.commit()

    found = await repo.get_by_unique_key(
        student_profile_id=fx.student_a_id,
        classroom_id=fx.classroom_id,
        subject_id=fx.subject_id,
        attendance_date=date(2026, 7, 2),
    )
    assert found is not None
    assert found.id == created.id

    missing = await repo.get_by_unique_key(
        student_profile_id=fx.student_b_id,
        classroom_id=fx.classroom_id,
        subject_id=fx.subject_id,
        attendance_date=date(2026, 7, 2),
    )
    assert missing is None


async def test_duplicate_natural_key_is_rejected(db_session: AsyncSession) -> None:
    fx = await _seed(db_session, suffix="duplicate")
    repo = AttendanceRepository(db_session)
    await repo.create(
        student_profile_id=fx.student_a_id,
        classroom_id=fx.classroom_id,
        subject_id=fx.subject_id,
        attendance_date=date(2026, 7, 3),
        status=AttendanceStatus.PRESENT,
        marked_by_user_id=fx.teacher_user_id,
    )
    await db_session.commit()

    with pytest.raises(AttendanceRecordAlreadyExistsError):
        await repo.create(
            student_profile_id=fx.student_a_id,
            classroom_id=fx.classroom_id,
            subject_id=fx.subject_id,
            attendance_date=date(2026, 7, 3),
            status=AttendanceStatus.ABSENT,
            marked_by_user_id=fx.teacher_user_id,
        )


async def test_update_changes_status_remarks_and_marked_by(db_session: AsyncSession) -> None:
    fx = await _seed(db_session, suffix="update")
    repo = AttendanceRepository(db_session)
    record = await repo.create(
        student_profile_id=fx.student_a_id,
        classroom_id=fx.classroom_id,
        subject_id=fx.subject_id,
        attendance_date=date(2026, 7, 4),
        status=AttendanceStatus.ABSENT,
        marked_by_user_id=fx.teacher_user_id,
    )
    await db_session.commit()

    other_marker_id = await _create_user(
        db_session, email="att-second-marker@example.com", role=UserRole.ADMIN
    )
    updated = await repo.update(
        record, status=AttendanceStatus.PRESENT, marked_by_user_id=other_marker_id, remarks="late"
    )
    await db_session.commit()

    assert updated.status is AttendanceStatus.PRESENT
    assert updated.remarks == "late"
    assert updated.marked_by_user_id == other_marker_id


# --- listing / filtering -----------------------------------------------------


async def test_list_is_deterministically_ordered_and_filters_by_classroom_and_subject(
    db_session: AsyncSession,
) -> None:
    fx = await _seed(db_session, suffix="list-filter")
    other_classroom_id = await _create_classroom(db_session, code="att-other-classroom")
    other_subject_id = await _create_subject(db_session, code="att-other-subject")
    repo = AttendanceRepository(db_session)

    await repo.create(
        student_profile_id=fx.student_a_id,
        classroom_id=fx.classroom_id,
        subject_id=fx.subject_id,
        attendance_date=date(2026, 7, 5),
        status=AttendanceStatus.PRESENT,
        marked_by_user_id=fx.teacher_user_id,
    )
    await repo.create(
        student_profile_id=fx.student_b_id,
        classroom_id=fx.classroom_id,
        subject_id=fx.subject_id,
        attendance_date=date(2026, 7, 5),
        status=AttendanceStatus.ABSENT,
        marked_by_user_id=fx.teacher_user_id,
    )
    # A record in an unrelated classroom/subject must not appear in the
    # filtered listing below.
    unrelated_student_id = await _create_student_profile(
        db_session,
        email="att-unrelated-student@example.com",
        classroom_id=other_classroom_id,
        roll_number="01",
    )
    await repo.create(
        student_profile_id=unrelated_student_id,
        classroom_id=other_classroom_id,
        subject_id=other_subject_id,
        attendance_date=date(2026, 7, 5),
        status=AttendanceStatus.PRESENT,
        marked_by_user_id=fx.teacher_user_id,
    )
    await db_session.commit()

    rows = await repo.list(classroom_id=fx.classroom_id, subject_id=fx.subject_id)
    assert {row.student_profile_id for row in rows} == {fx.student_a_id, fx.student_b_id}

    # Re-running the same query must return the exact same order (no
    # implicit, database-default ordering being relied on).
    rows_again = await repo.list(classroom_id=fx.classroom_id, subject_id=fx.subject_id)
    assert [row.id for row in rows] == [row.id for row in rows_again]


async def test_list_filters_by_student_profile_id(db_session: AsyncSession) -> None:
    fx = await _seed(db_session, suffix="student-filter")
    repo = AttendanceRepository(db_session)
    await repo.create(
        student_profile_id=fx.student_a_id,
        classroom_id=fx.classroom_id,
        subject_id=fx.subject_id,
        attendance_date=date(2026, 7, 6),
        status=AttendanceStatus.PRESENT,
        marked_by_user_id=fx.teacher_user_id,
    )
    await repo.create(
        student_profile_id=fx.student_b_id,
        classroom_id=fx.classroom_id,
        subject_id=fx.subject_id,
        attendance_date=date(2026, 7, 6),
        status=AttendanceStatus.ABSENT,
        marked_by_user_id=fx.teacher_user_id,
    )
    await db_session.commit()

    rows = await repo.list(student_profile_id=fx.student_a_id)
    assert {row.student_profile_id for row in rows} == {fx.student_a_id}


async def test_list_filters_by_date_range(db_session: AsyncSession) -> None:
    fx = await _seed(db_session, suffix="date-range")
    repo = AttendanceRepository(db_session)
    base = date(2026, 7, 10)
    for offset in range(3):
        await repo.create(
            student_profile_id=fx.student_a_id,
            classroom_id=fx.classroom_id,
            subject_id=fx.subject_id,
            attendance_date=base + timedelta(days=offset),
            status=AttendanceStatus.PRESENT,
            marked_by_user_id=fx.teacher_user_id,
        )
    await db_session.commit()

    rows = await repo.list(
        student_profile_id=fx.student_a_id,
        date_from=base + timedelta(days=1),
        date_to=base + timedelta(days=2),
    )
    assert {row.attendance_date for row in rows} == {
        base + timedelta(days=1),
        base + timedelta(days=2),
    }


async def test_count_matches_list_filters(db_session: AsyncSession) -> None:
    fx = await _seed(db_session, suffix="count")
    repo = AttendanceRepository(db_session)
    for offset in range(4):
        await repo.create(
            student_profile_id=fx.student_a_id if offset % 2 == 0 else fx.student_b_id,
            classroom_id=fx.classroom_id,
            subject_id=fx.subject_id,
            attendance_date=date(2026, 7, 15) + timedelta(days=offset),
            status=AttendanceStatus.PRESENT,
            marked_by_user_id=fx.teacher_user_id,
        )
    await db_session.commit()

    total = await repo.count(classroom_id=fx.classroom_id, subject_id=fx.subject_id)
    assert total == 4
    only_a = await repo.count(student_profile_id=fx.student_a_id)
    assert only_a == 2


# --- aggregation --------------------------------------------------------------


async def test_aggregate_counts_present_absent_total(db_session: AsyncSession) -> None:
    fx = await _seed(db_session, suffix="aggregate")
    repo = AttendanceRepository(db_session)
    await repo.create(
        student_profile_id=fx.student_a_id,
        classroom_id=fx.classroom_id,
        subject_id=fx.subject_id,
        attendance_date=date(2026, 7, 20),
        status=AttendanceStatus.PRESENT,
        marked_by_user_id=fx.teacher_user_id,
    )
    await repo.create(
        student_profile_id=fx.student_b_id,
        classroom_id=fx.classroom_id,
        subject_id=fx.subject_id,
        attendance_date=date(2026, 7, 20),
        status=AttendanceStatus.ABSENT,
        marked_by_user_id=fx.teacher_user_id,
    )
    await repo.create(
        student_profile_id=fx.student_a_id,
        classroom_id=fx.classroom_id,
        subject_id=fx.subject_id,
        attendance_date=date(2026, 7, 21),
        status=AttendanceStatus.PRESENT,
        marked_by_user_id=fx.teacher_user_id,
    )
    await db_session.commit()

    total, present, absent = await repo.aggregate_counts(
        classroom_id=fx.classroom_id, subject_id=fx.subject_id
    )
    assert (total, present, absent) == (3, 2, 1)


async def test_aggregate_counts_are_zero_for_no_matching_rows(db_session: AsyncSession) -> None:
    fx = await _seed(db_session, suffix="aggregate-empty")
    repo = AttendanceRepository(db_session)
    total, present, absent = await repo.aggregate_counts(
        classroom_id=fx.classroom_id, subject_id=fx.subject_id
    )
    assert (total, present, absent) == (0, 0, 0)
