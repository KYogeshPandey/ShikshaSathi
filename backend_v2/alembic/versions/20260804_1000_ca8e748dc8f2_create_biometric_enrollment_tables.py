"""create_biometric_enrollment_tables

Revision ID: ca8e748dc8f2
Revises: e1208296dad5
Create Date: 2026-08-04 10:00:00.000000

Phase 5 Stage 2's schema-defining migration, built directly on top of
Phase 4's head (``e1208296dad5``). Creates, in FK-dependency order:

1. ``biometric_enrollment_status`` enum (``pending`` / ``active`` /
   ``deletion_pending`` / ``deleted``)
2. ``biometric_sample_status`` enum (``pending`` / ``active`` /
   ``replacement_pending`` / ``deletion_pending`` / ``quarantined`` /
   ``deleted``)
3. ``biometric_recognition_processing_state`` enum (``pending_processing``
   / ``processed`` / ``processing_failed`` — Stage 2 code only ever
   writes ``pending_processing``; the other two values are declared now
   so Stage 3 does not need an ``ALTER TYPE ... ADD VALUE`` migration
   later)
4. ``biometric_enrollments`` — depends on ``student_profiles`` (Phase 3)
   and ``users`` (Phase 2)
   (app/modules/biometric_enrollment/models.py's ``BiometricEnrollment``)
5. ``biometric_samples`` — depends on ``biometric_enrollments`` (this
   migration), ``users`` (Phase 2), and self-references
   ``biometric_samples.id`` (``previous_sample_id``)
   (app/modules/biometric_enrollment/models.py's ``BiometricSample``)

No image byte, embedding, or biometric content is ever a column here —
only opaque storage keys and safe, non-biometric metadata (MIME type,
byte size, pixel dimensions, content hash). See
docs/BIOMETRIC_DATA_POLICY.md and
app/modules/biometric_enrollment/models.py's module docstring for the
full design rationale (including why ``storage_key`` is a separate,
server-generated value rather than reusing ``id``, and why the two
partial unique indexes below exist).

``downgrade()`` reverses this exactly: ``biometric_samples`` (the
child — it references ``biometric_enrollments``) before
``biometric_enrollments``, then all three enums only after both tables
are gone — landing back at Phase 4 head (``e1208296dad5``) with no
leftover type blocking a future re-creation, the same pattern
established by the Phase 3 -> Phase 4 migration.

Constraint/index names are written out explicitly to match the naming
convention in app/db/naming.py and the ``__table_args__`` in
app/modules/biometric_enrollment/models.py exactly, so a future
``alembic revision --autogenerate`` diff against these models shows no
spurious renames.

Revision ``e1208296dad5`` (this migration's parent) is immutable and is
not edited here or anywhere else in this migration.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "ca8e748dc8f2"
down_revision: str | None = "e1208296dad5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_enrollment_status = postgresql.ENUM(
    "pending", "active", "deletion_pending", "deleted", name="biometric_enrollment_status"
)
_sample_status = postgresql.ENUM(
    "pending",
    "active",
    "replacement_pending",
    "deletion_pending",
    "quarantined",
    "deleted",
    name="biometric_sample_status",
)
_processing_state = postgresql.ENUM(
    "pending_processing",
    "processed",
    "processing_failed",
    name="biometric_recognition_processing_state",
)


def upgrade() -> None:
    bind = op.get_bind()
    _enrollment_status.create(bind, checkfirst=True)
    _sample_status.create(bind, checkfirst=True)
    _processing_state.create(bind, checkfirst=True)

    # --- biometric_enrollments ----------------------------------------------
    op.create_table(
        "biometric_enrollments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending",
                "active",
                "deletion_pending",
                "deleted",
                name="biometric_enrollment_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deletion_requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("deletion_requested_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_biometric_enrollments"),
        sa.UniqueConstraint(
            "student_profile_id", name="uq_biometric_enrollments_student_profile_id"
        ),
        sa.ForeignKeyConstraint(
            ["student_profile_id"],
            ["student_profiles.id"],
            name="fk_biometric_enrollments_student_profile_id_student_profiles",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_biometric_enrollments_created_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["deletion_requested_by_user_id"],
            ["users.id"],
            name="fk_biometric_enrollments_deletion_requested_by_user_id_users",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_biometric_enrollments_status", "biometric_enrollments", ["status"])
    op.create_index(
        "ix_biometric_enrollments_created_by_user_id",
        "biometric_enrollments",
        ["created_by_user_id"],
    )

    # --- biometric_samples ---------------------------------------------------
    op.create_table(
        "biometric_samples",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("enrollment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_key", sa.String(length=64), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("content_type", sa.String(length=64), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("width_px", sa.Integer(), nullable=False),
        sa.Column("height_px", sa.Integer(), nullable=False),
        sa.Column("sha256_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending",
                "active",
                "replacement_pending",
                "deletion_pending",
                "quarantined",
                "deleted",
                name="biometric_sample_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "processing_state",
            postgresql.ENUM(
                "pending_processing",
                "processed",
                "processing_failed",
                name="biometric_recognition_processing_state",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("previous_sample_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quarantined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_biometric_samples"),
        sa.UniqueConstraint("storage_key", name="uq_biometric_samples_storage_key"),
        sa.ForeignKeyConstraint(
            ["enrollment_id"],
            ["biometric_enrollments.id"],
            name="fk_biometric_samples_enrollment_id_biometric_enrollments",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["previous_sample_id"],
            ["biometric_samples.id"],
            name="fk_biometric_samples_previous_sample_id_biometric_samples",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_biometric_samples_created_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("width_px > 0", name="ck_biometric_samples_width_px_positive"),
        sa.CheckConstraint("height_px > 0", name="ck_biometric_samples_height_px_positive"),
        sa.CheckConstraint(
            "file_size_bytes > 0", name="ck_biometric_samples_file_size_bytes_positive"
        ),
        sa.CheckConstraint(
            "sha256_hash ~ '^[0-9a-f]{64}$'", name="ck_biometric_samples_sha256_hash_format"
        ),
    )
    op.create_index("ix_biometric_samples_enrollment_id", "biometric_samples", ["enrollment_id"])
    op.create_index("ix_biometric_samples_status", "biometric_samples", ["status"])
    op.create_index(
        "ix_biometric_samples_created_by_user_id", "biometric_samples", ["created_by_user_id"]
    )
    op.create_index(
        "ix_biometric_samples_previous_sample_id", "biometric_samples", ["previous_sample_id"]
    )
    # At most one ACTIVE sample per enrollment — a database-enforced
    # backstop, not merely a service-layer assumption (see
    # app/modules/biometric_enrollment/models.py's module docstring).
    op.create_index(
        "uq_biometric_samples_enrollment_active",
        "biometric_samples",
        ["enrollment_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    # Re-uploading identical content for the same student is rejected as
    # a duplicate while the earlier copy is not DELETED; identical
    # content across *different* students is explicitly allowed (this
    # index is scoped to enrollment_id, not global).
    op.create_index(
        "uq_biometric_samples_enrollment_sha256_live",
        "biometric_samples",
        ["enrollment_id", "sha256_hash"],
        unique=True,
        postgresql_where=sa.text("status != 'deleted'"),
    )


def downgrade() -> None:
    op.drop_index("uq_biometric_samples_enrollment_sha256_live", table_name="biometric_samples")
    op.drop_index("uq_biometric_samples_enrollment_active", table_name="biometric_samples")
    op.drop_index("ix_biometric_samples_previous_sample_id", table_name="biometric_samples")
    op.drop_index("ix_biometric_samples_created_by_user_id", table_name="biometric_samples")
    op.drop_index("ix_biometric_samples_status", table_name="biometric_samples")
    op.drop_index("ix_biometric_samples_enrollment_id", table_name="biometric_samples")
    op.drop_table("biometric_samples")

    op.drop_index("ix_biometric_enrollments_created_by_user_id", table_name="biometric_enrollments")
    op.drop_index("ix_biometric_enrollments_status", table_name="biometric_enrollments")
    op.drop_table("biometric_enrollments")

    bind = op.get_bind()
    _processing_state.drop(bind, checkfirst=True)
    _sample_status.drop(bind, checkfirst=True)
    _enrollment_status.drop(bind, checkfirst=True)
