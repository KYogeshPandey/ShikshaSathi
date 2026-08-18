"""The ``RefreshSession`` ORM model — server-side refresh-token state.

Only a SHA-256 digest of the raw refresh token is ever stored
(``token_hash``) — never the raw token itself (instruction D). The row's
own primary key (``id``) is the "token/session identifier" referred to
in the Phase 2 brief; ``replaced_by_id`` records the rotation lineage
used for reuse detection (see app/modules/auth/service.py).
"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RefreshSession(Base):
    """A single refresh-token session.

    Lifecycle:

    - **Created** at login or at successful rotation, with
      ``revoked_at`` and ``replaced_by_id`` both null.
    - **Rotated** on a successful ``POST /auth/refresh``: a new session
      row is created, and this row's ``revoked_at`` is set to now and
      ``replaced_by_id`` is set to the new row's id. From this point,
      presenting *this* session's raw token again is a reuse of an
      already-rotated token — see app/modules/auth/service.py's reuse
      detection.
    - **Revoked directly** on logout: ``revoked_at`` is set, but
      ``replaced_by_id`` stays null — this distinguishes "logged out"
      from "rotated" when a revoked session's token is presented again.
    """

    __tablename__ = "refresh_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # SHA-256 hex digest (64 hex characters) — see
    # app/modules/auth/security.py's hash_refresh_token.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("refresh_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        sa.UniqueConstraint("token_hash", name="uq_refresh_sessions_token_hash"),
        sa.Index("ix_refresh_sessions_user_id", "user_id"),
        sa.Index("ix_refresh_sessions_user_active", "user_id", "revoked_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - trivial, excludes token_hash
        return (
            f"RefreshSession(id={self.id!r}, user_id={self.user_id!r}, "
            f"revoked_at={self.revoked_at!r})"
        )
