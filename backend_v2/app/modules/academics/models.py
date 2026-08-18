"""ORM models for the academic domain: ``Classroom``, ``Subject``,
``TeacherAssignment``, and ``TimetableEntry``.

Design decisions for Phase 3 Stage 1 (see docs/HANDOVER_PHASE_3_STAGE_1.md
and docs/adr/0007-phase3-stage1-academic-domain.md for full rationale;
summarized here at the point of use):

- **UUID primary keys** on every new table, matching the Phase 2 decision
  (docs/adr/0006) for the same enumeration-resistance reason — nothing in
  project documentation says otherwise for Phase 3, so the existing
  convention is simply continued, not re-litigated.
- **``code`` columns are normalized and unique**, with the same
  application-normalization + DB-level-CHECK-constraint belt-and-suspenders
  pattern as ``users.email`` (``app.modules.academics.normalization``,
  ``ck_classrooms_code_lowercase`` / ``ck_subjects_code_lowercase``).
- **Soft delete via ``is_active``**, not row deletion, for `Classroom` and
  `Subject` — matches the legacy app's own soft-delete convention
  (``backend/app/models/classroom.py``'s ``delete_classroom(hard=False)``)
  and keeps historical assignments/timetable entries referencing a real,
  inspectable row instead of an orphaned foreign key.
- **``TeacherAssignment`` is an explicit association model**
  (teacher_profile x classroom x subject), not a comma-separated ID list on
  `Classroom`/`Subject`/`TeacherProfile` — required by the Stage 1 brief
  ("Avoid storing comma-separated IDs ... use explicit association
  tables/models where many-to-many relationships exist"). A teacher can be
  assigned to many (classroom, subject) pairs, and multiple teachers may
  share a pair. The unique constraint below prevents only a duplicate of
  the same teacher/classroom/subject triple.
- **Timetable collision rule.** No project document defines an exact
  overlap-detection invariant, so the simplest safe MVP rule is chosen and
  documented here: an exact-start-time collision for the *same classroom*
  or for the *same teacher* on the same day is rejected at the database
  level via unique constraints. Detecting partially *overlapping* but
  differently-timed slots (e.g. 09:00-10:00 vs. 09:30-10:30) is **not**
  enforced in Stage 1 — flagged as a known limitation for Stage 2's
  service layer to potentially extend with an explicit overlap query.
"""

from __future__ import annotations

import uuid
from datetime import datetime, time
from enum import Enum, StrEnum

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Time
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _enum_values(enum_cls: type[Enum]) -> list[str]:
    """Persist each enum member's public value, not its Python member name.

    Duplicated (rather than imported) from ``app.modules.users.models`` to
    avoid a cross-module import between two otherwise-independent domain
    modules for the sake of one four-line helper.
    """
    return [str(member.value) for member in enum_cls]


class DayOfWeek(StrEnum):
    """A native PostgreSQL enum so an invalid day is structurally impossible."""

    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"


class Classroom(Base):
    """A single classroom/section (e.g. "Grade 8 - Section A")."""

    __tablename__ = "classrooms"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    grade_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    section: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=sa.true()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        nullable=False,
    )

    __table_args__ = (
        sa.UniqueConstraint("code", name="uq_classrooms_code"),
        sa.CheckConstraint("code = lower(code)", name="ck_classrooms_code_lowercase"),
        sa.Index("ix_classrooms_is_active", "is_active"),
    )

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"Classroom(id={self.id!r}, code={self.code!r})"


class Subject(Base):
    """A single subject (e.g. "Mathematics"), independent of any classroom."""

    __tablename__ = "subjects"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    is_elective: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa.false()
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=sa.true()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        nullable=False,
    )

    __table_args__ = (
        sa.UniqueConstraint("code", name="uq_subjects_code"),
        sa.CheckConstraint("code = lower(code)", name="ck_subjects_code_lowercase"),
        sa.Index("ix_subjects_is_active", "is_active"),
    )

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"Subject(id={self.id!r}, code={self.code!r})"


class TeacherAssignment(Base):
    """Explicit association: a teacher profile assigned to a (classroom, subject) pair.

    ``app.modules.profiles.models.TeacherProfile`` is referenced by id
    only (no back-reference relationship is declared in Stage 1 — Stage 2
    services can add ORM ``relationship()`` wiring once query patterns are
    known; Stage 1 sticks to columns/constraints per the brief's scope).
    """

    __tablename__ = "teacher_assignments"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    teacher_profile_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("teacher_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    classroom_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=sa.true()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        nullable=False,
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "teacher_profile_id",
            "classroom_id",
            "subject_id",
            name="uq_teacher_assignments_teacher_classroom_subject",
        ),
        sa.Index("ix_teacher_assignments_teacher_profile_id", "teacher_profile_id"),
        sa.Index("ix_teacher_assignments_classroom_id", "classroom_id"),
        sa.Index("ix_teacher_assignments_subject_id", "subject_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"TeacherAssignment(id={self.id!r}, teacher_profile_id={self.teacher_profile_id!r}, "
            f"classroom_id={self.classroom_id!r}, subject_id={self.subject_id!r})"
        )


class TimetableEntry(Base):
    """A single scheduled (classroom, subject, teacher) slot on one weekday."""

    __tablename__ = "timetable_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    classroom_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False
    )
    teacher_profile_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("teacher_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    day_of_week: Mapped[DayOfWeek] = mapped_column(
        sa.Enum(
            DayOfWeek,
            name="day_of_week",
            native_enum=True,
            validate_strings=True,
            values_callable=_enum_values,
        ),
        nullable=False,
    )
    start_time: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)
    end_time: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=sa.true()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        nullable=False,
    )

    __table_args__ = (
        sa.CheckConstraint("start_time < end_time", name="ck_timetable_entries_start_before_end"),
        sa.UniqueConstraint(
            "classroom_id",
            "day_of_week",
            "start_time",
            name="uq_timetable_entries_classroom_day_start",
        ),
        sa.UniqueConstraint(
            "teacher_profile_id",
            "day_of_week",
            "start_time",
            name="uq_timetable_entries_teacher_day_start",
        ),
        sa.Index("ix_timetable_entries_classroom_id", "classroom_id"),
        sa.Index("ix_timetable_entries_teacher_profile_id", "teacher_profile_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"TimetableEntry(id={self.id!r}, classroom_id={self.classroom_id!r}, "
            f"day_of_week={self.day_of_week!r}, start_time={self.start_time!r})"
        )
