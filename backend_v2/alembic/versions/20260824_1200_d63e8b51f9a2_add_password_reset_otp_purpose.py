"""add password-reset OTP purpose

Revision ID: d63e8b51f9a2
Revises: c52d7a40e8f1
Create Date: 2026-08-24 12:00:00.000000

The existing challenge table already has the lifecycle fields needed by
password reset. Only the native PostgreSQL enum needs another purpose.
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d63e8b51f9a2"
down_revision: str | None = "c52d7a40e8f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_login_only_purpose = postgresql.ENUM("login", name="otp_purpose")


def upgrade() -> None:
    op.execute("ALTER TYPE otp_purpose ADD VALUE IF NOT EXISTS 'password_reset'")


def downgrade() -> None:
    # Rows using the new purpose cannot be represented by the prior enum.
    # They are short-lived security state, so dropping only those rows is the
    # narrow, safe downgrade behavior; login challenges remain untouched.
    op.execute("DELETE FROM otp_challenges WHERE purpose = 'password_reset'")
    op.execute("ALTER TYPE otp_purpose RENAME TO otp_purpose_with_password_reset")
    _login_only_purpose.create(op.get_bind(), checkfirst=False)
    op.execute(
        "ALTER TABLE otp_challenges ALTER COLUMN purpose TYPE otp_purpose "
        "USING purpose::text::otp_purpose"
    )
    op.execute("DROP TYPE otp_purpose_with_password_reset")
