"""ORM models for the announcements domain: ``Announcement`` and its
explicit classroom-audience association, ``AnnouncementClassroom``.

Design decisions for Phase 3 Stage 1 (see docs/HANDOVER_PHASE_3_STAGE_1.md
for the full rationale; summarized here at the point of use):

- **Audience is an explicit, structured representation, not a
  comma-separated ID list.** ``Announcement.audience`` is a native
  PostgreSQL enum (``announcement_audience``: ``all`` / ``classroom`` /
  ``teacher`` / ``student``),
  matching the ``DayOfWeek``/``UserRole`` pattern already used elsewhere
  in this rebuild — an invalid audience value is structurally
  impossible to store, not just application-validated. When
  ``audience == "classroom"``, the specific target classrooms are rows
  in the explicit ``announcement_classrooms`` association table (an
  announcement can target many classrooms, and a classroom can be the
  target of many announcements — a genuine many-to-many, so this is an
  explicit association model per the Stage 1 brief's instruction,
  exactly like ``app.modules.academics.models.TeacherAssignment``).
  Every non-classroom audience has no ``announcement_classrooms`` rows.
  That cross-table invariant cannot cleanly be expressed as a single-table
  CHECK constraint (it depends on rows in a *different* table), so it
  is enforced in ``app.modules.announcements.repository`` instead — the
  same reasoning already documented for the role-match invariant in
  ``app.modules.profiles.models``.
- **UUID primary keys**, matching every other Phase 2/3 table.
- **Soft delete via ``is_active``**, matching ``Classroom``/``Subject``
  — an announcement can be retracted without losing the historical
  record (audit-trail spirit of docs/ARCHITECTURE.md §8).
- **``author_user_id`` uses ``ondelete="RESTRICT"``, not ``CASCADE``.**
  Every Phase 3 profile FK to ``users.id`` uses ``CASCADE`` because the
  child row (a profile) is meaningless without its user. An
  announcement is different: it is standalone content, and this app's
  user-removal path is a soft ``is_active`` flip, not a hard delete
  (docs/AUDIT.md's audit-log discussion). ``RESTRICT`` means a genuine
  hard delete of a user who has posted announcements fails loudly
  instead of silently destroying announcement history — the same
  fail-loud-not-silent philosophy as the rest of this rebuild
  (docs/ARCHITECTURE.md §6).
- **``AnnouncementClassroom`` has no ``is_active``/``updated_at``.** A
  row's existence *is* the state (a classroom is in the audience, or it
  isn't); there is no independent lifecycle to soft-delete or update,
  unlike ``TeacherAssignment`` (which tracks an ongoing, revocable
  assignment). Removing a classroom from an announcement's audience
  deletes the association row directly.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum, StrEnum

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _enum_values(enum_cls: type[Enum]) -> list[str]:
    """Persist each enum member's public value, not its Python member name.

    Duplicated (rather than imported) from ``app.modules.users.models`` /
    ``app.modules.academics.models`` — same rationale as those modules'
    identical helper: not worth a cross-module import for four lines.
    """
    return [str(member.value) for member in enum_cls]


class AnnouncementAudience(StrEnum):
    """Who an announcement is visible to.

    Stage 1 introduced ``all`` and ``classroom``. Stage 2 adds
    ``teacher`` and ``student`` because its API acceptance criteria
    explicitly require role-scoped visibility.
    """

    ALL = "all"
    CLASSROOM = "classroom"
    TEACHER = "teacher"
    STUDENT = "student"


class Announcement(Base):
    """A single announcement, authored by a user, with a structured audience."""

    __tablename__ = "announcements"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    author_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    audience: Mapped[AnnouncementAudience] = mapped_column(
        sa.Enum(
            AnnouncementAudience,
            name="announcement_audience",
            native_enum=True,
            validate_strings=True,
            values_callable=_enum_values,
        ),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
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
        sa.Index("ix_announcements_author_user_id", "author_user_id"),
        sa.Index("ix_announcements_audience_is_active", "audience", "is_active"),
    )

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"Announcement(id={self.id!r}, audience={self.audience!r})"


class AnnouncementClassroom(Base):
    """Explicit association: one classroom in one announcement's audience.

    Only ever populated when the owning ``Announcement.audience`` is
    ``AnnouncementAudience.CLASSROOM`` — see this module's docstring for
    why that invariant is enforced at the repository layer.
    """

    __tablename__ = "announcement_classrooms"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    announcement_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("announcements.id", ondelete="CASCADE"),
        nullable=False,
    )
    classroom_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "announcement_id",
            "classroom_id",
            name="uq_announcement_classrooms_announcement_classroom",
        ),
        sa.Index("ix_announcement_classrooms_announcement_id", "announcement_id"),
        sa.Index("ix_announcement_classrooms_classroom_id", "classroom_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"AnnouncementClassroom(id={self.id!r}, "
            f"announcement_id={self.announcement_id!r}, classroom_id={self.classroom_id!r})"
        )
