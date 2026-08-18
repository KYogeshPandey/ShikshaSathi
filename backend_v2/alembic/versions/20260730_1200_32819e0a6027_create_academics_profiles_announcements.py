"""create_academics_profiles_announcements

Revision ID: 32819e0a6027
Revises: 6eeb9420bf8b
Create Date: 2026-07-30 12:00:00.000000

Phase 3 Stage 1's single schema-defining migration, built directly on
top of Phase 2's head (``6eeb9420bf8b``). Creates every Stage 1 table
in FK-dependency order:

Before this still-unverified migration's Docker/PostgreSQL gate, Stage 2
extended ``announcement_audience`` with ``teacher`` and ``student`` to
satisfy its explicit role-audience API acceptance criteria (ADR 0008).

1. ``classrooms`` / ``subjects`` — no dependencies (app/modules/academics/models.py)
2. ``teacher_profiles`` — depends on ``users`` (app/modules/profiles/models.py)
3. ``student_profiles`` — depends on ``users``, ``classrooms`` (app/modules/profiles/models.py)
4. ``teacher_assignments`` — depends on ``teacher_profiles``, ``classrooms``,
   ``subjects`` (app/modules/academics/models.py)
5. ``timetable_entries`` — depends on ``classrooms``, ``subjects``,
   ``teacher_profiles``; also creates the ``day_of_week`` enum
   (app/modules/academics/models.py)
6. ``announcements`` — depends on ``users``
   (app/modules/announcements/models.py); also creates the
   ``announcement_audience`` enum
7. ``announcement_classrooms`` — depends on ``announcements``,
   ``classrooms`` (app/modules/announcements/models.py)

``downgrade()`` reverses this exactly, dropping child tables before the
parents they reference, and both enums only after every table that uses
them is gone — landing back at Phase 2 head (``6eeb9420bf8b``) with no
leftover type blocking a future re-creation, the same pattern already
established by the Phase 1→Phase 2 migration's own downgrade.

Constraint/index names are written out explicitly to match the naming
convention in app/db/naming.py and the ``__table_args__`` in every
Stage 1 model file exactly, so a future ``alembic revision
--autogenerate`` diff against these models shows no spurious renames.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "32819e0a6027"
down_revision: str | None = "6eeb9420bf8b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_day_of_week = postgresql.ENUM(
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    name="day_of_week",
)
_announcement_audience = postgresql.ENUM(
    "all", "classroom", "teacher", "student", name="announcement_audience"
)


def upgrade() -> None:
    bind = op.get_bind()
    _day_of_week.create(bind, checkfirst=True)
    _announcement_audience.create(bind, checkfirst=True)

    # --- classrooms ------------------------------------------------------
    op.create_table(
        "classrooms",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("grade_level", sa.String(length=32), nullable=True),
        sa.Column("section", sa.String(length=32), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_classrooms"),
        sa.UniqueConstraint("code", name="uq_classrooms_code"),
        sa.CheckConstraint("code = lower(code)", name="ck_classrooms_code_lowercase"),
    )
    op.create_index("ix_classrooms_is_active", "classrooms", ["is_active"])

    # --- subjects ----------------------------------------------------------
    op.create_table(
        "subjects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("is_elective", sa.Boolean(), server_default=sa.false(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="pk_subjects"),
        sa.UniqueConstraint("code", name="uq_subjects_code"),
        sa.CheckConstraint("code = lower(code)", name="ck_subjects_code_lowercase"),
    )
    op.create_index("ix_subjects_is_active", "subjects", ["is_active"])

    # --- teacher_profiles ----------------------------------------------
    op.create_table(
        "teacher_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_code", sa.String(length=64), nullable=True),
        sa.Column("phone_number", sa.String(length=32), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_teacher_profiles"),
        sa.UniqueConstraint("user_id", name="uq_teacher_profiles_user_id"),
        sa.UniqueConstraint("employee_code", name="uq_teacher_profiles_employee_code"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_teacher_profiles_user_id_users",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_teacher_profiles_user_id", "teacher_profiles", ["user_id"])

    # --- student_profiles ------------------------------------------------
    op.create_table(
        "student_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("classroom_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("roll_number", sa.String(length=32), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_student_profiles"),
        sa.UniqueConstraint("user_id", name="uq_student_profiles_user_id"),
        sa.UniqueConstraint(
            "classroom_id", "roll_number", name="uq_student_profiles_classroom_roll"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_student_profiles_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["classroom_id"],
            ["classrooms.id"],
            name="fk_student_profiles_classroom_id_classrooms",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_student_profiles_user_id", "student_profiles", ["user_id"])
    op.create_index("ix_student_profiles_classroom_id", "student_profiles", ["classroom_id"])

    # --- teacher_assignments ---------------------------------------------
    op.create_table(
        "teacher_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("teacher_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("classroom_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="pk_teacher_assignments"),
        sa.UniqueConstraint(
            "teacher_profile_id",
            "classroom_id",
            "subject_id",
            name="uq_teacher_assignments_teacher_classroom_subject",
        ),
        sa.ForeignKeyConstraint(
            ["teacher_profile_id"],
            ["teacher_profiles.id"],
            name="fk_teacher_assignments_teacher_profile_id_teacher_profiles",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["classroom_id"],
            ["classrooms.id"],
            name="fk_teacher_assignments_classroom_id_classrooms",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subjects.id"],
            name="fk_teacher_assignments_subject_id_subjects",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_teacher_assignments_teacher_profile_id", "teacher_assignments", ["teacher_profile_id"]
    )
    op.create_index("ix_teacher_assignments_classroom_id", "teacher_assignments", ["classroom_id"])
    op.create_index("ix_teacher_assignments_subject_id", "teacher_assignments", ["subject_id"])

    # --- timetable_entries -------------------------------------------------
    op.create_table(
        "timetable_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("classroom_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("teacher_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "day_of_week",
            postgresql.ENUM(
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
                name="day_of_week",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="pk_timetable_entries"),
        sa.CheckConstraint("start_time < end_time", name="ck_timetable_entries_start_before_end"),
        sa.UniqueConstraint(
            "classroom_id",
            "day_of_week",
            "start_time",
            name="uq_timetable_entries_classroom_day_start",
        ),
        sa.UniqueConstraint(
            "teacher_profile_id",
            "day_of_week",
            "start_time",
            name="uq_timetable_entries_teacher_day_start",
        ),
        sa.ForeignKeyConstraint(
            ["classroom_id"],
            ["classrooms.id"],
            name="fk_timetable_entries_classroom_id_classrooms",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subjects.id"],
            name="fk_timetable_entries_subject_id_subjects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["teacher_profile_id"],
            ["teacher_profiles.id"],
            name="fk_timetable_entries_teacher_profile_id_teacher_profiles",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_timetable_entries_classroom_id", "timetable_entries", ["classroom_id"])
    op.create_index(
        "ix_timetable_entries_teacher_profile_id", "timetable_entries", ["teacher_profile_id"]
    )

    # --- announcements -----------------------------------------------------
    op.create_table(
        "announcements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("author_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "audience",
            postgresql.ENUM(
                "all",
                "classroom",
                "teacher",
                "student",
                name="announcement_audience",
                create_type=False,
            ),
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
        sa.PrimaryKeyConstraint("id", name="pk_announcements"),
        sa.ForeignKeyConstraint(
            ["author_user_id"],
            ["users.id"],
            name="fk_announcements_author_user_id_users",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_announcements_author_user_id", "announcements", ["author_user_id"])
    op.create_index(
        "ix_announcements_audience_is_active", "announcements", ["audience", "is_active"]
    )

    # --- announcement_classrooms ------------------------------------------
    op.create_table(
        "announcement_classrooms",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("announcement_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("classroom_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_announcement_classrooms"),
        sa.UniqueConstraint(
            "announcement_id",
            "classroom_id",
            name="uq_announcement_classrooms_announcement_classroom",
        ),
        sa.ForeignKeyConstraint(
            ["announcement_id"],
            ["announcements.id"],
            name="fk_announcement_classrooms_announcement_id_announcements",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["classroom_id"],
            ["classrooms.id"],
            name="fk_announcement_classrooms_classroom_id_classrooms",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_announcement_classrooms_announcement_id",
        "announcement_classrooms",
        ["announcement_id"],
    )
    op.create_index(
        "ix_announcement_classrooms_classroom_id", "announcement_classrooms", ["classroom_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_announcement_classrooms_classroom_id", table_name="announcement_classrooms")
    op.drop_index(
        "ix_announcement_classrooms_announcement_id", table_name="announcement_classrooms"
    )
    op.drop_table("announcement_classrooms")

    op.drop_index("ix_announcements_audience_is_active", table_name="announcements")
    op.drop_index("ix_announcements_author_user_id", table_name="announcements")
    op.drop_table("announcements")

    op.drop_index("ix_timetable_entries_teacher_profile_id", table_name="timetable_entries")
    op.drop_index("ix_timetable_entries_classroom_id", table_name="timetable_entries")
    op.drop_table("timetable_entries")

    op.drop_index("ix_teacher_assignments_subject_id", table_name="teacher_assignments")
    op.drop_index("ix_teacher_assignments_classroom_id", table_name="teacher_assignments")
    op.drop_index("ix_teacher_assignments_teacher_profile_id", table_name="teacher_assignments")
    op.drop_table("teacher_assignments")

    op.drop_index("ix_student_profiles_classroom_id", table_name="student_profiles")
    op.drop_index("ix_student_profiles_user_id", table_name="student_profiles")
    op.drop_table("student_profiles")

    op.drop_index("ix_teacher_profiles_user_id", table_name="teacher_profiles")
    op.drop_table("teacher_profiles")

    op.drop_index("ix_subjects_is_active", table_name="subjects")
    op.drop_table("subjects")

    op.drop_index("ix_classrooms_is_active", table_name="classrooms")
    op.drop_table("classrooms")

    bind = op.get_bind()
    _announcement_audience.drop(bind, checkfirst=True)
    _day_of_week.drop(bind, checkfirst=True)
