"""ORM models for attendance core and the audit trail.

Design decisions (see docs/adr/0010-phase4-attendance-and-audit-trail.md
for full rationale; summarized here at the point of use):

- **UUID primary keys**, continuing the Phase 2/3 convention (docs/adr/0006)
  for the same enumeration-resistance reason.
- **``AttendanceRecord`` uniqueness** is enforced by a four-column unique
  constraint on (``student_profile_id``, ``classroom_id``, ``subject_id``,
  ``attendance_date``) — a student can have at most one attendance row for
  a given classroom/subject/date triple. This is a database-level
  backstop for the service-layer upsert behavior implemented in Stage 2,
  not merely an application-level assumption.
- **No attendance-session table.** Nothing in `docs/IMPLEMENTATION_PLAN.md`
  Phase 4 or `docs/ARCHITECTURE.md` calls for a separate "session" concept
  distinct from (classroom, subject, date); the simplest schema that
  satisfies the documented acceptance criteria is chosen instead, per the
  Phase 4 brief's explicit instruction not to add one without a proven
  need.
- **``status`` is a native PostgreSQL enum** (``attendance_status``),
  limited to ``present``/``absent`` — an invalid status is structurally
  impossible to store, matching the ``user_role``/``day_of_week``/
  ``announcement_audience`` pattern already established in Phase 2/3.
- **``marked_by_user_id`` uses ``ondelete="RESTRICT"``**, matching
  ``Announcement.author_user_id``'s rationale
  (app/modules/announcements/models.py): an attendance row is an
  attributable historical record, so the user who marked it must not be
  silently orphaned by a hard user deletion. In practice users are only
  ever soft-deactivated (``is_active=False``), never hard-deleted, so this
  is a structural backstop rather than an expected code path.
- **``AuditLog`` is intentionally append-only**: no ``updated_at`` column,
  and — enforced at the repository layer, not the schema layer — no
  update/delete method exists anywhere in
  ``app.modules.attendance.repository.AuditLogRepository``. This directly
  satisfies the Phase 4 brief's "audit logs must be append-only" / "no
  update endpoint, no delete endpoint, no repository update/delete
  operation" requirement.
- **``AuditLog.actor_user_id`` is non-nullable.** Every attendance
  operation this module logs (successful write, or a blocked/forbidden
  attempt) is only ever reached after authentication has already
  succeeded (Phase 2's ``get_current_active_user`` dependency) — an
  unauthenticated request never reaches a point where an audit row would
  be created at all. There is therefore no genuine case in Stage 1/2's
  scope where the actor is unknown, so the nullable-only-when-necessary
  guidance in the Phase 4 brief resolves to "not nullable" here. FK uses
  ``ondelete="RESTRICT"`` for the same historical-attributability reason
  as ``marked_by_user_id`` above.
- **``AuditLog.classroom_id`` / ``subject_id`` use ``ondelete="SET NULL"``.**
  These are optional contextual-scope columns on an audit row, not the
  row's own identity — losing the classroom/subject reference (an
  extremely unlikely hard-delete in this application) should not cascade
  into deleting audit history, so ``SET NULL`` is used instead of
  ``CASCADE``/``RESTRICT``.
- **``AuditLog.event_metadata`` is a sanitized JSONB column.** Populated
  exclusively by the service layer (Stage 2) with pre-sanitized,
  size-bounded content — never a raw request body, token, password,
  cookie, or stack trace (Phase 4 brief, instruction D). The column is
  named ``event_metadata`` rather than ``metadata``, since ``metadata`` is
  reserved by SQLAlchemy's ``DeclarativeBase``.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum, StrEnum

import sqlalchemy as sa
from sqlalchemy import Date, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _enum_values(enum_cls: type[Enum]) -> list[str]:
    """Persist each enum member's public value, not its Python member name.

    Duplicated (rather than imported) from ``app.modules.users.models``,
    matching the same deliberate choice already made in
    ``app.modules.academics.models`` — avoiding a cross-module import
    between two otherwise-independent domain modules for the sake of one
    four-line helper.
    """
    return [str(member.value) for member in enum_cls]


class AttendanceStatus(StrEnum):
    """The only two attendance outcomes required by the Phase 4 brief."""

    PRESENT = "present"
    ABSENT = "absent"


class AuditOutcome(StrEnum):
    """Whether the audited action actually happened or was rejected."""

    SUCCESS = "success"
    BLOCKED = "blocked"


class AttendanceRecord(Base):
    """One student's attendance status for one classroom/subject/date."""

    __tablename__ = "attendance_records"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    student_profile_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("student_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    classroom_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False
    )
    attendance_date: Mapped[date] = mapped_column(Date(), nullable=False)
    status: Mapped[AttendanceStatus] = mapped_column(
        sa.Enum(
            AttendanceStatus,
            name="attendance_status",
            native_enum=True,
            validate_strings=True,
            values_callable=_enum_values,
        ),
        nullable=False,
    )
    remarks: Mapped[str | None] = mapped_column(String(500), nullable=True)
    marked_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
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
            "student_profile_id",
            "classroom_id",
            "subject_id",
            "attendance_date",
            name="uq_attendance_records_student_classroom_subject_date",
        ),
        sa.Index("ix_attendance_records_student_profile_id", "student_profile_id"),
        sa.Index("ix_attendance_records_classroom_id", "classroom_id"),
        sa.Index("ix_attendance_records_subject_id", "subject_id"),
        sa.Index("ix_attendance_records_attendance_date", "attendance_date"),
        sa.Index("ix_attendance_records_marked_by_user_id", "marked_by_user_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"AttendanceRecord(id={self.id!r}, student_profile_id={self.student_profile_id!r}, "
            f"classroom_id={self.classroom_id!r}, subject_id={self.subject_id!r}, "
            f"attendance_date={self.attendance_date!r}, status={self.status!r})"
        )


class AuditLog(Base):
    """An immutable record of a successful or blocked attendance-related action.

    Append-only by design: see this module's docstring and
    ``app.modules.attendance.repository.AuditLogRepository`` — no
    update/delete method exists for this model anywhere in the
    application.
    """

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[AuditOutcome] = mapped_column(
        sa.Enum(
            AuditOutcome,
            name="audit_outcome",
            native_enum=True,
            validate_strings=True,
            values_callable=_enum_values,
        ),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    classroom_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("classrooms.id", ondelete="SET NULL"), nullable=True
    )
    subject_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True
    )
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Named `event_metadata`, not `metadata`: the latter is reserved by
    # SQLAlchemy's DeclarativeBase (app/db/base.py).
    event_metadata: Mapped[dict[str, object]] = mapped_column(
        JSONB(), nullable=False, default=dict, server_default=sa.text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )

    __table_args__ = (
        sa.Index("ix_audit_logs_actor_user_id", "actor_user_id"),
        sa.Index("ix_audit_logs_action", "action"),
        sa.Index("ix_audit_logs_outcome", "outcome"),
        sa.Index("ix_audit_logs_entity_type_entity_id", "entity_type", "entity_id"),
        sa.Index("ix_audit_logs_classroom_id", "classroom_id"),
        sa.Index("ix_audit_logs_subject_id", "subject_id"),
        sa.Index("ix_audit_logs_created_at", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"AuditLog(id={self.id!r}, action={self.action!r}, outcome={self.outcome!r}, "
            f"entity_type={self.entity_type!r}, entity_id={self.entity_id!r})"
        )


__all__ = [
    "AttendanceRecord",
    "AttendanceStatus",
    "AuditLog",
    "AuditOutcome",
]
