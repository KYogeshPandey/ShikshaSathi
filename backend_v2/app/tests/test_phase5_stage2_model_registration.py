"""Regression tests for Phase 5 Stage 2 ORM importability and Alembic metadata registration.

Mirrors ``app.tests.test_phase4_model_registration`` (kept as a separate,
additive file for the same reason Phase 4's is separate from Phase 3's).
No database connection is required — every assertion here inspects
``Base.metadata`` directly.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Index, UniqueConstraint

from app.db.base import Base
from app.db.models import BiometricEnrollment, BiometricSample
from app.modules.biometric_enrollment.models import (
    BiometricEnrollment as DirectBiometricEnrollment,
)
from app.modules.biometric_enrollment.models import (
    BiometricSample as DirectBiometricSample,
)
from app.modules.biometric_enrollment.models import (
    EnrollmentStatus,
    RecognitionProcessingState,
    SampleStatus,
)


def test_phase5_stage2_orm_model_modules_import_without_mapping_errors() -> None:
    """Every Phase 5 Stage 2 module imports cleanly and app.db.models re-exports the same class."""
    assert DirectBiometricEnrollment is BiometricEnrollment
    assert DirectBiometricSample is BiometricSample


def test_phase5_stage2_tables_are_registered_in_base_metadata() -> None:
    expected_tables = {"biometric_enrollments", "biometric_samples"}
    assert expected_tables.issubset(Base.metadata.tables)


def test_earlier_phase_tables_still_coexist() -> None:
    """Stage 2 is additive — every earlier-phase table remains registered."""
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
        "biometric_enrollments",
        "biometric_samples",
    }.issubset(Base.metadata.tables)


def test_enrollment_status_enum_values_are_registered() -> None:
    assert {status.value for status in EnrollmentStatus} == {
        "pending",
        "active",
        "deletion_pending",
        "deleted",
    }


def test_sample_status_enum_values_are_registered() -> None:
    assert {status.value for status in SampleStatus} == {
        "pending",
        "active",
        "replacement_pending",
        "deletion_pending",
        "quarantined",
        "deleted",
    }


def test_recognition_processing_state_enum_declares_all_three_values() -> None:
    """Stage 2 code only ever *writes* PENDING_PROCESSING; all three must exist as valid states."""
    assert {state.value for state in RecognitionProcessingState} == {
        "pending_processing",
        "processed",
        "processing_failed",
    }


def test_biometric_enrollments_student_profile_id_is_unique() -> None:
    table = Base.metadata.tables["biometric_enrollments"]
    unique_constraints = [
        constraint for constraint in table.constraints if isinstance(constraint, UniqueConstraint)
    ]
    assert len(unique_constraints) == 1
    assert {column.name for column in unique_constraints[0].columns} == {"student_profile_id"}


def test_biometric_samples_storage_key_is_unique() -> None:
    table = Base.metadata.tables["biometric_samples"]
    unique_constraints = [
        constraint for constraint in table.constraints if isinstance(constraint, UniqueConstraint)
    ]
    assert len(unique_constraints) == 1
    assert {column.name for column in unique_constraints[0].columns} == {"storage_key"}


def test_biometric_samples_has_positive_dimension_and_size_check_constraints() -> None:
    table = Base.metadata.tables["biometric_samples"]
    check_names = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert {
        "ck_biometric_samples_width_px_positive",
        "ck_biometric_samples_height_px_positive",
        "ck_biometric_samples_file_size_bytes_positive",
        "ck_biometric_samples_sha256_hash_format",
    }.issubset(check_names)


def test_biometric_samples_has_partial_unique_indexes_for_active_and_duplicate_content() -> None:
    """Database-enforced backstops, not just service-layer assumptions.

    See app/modules/biometric_enrollment/models.py's module docstring.
    """
    table = Base.metadata.tables["biometric_samples"]
    indexes_by_name = {index.name: index for index in table.indexes}

    active_index = indexes_by_name["uq_biometric_samples_enrollment_active"]
    assert active_index.unique is True
    assert {column.name for column in active_index.columns} == {"enrollment_id"}
    assert active_index.dialect_options["postgresql"]["where"] is not None

    dup_index = indexes_by_name["uq_biometric_samples_enrollment_sha256_live"]
    assert dup_index.unique is True
    assert {column.name for column in dup_index.columns} == {"enrollment_id", "sha256_hash"}
    assert dup_index.dialect_options["postgresql"]["where"] is not None


def test_biometric_samples_previous_sample_id_self_references_same_table() -> None:
    table = Base.metadata.tables["biometric_samples"]
    fk_targets = {fk.column.table.name for fk in table.columns["previous_sample_id"].foreign_keys}
    assert fk_targets == {"biometric_samples"}


def test_biometric_enrollments_has_expected_indexes() -> None:
    table = Base.metadata.tables["biometric_enrollments"]
    index_names = {index.name for index in table.indexes if isinstance(index, Index)}
    assert {
        "ix_biometric_enrollments_status",
        "ix_biometric_enrollments_created_by_user_id",
    }.issubset(index_names)
