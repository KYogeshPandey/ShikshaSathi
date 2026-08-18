"""ORM models for Phase 5 face recognition.

**One new aggregate, owned by this module** — not bolted onto
``app.modules.biometric_enrollment.models.BiometricSample`` as extra
columns, and not a fourth Stage 2 table. Rationale:

- ``BiometricSample`` is Stage 2's aggregate for the *stored image
  file*; ``BiometricEmbedding`` is Stage 3's aggregate for the
  *numeric result of processing that file*. They have different
  lifecycles (a sample can exist for a long time before ever being
  processed; an embedding is created atomically, once, on success) and
  different sensitivity profiles (an embedding is the actual biometric
  template — the thing ``docs/BIOMETRIC_DATA_POLICY.md`` is most
  protective about — while a sample row carries only file metadata).
  Separating them means every query that must never touch embedding
  data (e.g. any Stage 2 enrollment-listing endpoint) provably cannot,
  simply by not joining this table.
- Matches this codebase's existing "one repository per aggregate"
  convention (``app.modules.biometric_enrollment.repository``'s
  docstring) — a `BiometricEmbeddingRepository` for this table, kept
  separate from `BiometricSampleRepository`.

**One-to-one-ish via ``is_active`` rather than a hard unique
constraint on ``biometric_sample_id`` alone:** a sample is processed at
most once under normal operation (Stage 3 never re-processes an
already-``PROCESSED`` sample except via an explicit, not-yet-exposed
force-reprocess path — see
``app.modules.face_recognition.processing_service``), but the schema
itself allows a superseded row to remain for audit/history rather than
being overwritten or deleted, mirroring
``BiometricSample.status``/``previous_sample_id``'s own "keep history,
partial-unique-index the current one" pattern (Stage 2). A partial
unique index enforces **at most one ``is_active=true`` row per
``biometric_sample_id``** — the actual "one embedding actually usable
for matching per sample" invariant — at the database layer, not just
in application code.

**Embedding representation (Stage 3 brief, instruction 7):** a plain
PostgreSQL ``DOUBLE PRECISION[]`` array
(``postgresql.ARRAY(postgresql.DOUBLE_PRECISION)``), not ``pgvector``.
Chosen because:

- This project's current scale (single-school deployment, hundreds to
  low thousands of enrolled students, candidate-scoped matching against
  an explicit small roster — never a full-database nearest-neighbor
  search) does not need pgvector's approximate-nearest-neighbor index
  structures; a bounded, explicitly-scoped Python-side cosine-
  similarity loop (``app.modules.face_recognition.providers.similarity_matcher``)
  over at most a classroom's worth of candidates is fast enough.
- Avoids taking a new PostgreSQL extension dependency
  (``CREATE EXTENSION vector``) for a benefit this project cannot yet
  measure a need for — "prefer the simplest correctly typed and tested
  representation unless performance evidence justifies an extension"
  (Stage 3 brief, instruction 7, verbatim).
- A native array is directly, losslessly round-trippable to/from this
  project's own ``EmbeddingVector`` domain type
  (``tuple[float, ...]``) with no extra serialization library.
- **Precision:** ``DOUBLE PRECISION`` (8-byte float, PostgreSQL's
  `float8`) — matches Python's native ``float`` exactly, so no
  precision is lost storing or retrieving a value already validated as
  finite by ``EmbeddingVector`` (``app.modules.face_recognition.domain``).
- **Portability:** PostgreSQL-specific (this project's only supported
  database — ``app/core/config.py`` rejects anything else at startup),
  so no cross-database portability concern applies.
- **Migration consequences:** a plain array column has no extension-
  enablement/version-pinning story the way pgvector would (no
  ``CREATE EXTENSION``/``DROP EXTENSION`` in this migration's
  upgrade/downgrade) — see
  ``alembic/versions/*_create_biometric_embedding_and_processing_columns.py``.

**Security/privacy:** no route/schema in this application ever returns
``embedding_values`` — see ``app.modules.face_recognition.schemas`` (no
schema even declares this field) and
``app.modules.face_recognition.router``'s module docstring. No audit-
log call anywhere in this module ever passes embedding values as
``event_metadata`` — see
``app.modules.face_recognition.processing_service``.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum

import sqlalchemy as sa
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY, DOUBLE_PRECISION
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.face_recognition.domain import MatchStatus


def _enum_values(enum_cls: type[Enum]) -> list[str]:
    return [str(member.value) for member in enum_cls]


class BiometricEmbedding(Base):
    """One computed face embedding for one ``BiometricSample``."""

    __tablename__ = "biometric_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    biometric_sample_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("biometric_samples.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Opaque provider identifiers — safe to log/display; never a
    # filesystem path (see app/modules/face_recognition/model_artifacts.py).
    provider_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(Integer(), nullable=False)
    # DOUBLE PRECISION[] — see this module's docstring, "Embedding representation".
    embedding_values: Mapped[list[float]] = mapped_column(ARRAY(DOUBLE_PRECISION()), nullable=False)
    # Optional: the model *artifact* checksum (app/modules/face_recognition/
    # model_artifacts.py) in effect when this embedding was computed — lets
    # a future audit distinguish "computed with the currently-configured
    # model" from "computed with an older model file", without storing
    # anything about the embedding's own content. Never the embedding's own
    # hash (embeddings are not hashed/verified this way anywhere).
    model_artifact_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )

    __table_args__ = (
        sa.Index("ix_biometric_embeddings_biometric_sample_id", "biometric_sample_id"),
        # At most one ACTIVE embedding per sample — the database-enforced
        # backstop for this module's "one-to-one-ish via is_active"
        # design (see this module's docstring), matching
        # BiometricSample's own "at most one ACTIVE sample per
        # enrollment" partial-unique-index pattern (Stage 2).
        sa.Index(
            "uq_biometric_embeddings_sample_active",
            "biometric_sample_id",
            unique=True,
            postgresql_where=sa.text("is_active = true"),
        ),
        sa.CheckConstraint("embedding_dimension > 0", name="embedding_dimension_positive"),
        sa.CheckConstraint(
            "array_length(embedding_values, 1) = embedding_dimension",
            name="embedding_values_length_matches_dimension",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"BiometricEmbedding(id={self.id!r}, "
            f"biometric_sample_id={self.biometric_sample_id!r}, "
            f"is_active={self.is_active!r})"
        )


class RecognitionAttendanceAttempt(Base):
    """One persisted, classroom-scoped recognition attendance decision.

    Only bounded identifiers and lifecycle state are stored. Probe images,
    embeddings, similarity vectors, provider paths, and raw errors never enter
    this table. ``candidate_student_profile_ids`` is the authorized roster
    snapshot used for matching and for later human-confirmation enforcement.
    """

    __tablename__ = "recognition_attendance_attempts"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    classroom_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("classrooms.id", ondelete="RESTRICT"), nullable=False
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False
    )
    attendance_date: Mapped[date] = mapped_column(Date(), nullable=False)
    decision: Mapped[MatchStatus] = mapped_column(
        sa.Enum(
            MatchStatus,
            name="recognition_attendance_decision",
            native_enum=True,
            validate_strings=True,
            values_callable=_enum_values,
        ),
        nullable=False,
    )
    matched_student_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("student_profiles.id", ondelete="RESTRICT"),
        nullable=True,
    )
    candidate_count: Mapped[int] = mapped_column(Integer(), nullable=False)
    candidate_student_profile_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)), nullable=False
    )
    confirmed_student_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("student_profiles.id", ondelete="RESTRICT"),
        nullable=True,
    )
    confirmed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attendance_record_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("attendance_records.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        nullable=False,
    )

    __table_args__ = (
        sa.Index("ix_recognition_attendance_attempts_actor_user_id", "actor_user_id"),
        sa.Index("ix_recognition_attendance_attempts_classroom_id", "classroom_id"),
        sa.Index("ix_recognition_attendance_attempts_subject_id", "subject_id"),
        sa.Index(
            "ix_recognition_attendance_attempts_attendance_record_id",
            "attendance_record_id",
        ),
        sa.CheckConstraint(
            "candidate_count > 0",
            name="candidate_count_positive",
        ),
        sa.CheckConstraint(
            "cardinality(candidate_student_profile_ids) = candidate_count",
            name="candidate_roster_count_matches",
        ),
        sa.CheckConstraint(
            "(decision = 'found' AND matched_student_profile_id IS NOT NULL) OR "
            "(decision <> 'found' AND matched_student_profile_id IS NULL)",
            name="matched_student_matches_decision",
        ),
        sa.CheckConstraint(
            "(confirmed_student_profile_id IS NULL AND confirmed_by_user_id IS NULL "
            "AND confirmed_at IS NULL) OR "
            "(confirmed_student_profile_id IS NOT NULL AND confirmed_by_user_id IS NOT NULL "
            "AND confirmed_at IS NOT NULL)",
            name="confirmation_fields_consistent",
        ),
    )


__all__ = ["BiometricEmbedding", "RecognitionAttendanceAttempt"]
