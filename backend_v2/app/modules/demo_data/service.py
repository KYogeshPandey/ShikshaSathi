"""Small, deterministic demo dataset built entirely from existing models.

Nothing in this module runs at application startup. The only production entry
point is the explicit ``scripts.seed_demo_data`` command, which applies the
environment guard below before opening a database transaction.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, time, timedelta
from typing import cast

from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Environment, Settings
from app.db.base import Base
from app.modules.academics.models import (
    Classroom,
    DayOfWeek,
    Subject,
    TeacherAssignment,
    TimetableEntry,
)
from app.modules.announcements.models import (
    Announcement,
    AnnouncementAudience,
    AnnouncementClassroom,
)
from app.modules.attendance.models import AttendanceRecord, AttendanceStatus
from app.modules.auth.security import hash_password
from app.modules.profiles.models import StudentProfile, TeacherProfile
from app.modules.users.models import User, UserRole
from app.modules.users.normalization import normalize_email

_NAMESPACE = uuid.UUID("ddc2f10b-a621-4cb4-8952-35f395b75d85")


class DemoDataCollisionError(RuntimeError):
    """A demo natural key is already owned by a different database row."""


class DemoProductionSafetyError(RuntimeError):
    """Demo writes were attempted in production without explicit opt-in."""


@dataclass(frozen=True, slots=True)
class SeedRow:
    id: uuid.UUID
    values: dict[str, object]


@dataclass(frozen=True, slots=True)
class DemoSeedResult:
    desired_counts: dict[str, int]
    created: int
    updated: int
    reset_rows_removed: int
    attendance_start: date
    attendance_end: date


def _id(kind: str, key: str) -> uuid.UUID:
    return uuid.uuid5(_NAMESPACE, f"{kind}:{key}")


def assert_demo_seeding_allowed(settings: Settings, *, dry_run: bool = False) -> None:
    """Refuse production database mutation unless the operator explicitly opts in."""
    if (
        not dry_run
        and settings.APP_ENV is Environment.PRODUCTION
        and not settings.DEMO_SEED_ALLOW_PRODUCTION
    ):
        raise DemoProductionSafetyError(
            "Demo seeding is disabled in production. Set "
            "DEMO_SEED_ALLOW_PRODUCTION=true only for a deliberately selected "
            "demo environment."
        )


def _user_rows(settings: Settings, password_hash: str) -> tuple[SeedRow, ...]:
    rows = [
        SeedRow(
            _id("user", "admin"),
            {
                "email": normalize_email(settings.DEMO_ADMIN_EMAIL),
                "password_hash": password_hash,
                "full_name": "Demo Administrator",
                "role": UserRole.ADMIN,
                "is_active": True,
            },
        ),
        SeedRow(
            _id("user", "teacher-01"),
            {
                "email": normalize_email(settings.DEMO_TEACHER_ONE_EMAIL),
                "password_hash": password_hash,
                "full_name": "Demo Teacher One",
                "role": UserRole.TEACHER,
                "is_active": True,
            },
        ),
        SeedRow(
            _id("user", "teacher-02"),
            {
                "email": normalize_email(settings.DEMO_TEACHER_TWO_EMAIL),
                "password_hash": password_hash,
                "full_name": "Demo Teacher Two",
                "role": UserRole.TEACHER,
                "is_active": True,
            },
        ),
    ]
    for number in range(1, 13):
        email = (
            settings.DEMO_STUDENT_ONE_EMAIL
            if number == 1
            else f"student.{number:02d}@demo.shikshasathi.example"
        )
        rows.append(
            SeedRow(
                _id("user", f"student-{number:02d}"),
                {
                    "email": normalize_email(email),
                    "password_hash": password_hash,
                    "full_name": f"Demo Student {number:02d}",
                    "role": UserRole.STUDENT,
                    "is_active": True,
                },
            )
        )
    return tuple(rows)


def _classroom_rows() -> tuple[SeedRow, ...]:
    return (
        SeedRow(
            _id("classroom", "10-a"),
            {
                "name": "Demo Class 10-A",
                "code": "demo-10-a",
                "grade_level": "10",
                "section": "A",
                "is_active": True,
            },
        ),
        SeedRow(
            _id("classroom", "10-b"),
            {
                "name": "Demo Class 10-B",
                "code": "demo-10-b",
                "grade_level": "10",
                "section": "B",
                "is_active": True,
            },
        ),
    )


def _subject_rows() -> tuple[SeedRow, ...]:
    return tuple(
        SeedRow(
            _id("subject", code),
            {
                "name": name,
                "code": f"demo-{code}",
                "is_elective": False,
                "is_active": True,
            },
        )
        for code, name in (
            ("math", "Mathematics"),
            ("science", "Science"),
            ("english", "English"),
        )
    )


def _teacher_profile_rows() -> tuple[SeedRow, ...]:
    return tuple(
        SeedRow(
            _id("teacher-profile", f"teacher-{number:02d}"),
            {
                "user_id": _id("user", f"teacher-{number:02d}"),
                "employee_code": f"DEMO-T-{number:03d}",
                "phone_number": None,
                "is_active": True,
            },
        )
        for number in (1, 2)
    )


def _student_profile_rows() -> tuple[SeedRow, ...]:
    rows: list[SeedRow] = []
    for number in range(1, 13):
        classroom_key = "10-a" if number <= 6 else "10-b"
        roll_number = number if number <= 6 else number - 6
        rows.append(
            SeedRow(
                _id("student-profile", f"student-{number:02d}"),
                {
                    "user_id": _id("user", f"student-{number:02d}"),
                    "classroom_id": _id("classroom", classroom_key),
                    "roll_number": f"{roll_number:02d}",
                    "is_active": True,
                },
            )
        )
    return tuple(rows)


_ASSIGNMENT_MAP: tuple[tuple[str, str, str], ...] = (
    ("teacher-01", "10-a", "math"),
    ("teacher-01", "10-a", "science"),
    ("teacher-01", "10-b", "math"),
    ("teacher-02", "10-a", "english"),
    ("teacher-02", "10-b", "science"),
    ("teacher-02", "10-b", "english"),
)


def _assignment_rows() -> tuple[SeedRow, ...]:
    return tuple(
        SeedRow(
            _id("assignment", f"{teacher}:{classroom}:{subject}"),
            {
                "teacher_profile_id": _id("teacher-profile", teacher),
                "classroom_id": _id("classroom", classroom),
                "subject_id": _id("subject", subject),
                "is_active": True,
            },
        )
        for teacher, classroom, subject in _ASSIGNMENT_MAP
    )


_WEEKDAY_SUBJECTS: tuple[tuple[DayOfWeek, str], ...] = (
    (DayOfWeek.MONDAY, "math"),
    (DayOfWeek.TUESDAY, "science"),
    (DayOfWeek.WEDNESDAY, "english"),
    (DayOfWeek.THURSDAY, "math"),
    (DayOfWeek.FRIDAY, "science"),
)


def _teacher_for(classroom: str, subject: str) -> str:
    for teacher, assignment_classroom, assignment_subject in _ASSIGNMENT_MAP:
        if (assignment_classroom, assignment_subject) == (classroom, subject):
            return teacher
    raise AssertionError("Demo timetable references an unassigned teacher scope.")


def _timetable_rows() -> tuple[SeedRow, ...]:
    rows: list[SeedRow] = []
    for day, subject in _WEEKDAY_SUBJECTS:
        for classroom, start_hour in (("10-a", 9), ("10-b", 10)):
            teacher = _teacher_for(classroom, subject)
            key = f"{classroom}:{day.value}:{start_hour}"
            rows.append(
                SeedRow(
                    _id("timetable", key),
                    {
                        "classroom_id": _id("classroom", classroom),
                        "subject_id": _id("subject", subject),
                        "teacher_profile_id": _id("teacher-profile", teacher),
                        "day_of_week": day,
                        "start_time": time(start_hour, 0),
                        "end_time": time(start_hour, 45),
                        "is_active": True,
                    },
                )
            )
    return tuple(rows)


def _announcement_rows() -> tuple[SeedRow, ...]:
    admin_id = _id("user", "admin")
    return (
        SeedRow(
            _id("announcement", "welcome"),
            {
                "title": "Welcome to the Demo School",
                "content": (
                    "Explore attendance, reports, and role-aware analytics using synthetic data."
                ),
                "author_user_id": admin_id,
                "audience": AnnouncementAudience.ALL,
                "is_active": True,
            },
        ),
        SeedRow(
            _id("announcement", "teacher-review"),
            {
                "title": "Attendance Review Reminder",
                "content": "Please review each attendance session before confirming it.",
                "author_user_id": admin_id,
                "audience": AnnouncementAudience.TEACHER,
                "is_active": True,
            },
        ),
        SeedRow(
            _id("announcement", "class-a-science"),
            {
                "title": "Class 10-A Science Activity",
                "content": "Bring your science notebook for the next scheduled activity.",
                "author_user_id": admin_id,
                "audience": AnnouncementAudience.CLASSROOM,
                "is_active": True,
            },
        ),
    )


def _announcement_classroom_rows() -> tuple[SeedRow, ...]:
    return (
        SeedRow(
            _id("announcement-classroom", "class-a-science:10-a"),
            {
                "announcement_id": _id("announcement", "class-a-science"),
                "classroom_id": _id("classroom", "10-a"),
            },
        ),
    )


def _attendance_rows(anchor: date) -> tuple[SeedRow, ...]:
    rows: list[SeedRow] = []
    weekday_subject = {index: subject for index, (_, subject) in enumerate(_WEEKDAY_SUBJECTS)}
    for days_ago in range(1, 31):
        attendance_date = anchor - timedelta(days=days_ago)
        if attendance_date.weekday() >= 5:
            continue
        subject = weekday_subject[attendance_date.weekday()]
        for student_number in range(1, 13):
            classroom = "10-a" if student_number <= 6 else "10-b"
            classroom_index = 0 if classroom == "10-a" else 1
            within_class = student_number if student_number <= 6 else student_number - 6
            score = (attendance_date.toordinal() * 3 + within_class * 7 + classroom_index * 5) % 20
            absent_cutoff = 1 + classroom_index
            if within_class == 5:
                absent_cutoff += 2
            elif within_class == 6:
                absent_cutoff += 6
            status = AttendanceStatus.ABSENT if score < absent_cutoff else AttendanceStatus.PRESENT
            teacher = _teacher_for(classroom, subject)
            key = (
                f"student-{student_number:02d}:{classroom}:{subject}:{attendance_date.isoformat()}"
            )
            rows.append(
                SeedRow(
                    _id("attendance", key),
                    {
                        "student_profile_id": _id(
                            "student-profile", f"student-{student_number:02d}"
                        ),
                        "classroom_id": _id("classroom", classroom),
                        "subject_id": _id("subject", subject),
                        "attendance_date": attendance_date,
                        "status": status,
                        "remarks": "Synthetic demo history",
                        "marked_by_user_id": _id("user", teacher),
                    },
                )
            )
    return tuple(rows)


def demo_manifest_counts(*, anchor: date | None = None) -> dict[str, int]:
    effective_anchor = anchor or date.today()
    return {
        "users": 15,
        "teacher_profiles": len(_teacher_profile_rows()),
        "student_profiles": len(_student_profile_rows()),
        "classrooms": len(_classroom_rows()),
        "subjects": len(_subject_rows()),
        "teacher_assignments": len(_assignment_rows()),
        "timetable_entries": len(_timetable_rows()),
        "announcements": len(_announcement_rows()),
        "announcement_classrooms": len(_announcement_classroom_rows()),
        "attendance_records": len(_attendance_rows(effective_anchor)),
    }


async def _assert_no_natural_key_collisions(
    session: AsyncSession,
    users: tuple[SeedRow, ...],
) -> None:
    expected_users = {str(row.values["email"]): row.id for row in users}
    existing_users = await session.execute(
        select(User.id, User.email).where(User.email.in_(tuple(expected_users)))
    )
    for existing_id, email in existing_users:
        if expected_users[email] != existing_id:
            raise DemoDataCollisionError(f"Demo email {email!r} is already in use.")

    for model, rows, field_name in (
        (Classroom, _classroom_rows(), "code"),
        (Subject, _subject_rows(), "code"),
        (TeacherProfile, _teacher_profile_rows(), "employee_code"),
    ):
        expected = {str(row.values[field_name]): row.id for row in rows}
        field = getattr(model, field_name)
        existing_rows = await session.execute(
            select(model.id, field).where(field.in_(tuple(expected)))
        )
        for existing_id, natural_key in existing_rows:
            if expected[str(natural_key)] != existing_id:
                raise DemoDataCollisionError(
                    f"Demo {field_name} {natural_key!r} is already in use."
                )


async def _upsert_by_id[ModelT: Base](
    session: AsyncSession,
    model: type[ModelT],
    row: SeedRow,
) -> bool:
    existing = await session.get(model, row.id)
    if existing is None:
        session.add(model(**{"id": row.id, **row.values}))
        return True
    for field_name, value in row.values.items():
        setattr(existing, field_name, value)
    return False


async def _remove_demo_history(session: AsyncSession) -> int:
    student_ids = tuple(row.id for row in _student_profile_rows())
    classroom_ids = tuple(row.id for row in _classroom_rows())
    subject_ids = tuple(row.id for row in _subject_rows())
    statements = (
        delete(AttendanceRecord).where(
            AttendanceRecord.student_profile_id.in_(student_ids),
            AttendanceRecord.classroom_id.in_(classroom_ids),
            AttendanceRecord.subject_id.in_(subject_ids),
        ),
        delete(AnnouncementClassroom).where(
            AnnouncementClassroom.id.in_(tuple(row.id for row in _announcement_classroom_rows()))
        ),
        delete(Announcement).where(
            Announcement.id.in_(tuple(row.id for row in _announcement_rows()))
        ),
        delete(TimetableEntry).where(
            TimetableEntry.id.in_(tuple(row.id for row in _timetable_rows()))
        ),
        delete(TeacherAssignment).where(
            TeacherAssignment.id.in_(tuple(row.id for row in _assignment_rows()))
        ),
    )
    removed = 0
    for statement in statements:
        result = cast(CursorResult[object], await session.execute(statement))
        removed += result.rowcount or 0
    return removed


async def seed_demo_data(
    session: AsyncSession,
    *,
    settings: Settings,
    raw_password: str,
    anchor: date | None = None,
    reset_demo: bool = False,
) -> DemoSeedResult:
    """Upsert the known demo manifest in one transaction."""
    assert_demo_seeding_allowed(settings)
    effective_anchor = anchor or date.today()
    password_hash = hash_password(raw_password)
    users = _user_rows(settings, password_hash)
    attendance = _attendance_rows(effective_anchor)
    groups: tuple[tuple[type[Base], tuple[SeedRow, ...]], ...] = (
        (User, users),
        (Classroom, _classroom_rows()),
        (Subject, _subject_rows()),
        (TeacherProfile, _teacher_profile_rows()),
        (StudentProfile, _student_profile_rows()),
        (TeacherAssignment, _assignment_rows()),
        (TimetableEntry, _timetable_rows()),
        (Announcement, _announcement_rows()),
        (AnnouncementClassroom, _announcement_classroom_rows()),
        (AttendanceRecord, attendance),
    )
    created = 0
    updated = 0
    reset_rows_removed = 0
    async with session.begin():
        await _assert_no_natural_key_collisions(session, users)
        if reset_demo:
            reset_rows_removed = await _remove_demo_history(session)
        for model, rows in groups:
            for row in rows:
                if await _upsert_by_id(session, model, row):
                    created += 1
                else:
                    updated += 1
            # These models intentionally do not declare ORM relationships;
            # flushing each FK layer preserves the explicit parent-first order.
            await session.flush()

    dates = [cast(date, row.values["attendance_date"]) for row in attendance]
    return DemoSeedResult(
        desired_counts=demo_manifest_counts(anchor=effective_anchor),
        created=created,
        updated=updated,
        reset_rows_removed=reset_rows_removed,
        attendance_start=min(dates),
        attendance_end=max(dates),
    )


__all__ = [
    "DemoDataCollisionError",
    "DemoProductionSafetyError",
    "DemoSeedResult",
    "assert_demo_seeding_allowed",
    "demo_manifest_counts",
    "seed_demo_data",
]
