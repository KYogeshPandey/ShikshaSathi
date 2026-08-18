"""create_recognition_attendance_attempts

Revision ID: 4f8c1a6e92b7
Revises: d22bce264ecd
Create Date: 2026-08-16 12:00:00.000000

Phase 5 Stage 4's sole migration. It persists only the bounded identifiers
needed to audit a recognition decision, enforce the original authorized
roster during manual confirmation, and make confirmation idempotent. It has no
image, embedding, similarity-vector, provider-path, or raw-error column.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "4f8c1a6e92b7"
down_revision: str | None = "d22bce264ecd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_recognition_decision = postgresql.ENUM(
    "found", "unknown", "ambiguous", name="recognition_attendance_decision"
)


def upgrade() -> None:
    bind = op.get_bind()
    _recognition_decision.create(bind, checkfirst=True)

    op.create_table(
        "recognition_attendance_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("classroom_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attendance_date", sa.Date(), nullable=False),
        sa.Column(
            "decision",
            postgresql.ENUM(
                "found",
                "unknown",
                "ambiguous",
                name="recognition_attendance_decision",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("matched_student_profile_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column(
            "candidate_student_profile_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
        ),
        sa.Column("confirmed_student_profile_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("confirmed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attendance_record_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_recognition_attendance_attempts"),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_recognition_attendance_attempts_actor_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["classroom_id"],
            ["classrooms.id"],
            name="fk_recognition_attendance_attempts_classroom_id_classrooms",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subjects.id"],
            name="fk_recognition_attendance_attempts_subject_id_subjects",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["matched_student_profile_id"],
            ["student_profiles.id"],
            name=op.f(
                "fk_recognition_attendance_attempts_matched_student_profile_id_student_profiles"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_student_profile_id"],
            ["student_profiles.id"],
            name=op.f(
                "fk_recognition_attendance_attempts_confirmed_student_profile_id_student_profiles"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by_user_id"],
            ["users.id"],
            name="fk_recognition_attendance_attempts_confirmed_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["attendance_record_id"],
            ["attendance_records.id"],
            name=op.f("fk_recognition_attendance_attempts_attendance_record_id_attendance_records"),
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "candidate_count > 0",
            name="ck_recognition_attendance_attempts_candidate_count_positive",
        ),
        sa.CheckConstraint(
            "cardinality(candidate_student_profile_ids) = candidate_count",
            name=op.f("ck_recognition_attendance_attempts_candidate_roster_count_matches"),
        ),
        sa.CheckConstraint(
            "(decision = 'found' AND matched_student_profile_id IS NOT NULL) OR "
            "(decision <> 'found' AND matched_student_profile_id IS NULL)",
            name=op.f("ck_recognition_attendance_attempts_matched_student_matches_decision"),
        ),
        sa.CheckConstraint(
            "(confirmed_student_profile_id IS NULL AND confirmed_by_user_id IS NULL "
            "AND confirmed_at IS NULL) OR "
            "(confirmed_student_profile_id IS NOT NULL AND confirmed_by_user_id IS NOT NULL "
            "AND confirmed_at IS NOT NULL)",
            name=op.f("ck_recognition_attendance_attempts_confirmation_fields_consistent"),
        ),
    )
    op.create_index(
        "ix_recognition_attendance_attempts_actor_user_id",
        "recognition_attendance_attempts",
        ["actor_user_id"],
    )
    op.create_index(
        "ix_recognition_attendance_attempts_classroom_id",
        "recognition_attendance_attempts",
        ["classroom_id"],
    )
    op.create_index(
        "ix_recognition_attendance_attempts_subject_id",
        "recognition_attendance_attempts",
        ["subject_id"],
    )
    op.create_index(
        "ix_recognition_attendance_attempts_attendance_record_id",
        "recognition_attendance_attempts",
        ["attendance_record_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_recognition_attendance_attempts_attendance_record_id",
        table_name="recognition_attendance_attempts",
    )
    op.drop_index(
        "ix_recognition_attendance_attempts_subject_id",
        table_name="recognition_attendance_attempts",
    )
    op.drop_index(
        "ix_recognition_attendance_attempts_classroom_id",
        table_name="recognition_attendance_attempts",
    )
    op.drop_index(
        "ix_recognition_attendance_attempts_actor_user_id",
        table_name="recognition_attendance_attempts",
    )
    op.drop_table("recognition_attendance_attempts")
    _recognition_decision.drop(op.get_bind(), checkfirst=True)
