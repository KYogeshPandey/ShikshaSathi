"""ORM models for role-linked profile data: ``TeacherProfile`` and ``StudentProfile``.

Design decisions:

- **One-to-one with ``users``.** Both tables carry a ``UniqueConstraint``
  on ``user_id`` (not just a plain foreign key), so the database itself
  rejects a second profile row for the same user — not only an
  application-layer check (Stage 1 brief: "one TeacherProfile per teacher
  User", "one StudentProfile per student User").
- **``ondelete="CASCADE"`` on ``user_id``.** If a ``User`` row is ever
  hard-deleted, its profile row must not become an orphan (Stage 1 brief:
  "no orphan profile rows"). In practice, Phase 2's ``is_active`` soft-flag
  is expected to be used instead of deleting user rows outright, but the
  FK behavior is still a correct structural backstop either way.
- **Role match is enforced at the repository layer, not a DB CHECK
  constraint.** PostgreSQL cannot express "this row's implied role must
  equal a *different table's* row's ``role`` column" as a single-table
  CHECK constraint without a trigger. Given no project document mandates
  a trigger-based approach, the simplest safe MVP rule (per the Stage 1
  brief's instruction 5) is chosen instead: ``ProfileRepository.create()``
  loads the referenced ``User`` and raises ``ProfileRoleMismatchError``
  before ever inserting a mismatched profile row. This is documented
  as a known structural limitation (a direct row inserted by raw SQL,
  bypassing the repository, would not be caught) rather than silently
  assumed to be airtight.
- **``StudentProfile.classroom_id`` is a plain nullable foreign key, not
  an association table.** The legacy app models student-classroom
  membership as exactly one classroom per student
  (``backend/app/models/student.py``'s single ``classroom_id`` field), a
  many-to-one relationship — an explicit association table is required
  by the Stage 1 brief only "where many-to-many relationships exist",
  which this is not. Nullable so a student profile can exist before being
  assigned to any classroom yet, without that being an error state.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TeacherProfile(Base):
    """Extended profile data for a ``User`` with role ``teacher``."""

    __tablename__ = "teacher_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    employee_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
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
        sa.UniqueConstraint("user_id", name="uq_teacher_profiles_user_id"),
        sa.UniqueConstraint("employee_code", name="uq_teacher_profiles_employee_code"),
        sa.Index("ix_teacher_profiles_user_id", "user_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"TeacherProfile(id={self.id!r}, user_id={self.user_id!r})"


class StudentProfile(Base):
    """Extended profile data for a ``User`` with role ``student``."""

    __tablename__ = "student_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    classroom_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("classrooms.id", ondelete="SET NULL"), nullable=True
    )
    roll_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
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
        sa.UniqueConstraint("user_id", name="uq_student_profiles_user_id"),
        sa.UniqueConstraint(
            "classroom_id", "roll_number", name="uq_student_profiles_classroom_roll"
        ),
        sa.Index("ix_student_profiles_user_id", "user_id"),
        sa.Index("ix_student_profiles_classroom_id", "classroom_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"StudentProfile(id={self.id!r}, user_id={self.user_id!r}, "
            f"classroom_id={self.classroom_id!r})"
        )
