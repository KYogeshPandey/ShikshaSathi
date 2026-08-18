"""ORM models for Phase 5 Stage 2: biometric enrollment and stored samples.

Design decisions (see docs/HANDOVER_PHASE_5_STAGE_2.md for the full
rationale; summarized here at the point of use):

- **Two tables, clear separation of concerns.** ``BiometricEnrollment``
  is the student's enrollment *identity/lifecycle* (at most one row per
  student — enforced by a unique constraint on ``student_profile_id``).
  ``BiometricSample`` is one *stored image* attempt against that
  enrollment; a student accumulates a history of samples over time
  (created, replaced, deleted) but — per the Stage 2 brief's single
  "create"/"replace" API shape — has at most one ``ACTIVE`` sample at
  any moment, enforced by a partial unique index rather than trusted to
  application logic alone.
- **UUID primary keys**, continuing the Phase 2-4 convention (docs/adr/0006).
- **``storage_key`` is a separate, server-generated opaque value — never
  the row's own ``id``.** This is deliberate defense in depth: even
  though both are server-generated UUIDs today, decoupling "database
  identity" from "filesystem locator" means a future storage-layout
  change (sharding, key rotation) never requires renumbering primary
  keys, and a client can never influence a storage path by any means
  (there is no client-supplied value anywhere near this column — see
  app/modules/biometric_enrollment/storage.py).
- **``status`` (``biometric_enrollment_status`` / ``biometric_sample_status``)
  are native PostgreSQL enums**, matching the ``attendance_status`` /
  ``audit_outcome`` pattern already established in Phase 4 — an invalid
  status is structurally impossible to store.
- **``processing_state`` is intentionally its own, separate enum from
  ``status``.** ``status`` tracks the *file lifecycle* (is this sample
  staged, active, being replaced, being deleted?); ``processing_state``
  tracks *recognition readiness* (has Stage 3 successfully embedded this
  sample yet?). Stage 2 code only ever writes
  ``RecognitionProcessingState.PENDING_PROCESSING`` — ``PROCESSED`` and
  ``PROCESSING_FAILED`` are declared now (so Stage 3 does not need an
  ``ALTER TYPE ... ADD VALUE`` migration later) but are never set by any
  Stage 2 code path. No Stage 2 code path ever claims a sample is
  recognition-ready.
- **``previous_sample_id`` is a nullable self-referencing FK**
  (``ondelete="SET NULL"``), populated only when a new sample is created
  to *replace* an existing one (see
  app/modules/biometric_enrollment/service.py's replace flow). It lets a
  reconciliation/audit read reconstruct "what did this replace" without
  needing a separate history table.
- **``created_by_user_id`` uses ``ondelete="RESTRICT"``**, matching
  ``AttendanceRecord.marked_by_user_id``'s rationale
  (app/modules/attendance/models.py): an attributable historical record
  must not be silently orphaned by a hard user deletion. In practice
  users are only ever soft-deactivated, never hard-deleted (docs/AUDIT.md
  §2.3 positive finding carried forward), so this is a structural
  backstop, not an expected code path.
- **``BiometricEnrollment.deletion_requested_by_user_id`` uses
  ``ondelete="SET NULL"``.** Unlike ``created_by_user_id``, this is
  optional context on an in-progress lifecycle transition, not the row's
  own identity — losing it should not block a hard user deletion (which,
  again, does not happen in practice today).
- **Content-integrity/shape constraints are enforced at the database
  layer, not just in Pydantic/service code**: ``width_px``/``height_px``/
  ``file_size_bytes`` must be positive, and ``sha256_hash`` must be
  exactly 64 lowercase hex characters. These are structural backstops
  against a future code path writing a row some other way, matching this
  application's existing preference for database-enforced invariants
  (e.g. the attendance four-column unique constraint) over
  application-only assumptions.
- **No raw image bytes, and no embedding, is ever a column on either
  table.** ``BiometricSample`` stores only a storage *key* (a location
  reference) plus safe, non-biometric metadata (MIME type, byte size,
  pixel dimensions, content hash). This directly satisfies
  docs/BIOMETRIC_DATA_POLICY.md's "biometric image bytes are never
  stored in PostgreSQL" requirement.

- **Phase 5 Stage 3 addendum:** three nullable bookkeeping columns
  (``processing_started_at``, ``processing_completed_at``,
  ``processing_failure_reason_code``) were added to ``BiometricSample``
  via a new migration on top of Stage 2's (Stage 2's own migration file
  is never edited — see
  ``alembic/versions/*_create_biometric_embedding_and_processing_columns.py``).
  The actual embedding vector lives in a new, separate
  ``app.modules.face_recognition.models.BiometricEmbedding`` table (one
  new aggregate root, owned by the ``face_recognition`` module, not
  this one) — see that module's docstring for why persistence for the
  embedding itself was deliberately not added here as a fourth Stage-2
  table column.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum, StrEnum

import sqlalchemy as sa
from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _enum_values(enum_cls: type[Enum]) -> list[str]:
    """Persist each enum member's public value, not its Python member name.

    Duplicated (rather than imported) from ``app.modules.attendance.models``
    — same deliberate choice already made there and in
    ``app.modules.academics.models``: avoiding a cross-module import
    between two otherwise-independent domain modules for one four-line
    helper.
    """
    return [str(member.value) for member in enum_cls]


class EnrollmentStatus(StrEnum):
    """The biometric-enrollment *identity* lifecycle (one row per student)."""

    PENDING = "pending"
    ACTIVE = "active"
    DELETION_PENDING = "deletion_pending"
    DELETED = "deleted"


class SampleStatus(StrEnum):
    """One stored sample's *file* lifecycle.

    ``PENDING`` -> ``ACTIVE`` (normal path). ``ACTIVE`` ->
    ``REPLACEMENT_PENDING`` when a new sample is being promoted to take
    its place. ``ACTIVE``/``REPLACEMENT_PENDING`` -> ``DELETION_PENDING``
    -> ``QUARANTINED`` -> ``DELETED`` on removal. See
    app/modules/biometric_enrollment/service.py for the exact state
    machine and app/modules/biometric_enrollment/storage.py for the
    matching physical-directory zones (staging/active/quarantine).
    """

    PENDING = "pending"
    ACTIVE = "active"
    REPLACEMENT_PENDING = "replacement_pending"
    DELETION_PENDING = "deletion_pending"
    QUARANTINED = "quarantined"
    DELETED = "deleted"


class RecognitionProcessingState(StrEnum):
    """Whether Stage 3 has embedded this sample yet.

    Stage 2 never sets anything other than ``PENDING_PROCESSING`` — see
    this module's docstring.
    """

    PENDING_PROCESSING = "pending_processing"
    PROCESSED = "processed"
    PROCESSING_FAILED = "processing_failed"


class BiometricEnrollment(Base):
    """A student's biometric-enrollment identity (at most one per student)."""

    __tablename__ = "biometric_enrollments"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    student_profile_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("student_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[EnrollmentStatus] = mapped_column(
        sa.Enum(
            EnrollmentStatus,
            name="biometric_enrollment_status",
            native_enum=True,
            validate_strings=True,
            values_callable=_enum_values,
        ),
        nullable=False,
        default=EnrollmentStatus.PENDING,
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    deletion_requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    deletion_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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
        sa.UniqueConstraint(
            "student_profile_id", name="uq_biometric_enrollments_student_profile_id"
        ),
        sa.Index("ix_biometric_enrollments_status", "status"),
        sa.Index("ix_biometric_enrollments_created_by_user_id", "created_by_user_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"BiometricEnrollment(id={self.id!r}, "
            f"student_profile_id={self.student_profile_id!r}, status={self.status!r})"
        )


class BiometricSample(Base):
    """One stored biometric image sample belonging to an enrollment.

    Not recognition-ready by construction: see
    ``RecognitionProcessingState`` above. No column here ever holds raw
    image bytes or an embedding — only a storage *key* and safe,
    non-biometric metadata.
    """

    __tablename__ = "biometric_samples"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("biometric_enrollments.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Opaque, server-generated, never derived from any client-supplied
    # value (filename, path, or otherwise) — see this module's docstring.
    storage_key: Mapped[str] = mapped_column(String(64), nullable=False)
    # Sanitized metadata only (never used to build a filesystem path) —
    # see app/modules/biometric_enrollment/storage.py.
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    width_px: Mapped[int] = mapped_column(Integer(), nullable=False)
    height_px: Mapped[int] = mapped_column(Integer(), nullable=False)
    sha256_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[SampleStatus] = mapped_column(
        sa.Enum(
            SampleStatus,
            name="biometric_sample_status",
            native_enum=True,
            validate_strings=True,
            values_callable=_enum_values,
        ),
        nullable=False,
        default=SampleStatus.PENDING,
    )
    processing_state: Mapped[RecognitionProcessingState] = mapped_column(
        sa.Enum(
            RecognitionProcessingState,
            name="biometric_recognition_processing_state",
            native_enum=True,
            validate_strings=True,
            values_callable=_enum_values,
        ),
        nullable=False,
        default=RecognitionProcessingState.PENDING_PROCESSING,
    )
    previous_sample_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("biometric_samples.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    quarantined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # --- Phase 5 Stage 3: recognition-processing bookkeeping ---------------
    # Added via a NEW migration (parent ca8e748dc8f2 — Stage 2's own
    # migration file is never edited, see
    # alembic/versions/*_create_biometric_embedding_and_processing_columns.py).
    # `processing_state` itself (above) is Stage 2 schema already; these
    # three columns give Stage 3 somewhere to record *when* a processing
    # attempt ran and *why* it failed, without touching Stage 2's table
    # definition. Never contains raw exception text or a filesystem path
    # — always one of the short reason codes documented in
    # app/modules/face_recognition/processing_service.py.
    processing_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processing_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processing_failure_reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
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
        sa.UniqueConstraint("storage_key", name="uq_biometric_samples_storage_key"),
        sa.Index("ix_biometric_samples_enrollment_id", "enrollment_id"),
        sa.Index("ix_biometric_samples_status", "status"),
        sa.Index("ix_biometric_samples_created_by_user_id", "created_by_user_id"),
        sa.Index("ix_biometric_samples_previous_sample_id", "previous_sample_id"),
        # At most one ACTIVE sample per enrollment — a database-enforced
        # backstop for the "single current sample" lifecycle, not merely
        # a service-layer assumption.
        sa.Index(
            "uq_biometric_samples_enrollment_active",
            "enrollment_id",
            unique=True,
            postgresql_where=sa.text("status = 'active'"),
        ),
        # Re-uploading the exact same image content for the same student
        # is rejected as a duplicate (Stage 2 brief §7) while the earlier
        # copy is not DELETED; once DELETED, the same content may be
        # re-enrolled. Identical content across *different* students is
        # explicitly allowed (not scoped globally).
        sa.Index(
            "uq_biometric_samples_enrollment_sha256_live",
            "enrollment_id",
            "sha256_hash",
            unique=True,
            postgresql_where=sa.text("status != 'deleted'"),
        ),
        # NOTE: these `name=` values are deliberately *bare* (no
        # "ck_biometric_samples_" prefix) — CheckConstraint has no
        # participating columns to derive a name from the way a
        # ForeignKey/UniqueConstraint can, so SQLAlchemy's naming
        # convention (app/db/naming.py: "ck_%(table_name)s_%(constraint_name)s")
        # substitutes whatever is passed here directly as the
        # `constraint_name` token. Passing an already-prefixed name would
        # double-prefix the result (`ck_biometric_samples_ck_biometric_samples_...`),
        # which does not match the literal names Alembic's migration
        # creates (see alembic/versions/20260804_1000_ca8e748dc8f2_*.py)
        # or what the test suite asserts.
        sa.CheckConstraint("width_px > 0", name="width_px_positive"),
        sa.CheckConstraint("height_px > 0", name="height_px_positive"),
        sa.CheckConstraint("file_size_bytes > 0", name="file_size_bytes_positive"),
        sa.CheckConstraint("sha256_hash ~ '^[0-9a-f]{64}$'", name="sha256_hash_format"),
    )

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"BiometricSample(id={self.id!r}, enrollment_id={self.enrollment_id!r}, "
            f"status={self.status!r}, processing_state={self.processing_state!r})"
        )


__all__ = [
    "BiometricEnrollment",
    "BiometricSample",
    "EnrollmentStatus",
    "RecognitionProcessingState",
    "SampleStatus",
]
