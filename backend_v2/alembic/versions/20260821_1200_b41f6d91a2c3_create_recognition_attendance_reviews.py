"""create recognition attendance reviews

Revision ID: b41f6d91a2c3
Revises: 4f8c1a6e92b7
Create Date: 2026-08-21 12:00:00.000000

Adds a non-biometric review envelope for multi-face image proposals and
explicit teacher confirmation. No image bytes or embeddings are persisted.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b41f6d91a2c3"
down_revision: str | None = "4f8c1a6e92b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recognition_attendance_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("classroom_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attendance_date", sa.Date(), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column(
            "candidate_student_profile_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
        ),
        sa.Column("face_count", sa.Integer(), nullable=False),
        sa.Column("confirmed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_records", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "attendance_record_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=True,
        ),
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
        sa.PrimaryKeyConstraint("id", name="pk_recognition_attendance_reviews"),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_recognition_attendance_reviews_actor_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["classroom_id"],
            ["classrooms.id"],
            name="fk_recognition_attendance_reviews_classroom_id_classrooms",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subjects.id"],
            name="fk_recognition_attendance_reviews_subject_id_subjects",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by_user_id"],
            ["users.id"],
            name="fk_recognition_attendance_reviews_confirmed_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "candidate_count > 0",
            name="ck_recognition_attendance_reviews_candidate_count_positive",
        ),
        sa.CheckConstraint(
            "cardinality(candidate_student_profile_ids) = candidate_count",
            name="ck_recognition_attendance_reviews_candidate_roster_count_matches",
        ),
        sa.CheckConstraint(
            "face_count >= 0",
            name="ck_recognition_attendance_reviews_face_count_non_negative",
        ),
        sa.CheckConstraint(
            "(confirmed_by_user_id IS NULL AND confirmed_at IS NULL "
            "AND confirmed_records IS NULL AND attendance_record_ids IS NULL) OR "
            "(confirmed_by_user_id IS NOT NULL AND confirmed_at IS NOT NULL "
            "AND confirmed_records IS NOT NULL AND attendance_record_ids IS NOT NULL)",
            name="ck_recognition_attendance_reviews_confirmation_fields_consistent",
        ),
    )
    op.create_index(
        "ix_recognition_attendance_reviews_actor_user_id",
        "recognition_attendance_reviews",
        ["actor_user_id"],
    )
    op.create_index(
        "ix_recognition_attendance_reviews_classroom_id",
        "recognition_attendance_reviews",
        ["classroom_id"],
    )
    op.create_index(
        "ix_recognition_attendance_reviews_subject_id",
        "recognition_attendance_reviews",
        ["subject_id"],
    )

    op.add_column(
        "recognition_attendance_attempts",
        sa.Column("review_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "recognition_attendance_attempts",
        sa.Column("face_index", sa.Integer(), nullable=True),
    )
    op.add_column(
        "recognition_attendance_attempts",
        sa.Column("is_duplicate", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_foreign_key(
        "fk_recognition_attempts_review_id_reviews",
        "recognition_attendance_attempts",
        "recognition_attendance_reviews",
        ["review_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "ck_recognition_attendance_attempts_face_index_non_negative",
        "recognition_attendance_attempts",
        "face_index IS NULL OR face_index >= 0",
    )
    op.create_unique_constraint(
        "uq_recognition_attempts_review_face",
        "recognition_attendance_attempts",
        ["review_id", "face_index"],
    )
    op.create_index(
        "ix_recognition_attendance_attempts_review_id",
        "recognition_attendance_attempts",
        ["review_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_recognition_attendance_attempts_review_id",
        table_name="recognition_attendance_attempts",
    )
    op.drop_constraint(
        "uq_recognition_attempts_review_face",
        "recognition_attendance_attempts",
        type_="unique",
    )
    op.drop_constraint(
        "ck_recognition_attendance_attempts_face_index_non_negative",
        "recognition_attendance_attempts",
        type_="check",
    )
    op.drop_constraint(
        "fk_recognition_attempts_review_id_reviews",
        "recognition_attendance_attempts",
        type_="foreignkey",
    )
    op.drop_column("recognition_attendance_attempts", "is_duplicate")
    op.drop_column("recognition_attendance_attempts", "face_index")
    op.drop_column("recognition_attendance_attempts", "review_id")
    op.drop_index(
        "ix_recognition_attendance_reviews_subject_id",
        table_name="recognition_attendance_reviews",
    )
    op.drop_index(
        "ix_recognition_attendance_reviews_classroom_id",
        table_name="recognition_attendance_reviews",
    )
    op.drop_index(
        "ix_recognition_attendance_reviews_actor_user_id",
        table_name="recognition_attendance_reviews",
    )
    op.drop_table("recognition_attendance_reviews")
