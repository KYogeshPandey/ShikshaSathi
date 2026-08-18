"""Regression tests for Phase 3 ORM importability and Alembic metadata registration.

Mirrors ``app.tests.test_model_registration`` (the Phase 2 version of
this same test) — kept as a separate file rather than edited into that
one, since that file is Phase 2's own regression test and Stage 1's
brief is additive, not a rewrite of Phase 2 work.
"""

from __future__ import annotations

from app.db.base import Base
from app.db.models import (
    Announcement,
    AnnouncementClassroom,
    Classroom,
    RefreshSession,
    StudentProfile,
    Subject,
    TeacherAssignment,
    TeacherProfile,
    TimetableEntry,
    User,
)
from app.modules.academics.models import (
    Classroom as DirectClassroom,
)
from app.modules.academics.models import (
    Subject as DirectSubject,
)
from app.modules.academics.models import (
    TeacherAssignment as DirectTeacherAssignment,
)
from app.modules.academics.models import (
    TimetableEntry as DirectTimetableEntry,
)
from app.modules.announcements.models import (
    Announcement as DirectAnnouncement,
)
from app.modules.announcements.models import (
    AnnouncementAudience,
)
from app.modules.announcements.models import (
    AnnouncementClassroom as DirectAnnouncementClassroom,
)
from app.modules.profiles.models import (
    StudentProfile as DirectStudentProfile,
)
from app.modules.profiles.models import (
    TeacherProfile as DirectTeacherProfile,
)


def test_phase3_orm_model_modules_import_without_mapping_errors() -> None:
    """Every Phase 3 module imports cleanly and app.db.models re-exports the same class object."""
    assert DirectClassroom is Classroom
    assert DirectSubject is Subject
    assert DirectTeacherAssignment is TeacherAssignment
    assert DirectTimetableEntry is TimetableEntry
    assert DirectTeacherProfile is TeacherProfile
    assert DirectStudentProfile is StudentProfile
    assert DirectAnnouncement is Announcement
    assert DirectAnnouncementClassroom is AnnouncementClassroom


def test_phase3_tables_are_registered_in_base_metadata() -> None:
    expected_tables = {
        "classrooms",
        "subjects",
        "teacher_profiles",
        "student_profiles",
        "teacher_assignments",
        "timetable_entries",
        "announcements",
        "announcement_classrooms",
    }
    assert expected_tables.issubset(Base.metadata.tables)


def test_phase2_and_phase3_tables_coexist_in_one_metadata() -> None:
    """Phase 2's tables are still registered — Stage 1 is additive, not a replacement."""
    assert {"users", "refresh_sessions"}.issubset(Base.metadata.tables)
    assert RefreshSession.__tablename__ == "refresh_sessions"
    assert User.__tablename__ == "users"


def test_stage2_announcement_audience_values_are_registered() -> None:
    assert {audience.value for audience in AnnouncementAudience} == {
        "all",
        "classroom",
        "teacher",
        "student",
    }
