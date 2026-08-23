from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Environment, Settings, get_settings
from app.modules.academics.models import Classroom, Subject, TeacherAssignment, TimetableEntry
from app.modules.analytics.service import AnalyticsService
from app.modules.announcements.models import Announcement, AnnouncementAudience
from app.modules.attendance.models import AttendanceRecord, AttendanceStatus
from app.modules.auth.security import hash_password
from app.modules.demo_data.service import (
    DemoProductionSafetyError,
    assert_demo_seeding_allowed,
    demo_manifest_counts,
    seed_demo_data,
)
from app.modules.profiles.models import StudentProfile, TeacherProfile
from app.modules.users.models import User, UserRole

pytestmark = pytest.mark.asyncio

_ANCHOR = date(2026, 8, 20)
_TEST_PASSWORD = "demo-test-password-123"


async def _count(session: AsyncSession, model: type[object]) -> int:
    return int((await session.scalar(select(func.count()).select_from(model))) or 0)


async def test_demo_seed_is_idempotent_and_relationships_are_valid(
    db_session: AsyncSession,
) -> None:
    settings = get_settings()
    expected = demo_manifest_counts(anchor=_ANCHOR)

    first = await seed_demo_data(
        db_session,
        settings=settings,
        raw_password=_TEST_PASSWORD,
        anchor=_ANCHOR,
    )
    assert first.created == sum(expected.values())
    assert first.updated == 0
    assert first.attendance_end < _ANCHOR

    model_counts = {
        "users": await _count(db_session, User),
        "teacher_profiles": await _count(db_session, TeacherProfile),
        "student_profiles": await _count(db_session, StudentProfile),
        "classrooms": await _count(db_session, Classroom),
        "subjects": await _count(db_session, Subject),
        "teacher_assignments": await _count(db_session, TeacherAssignment),
        "timetable_entries": await _count(db_session, TimetableEntry),
        "announcements": await _count(db_session, Announcement),
        "attendance_records": await _count(db_session, AttendanceRecord),
    }
    assert model_counts == {key: value for key, value in expected.items() if key in model_counts}

    await db_session.commit()
    second = await seed_demo_data(
        db_session,
        settings=settings,
        raw_password=_TEST_PASSWORD,
        anchor=_ANCHOR,
    )
    assert second.created == 0
    assert second.updated == sum(expected.values())
    assert await _count(db_session, AttendanceRecord) == expected["attendance_records"]

    class_sizes = (
        await db_session.execute(
            select(StudentProfile.classroom_id, func.count(StudentProfile.id)).group_by(
                StudentProfile.classroom_id
            )
        )
    ).all()
    assert sorted(count for _, count in class_sizes) == [6, 6]
    assert await _count(db_session, TeacherAssignment) == 6
    assert await _count(db_session, TimetableEntry) == 10

    status_counts = dict(
        (
            await db_session.execute(
                select(AttendanceRecord.status, func.count(AttendanceRecord.id)).group_by(
                    AttendanceRecord.status
                )
            )
        ).all()
    )
    assert status_counts[AttendanceStatus.PRESENT] > 0
    assert status_counts[AttendanceStatus.ABSENT] > 0

    absent_by_student = (
        await db_session.execute(
            select(AttendanceRecord.student_profile_id, func.count(AttendanceRecord.id))
            .where(AttendanceRecord.status == AttendanceStatus.ABSENT)
            .group_by(AttendanceRecord.student_profile_id)
        )
    ).all()
    assert len({count for _, count in absent_by_student}) >= 2

    admin = await db_session.scalar(select(User).where(User.email == settings.DEMO_ADMIN_EMAIL))
    assert admin is not None
    analytics = await AnalyticsService(db_session).overview(
        admin,
        days=30,
        date_to=_ANCHOR - timedelta(days=1),
    )
    assert analytics.attendance.total_count == expected["attendance_records"]
    assert analytics.attendance.present_count > 0
    assert analytics.attendance.absent_count > 0
    assert analytics.attention_classrooms


async def test_reset_restores_demo_history_without_touching_unrelated_rows(
    db_session: AsyncSession,
) -> None:
    settings = get_settings()
    await seed_demo_data(
        db_session,
        settings=settings,
        raw_password=_TEST_PASSWORD,
        anchor=_ANCHOR,
    )
    admin_id = await db_session.scalar(
        select(User.id).where(User.email == settings.DEMO_ADMIN_EMAIL)
    )
    assert admin_id is not None
    unrelated = Announcement(
        id=uuid.uuid4(),
        title="Unrelated school announcement",
        content="This row must survive the demo reset.",
        author_user_id=admin_id,
        audience=AnnouncementAudience.ALL,
        is_active=True,
    )
    unrelated_user = User(
        id=uuid.uuid4(),
        email="unrelated@example.com",
        password_hash=hash_password(_TEST_PASSWORD),
        full_name="Unrelated User",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add_all([unrelated, unrelated_user])
    await db_session.commit()

    reset = await seed_demo_data(
        db_session,
        settings=settings,
        raw_password=_TEST_PASSWORD,
        anchor=_ANCHOR,
        reset_demo=True,
    )
    assert reset.reset_rows_removed > 0
    assert await db_session.get(Announcement, unrelated.id) is not None
    assert await db_session.get(User, unrelated_user.id) is not None
    assert (
        await _count(db_session, AttendanceRecord)
        == demo_manifest_counts(anchor=_ANCHOR)["attendance_records"]
    )


async def test_production_demo_seed_requires_explicit_opt_in() -> None:
    values = get_settings().model_dump()
    values.update(
        {
            "APP_ENV": Environment.PRODUCTION,
            "DEBUG": False,
            "CORS_ALLOWED_ORIGINS": ["https://app.example.com"],
            "TRUSTED_HOSTS": ["api.example.com"],
            "REFRESH_TOKEN_COOKIE_SECURE": True,
            "DEMO_SEED_ALLOW_PRODUCTION": False,
        }
    )
    production_settings = Settings(**values)
    with pytest.raises(DemoProductionSafetyError):
        assert_demo_seeding_allowed(production_settings)
    assert_demo_seeding_allowed(production_settings, dry_run=True)

    opted_in = Settings(**{**values, "DEMO_SEED_ALLOW_PRODUCTION": True})
    assert_demo_seeding_allowed(opted_in)
