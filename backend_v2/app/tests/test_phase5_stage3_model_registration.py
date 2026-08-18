"""Regression tests for Phase 5 Stage 3 ORM importability and Alembic metadata registration.

Mirrors ``app.tests.test_phase5_stage2_model_registration``. No database
connection is required — every assertion here inspects
``Base.metadata`` directly.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint

from app.db.base import Base
from app.db.models import BiometricEmbedding
from app.modules.face_recognition.models import BiometricEmbedding as DirectBiometricEmbedding


def test_phase5_stage3_orm_model_module_imports_without_mapping_errors() -> None:
    assert DirectBiometricEmbedding is BiometricEmbedding


def test_phase5_stage3_table_is_registered_in_base_metadata() -> None:
    assert "biometric_embeddings" in Base.metadata.tables


def test_earlier_phase_tables_still_coexist_with_stage3_table() -> None:
    """Stage 3 is additive — every earlier-phase table remains registered."""
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
        "biometric_embeddings",
    }.issubset(Base.metadata.tables)


def test_biometric_samples_has_stage3_processing_columns() -> None:
    table = Base.metadata.tables["biometric_samples"]
    assert "processing_started_at" in table.columns
    assert "processing_completed_at" in table.columns
    assert "processing_failure_reason_code" in table.columns
    # All three must be nullable — every pre-Stage-3 row has none of them set.
    assert table.columns["processing_started_at"].nullable is True
    assert table.columns["processing_completed_at"].nullable is True
    assert table.columns["processing_failure_reason_code"].nullable is True


def test_biometric_embeddings_foreign_key_targets_biometric_samples() -> None:
    table = Base.metadata.tables["biometric_embeddings"]
    fk_targets = {fk.column.table.name for fk in table.columns["biometric_sample_id"].foreign_keys}
    assert fk_targets == {"biometric_samples"}
    fk = next(iter(table.columns["biometric_sample_id"].foreign_keys))
    assert fk.ondelete == "CASCADE"


def test_biometric_embeddings_has_positive_dimension_and_length_check_constraints() -> None:
    table = Base.metadata.tables["biometric_embeddings"]
    check_names = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert {
        "ck_biometric_embeddings_embedding_dimension_positive",
        "ck_biometric_embeddings_embedding_values_length_matches_dimension",
    }.issubset(check_names)


def test_biometric_embeddings_has_partial_unique_active_index() -> None:
    """Database-enforced backstop for "at most one active embedding per sample" —
    see app/modules/face_recognition/models.py's module docstring."""
    table = Base.metadata.tables["biometric_embeddings"]
    indexes_by_name = {index.name: index for index in table.indexes}
    active_index = indexes_by_name["uq_biometric_embeddings_sample_active"]
    assert active_index.unique is True
    assert {column.name for column in active_index.columns} == {"biometric_sample_id"}
    assert active_index.dialect_options["postgresql"]["where"] is not None


def test_biometric_embeddings_has_sample_id_index() -> None:
    table = Base.metadata.tables["biometric_embeddings"]
    index_names = {index.name for index in table.indexes}
    assert "ix_biometric_embeddings_biometric_sample_id" in index_names


def test_biometric_embeddings_required_columns_are_not_nullable() -> None:
    table = Base.metadata.tables["biometric_embeddings"]
    for column_name in (
        "id",
        "biometric_sample_id",
        "provider_name",
        "model_identifier",
        "model_version",
        "embedding_dimension",
        "embedding_values",
        "is_active",
        "created_at",
    ):
        assert table.columns[column_name].nullable is False, column_name


def test_biometric_embeddings_optional_columns_are_nullable() -> None:
    table = Base.metadata.tables["biometric_embeddings"]
    for column_name in ("model_artifact_checksum", "superseded_at"):
        assert table.columns[column_name].nullable is True, column_name


def test_biometric_embeddings_table_has_no_embedding_bytes_column() -> None:
    """Sanity guard: only a numeric array column carries the embedding —
    no raw image/byte column exists anywhere on this table."""
    table = Base.metadata.tables["biometric_embeddings"]
    assert "pixel_data" not in table.columns
    assert "image_bytes" not in table.columns
