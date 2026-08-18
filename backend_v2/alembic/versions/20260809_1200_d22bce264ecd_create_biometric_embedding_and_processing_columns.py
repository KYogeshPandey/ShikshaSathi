"""create_biometric_embedding_and_processing_columns

Revision ID: d22bce264ecd
Revises: ca8e748dc8f2
Create Date: 2026-08-09 12:00:00.000000

Phase 5 Stage 3's schema-defining migration, built directly on top of
Phase 5 Stage 2's head (``ca8e748dc8f2``) — that migration's own file is
not edited anywhere in this checkpoint.

Two changes, in dependency order:

1. **Three new nullable columns on the existing ``biometric_samples``
   table**: ``processing_started_at``, ``processing_completed_at``,
   ``processing_failure_reason_code``. Additive only — no existing
   column, constraint, or index from ``ca8e748dc8f2`` is touched.
   Nullable because every row that already exists at the time this
   migration runs predates Stage 3 processing and has attempted no
   processing yet (Stage 2 code only ever writes
   ``processing_state = 'pending_processing'`` — see
   ``app/modules/biometric_enrollment/models.py``'s module docstring).
2. **``biometric_embeddings``** — depends on ``biometric_samples``
   (Phase 5 Stage 2). See
   ``app/modules/face_recognition/models.py``'s module docstring for
   the full design rationale (why this is a separate table rather than
   more ``biometric_samples`` columns, why a plain ``DOUBLE
   PRECISION[]`` array rather than ``pgvector``, and why
   ``is_active``/partial-unique-index rather than a hard 1:1 unique
   constraint).

No image byte is ever a column here, and the one column that *is*
sensitive (``embedding_values``) is never read by any Stage 2/3 API
response — see ``app/modules/face_recognition/schemas.py``.

``downgrade()`` reverses this exactly: drop ``biometric_embeddings``
(the child) first, then drop the three added columns from
``biometric_samples`` — landing back at Stage 2 head (``ca8e748dc8f2``)
with the original Stage 2 schema restored exactly, and no leftover
type/column blocking a future re-creation.

Constraint/index names are written out explicitly to match
``app/db/naming.py`` and ``app/modules/face_recognition/models.py``'s
``__table_args__`` exactly, so a future ``alembic revision
--autogenerate`` diff against these models shows no spurious renames.

Revision ``ca8e748dc8f2`` (this migration's parent) is immutable and is
not edited here or anywhere else in this migration.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d22bce264ecd"
down_revision: str | None = "ca8e748dc8f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- biometric_samples: additive processing-bookkeeping columns --------
    op.add_column(
        "biometric_samples",
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "biometric_samples",
        sa.Column("processing_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "biometric_samples",
        sa.Column("processing_failure_reason_code", sa.String(length=64), nullable=True),
    )

    # --- biometric_embeddings -----------------------------------------------
    op.create_table(
        "biometric_embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("biometric_sample_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_name", sa.String(length=100), nullable=False),
        sa.Column("model_identifier", sa.String(length=255), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False),
        sa.Column(
            "embedding_values",
            postgresql.ARRAY(postgresql.DOUBLE_PRECISION()),
            nullable=False,
        ),
        sa.Column("model_artifact_checksum", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_biometric_embeddings"),
        sa.ForeignKeyConstraint(
            ["biometric_sample_id"],
            ["biometric_samples.id"],
            name="fk_biometric_embeddings_biometric_sample_id_biometric_samples",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "embedding_dimension > 0",
            name="ck_biometric_embeddings_embedding_dimension_positive",
        ),
        sa.CheckConstraint(
            "array_length(embedding_values, 1) = embedding_dimension",
            name="ck_biometric_embeddings_embedding_values_length_matches_dimension",
        ),
    )
    op.create_index(
        "ix_biometric_embeddings_biometric_sample_id",
        "biometric_embeddings",
        ["biometric_sample_id"],
    )
    # At most one ACTIVE embedding per sample — database-enforced, not
    # merely a service-layer assumption (see
    # app/modules/face_recognition/models.py's module docstring).
    op.create_index(
        "uq_biometric_embeddings_sample_active",
        "biometric_embeddings",
        ["biometric_sample_id"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )


def downgrade() -> None:
    op.drop_index("uq_biometric_embeddings_sample_active", table_name="biometric_embeddings")
    op.drop_index("ix_biometric_embeddings_biometric_sample_id", table_name="biometric_embeddings")
    op.drop_table("biometric_embeddings")

    op.drop_column("biometric_samples", "processing_failure_reason_code")
    op.drop_column("biometric_samples", "processing_completed_at")
    op.drop_column("biometric_samples", "processing_started_at")
