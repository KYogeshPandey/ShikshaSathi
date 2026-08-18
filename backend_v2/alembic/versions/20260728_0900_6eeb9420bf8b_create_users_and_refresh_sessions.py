"""create_users_and_refresh_sessions

Revision ID: 6eeb9420bf8b
Revises: 98161483914f
Create Date: 2026-07-28 09:00:00.000000

Phase 2's first real schema-defining migration, built on top of Phase 1's
intentionally empty baseline (see that migration's docstring and
docs/IMPLEMENTATION_PLAN.md). Creates:

- the ``user_role`` native PostgreSQL enum (admin/teacher/student)
- ``users`` — the identity record every access/refresh token resolves
  against (app/modules/users/models.py)
- ``refresh_sessions`` — server-side refresh-token session state,
  supporting rotation and reuse detection (app/modules/auth/models.py)

Constraint/index names are written out explicitly to match the naming
convention in app/db/naming.py and the ``__table_args__`` in both model
files exactly, so a future ``alembic revision --autogenerate`` diff
against these models shows no spurious renames.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "6eeb9420bf8b"
down_revision: str | None = "98161483914f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_user_role = postgresql.ENUM("admin", "teacher", "student", name="user_role")


def upgrade() -> None:
    bind = op.get_bind()
    _user_role.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM("admin", "teacher", "student", name="user_role", create_type=False),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.CheckConstraint("email = lower(email)", name="ck_users_email_lowercase"),
    )
    op.create_index("ix_users_role_is_active", "users", ["role", "is_active"])

    op.create_table(
        "refresh_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_refresh_sessions"),
        sa.UniqueConstraint("token_hash", name="uq_refresh_sessions_token_hash"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_refresh_sessions_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["replaced_by_id"],
            ["refresh_sessions.id"],
            name="fk_refresh_sessions_replaced_by_id_refresh_sessions",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_refresh_sessions_user_id", "refresh_sessions", ["user_id"])
    op.create_index(
        "ix_refresh_sessions_user_active", "refresh_sessions", ["user_id", "revoked_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_refresh_sessions_user_active", table_name="refresh_sessions")
    op.drop_index("ix_refresh_sessions_user_id", table_name="refresh_sessions")
    op.drop_table("refresh_sessions")

    op.drop_index("ix_users_role_is_active", table_name="users")
    op.drop_table("users")

    bind = op.get_bind()
    _user_role.drop(bind, checkfirst=True)
