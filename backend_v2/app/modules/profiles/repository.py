"""Repositories for the profiles domain.

``TeacherProfileRepository.create`` and ``StudentProfileRepository.create``
each load the referenced ``User`` first and enforce the role-match
invariant in application code before ever inserting a row — see
``app.modules.profiles.models``' module docstring for exactly why this is
not (and cannot cleanly be) a single-table database CHECK constraint.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.profiles.errors import (
    DuplicateClassroomRollNumberError,
    ProfileRoleMismatchError,
    StudentProfileAlreadyExistsError,
    TeacherEmployeeCodeAlreadyExistsError,
    TeacherProfileAlreadyExistsError,
    UserNotFoundError,
)
from app.modules.profiles.models import StudentProfile, TeacherProfile
from app.modules.users.models import User, UserRole

_TEACHER_PROFILE_USER_CONSTRAINT = "uq_teacher_profiles_user_id"
_TEACHER_PROFILE_EMPLOYEE_CODE_CONSTRAINT = "uq_teacher_profiles_employee_code"
_STUDENT_PROFILE_USER_CONSTRAINT = "uq_student_profiles_user_id"
_STUDENT_PROFILE_CLASSROOM_ROLL_CONSTRAINT = "uq_student_profiles_classroom_roll"


@dataclass(frozen=True)
class StudentProfileIdentity:
    """A profile paired with its existing user-owned display name."""

    profile: StudentProfile
    full_name: str


def _matches_constraint(exc: IntegrityError, constraint_name: str) -> bool:
    candidates = (
        exc.orig,
        getattr(exc.orig, "__cause__", None),
        getattr(exc.orig, "__context__", None),
    )
    for candidate in candidates:
        if getattr(candidate, "constraint_name", None) == constraint_name:
            return True
    return constraint_name in str(exc.orig)


class TeacherProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, profile_id: uuid.UUID) -> TeacherProfile | None:
        return await self._session.get(TeacherProfile, profile_id)

    async def get_by_user_id(self, user_id: uuid.UUID) -> TeacherProfile | None:
        stmt = select(TeacherProfile).where(TeacherProfile.user_id == user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(
        self, *, include_inactive: bool = False, limit: int = 50, offset: int = 0
    ) -> list[TeacherProfile]:
        stmt = (
            select(TeacherProfile)
            .order_by(TeacherProfile.created_at, TeacherProfile.id)
            .limit(limit)
            .offset(offset)
        )
        if not include_inactive:
            stmt = stmt.where(TeacherProfile.is_active.is_(True))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, *, include_inactive: bool = False) -> int:
        stmt = select(func.count()).select_from(TeacherProfile)
        if not include_inactive:
            stmt = stmt.where(TeacherProfile.is_active.is_(True))
        return int((await self._session.execute(stmt)).scalar_one())

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        employee_code: str | None = None,
        phone_number: str | None = None,
    ) -> TeacherProfile:
        """Create a teacher profile for ``user_id``.

        Raises ``UserNotFoundError`` if the user does not exist,
        ``ProfileRoleMismatchError`` if the user's role is not
        ``teacher``, or ``TeacherProfileAlreadyExistsError`` if the user
        already has a teacher profile.
        """
        user = await self._session.get(User, user_id)
        if user is None:
            raise UserNotFoundError()
        if user.role is not UserRole.TEACHER:
            raise ProfileRoleMismatchError(expected_role=UserRole.TEACHER.value)

        profile = TeacherProfile(
            user_id=user_id, employee_code=employee_code, phone_number=phone_number
        )
        self._session.add(profile)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            if _matches_constraint(exc, _TEACHER_PROFILE_USER_CONSTRAINT):
                raise TeacherProfileAlreadyExistsError() from exc
            if _matches_constraint(exc, _TEACHER_PROFILE_EMPLOYEE_CODE_CONSTRAINT):
                raise TeacherEmployeeCodeAlreadyExistsError() from exc
            raise
        await self._session.refresh(profile)
        return profile

    async def deactivate(self, profile: TeacherProfile) -> TeacherProfile:
        profile.is_active = False
        await self._session.flush()
        await self._session.refresh(profile)
        return profile

    async def update(self, profile: TeacherProfile, **changes: object) -> TeacherProfile:
        for field, value in changes.items():
            setattr(profile, field, value)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            if _matches_constraint(exc, _TEACHER_PROFILE_EMPLOYEE_CODE_CONSTRAINT):
                raise TeacherEmployeeCodeAlreadyExistsError() from exc
            raise
        await self._session.refresh(profile)
        return profile


class StudentProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, profile_id: uuid.UUID) -> StudentProfile | None:
        return await self._session.get(StudentProfile, profile_id)

    async def get_by_user_id(self, user_id: uuid.UUID) -> StudentProfile | None:
        stmt = select(StudentProfile).where(StudentProfile.user_id == user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_classroom(self, classroom_id: uuid.UUID) -> list[StudentProfile]:
        stmt = select(StudentProfile).where(StudentProfile.classroom_id == classroom_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_identities_by_classroom(
        self, classroom_id: uuid.UUID
    ) -> list[StudentProfileIdentity]:
        """Return classroom profiles with names sourced from ``User.full_name``."""
        stmt = (
            select(StudentProfile, User.full_name)
            .join(User, User.id == StudentProfile.user_id)
            .where(StudentProfile.classroom_id == classroom_id)
        )
        result = await self._session.execute(stmt)
        return [
            StudentProfileIdentity(profile=profile, full_name=full_name)
            for profile, full_name in result.tuples().all()
        ]

    async def list(
        self, *, include_inactive: bool = False, limit: int = 50, offset: int = 0
    ) -> list[StudentProfile]:
        stmt = (
            select(StudentProfile)
            .order_by(StudentProfile.created_at, StudentProfile.id)
            .limit(limit)
            .offset(offset)
        )
        if not include_inactive:
            stmt = stmt.where(StudentProfile.is_active.is_(True))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, *, include_inactive: bool = False) -> int:
        stmt = select(func.count()).select_from(StudentProfile)
        if not include_inactive:
            stmt = stmt.where(StudentProfile.is_active.is_(True))
        return int((await self._session.execute(stmt)).scalar_one())

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        classroom_id: uuid.UUID | None = None,
        roll_number: str | None = None,
    ) -> StudentProfile:
        """Create a student profile for ``user_id``.

        Raises ``UserNotFoundError`` if the user does not exist,
        ``ProfileRoleMismatchError`` if the user's role is not
        ``student``, ``StudentProfileAlreadyExistsError`` if the user
        already has a student profile, or
        ``DuplicateClassroomRollNumberError`` if ``roll_number`` is
        already taken within ``classroom_id``.
        """
        user = await self._session.get(User, user_id)
        if user is None:
            raise UserNotFoundError()
        if user.role is not UserRole.STUDENT:
            raise ProfileRoleMismatchError(expected_role=UserRole.STUDENT.value)

        profile = StudentProfile(
            user_id=user_id, classroom_id=classroom_id, roll_number=roll_number
        )
        self._session.add(profile)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            if _matches_constraint(exc, _STUDENT_PROFILE_USER_CONSTRAINT):
                raise StudentProfileAlreadyExistsError() from exc
            if _matches_constraint(exc, _STUDENT_PROFILE_CLASSROOM_ROLL_CONSTRAINT):
                raise DuplicateClassroomRollNumberError() from exc
            raise
        await self._session.refresh(profile)
        return profile

    async def assign_classroom(
        self,
        profile: StudentProfile,
        *,
        classroom_id: uuid.UUID | None,
        roll_number: str | None,
    ) -> StudentProfile:
        """Assign (or reassign/unassign, if ``classroom_id`` is ``None``) a classroom.

        Raises ``DuplicateClassroomRollNumberError`` if the target
        ``(classroom_id, roll_number)`` pair is already in use by a
        different student profile.
        """
        profile.classroom_id = classroom_id
        profile.roll_number = roll_number
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            if _matches_constraint(exc, _STUDENT_PROFILE_CLASSROOM_ROLL_CONSTRAINT):
                raise DuplicateClassroomRollNumberError() from exc
            raise
        await self._session.refresh(profile)
        return profile

    async def deactivate(self, profile: StudentProfile) -> StudentProfile:
        profile.is_active = False
        await self._session.flush()
        await self._session.refresh(profile)
        return profile

    async def update(self, profile: StudentProfile, **changes: object) -> StudentProfile:
        for field, value in changes.items():
            setattr(profile, field, value)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            if _matches_constraint(exc, _STUDENT_PROFILE_CLASSROOM_ROLL_CONSTRAINT):
                raise DuplicateClassroomRollNumberError() from exc
            raise
        await self._session.refresh(profile)
        return profile
