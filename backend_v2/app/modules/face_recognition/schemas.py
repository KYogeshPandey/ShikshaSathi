"""Safe request/response schemas for the Phase 5 face-recognition APIs.

**Not one response schema in this file has a field for an embedding value, raw
image bytes, or a filesystem path** (Stage 3 brief §14: "Never return
embeddings or image bytes through APIs"). This is enforced structurally
— every schema below is a small, explicit Pydantic model naming only
the fields it needs — not by a runtime redaction step that could be
forgotten on a new field.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.attendance.models import AttendanceStatus
from app.modules.face_recognition.domain import MatchStatus, ProviderStatus


class SampleProcessingStatusRead(BaseModel):
    """Safe processing status for one biometric sample.

    Deliberately excludes ``embedding_dimension``/``provider_name``/
    etc. (those live only in ``app.modules.face_recognition.models.BiometricEmbedding``,
    which has no read route at all in Stage 3) — this schema answers
    "did processing succeed", not "what did processing produce".
    """

    model_config = ConfigDict(frozen=True)

    sample_id: uuid.UUID
    processing_state: str
    processing_started_at: datetime | None
    processing_completed_at: datetime | None
    failure_reason_code: str | None


class ProcessSampleResult(BaseModel):
    """Result of one process/retry call."""

    model_config = ConfigDict(frozen=True)

    sample_id: uuid.UUID
    succeeded: bool
    reason_code: str | None = None


class BatchProcessingResult(BaseModel):
    """Result of one bounded process-pending-batch call."""

    model_config = ConfigDict(frozen=True)

    attempted_count: int
    succeeded_count: int
    failed_count: int
    results: list[ProcessSampleResult]


class ProviderHealthRead(BaseModel):
    """One provider's safe health metadata — mirrors ``domain.ProviderHealth`` exactly."""

    model_config = ConfigDict(frozen=True)

    provider_name: str
    status: ProviderStatus
    detail: str | None = None


class FaceRecognitionHealthRead(BaseModel):
    """Combined detector + embedder health for the ``GET /face-recognition/health`` route."""

    model_config = ConfigDict(frozen=True)

    overall_status: ProviderStatus
    detector: ProviderHealthRead
    embedder: ProviderHealthRead


class MatchProbeResult(BaseModel):
    """Result of an explicitly candidate-scoped match-probe validation call.

    ``matched_student_profile_id`` is populated only when
    ``status == MatchStatus.FOUND``. Similarity scores are plain floats
    (never a vector) and are included for operator visibility into
    *how* confident a result was — never enough information to
    reconstruct an embedding.
    """

    model_config = ConfigDict(frozen=True)

    status: MatchStatus
    matched_student_profile_id: uuid.UUID | None
    best_similarity: float | None
    runner_up_similarity: float | None


class RecognitionAttendanceAttemptRead(BaseModel):
    """Safe Stage 4 result; never exposes the roster snapshot or biometric data."""

    model_config = ConfigDict(frozen=True)

    attempt_id: uuid.UUID
    classroom_id: uuid.UUID
    subject_id: uuid.UUID
    attendance_date: date
    decision: MatchStatus
    matched_student_profile_id: uuid.UUID | None
    attendance_record_id: uuid.UUID | None
    requires_confirmation: bool


class RecognitionAttendanceConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    student_profile_id: uuid.UUID


class RecognitionAttendanceConfirmationRead(BaseModel):
    """Idempotent confirmation result with only attendance-safe identifiers."""

    model_config = ConfigDict(frozen=True)

    attempt_id: uuid.UUID
    decision: MatchStatus
    confirmed_student_profile_id: uuid.UUID
    attendance_record_id: uuid.UUID


class RecognitionAttendanceProposalRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    attempt_id: uuid.UUID
    face_index: int
    decision: MatchStatus
    matched_student_profile_id: uuid.UUID | None
    best_similarity: float | None
    is_duplicate: bool


class RecognitionAttendanceReviewRead(BaseModel):
    """In-memory recognition results plus a persisted, non-biometric review ID."""

    model_config = ConfigDict(frozen=True)

    review_id: uuid.UUID
    classroom_id: uuid.UUID
    subject_id: uuid.UUID
    attendance_date: date
    face_count: int
    proposals: list[RecognitionAttendanceProposalRead]


class RecognitionAttendanceReviewRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    student_profile_id: uuid.UUID
    status: AttendanceStatus


class RecognitionAttendanceReviewConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    records: list[RecognitionAttendanceReviewRecord] = Field(min_length=1)

    @model_validator(mode="after")
    def _reject_duplicate_students(self) -> RecognitionAttendanceReviewConfirmationRequest:
        student_ids = [record.student_profile_id for record in self.records]
        if len(student_ids) != len(set(student_ids)):
            raise ValueError("Each student may appear at most once in a review confirmation.")
        return self


class RecognitionAttendanceReviewConfirmationRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    review_id: uuid.UUID
    attendance_record_ids: list[uuid.UUID]
    confirmed_records: list[RecognitionAttendanceReviewRecord]
