"""create_initial_schema_baseline

Revision ID: 98161483914f
Revises:
Create Date: 2026-07-26 12:00:00.000000

This is an intentionally empty baseline migration (see
docs/IMPLEMENTATION_PLAN.md, Phase 1 scope: "Because no business models
exist yet, the initial migration may be an intentionally empty baseline
migration"). Its only purpose is to prove the Alembic pipeline works
end-to-end — including a full upgrade/downgrade round trip — against a
real PostgreSQL database, before any domain model exists. Phase 3 will
add the first real schema-defining migration on top of this one.
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "98161483914f"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No-op: establishes this revision as the baseline for this database."""
    pass


def downgrade() -> None:
    """No-op: mirrors upgrade()."""
    pass
