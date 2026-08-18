"""Regression tests for Phase 4 Stage 1 ORM importability and Alembic metadata registration.

Mirrors ``app.tests.test_phase3_model_registration`` (kept as a separate
file for the same reason that one is separate from Phase 2's: additive,
not a rewrite of earlier-phase work).
"""

from __future__ import annotations

from sqlalchemy import UniqueConstraint

from app.db.base import Base
from app.db.models import AttendanceRecord, AuditLog
from app.modules.attendance.models import (
    AttendanceRecord as DirectAttendanceRecord,
)
from app.modules.attendance.models import (
    AttendanceStatus,
    AuditOutcome,
)
from app.modules.attendance.models import (
    AuditLog as DirectAuditLog,
)


def test_phase4_orm_model_modules_import_without_mapping_errors() -> None:
    """Every Phase 4 Stage 1 module imports cleanly and app.db.models re-exports the same class."""
    assert DirectAttendanceRecord is AttendanceRecord
    assert DirectAuditLog is AuditLog


def test_phase4_tables_are_registered_in_base_metadata() -> None:
    expected_tables = {"attendance_records", "audit_logs"}
    assert expected_tables.issubset(Base.metadata.tables)


def test_phase2_phase3_and_phase4_tables_coexist_in_one_metadata() -> None:
    """Earlier-phase tables are still registered — Stage 1 is additive, not a replacement."""
    assert {
        "users",
        "refresh_sessions",
        "classrooms",
        "subjects",
        "teacher_profiles",
        "student_profiles",
        "teacher_assignments",
        "timetable_entries",
        "announcements",
        "announcement_classrooms",
        "attendance_records",
        "audit_logs",
    }.issubset(Base.metadata.tables)


def test_attendance_status_enum_values_are_registered() -> None:
    assert {status.value for status in AttendanceStatus} == {"present", "absent"}


def test_audit_outcome_enum_values_are_registered() -> None:
    assert {outcome.value for outcome in AuditOutcome} == {"success", "blocked"}


def test_attendance_records_unique_constraint_columns() -> None:
    table = Base.metadata.tables["attendance_records"]
    unique_constraints = [
        constraint for constraint in table.constraints if isinstance(constraint, UniqueConstraint)
    ]
    assert len(unique_constraints) == 1
    column_names = {column.name for column in unique_constraints[0].columns}
    assert column_names == {
        "student_profile_id",
        "classroom_id",
        "subject_id",
        "attendance_date",
    }
