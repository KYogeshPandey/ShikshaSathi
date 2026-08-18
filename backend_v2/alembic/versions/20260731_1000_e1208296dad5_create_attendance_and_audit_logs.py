"""create_attendance_and_audit_logs

Revision ID: e1208296dad5
Revises: 32819e0a6027
Create Date: 2026-07-31 10:00:00.000000

Phase 4 Stage 1's schema-defining migration, built directly on top of
Phase 3's head (``32819e0a6027``). Creates, in FK-dependency order:

1. ``attendance_status`` enum (``present`` / ``absent``)
2. ``audit_outcome`` enum (``success`` / ``blocked``)
3. ``attendance_records`` — depends on ``student_profiles``, ``classrooms``,
   ``subjects`` (all Phase 3), and ``users`` (Phase 2)
   (app/modules/attendance/models.py's ``AttendanceRecord``)
4. ``audit_logs`` — depends on ``users`` (Phase 2), and optionally
   ``classrooms``/``subjects`` (Phase 3)
   (app/modules/attendance/models.py's ``AuditLog``)

``downgrade()`` reverses this exactly: ``audit_logs`` before
``attendance_records`` (neither references the other, but this keeps a
single, unambiguous child-before-parent ordering), then both enums only
after every table that uses them is gone — landing back at Phase 3 head
(``32819e0a6027``) with no leftover type blocking a future re-creation,
the same pattern established by the Phase 2 -> Phase 3 migration.

Constraint/index names are written out explicitly to match the naming
convention in app/db/naming.py and the ``__table_args__`` in
app/modules/attendance/models.py exactly, so a future
``alembic revision --autogenerate`` diff against these models shows no
spurious renames.

Revision ``32819e0a6027`` (this migration's parent) is immutable and is
not edited here or anywhere else in this migration.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e1208296dad5"
down_revision: str | None = "32819e0a6027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_attendance_status = postgresql.ENUM("present", "absent", name="attendance_status")
_audit_outcome = postgresql.ENUM("success", "blocked", name="audit_outcome")


def upgrade() -> None:
    bind = op.get_bind()
    _attendance_status.create(bind, checkfirst=True)
    _audit_outcome.create(bind, checkfirst=True)

    # --- attendance_records ------------------------------------------------
    op.create_table(
        "attendance_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("classroom_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attendance_date", sa.Date(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM("present", "absent", name="attendance_status", create_type=False),
            nullable=False,
        ),
        sa.Column("remarks", sa.String(length=500), nullable=True),
        sa.Column("marked_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="pk_attendance_records"),
        sa.UniqueConstraint(
            "student_profile_id",
            "classroom_id",
            "subject_id",
            "attendance_date",
            name="uq_attendance_records_student_classroom_subject_date",
        ),
        sa.ForeignKeyConstraint(
            ["student_profile_id"],
            ["student_profiles.id"],
            name="fk_attendance_records_student_profile_id_student_profiles",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["classroom_id"],
            ["classrooms.id"],
            name="fk_attendance_records_classroom_id_classrooms",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subjects.id"],
            name="fk_attendance_records_subject_id_subjects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["marked_by_user_id"],
            ["users.id"],
            name="fk_attendance_records_marked_by_user_id_users",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_attendance_records_student_profile_id", "attendance_records", ["student_profile_id"]
    )
    op.create_index("ix_attendance_records_classroom_id", "attendance_records", ["classroom_id"])
    op.create_index("ix_attendance_records_subject_id", "attendance_records", ["subject_id"])
    op.create_index(
        "ix_attendance_records_attendance_date", "attendance_records", ["attendance_date"]
    )
    op.create_index(
        "ix_attendance_records_marked_by_user_id", "attendance_records", ["marked_by_user_id"]
    )

    # --- audit_logs ----------------------------------------------------------
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column(
            "outcome",
            postgresql.ENUM("success", "blocked", name="audit_outcome", create_type=False),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("classroom_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column(
            "event_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_logs"),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_audit_logs_actor_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["classroom_id"],
            ["classrooms.id"],
            name="fk_audit_logs_classroom_id_classrooms",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subjects.id"],
            name="fk_audit_logs_subject_id_subjects",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_audit_logs_actor_user_id", "audit_logs", ["actor_user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_outcome", "audit_logs", ["outcome"])
    op.create_index(
        "ix_audit_logs_entity_type_entity_id", "audit_logs", ["entity_type", "entity_id"]
    )
    op.create_index("ix_audit_logs_classroom_id", "audit_logs", ["classroom_id"])
    op.create_index("ix_audit_logs_subject_id", "audit_logs", ["subject_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_subject_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_classroom_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_entity_type_entity_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_outcome", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_user_id", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index("ix_attendance_records_marked_by_user_id", table_name="attendance_records")
    op.drop_index("ix_attendance_records_attendance_date", table_name="attendance_records")
    op.drop_index("ix_attendance_records_subject_id", table_name="attendance_records")
    op.drop_index("ix_attendance_records_classroom_id", table_name="attendance_records")
    op.drop_index("ix_attendance_records_student_profile_id", table_name="attendance_records")
    op.drop_table("attendance_records")

    bind = op.get_bind()
    _audit_outcome.drop(bind, checkfirst=True)
    _attendance_status.drop(bind, checkfirst=True)
