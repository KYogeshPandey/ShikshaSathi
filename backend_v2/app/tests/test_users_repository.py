"""Database-backed tests for the ``users`` domain.

Uses the ``db_session`` fixture (app/tests/conftest.py), which requires
a reachable Phase 2-migrated PostgreSQL test database and skips
gracefully if one is not available — see that fixture's docstring for
exactly how isolation/cleanup works.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.security import hash_password
from app.modules.users.errors import EmailAlreadyExistsError
from app.modules.users.models import User, UserRole
from app.modules.users.normalization import normalize_email
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import UserRead


async def _create_user(
    session: AsyncSession,
    *,
    email: str,
    role: UserRole = UserRole.TEACHER,
    is_active: bool = True,
    password: str = "a-strong-real-password-1",
) -> User:
    repo = UserRepository(session)
    user = await repo.create(
        email=normalize_email(email),
        password_hash=hash_password(password),
        full_name="Test User",
        role=role,
        is_active=is_active,
    )
    await session.commit()
    return user


async def test_create_and_get_by_email(db_session: AsyncSession) -> None:
    user = await _create_user(db_session, email="Teacher@Example.com")
    fetched = await UserRepository(db_session).get_by_email("teacher@example.com")
    assert fetched is not None
    assert fetched.id == user.id


async def test_get_by_id(db_session: AsyncSession) -> None:
    user = await _create_user(db_session, email="lookup@example.com")
    fetched = await UserRepository(db_session).get_by_id(user.id)
    assert fetched is not None
    assert fetched.email == "lookup@example.com"


async def test_get_by_id_missing_returns_none(db_session: AsyncSession) -> None:
    fetched = await UserRepository(db_session).get_by_id(uuid.uuid4())
    assert fetched is None


async def test_case_insensitive_duplicate_email_is_rejected(db_session: AsyncSession) -> None:
    await _create_user(db_session, email="Dup@Example.com")
    with pytest.raises(EmailAlreadyExistsError):
        # A second caller normalizing differently-cased input still
        # produces the same normalized email — this is exactly what
        # instruction K's "case-insensitive duplicate email rejection"
        # is checking.
        await _create_user(db_session, email="dup@example.com")


async def test_database_check_constraint_rejects_non_normalized_email(
    db_session: AsyncSession,
) -> None:
    """The DB-level backstop: even bypassing normalize_email(), the CHECK constraint holds.

    This directly exercises ``ck_users_email_lowercase`` from
    app/modules/users/models.py, independent of the application-layer
    normalization every real caller is expected to perform.
    """
    stmt = insert(User).values(
        id=uuid.uuid4(),
        email="NOT-LOWERCASED@example.com",
        password_hash=hash_password("a-strong-real-password-1"),
        full_name="Bypasses Normalization",
        role=UserRole.STUDENT,
        is_active=True,
    )
    with pytest.raises(IntegrityError):
        await db_session.execute(stmt)
        await db_session.flush()
    await db_session.rollback()


async def test_password_is_hashed_not_stored_in_plaintext(db_session: AsyncSession) -> None:
    user = await _create_user(db_session, email="hashed@example.com", password="a-real-secret-1")
    assert user.password_hash != "a-real-secret-1"
    assert "a-real-secret-1" not in user.password_hash


async def test_user_read_schema_excludes_password_hash(db_session: AsyncSession) -> None:
    user = await _create_user(db_session, email="safe-response@example.com")
    dumped = UserRead.model_validate(user).model_dump()
    assert "password_hash" not in dumped
    assert "password_hash" not in UserRead.model_fields


async def test_role_round_trips_through_native_enum(db_session: AsyncSession) -> None:
    admin = await _create_user(db_session, email="admin-role@example.com", role=UserRole.ADMIN)
    fetched = await UserRepository(db_session).get_by_id(admin.id)
    assert fetched is not None
    assert fetched.role is UserRole.ADMIN


def test_user_role_enum_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        UserRole("not-a-real-role")


async def test_inactive_user_round_trips_correctly(db_session: AsyncSession) -> None:
    inactive = await _create_user(db_session, email="inactive@example.com", is_active=False)
    fetched = await UserRepository(db_session).get_by_id(inactive.id)
    assert fetched is not None
    assert fetched.is_active is False
