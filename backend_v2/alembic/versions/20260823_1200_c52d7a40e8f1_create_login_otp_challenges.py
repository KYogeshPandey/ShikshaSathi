"""create login OTP challenges

Revision ID: c52d7a40e8f1
Revises: b41f6d91a2c3
Create Date: 2026-08-23 12:00:00.000000

Persists only keyed OTP digests and bounded challenge lifecycle metadata.
No raw OTP, email body, access token, refresh token, or provider secret is
stored in this table.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c52d7a40e8f1"
down_revision: str | None = "b41f6d91a2c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_otp_purpose = postgresql.ENUM("login", name="otp_purpose")


def upgrade() -> None:
    _otp_purpose.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "otp_challenges",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "purpose",
            postgresql.ENUM("login", name="otp_purpose", create_type=False),
            nullable=False,
        ),
        sa.Column("otp_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_otp_challenges"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_otp_challenges_user_id_users",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_otp_challenges_attempt_count_non_negative",
        ),
        sa.CheckConstraint(
            "max_attempts > 0",
            name="ck_otp_challenges_max_attempts_positive",
        ),
        sa.CheckConstraint(
            "attempt_count <= max_attempts",
            name="ck_otp_challenges_attempt_count_bounded",
        ),
    )
    op.create_index("ix_otp_challenges_user_id", "otp_challenges", ["user_id"])
    op.create_index("ix_otp_challenges_expires_at", "otp_challenges", ["expires_at"])
    op.create_index(
        "uq_otp_challenges_user_purpose_active",
        "otp_challenges",
        ["user_id", "purpose"],
        unique=True,
        postgresql_where=sa.text("consumed_at IS NULL AND invalidated_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_otp_challenges_user_purpose_active",
        table_name="otp_challenges",
    )
    op.drop_index("ix_otp_challenges_expires_at", table_name="otp_challenges")
    op.drop_index("ix_otp_challenges_user_id", table_name="otp_challenges")
    op.drop_table("otp_challenges")
    _otp_purpose.drop(op.get_bind(), checkfirst=True)
