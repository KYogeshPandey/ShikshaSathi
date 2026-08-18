"""Database-backed tests for the ``announcements`` domain.

Uses the ``db_session`` fixture (app/tests/conftest.py), which requires
a reachable Phase 3-migrated PostgreSQL test database and skips
gracefully if one is not available.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.academics.normalization import normalize_code
from app.modules.academics.repository import ClassroomRepository
from app.modules.announcements.errors import (
    AnnouncementAuthorNotFoundError,
    AnnouncementClassroomReferenceError,
    InvalidAnnouncementAudienceError,
)
from app.modules.announcements.models import AnnouncementAudience
from app.modules.announcements.repository import AnnouncementRepository
from app.modules.announcements.schemas import AnnouncementCreate, AnnouncementRead
from app.modules.auth.security import hash_password
from app.modules.users.models import User, UserRole
from app.modules.users.normalization import normalize_email
from app.modules.users.repository import UserRepository


async def _create_author(session: AsyncSession, *, email: str = "author@example.com") -> User:
    user = await UserRepository(session).create(
        email=normalize_email(email),
        password_hash=hash_password("a-strong-real-password-1"),
        full_name="Test Author",
        role=UserRole.ADMIN,
        is_active=True,
    )
    await session.commit()
    return user


# --- Pydantic schema-level audience validation (no DB needed) --------------


def test_schema_rejects_all_audience_with_classroom_ids() -> None:
    with pytest.raises(ValidationError):
        AnnouncementCreate(
            title="Holiday",
            content="School closed tomorrow.",
            author_user_id=uuid.uuid4(),
            audience=AnnouncementAudience.ALL,
            classroom_ids=[uuid.uuid4()],
        )


def test_schema_rejects_classroom_audience_with_no_classroom_ids() -> None:
    with pytest.raises(ValidationError):
        AnnouncementCreate(
            title="Reminder",
            content="Bring your books.",
            author_user_id=uuid.uuid4(),
            audience=AnnouncementAudience.CLASSROOM,
            classroom_ids=[],
        )


def test_schema_accepts_all_audience_with_no_classroom_ids() -> None:
    created = AnnouncementCreate(
        title="  Welcome   Back ",
        content="School reopens Monday.",
        author_user_id=uuid.uuid4(),
        audience=AnnouncementAudience.ALL,
    )
    assert created.title == "Welcome Back"
    assert created.classroom_ids == []


def test_schema_dedupes_repeated_classroom_ids() -> None:
    classroom_id = uuid.uuid4()
    created = AnnouncementCreate(
        title="Exam schedule",
        content="See attached.",
        author_user_id=uuid.uuid4(),
        audience=AnnouncementAudience.CLASSROOM,
        classroom_ids=[classroom_id, classroom_id],
    )
    assert created.classroom_ids == [classroom_id]


# --- Repository-level behavior (DB-backed) ----------------------------------


async def test_create_all_audience_announcement(db_session: AsyncSession) -> None:
    author = await _create_author(db_session, email="author1@example.com")
    announcement = await AnnouncementRepository(db_session).create(
        title="Welcome Back",
        content="School reopens Monday.",
        author_user_id=author.id,
        audience=AnnouncementAudience.ALL,
    )
    await db_session.commit()

    assert announcement.audience is AnnouncementAudience.ALL
    classroom_ids = await AnnouncementRepository(db_session).list_classroom_ids(announcement.id)
    assert classroom_ids == []


async def test_create_classroom_audience_announcement_round_trip(
    db_session: AsyncSession,
) -> None:
    author = await _create_author(db_session, email="author2@example.com")
    classroom_a = await ClassroomRepository(db_session).create(
        name="Announce Classroom A", code=normalize_code("announce-classroom-a")
    )
    classroom_b = await ClassroomRepository(db_session).create(
        name="Announce Classroom B", code=normalize_code("announce-classroom-b")
    )
    await db_session.commit()

    repo = AnnouncementRepository(db_session)
    announcement = await repo.create(
        title="Exam schedule",
        content="See attached.",
        author_user_id=author.id,
        audience=AnnouncementAudience.CLASSROOM,
        classroom_ids=[classroom_a.id, classroom_b.id],
    )
    await db_session.commit()

    classroom_ids = await repo.list_classroom_ids(announcement.id)
    assert set(classroom_ids) == {classroom_a.id, classroom_b.id}
    classroom_ids_by_announcement = await repo.list_classroom_ids_for_announcements(
        [announcement.id]
    )
    assert set(classroom_ids_by_announcement[announcement.id]) == {
        classroom_a.id,
        classroom_b.id,
    }

    read_model = AnnouncementRead.from_model(announcement, classroom_ids)
    assert read_model.audience is AnnouncementAudience.CLASSROOM
    assert set(read_model.classroom_ids) == {classroom_a.id, classroom_b.id}


async def test_create_announcement_missing_author_is_rejected(db_session: AsyncSession) -> None:
    with pytest.raises(AnnouncementAuthorNotFoundError):
        await AnnouncementRepository(db_session).create(
            title="Ghost author",
            content="Should not be created.",
            author_user_id=uuid.uuid4(),
            audience=AnnouncementAudience.ALL,
        )


async def test_create_announcement_missing_classroom_is_rejected(
    db_session: AsyncSession,
) -> None:
    author = await _create_author(db_session, email="author3@example.com")
    with pytest.raises(AnnouncementClassroomReferenceError):
        await AnnouncementRepository(db_session).create(
            title="Bad classroom reference",
            content="Should not be created.",
            author_user_id=author.id,
            audience=AnnouncementAudience.CLASSROOM,
            classroom_ids=[uuid.uuid4()],
        )


async def test_repository_rejects_inconsistent_audience_even_bypassing_schema(
    db_session: AsyncSession,
) -> None:
    """Belt-and-suspenders: the repository re-validates even if a caller skips the schema."""
    author = await _create_author(db_session, email="author4@example.com")
    with pytest.raises(InvalidAnnouncementAudienceError):
        await AnnouncementRepository(db_session).create(
            title="Inconsistent",
            content="audience=all but classroom_ids given directly to the repository.",
            author_user_id=author.id,
            audience=AnnouncementAudience.ALL,
            classroom_ids=[uuid.uuid4()],
        )


async def test_deactivate_announcement(db_session: AsyncSession) -> None:
    author = await _create_author(db_session, email="author5@example.com")
    repo = AnnouncementRepository(db_session)
    announcement = await repo.create(
        title="Retract me",
        content="Temporary notice.",
        author_user_id=author.id,
        audience=AnnouncementAudience.ALL,
    )
    await db_session.commit()

    deactivated = await repo.deactivate(announcement)
    await db_session.commit()

    assert deactivated.is_active is False
