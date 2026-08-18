"""Enrollment-sample processing lifecycle — Phase 5 Stage 3.

Orchestrates exactly the pipeline described in the Stage 3 brief §8:
load a Stage 2 sample's stored image -> detect -> require exactly one
face -> align -> embed -> persist -> transition
``processing_state`` -> audit. This module is the **only** caller of
``app.modules.face_recognition.alignment``,
``app.modules.face_recognition.provider_factory``, and
``app.modules.face_recognition.repository.BiometricEmbeddingRepository``'s
write methods — every other Stage 3 module either implements a stage
of this pipeline or reads its results, never re-implements it.

**Reuses Phase 2-4/Stage 2 patterns directly** (matching
``app.modules.biometric_enrollment.service``'s own stated approach):
``app.db.transaction.service_transaction`` for the commit/rollback
boundary, and ``app.modules.attendance.repository.AuditLogRepository``
for the existing generic ``audit_logs`` table — no new audit table.

**Authorization:** every public method here assumes the caller (the
Stage 3 router) has already enforced ``require_roles(UserRole.ADMIN)``
— matching ``app.modules.biometric_enrollment.router``'s own
admin-only pattern for enrollment writes (see that router's docstring,
"Why there is no ownership-check dependency": an admin's role already
grants full scope, so there is no "right role, wrong scope" case to
add an object-level check for). There is no student- or teacher-facing
entrypoint into this module at all in Stage 3 — "students may not
process another student's biometrics" and "teachers only act within
authorized scope" are therefore satisfied structurally (no code path
exists for either), not by a runtime check this module would otherwise
need to perform itself.

**No half-persisted embedding on failure (Stage 3 brief §16):** the new
``BiometricEmbedding`` row and the sample's ``processing_state ->
PROCESSED`` transition happen inside the *same*
``service_transaction`` block (``_persist_success``) — a database
failure partway through rolls both back together. An inference failure
(detection/alignment/embedding raising before that block is ever
entered) never starts a transaction at all. The failure-path write
(``processing_state -> PROCESSING_FAILED`` plus a reason code) is a
separate, small, independent transaction (``_persist_failure``) that
runs *after* the success-path transaction has already been rolled back
or was never started — it must succeed on its own even though the
"real" work failed.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import numpy as np
import structlog
from PIL import Image, UnidentifiedImageError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.transaction import service_transaction
from app.modules.attendance.models import AuditOutcome
from app.modules.attendance.repository import AuditLogRepository
from app.modules.biometric_enrollment.errors import EnrollmentSampleNotFoundError
from app.modules.biometric_enrollment.models import (
    BiometricSample,
    RecognitionProcessingState,
    SampleStatus,
)
from app.modules.biometric_enrollment.repository import BiometricSampleRepository
from app.modules.biometric_enrollment.storage import PrivateBiometricStorage
from app.modules.face_recognition.domain import DecodedImage, EmbeddingVector
from app.modules.face_recognition.errors import (
    EnrollmentSampleMultipleFacesDetectedError,
    EnrollmentSampleNoFaceDetectedError,
    FaceAlignmentFailedError,
    FaceDetectionFailedError,
    FaceEmbeddingFailedError,
    FaceLandmarksUnavailableError,
    FaceProviderUnavailableError,
    FaceRecognitionError,
    ModelArtifactChecksumMismatchError,
    ModelArtifactMissingError,
    SampleImageDecodeFailedError,
    SampleNotEligibleForProcessingError,
    SampleStorageFileMissingError,
)
from app.modules.face_recognition.image_codec import ndarray_to_decoded_image
from app.modules.face_recognition.model_artifacts import compute_sha256
from app.modules.face_recognition.pipeline import detect_align_embed
from app.modules.face_recognition.providers.dlib_embedder import DlibResnetFaceEmbedder
from app.modules.face_recognition.repository import BiometricEmbeddingRepository
from app.modules.users.models import User

logger = structlog.get_logger(__name__)

ACTION_SAMPLE_PROCESS = "face_recognition.sample_process"
ACTION_SAMPLE_RETRY = "face_recognition.sample_retry"
_ENTITY_TYPE_SAMPLE = "biometric_sample"

# Safe, generic failure-reason codes — never a raw exception message, a
# model name, or a filesystem path (docs/BIOMETRIC_DATA_POLICY.md).
REASON_STORAGE_FILE_MISSING = "storage_file_missing"
REASON_IMAGE_DECODE_FAILED = "image_decode_failed"
REASON_PROVIDER_UNAVAILABLE = "provider_unavailable"
REASON_DETECTION_FAILED = "detection_failed"
REASON_ZERO_FACES = "zero_faces_detected"
REASON_MULTIPLE_FACES = "multiple_faces_detected"
REASON_ALIGNMENT_FAILED = "alignment_failed"
REASON_EMBEDDING_FAILED = "embedding_failed"
REASON_UNEXPECTED = "unexpected_processing_error"

# Ordered as a list-of-pairs (not a dict) deliberately, so a subclass
# always has the chance to be listed, and matched, ahead of a broader
# ancestor if one is ever added — not currently exercised (every entry
# below is presently a leaf error type) but cheap to preserve.
_REASON_CODES_BY_ERROR_TYPE: tuple[tuple[type[FaceRecognitionError], str], ...] = (
    (SampleStorageFileMissingError, REASON_STORAGE_FILE_MISSING),
    (SampleImageDecodeFailedError, REASON_IMAGE_DECODE_FAILED),
    (EnrollmentSampleNoFaceDetectedError, REASON_ZERO_FACES),
    (EnrollmentSampleMultipleFacesDetectedError, REASON_MULTIPLE_FACES),
    (FaceLandmarksUnavailableError, REASON_ALIGNMENT_FAILED),
    (FaceAlignmentFailedError, REASON_ALIGNMENT_FAILED),
    (FaceDetectionFailedError, REASON_DETECTION_FAILED),
    (FaceEmbeddingFailedError, REASON_EMBEDDING_FAILED),
    (FaceProviderUnavailableError, REASON_PROVIDER_UNAVAILABLE),
    (ModelArtifactMissingError, REASON_PROVIDER_UNAVAILABLE),
    (ModelArtifactChecksumMismatchError, REASON_PROVIDER_UNAVAILABLE),
)


def _reason_code_for_error(exc: FaceRecognitionError) -> str:
    for exc_type, reason in _REASON_CODES_BY_ERROR_TYPE:
        if isinstance(exc, exc_type):
            return reason
    return REASON_UNEXPECTED


@dataclass(frozen=True)
class ProcessingResult:
    """Safe outcome of one processing attempt — never carries embedding values."""

    sample_id: uuid.UUID
    succeeded: bool
    reason_code: str | None = None


class SampleProcessingService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        storage: PrivateBiometricStorage | None = None,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._storage = storage or PrivateBiometricStorage(self._settings)
        self._samples = BiometricSampleRepository(session)
        self._embeddings = BiometricEmbeddingRepository(session)
        self._audit_logs = AuditLogRepository(session)

    async def process_sample(
        self, *, sample_id: uuid.UUID, actor: User, request_id: str | None = None
    ) -> ProcessingResult:
        """Process a sample currently awaiting its first Stage 3 attempt.

        Accepts only ``status == ACTIVE`` **and**
        ``processing_state == PENDING_PROCESSING`` — this is an explicit
        allow-list, not "reject PROCESSED and let everything else
        through": a ``PROCESSING_FAILED`` sample is just as firmly
        rejected here as an already-``PROCESSED`` one. A previously
        failed attempt must go through ``retry_sample`` instead, which is
        the only method that accepts ``PROCESSING_FAILED`` — this keeps
        "first attempt" and "retry" as two distinct, auditable actions
        (``ACTION_SAMPLE_PROCESS`` vs ``ACTION_SAMPLE_RETRY``) rather than
        one method silently doing double duty.
        """
        sample = await self._require_sample(sample_id)
        if sample.status is not SampleStatus.ACTIVE:
            raise SampleNotEligibleForProcessingError("sample_not_active")
        if sample.processing_state is not RecognitionProcessingState.PENDING_PROCESSING:
            reason = (
                "sample_already_processed"
                if sample.processing_state is RecognitionProcessingState.PROCESSED
                else "sample_already_failed_use_retry"
            )
            raise SampleNotEligibleForProcessingError(reason)
        return await self._run_pipeline(
            sample, actor=actor, request_id=request_id, action=ACTION_SAMPLE_PROCESS
        )

    async def retry_sample(
        self, *, sample_id: uuid.UUID, actor: User, request_id: str | None = None
    ) -> ProcessingResult:
        """Retry a sample whose previous processing attempt failed.

        Accepts only ``status == ACTIVE`` **and**
        ``processing_state == PROCESSING_FAILED`` — the mirror image of
        ``process_sample``'s allow-list. Neither a still-pending sample
        (use ``process_sample``) nor an already-``PROCESSED`` one may be
        retried.
        """
        sample = await self._require_sample(sample_id)
        if sample.status is not SampleStatus.ACTIVE:
            raise SampleNotEligibleForProcessingError("sample_not_active")
        if sample.processing_state is not RecognitionProcessingState.PROCESSING_FAILED:
            raise SampleNotEligibleForProcessingError("sample_not_in_failed_state")
        return await self._run_pipeline(
            sample, actor=actor, request_id=request_id, action=ACTION_SAMPLE_RETRY
        )

    async def process_pending_batch(
        self, *, actor: User, request_id: str | None = None, limit: int | None = None
    ) -> list[ProcessingResult]:
        """Process up to ``limit`` (default/ceiling ``Settings.FACE_PROCESSING_BATCH_LIMIT``)
        samples still awaiting processing.

        Not an always-running worker — one bounded, on-demand call. A
        single sample's failure never stops the batch; every sample's
        outcome (success or failure, with its own reason code) is
        collected and returned.
        """
        ceiling = self._settings.FACE_PROCESSING_BATCH_LIMIT
        bounded_limit = min(limit, ceiling) if limit is not None else ceiling
        pending = await self._samples.list_active_pending_processing(limit=bounded_limit)
        results: list[ProcessingResult] = []
        for sample in pending:
            result = await self._run_pipeline(
                sample, actor=actor, request_id=request_id, action=ACTION_SAMPLE_PROCESS
            )
            results.append(result)
        return results

    # --- pipeline ------------------------------------------------------

    async def _run_pipeline(
        self, sample: BiometricSample, *, actor: User, request_id: str | None, action: str
    ) -> ProcessingResult:
        await self._samples.mark_processing_started(sample, started_at=_utcnow())

        try:
            # Stage 3 correction (finding 3): image decode + detect ->
            # align -> embed is synchronous, CPU/IO-bound work (Pillow
            # decode, YuNet inference, dlib inference) — running it
            # directly here would block this async worker's event loop
            # for the duration of one sample's full pipeline. Offloaded
            # as a single ``asyncio.to_thread`` call (not two separate
            # calls) so the image decode and the inference that
            # consumes it happen back-to-back on the same worker
            # thread, with no event-loop round trip in between.
            embedding = await asyncio.to_thread(self._load_and_embed_sync, sample)
        except FaceRecognitionError as exc:
            reason_code = _reason_code_for_error(exc)
            await self._persist_failure(
                sample,
                actor=actor,
                request_id=request_id,
                action=action,
                reason_code=reason_code,
            )
            return ProcessingResult(sample_id=sample.id, succeeded=False, reason_code=reason_code)
        except Exception:
            logger.error("face_recognition_processing_unexpected_error", sample_id=str(sample.id))
            await self._persist_failure(
                sample,
                actor=actor,
                request_id=request_id,
                action=action,
                reason_code=REASON_UNEXPECTED,
            )
            return ProcessingResult(
                sample_id=sample.id, succeeded=False, reason_code=REASON_UNEXPECTED
            )

        model_checksum = self._embedder_checksum()
        await self._persist_success(
            sample,
            actor=actor,
            request_id=request_id,
            action=action,
            embedding_values=list(embedding.values),
            model_checksum=model_checksum,
        )
        return ProcessingResult(sample_id=sample.id, succeeded=True)

    def _load_and_embed_sync(self, sample: BiometricSample) -> EmbeddingVector:
        """The synchronous half of one sample's pipeline — everything that must
        run off the event loop via ``asyncio.to_thread`` (see ``_run_pipeline``).

        Provider-instance thread-safety for the ``detect_align_embed`` portion
        is handled inside the cached provider adapters themselves
        (``YuNetFaceDetector._lock``/``DlibResnetFaceEmbedder._lock``), not
        here — this method just makes sure the *call* happens off-thread.
        """
        decoded_image = self._load_decoded_image(sample)
        return detect_align_embed(decoded_image, settings=self._settings)

    def _load_decoded_image(self, sample: BiometricSample) -> DecodedImage:
        if not self._storage.exists_active(sample.storage_key):
            raise SampleStorageFileMissingError()
        path = self._storage.active_path(sample.storage_key)
        try:
            data = path.read_bytes()
            with Image.open(BytesIO(data)) as image:
                rgb_image = image.convert("RGB")
                array = np.asarray(rgb_image, dtype=np.uint8)
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise SampleImageDecodeFailedError() from exc

        return ndarray_to_decoded_image(array, color_format="rgb")

    def _embedder_checksum(self) -> str | None:
        configured_path = (self._settings.FACE_EMBEDDER_MODEL_PATH or "").strip()
        if not configured_path:
            return None
        try:
            return compute_sha256(Path(configured_path))
        except OSError:  # pragma: no cover - defensive, model already validated by embedder
            return None

    async def _persist_success(
        self,
        sample: BiometricSample,
        *,
        actor: User,
        request_id: str | None,
        action: str,
        embedding_values: list[float],
        model_checksum: str | None,
    ) -> None:
        now = _utcnow()
        async with service_transaction(self._session):
            await self._embeddings.supersede_active_for_sample(sample.id, superseded_at=now)
            await self._embeddings.create_active(
                biometric_sample_id=sample.id,
                provider_name=DlibResnetFaceEmbedder.provider_name,
                model_identifier=DlibResnetFaceEmbedder.model_identifier,
                model_version="v1",
                embedding_values=embedding_values,
                model_artifact_checksum=model_checksum,
            )
            await self._samples.mark_processed(sample, completed_at=now)
            await self._audit_logs.create(
                actor_user_id=actor.id,
                action=action,
                outcome=AuditOutcome.SUCCESS,
                entity_type=_ENTITY_TYPE_SAMPLE,
                entity_id=sample.id,
                request_id=request_id,
                event_metadata={"processing_result": "processed"},
            )

    async def _persist_failure(
        self,
        sample: BiometricSample,
        *,
        actor: User,
        request_id: str | None,
        action: str,
        reason_code: str,
    ) -> None:
        now = _utcnow()
        async with service_transaction(self._session):
            await self._samples.mark_processing_failed(
                sample, completed_at=now, reason_code=reason_code
            )
            await self._audit_logs.create(
                actor_user_id=actor.id,
                action=action,
                outcome=AuditOutcome.SUCCESS,
                entity_type=_ENTITY_TYPE_SAMPLE,
                entity_id=sample.id,
                request_id=request_id,
                event_metadata={"processing_result": "failed", "reason_code": reason_code},
            )

    async def _require_sample(self, sample_id: uuid.UUID) -> BiometricSample:
        sample = await self._samples.get_by_id(sample_id)
        if sample is None:
            raise EnrollmentSampleNotFoundError()
        return sample


def _utcnow() -> datetime:
    return datetime.now(UTC)
