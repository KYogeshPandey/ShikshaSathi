"""Pydantic v2 schemas for biometric enrollment and photo ingestion.

Every response schema here is safe-metadata-only: no image bytes, no
embeddings, no storage-root/absolute/temporary paths, no provider
diagnostics. See ``BiometricSampleRead`` for the exact field list and
its docstring for what is deliberately excluded.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.biometric_enrollment.models import (
    EnrollmentStatus,
    RecognitionProcessingState,
    SampleStatus,
)


class _StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BiometricSampleRead(BaseModel):
    """Safe metadata about one stored sample.

    Deliberately excludes: ``storage_key`` (an internal filesystem
    locator), any absolute or temporary path, raw image bytes, and any
    embedding (Stage 3 does not exist yet, but even once it does, an
    embedding is never returned by any API — see
    docs/BIOMETRIC_DATA_POLICY.md).
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    enrollment_id: uuid.UUID
    status: SampleStatus
    processing_state: RecognitionProcessingState
    content_type: str
    file_size_bytes: int
    width_px: int
    height_px: int
    sha256_hash: str
    original_filename: str | None
    previous_sample_id: uuid.UUID | None
    created_by_user_id: uuid.UUID
    promoted_at: datetime | None
    quarantined_at: datetime | None
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class BiometricEnrollmentRead(BaseModel):
    """Safe metadata about one student's enrollment identity/lifecycle."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    student_profile_id: uuid.UUID
    status: EnrollmentStatus
    created_by_user_id: uuid.UUID
    deletion_requested_by_user_id: uuid.UUID | None
    deletion_requested_at: datetime | None
    created_at: datetime
    updated_at: datetime


class BiometricEnrollmentDetailRead(BaseModel):
    """Enrollment plus its full sample history — used by the list-samples read."""

    enrollment: BiometricEnrollmentRead
    samples: list[BiometricSampleRead]


class BiometricSampleReplaceResult(BaseModel):
    enrollment_id: uuid.UUID
    previous_sample_id: uuid.UUID
    new_sample: BiometricSampleRead


class BiometricSampleDeletionResult(BaseModel):
    enrollment_id: uuid.UUID
    sample_id: uuid.UUID
    status: SampleStatus
    message: str


# --- bulk ZIP ingestion -------------------------------------------------------


class BulkEnrollmentRowResult(BaseModel):
    row_number: int = Field(..., ge=1)
    student_profile_id: str
    filename: str
    outcome: Literal["enrolled", "failed"]
    error_code: str | None = None
    error_message: str | None = None
    sample_id: uuid.UUID | None = None


class BulkEnrollmentResult(BaseModel):
    """Whole-batch result — only reached once the archive itself is valid.

    See app/modules/biometric_enrollment/bulk_service.py's module
    docstring for the exact atomicity contract:

    - An archive-level problem (bad ZIP, unsafe path, missing manifest,
      etc.) never produces this schema at all — it surfaces as a plain
      ``422``/``413`` error response before any row is even considered.
    - A row-level problem (student not found/inactive/already enrolled,
      duplicate content) discovered during pre-validation produces
      ``success=False`` with ``enrolled_count=0`` — every row is
      reported failed, and nothing was written.
    - The one exception to "``success=False`` implies ``enrolled_count
      == 0``": a genuine infrastructure failure (disk/database) partway
      through the execution phase, after every row already passed
      pre-validation. That is the one documented case where
      ``enrolled_count`` can be greater than zero alongside
      ``success=False`` — see the "known risks" section of
      docs/HANDOVER_PHASE_5_STAGE_2.md.
    """

    success: bool
    total_rows: int = Field(..., ge=0)
    enrolled_count: int = Field(..., ge=0)
    failed_count: int = Field(..., ge=0)
    rows: list[BulkEnrollmentRowResult]


# --- reconciliation -----------------------------------------------------------


class ReconciliationFinding(BaseModel):
    """One piece of detected database/filesystem drift.

    ``key`` is the opaque storage key involved (never a path). This
    report only ever *describes* drift — see
    app/modules/biometric_enrollment/reconciliation.py's module
    docstring for why no automatic repair happens here.
    """

    finding_type: str
    key: str
    sample_id: uuid.UUID | None = None
    detail: str


class ReconciliationReport(BaseModel):
    generated_at: datetime
    findings: list[ReconciliationFinding]
    stale_pending_sample_count: int = Field(..., ge=0)
