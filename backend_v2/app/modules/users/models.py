"""The ``User`` ORM model — the single identity record for every role.

Design decisions (see docs/adr/0006-identity-and-auth-foundations.md for
the full rationale):

- **UUID primary key**, not an auto-incrementing integer. Nothing in
  earlier project documentation mandated a specific identifier
  strategy, so this is the concrete Phase 2 decision: sequential
  integer IDs make user enumeration trivial (``/users/2``,
  ``/users/3``, ...) once admin/teacher APIs exist in Phase 3; a UUID
  primary key removes that enumeration surface for free and costs
  nothing at this scale (docs/ARCHITECTURE.md §4's modular-monolith,
  single-Postgres-instance design does not need integer PKs for
  sharding or index-locality reasons).
- **Case-insensitive, unique email.** The authoritative normalization
  point is ``app.modules.users.normalization.normalize_email`` (lower
  + strip), applied before anything ever reaches this model. The
  ``ck_users_email_lowercase`` CHECK constraint below is a second,
  database-level guarantee that does not depend on every future
  caller remembering to normalize first — directly in the spirit of
  docs/AUDIT.md's C1/C2 findings, where the legacy app relied entirely
  on application-layer discipline with no structural backstop.
- **Role is a native PostgreSQL enum** (``user_role``), not a free-text
  column — a role value that isn't one of admin/teacher/student is
  structurally impossible to store, not just application-validated.
- **``is_active``** denies login, refresh, and protected actions the
  moment it flips to ``False`` — enforced in
  app/modules/auth/service.py and app/modules/auth/dependencies.py,
  not just at login time, so an admin deactivating a user takes effect
  immediately rather than waiting for that user's current access token
  to expire (instruction F).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum, StrEnum

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _enum_values(enum_cls: type[Enum]) -> list[str]:
    """Persist each enum member's public value, not its Python member name."""
    return [str(member.value) for member in enum_cls]


class UserRole(StrEnum):
    """Exactly the three roles required by the Phase 2 brief.

    Inherits from ``str`` so role values compare/serialize naturally
    (Pydantic, JSON, and equality against plain strings all work
    without extra adapters), while ``native_enum=True`` at the column
    level (below) still gets a real, constrained PostgreSQL enum type
    rather than a free-text column.
    """

    ADMIN = "admin"
    TEACHER = "teacher"
    STUDENT = "student"


class User(Base):
    """A single account: admin, teacher, or student."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    # Never selected into a response schema (see app/modules/users/schemas.py's
    # UserRead, which deliberately has no password_hash field) and never
    # logged (app/core/logging.py's blanket rule).
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        sa.Enum(
            UserRole,
            name="user_role",
            native_enum=True,
            validate_strings=True,
            values_callable=_enum_values,
        ),
        nullable=False,
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
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.CheckConstraint("email = lower(email)", name="ck_users_email_lowercase"),
        sa.Index("ix_users_role_is_active", "role", "is_active"),
    )

    def __repr__(self) -> str:  # pragma: no cover - trivial, excludes password_hash
        return f"User(id={self.id!r}, email={self.email!r}, role={self.role!r})"
