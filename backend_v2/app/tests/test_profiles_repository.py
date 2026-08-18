"""Database-backed tests for the ``profiles`` domain.

Uses the ``db_session`` fixture (app/tests/conftest.py), which requires
a reachable Phase 3-migrated PostgreSQL test database and skips
gracefully if one is not available.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.academics.normalization import normalize_code
from app.modules.academics.repository import ClassroomRepository
from app.modules.auth.security import hash_password
from app.modules.profiles.errors import (
    DuplicateClassroomRollNumberError,
    ProfileRoleMismatchError,
    StudentProfileAlreadyExistsError,
    TeacherEmployeeCodeAlreadyExistsError,
    TeacherProfileAlreadyExistsError,
    UserNotFoundError,
)
from app.modules.profiles.models import StudentProfile, TeacherProfile
from app.modules.profiles.repository import StudentProfileRepository, TeacherProfileRepository
from app.modules.users.models import User, UserRole
from app.modules.users.normalization import normalize_email
from app.modules.users.repository import UserRepository


async def _create_user(session: AsyncSession, *, email: str, role: UserRole) -> User:
    user = await UserRepository(session).create(
        email=normalize_email(email),
        password_hash=hash_password("a-strong-real-password-1"),
        full_name="Test User",
        role=role,
        is_active=True,
    )
    await session.commit()
    return user


# --- Teacher profiles ------------------------------------------------------


async def test_create_teacher_profile_for_teacher_user(db_session: AsyncSession) -> None:
    user = await _create_user(db_session, email="teacher1@example.com", role=UserRole.TEACHER)
    profile = await TeacherProfileRepository(db_session).create(
        user_id=user.id, employee_code="EMP-001"
    )
    await db_session.commit()

    assert profile.user_id == user.id
    assert profile.employee_code == "EMP-001"


async def test_one_teacher_profile_per_teacher_user(db_session: AsyncSession) -> None:
    user = await _create_user(db_session, email="teacher2@example.com", role=UserRole.TEACHER)
    repo = TeacherProfileRepository(db_session)
    await repo.create(user_id=user.id)
    await db_session.commit()

    with pytest.raises(TeacherProfileAlreadyExistsError):
        await repo.create(user_id=user.id)


async def test_teacher_profile_role_mismatch_is_rejected(db_session: AsyncSession) -> None:
    student_user = await _create_user(
        db_session, email="not-a-teacher@example.com", role=UserRole.STUDENT
    )
    with pytest.raises(ProfileRoleMismatchError):
        await TeacherProfileRepository(db_session).create(user_id=student_user.id)


async def test_teacher_profile_missing_user_is_rejected(db_session: AsyncSession) -> None:
    with pytest.raises(UserNotFoundError):
        await TeacherProfileRepository(db_session).create(user_id=uuid.uuid4())


async def test_teacher_employee_code_conflict_has_specific_error(
    db_session: AsyncSession,
) -> None:
    first_user = await _create_user(
        db_session, email="employee-code-a@example.com", role=UserRole.TEACHER
    )
    second_user = await _create_user(
        db_session, email="employee-code-b@example.com", role=UserRole.TEACHER
    )
    repository = TeacherProfileRepository(db_session)
    await repository.create(user_id=first_user.id, employee_code="EMP-DUPLICATE")
    await db_session.commit()

    with pytest.raises(TeacherEmployeeCodeAlreadyExistsError):
        await repository.create(
            user_id=second_user.id,
            employee_code="EMP-DUPLICATE",
        )


# --- Student profiles ------------------------------------------------------


async def test_create_student_profile_for_student_user(db_session: AsyncSession) -> None:
    user = await _create_user(db_session, email="student1@example.com", role=UserRole.STUDENT)
    profile = await StudentProfileRepository(db_session).create(user_id=user.id)
    await db_session.commit()

    assert profile.user_id == user.id
    assert profile.classroom_id is None


async def test_one_student_profile_per_student_user(db_session: AsyncSession) -> None:
    user = await _create_user(db_session, email="student2@example.com", role=UserRole.STUDENT)
    repo = StudentProfileRepository(db_session)
    await repo.create(user_id=user.id)
    await db_session.commit()

    with pytest.raises(StudentProfileAlreadyExistsError):
        await repo.create(user_id=user.id)


async def test_student_profile_role_mismatch_is_rejected(db_session: AsyncSession) -> None:
    teacher_user = await _create_user(
        db_session, email="not-a-student@example.com", role=UserRole.TEACHER
    )
    with pytest.raises(ProfileRoleMismatchError):
        await StudentProfileRepository(db_session).create(user_id=teacher_user.id)


async def test_student_profile_missing_user_is_rejected(db_session: AsyncSession) -> None:
    with pytest.raises(UserNotFoundError):
        await StudentProfileRepository(db_session).create(user_id=uuid.uuid4())


async def test_student_classroom_membership_assignment(db_session: AsyncSession) -> None:
    user = await _create_user(db_session, email="student3@example.com", role=UserRole.STUDENT)
    classroom = await ClassroomRepository(db_session).create(
        name="Membership Classroom", code=normalize_code("membership-classroom")
    )
    await db_session.commit()

    repo = StudentProfileRepository(db_session)
    profile = await repo.create(user_id=user.id)
    await db_session.commit()

    updated = await repo.assign_classroom(profile, classroom_id=classroom.id, roll_number="01")
    await db_session.commit()

    assert updated.classroom_id == classroom.id
    assert updated.roll_number == "01"

    fetched = await repo.get_by_user_id(user.id)
    assert fetched is not None
    assert fetched.classroom_id == classroom.id

    members = await repo.list_by_classroom(classroom.id)
    assert {member.id for member in members} == {profile.id}


async def test_duplicate_classroom_roll_number_is_rejected(db_session: AsyncSession) -> None:
    classroom = await ClassroomRepository(db_session).create(
        name="Roll Number Classroom", code=normalize_code("roll-number-classroom")
    )
    await db_session.commit()

    first_user = await _create_user(
        db_session, email="student4a@example.com", role=UserRole.STUDENT
    )
    second_user = await _create_user(
        db_session, email="student4b@example.com", role=UserRole.STUDENT
    )

    repo = StudentProfileRepository(db_session)
    await repo.create(user_id=first_user.id, classroom_id=classroom.id, roll_number="07")
    await db_session.commit()

    with pytest.raises(DuplicateClassroomRollNumberError):
        await repo.create(user_id=second_user.id, classroom_id=classroom.id, roll_number="07")


def test_profile_models_declare_expected_tables() -> None:
    """Cheap, DB-free sanity check that always runs (no db_session needed)."""
    assert TeacherProfile.__tablename__ == "teacher_profiles"
    assert StudentProfile.__tablename__ == "student_profiles"
