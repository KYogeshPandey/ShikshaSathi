"""Thin, authorized Phase 5 face-recognition API.

Stage 3 sample-processing, health, and diagnostic match-probe routes remain
admin-only. Stage 4 adds teacher/admin recognition-attendance routes; their
service authorizes the classroom/subject and derives the active roster before
the router reads or validates the upload. No route returns embeddings, image
bytes, candidate-roster snapshots, or filesystem/model paths.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date
from io import BytesIO
from typing import Annotated

import numpy as np
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.modules.attendance.schemas import BulkAttendanceRecordIn
from app.modules.auth.dependencies import require_roles
from app.modules.biometric_enrollment.errors import EnrollmentSampleNotFoundError
from app.modules.biometric_enrollment.repository import BiometricSampleRepository
from app.modules.face_recognition.domain import EmbeddingVector
from app.modules.face_recognition.errors import MatchProbeImageTooLargeError
from app.modules.face_recognition.health import get_face_recognition_health
from app.modules.face_recognition.image_codec import ndarray_to_decoded_image
from app.modules.face_recognition.match_probe_validation import (
    ValidatedProbeImage,
    validate_probe_image_bytes,
)
from app.modules.face_recognition.matching_service import MatchingService
from app.modules.face_recognition.pipeline import detect_align_embed, detect_align_embed_many
from app.modules.face_recognition.processing_service import SampleProcessingService
from app.modules.face_recognition.recognition_attendance_service import (
    RecognitionAttendanceService,
)
from app.modules.face_recognition.schemas import (
    BatchProcessingResult,
    FaceRecognitionHealthRead,
    MatchProbeResult,
    ProcessSampleResult,
    ProviderHealthRead,
    RecognitionAttendanceAttemptRead,
    RecognitionAttendanceConfirmationRead,
    RecognitionAttendanceConfirmationRequest,
    RecognitionAttendanceProposalRead,
    RecognitionAttendanceReviewConfirmationRead,
    RecognitionAttendanceReviewConfirmationRequest,
    RecognitionAttendanceReviewRead,
    SampleProcessingStatusRead,
)
from app.modules.users.models import User, UserRole

router = APIRouter(prefix="/face-recognition", tags=["face recognition"])

AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
AdminOrTeacher = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.TEACHER))]
Session = Annotated[AsyncSession, Depends(get_db_session)]

_UPLOAD_CHUNK_SIZE = 1024 * 1024
_MAX_PROBE_IMAGE_BYTES = 8 * 1024 * 1024


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


@router.post("/samples/{sample_id}/process", response_model=ProcessSampleResult)
async def process_sample(
    sample_id: uuid.UUID,
    admin: AdminUser,
    session: Session,
    request: Request,
) -> ProcessSampleResult:
    """Run detect -> align -> embed -> persist for one Stage 2 sample.

    409s if the sample is not ``ACTIVE`` or is already ``PROCESSED``
    (use ``/retry`` for a ``PROCESSING_FAILED`` sample). A processing
    *failure* (e.g. zero faces detected) is not an HTTP error — it is
    recorded on the sample and returned as
    ``ProcessSampleResult(succeeded=False, reason_code=...)``, mirroring
    how Stage 2 treats a rejected-but-well-formed request.
    """
    service = SampleProcessingService(session)
    result = await service.process_sample(
        sample_id=sample_id, actor=admin, request_id=_request_id(request)
    )
    return ProcessSampleResult(
        sample_id=result.sample_id, succeeded=result.succeeded, reason_code=result.reason_code
    )


@router.post("/samples/{sample_id}/retry", response_model=ProcessSampleResult)
async def retry_sample(
    sample_id: uuid.UUID,
    admin: AdminUser,
    session: Session,
    request: Request,
) -> ProcessSampleResult:
    """Retry a sample whose previous processing attempt failed."""
    service = SampleProcessingService(session)
    result = await service.retry_sample(
        sample_id=sample_id, actor=admin, request_id=_request_id(request)
    )
    return ProcessSampleResult(
        sample_id=result.sample_id, succeeded=result.succeeded, reason_code=result.reason_code
    )


@router.post("/samples/process-pending", response_model=BatchProcessingResult)
async def process_pending_samples(
    admin: AdminUser,
    session: Session,
    request: Request,
    limit: int | None = None,
) -> BatchProcessingResult:
    """Process up to a bounded number of samples still awaiting processing.

    One on-demand call, not a background worker — see
    ``SampleProcessingService.process_pending_batch``'s docstring.
    """
    service = SampleProcessingService(session)
    results = await service.process_pending_batch(
        actor=admin, request_id=_request_id(request), limit=limit
    )
    succeeded = sum(1 for result in results if result.succeeded)
    return BatchProcessingResult(
        attempted_count=len(results),
        succeeded_count=succeeded,
        failed_count=len(results) - succeeded,
        results=[
            ProcessSampleResult(
                sample_id=result.sample_id,
                succeeded=result.succeeded,
                reason_code=result.reason_code,
            )
            for result in results
        ],
    )


@router.get("/samples/{sample_id}/status", response_model=SampleProcessingStatusRead)
async def get_sample_processing_status(
    sample_id: uuid.UUID,
    admin: AdminUser,
    session: Session,
) -> SampleProcessingStatusRead:
    """Safe processing status for one sample — never the embedding itself."""
    sample = await BiometricSampleRepository(session).get_by_id(sample_id)
    if sample is None:
        raise EnrollmentSampleNotFoundError()
    return SampleProcessingStatusRead(
        sample_id=sample.id,
        processing_state=sample.processing_state.value,
        processing_started_at=sample.processing_started_at,
        processing_completed_at=sample.processing_completed_at,
        failure_reason_code=sample.processing_failure_reason_code,
    )


@router.get("/health", response_model=FaceRecognitionHealthRead)
async def get_health(admin: AdminUser) -> FaceRecognitionHealthRead:
    """Provider/model readiness — never runs recognition against a real image.

    See ``app.modules.face_recognition.health``'s module docstring.

    Stage 3 correction (finding 3): ``get_face_recognition_health`` can
    perform blocking model-file I/O (checksum computation, loading a
    YuNet/dlib model into memory for the first time) via each
    provider's ``is_available()`` — offloaded via ``asyncio.to_thread``
    so a cold-start health check cannot block this worker's event loop.
    """
    settings = get_settings()
    health = await asyncio.to_thread(get_face_recognition_health, settings)
    return FaceRecognitionHealthRead(
        overall_status=health.overall_status,
        detector=ProviderHealthRead(
            provider_name=health.detector.provider_name,
            status=health.detector.status,
            detail=health.detector.detail,
        ),
        embedder=ProviderHealthRead(
            provider_name=health.embedder.provider_name,
            status=health.embedder.status,
            detail=health.embedder.detail,
        ),
    )


def _validate_and_embed_probe_sync(
    data: bytes, *, settings: Settings, declared_content_type: str | None
) -> EmbeddingVector:
    """The synchronous half of one match-probe request — decoded-content
    validation (Stage 3 correction finding 5) followed by detect -> align ->
    embed (finding 3's offload target). Both are CPU/IO-bound and must run
    off the event loop; bundled into one function so ``match_probe`` below
    can offload them with a single ``asyncio.to_thread`` call, exactly
    mirroring ``SampleProcessingService._load_and_embed_sync``.

    Raises a ``MatchProbeImage*Error`` (validation) or a
    ``FaceRecognitionError`` subclass (detection/alignment/embedding) —
    both are already sanitized, generic ``AppError``s; nothing here needs
    to catch and re-wrap them again.
    """
    validated: ValidatedProbeImage = validate_probe_image_bytes(
        data, settings=settings, declared_content_type=declared_content_type
    )
    with Image.open(BytesIO(data)) as image:
        rgb_image = image.convert("RGB")
        array = np.asarray(rgb_image, dtype=np.uint8)
    del validated  # metadata only used for validation; the array above is re-decoded fresh
    decoded_image = ndarray_to_decoded_image(array, color_format="rgb")
    return detect_align_embed(decoded_image, settings=settings)


def _validate_and_embed_attendance_sync(
    data: bytes, *, settings: Settings, declared_content_type: str | None
) -> list[EmbeddingVector]:
    """Validate once, embed every detected face, and retain no image data."""
    validate_probe_image_bytes(data, settings=settings, declared_content_type=declared_content_type)
    with Image.open(BytesIO(data)) as image:
        rgb_image = image.convert("RGB")
        array = np.asarray(rgb_image, dtype=np.uint8)
    decoded_image = ndarray_to_decoded_image(array, color_format="rgb")
    return detect_align_embed_many(decoded_image, settings=settings)


@router.post("/match-probe", response_model=MatchProbeResult)
async def match_probe(
    admin: AdminUser,
    session: Session,
    request: Request,
    file: Annotated[UploadFile, File(description="A single still image (JPEG/PNG/WEBP).")],
    candidate_student_profile_ids: Annotated[
        list[uuid.UUID],
        Form(
            description=(
                "Explicit, non-empty list of student profile IDs to match against. "
                "There is no way to match against every enrolled student at once."
            )
        ),
    ],
) -> MatchProbeResult:
    """Validate the detect -> align -> embed -> match pipeline against an ad hoc image.

    Diagnostic/validation only — see this module's docstring, "Stage
    boundary". Requires at least one candidate ID; raises
    ``CandidateScopeRequiredError`` (400) otherwise.

    Stage 3 v3 correction: the empty-scope check below is
    ``MatchingService.ensure_candidate_scope`` itself (not a separate,
    duplicate check) so a real HTTP request with an empty scope writes
    the exact same ``BLOCKED`` audit row a direct caller of
    ``MatchingService.match_probe`` would get — a v2 regression where
    this endpoint's own inline pre-check ran *before* any
    ``MatchingService`` was even constructed, silently bypassing that
    audit for every real request. Checked before any file
    reading/validation/inference happens, so an empty scope never
    triggers that work either. (A request FastAPI itself rejects during
    request parsing — e.g. a malformed multipart body — never reaches
    this function at all, and so cannot create an application audit row;
    that is a framework-level rejection, not one this endpoint's own
    logic can observe or record.)

    The uploaded image is validated to the same decoded-content
    protection class as Stage 2 enrollment uploads (decompression-bomb
    guard, max pixels/dimensions, JPEG/PNG/WEBP allowlist, animated-
    image rejection, full decode verification — see
    ``app.modules.face_recognition.match_probe_validation``) before
    ever reaching the detector.
    """
    settings = get_settings()
    matching_service = MatchingService(session, settings=settings)
    request_id = _request_id(request)

    await matching_service.ensure_candidate_scope(
        candidate_student_profile_ids=list(candidate_student_profile_ids),
        actor=admin,
        request_id=request_id,
    )

    data = await file.read(_MAX_PROBE_IMAGE_BYTES + 1)
    declared_content_type = file.content_type
    await file.close()
    if len(data) > _MAX_PROBE_IMAGE_BYTES:
        raise MatchProbeImageTooLargeError(_MAX_PROBE_IMAGE_BYTES)

    # Stage 3 correction (finding 3): validation + detect -> align ->
    # embed is synchronous, CPU/IO-bound work — never called directly on
    # the event loop. See ``_validate_and_embed_probe_sync``.
    probe_embedding = await asyncio.to_thread(
        _validate_and_embed_probe_sync,
        data,
        settings=settings,
        declared_content_type=declared_content_type,
    )

    outcome = await matching_service.match_probe(
        probe_embedding=probe_embedding,
        candidate_student_profile_ids=list(candidate_student_profile_ids),
        actor=admin,
        request_id=request_id,
    )
    return MatchProbeResult(
        status=outcome.status,
        matched_student_profile_id=outcome.matched_student_profile_id,
        best_similarity=outcome.best_similarity,
        runner_up_similarity=outcome.runner_up_similarity,
    )


@router.post(
    "/attendance/attempts",
    response_model=RecognitionAttendanceAttemptRead,
)
async def create_recognition_attendance_attempt(
    current_user: AdminOrTeacher,
    session: Session,
    request: Request,
    classroom_id: Annotated[uuid.UUID, Form()],
    subject_id: Annotated[uuid.UUID, Form()],
    attendance_date: Annotated[date, Form()],
    file: Annotated[UploadFile, File(description="A single still image (JPEG/PNG/WEBP).")],
) -> RecognitionAttendanceAttemptRead:
    """Recognize only within an authorized classroom roster."""
    settings = get_settings()
    service = RecognitionAttendanceService(session, settings=settings)
    request_id = _request_id(request)

    # Authorization and roster derivation precede even reading the upload,
    # preventing an unrelated teacher from using inference as an oracle.
    scope = await service.resolve_authorized_scope(
        current_user=current_user,
        classroom_id=classroom_id,
        subject_id=subject_id,
        attendance_date=attendance_date,
        request_id=request_id,
    )

    data = await file.read(_MAX_PROBE_IMAGE_BYTES + 1)
    declared_content_type = file.content_type
    await file.close()
    if len(data) > _MAX_PROBE_IMAGE_BYTES:
        raise MatchProbeImageTooLargeError(_MAX_PROBE_IMAGE_BYTES)

    probe_embedding = await asyncio.to_thread(
        _validate_and_embed_probe_sync,
        data,
        settings=settings,
        declared_content_type=declared_content_type,
    )
    outcome = await service.create_attempt(
        current_user=current_user,
        scope=scope,
        probe_embedding=probe_embedding,
        request_id=request_id,
    )
    return RecognitionAttendanceAttemptRead(
        attempt_id=outcome.attempt_id,
        classroom_id=outcome.classroom_id,
        subject_id=outcome.subject_id,
        attendance_date=outcome.attendance_date,
        decision=outcome.decision,
        matched_student_profile_id=outcome.matched_student_profile_id,
        attendance_record_id=outcome.attendance_record_id,
        requires_confirmation=True,
    )


@router.post(
    "/attendance/reviews",
    response_model=RecognitionAttendanceReviewRead,
)
async def create_recognition_attendance_review(
    current_user: AdminOrTeacher,
    session: Session,
    request: Request,
    classroom_id: Annotated[uuid.UUID, Form()],
    subject_id: Annotated[uuid.UUID, Form()],
    attendance_date: Annotated[date, Form()],
    file: Annotated[UploadFile, File(description="A still classroom image (JPEG/PNG/WEBP).")],
) -> RecognitionAttendanceReviewRead:
    """Return bounded multi-face proposals; never write attendance."""
    settings = get_settings()
    service = RecognitionAttendanceService(session, settings=settings)
    request_id = _request_id(request)
    scope = await service.resolve_authorized_scope(
        current_user=current_user,
        classroom_id=classroom_id,
        subject_id=subject_id,
        attendance_date=attendance_date,
        request_id=request_id,
    )
    data = await file.read(settings.MAX_ATTENDANCE_IMAGE_BYTES + 1)
    declared_content_type = file.content_type
    await file.close()
    if len(data) > settings.MAX_ATTENDANCE_IMAGE_BYTES:
        raise MatchProbeImageTooLargeError(settings.MAX_ATTENDANCE_IMAGE_BYTES)
    embeddings = await asyncio.to_thread(
        _validate_and_embed_attendance_sync,
        data,
        settings=settings,
        declared_content_type=declared_content_type,
    )
    outcome = await service.create_review(
        current_user=current_user,
        scope=scope,
        probe_embeddings=embeddings,
        request_id=request_id,
    )
    return RecognitionAttendanceReviewRead(
        review_id=outcome.review_id,
        classroom_id=outcome.classroom_id,
        subject_id=outcome.subject_id,
        attendance_date=outcome.attendance_date,
        face_count=outcome.face_count,
        proposals=[
            RecognitionAttendanceProposalRead(
                attempt_id=proposal.attempt_id,
                face_index=proposal.face_index,
                decision=proposal.decision,
                matched_student_profile_id=proposal.matched_student_profile_id,
                best_similarity=proposal.best_similarity,
                is_duplicate=proposal.is_duplicate,
            )
            for proposal in outcome.proposals
        ],
    )


@router.post(
    "/attendance/reviews/{review_id}/confirm",
    response_model=RecognitionAttendanceReviewConfirmationRead,
)
async def confirm_recognition_attendance_review(
    review_id: uuid.UUID,
    payload: RecognitionAttendanceReviewConfirmationRequest,
    current_user: AdminOrTeacher,
    session: Session,
    request: Request,
) -> RecognitionAttendanceReviewConfirmationRead:
    """Persist only explicitly reviewed present/absent statuses."""
    outcome = await RecognitionAttendanceService(session).confirm_review(
        current_user=current_user,
        review_id=review_id,
        records=[
            BulkAttendanceRecordIn(
                student_profile_id=record.student_profile_id,
                status=record.status,
            )
            for record in payload.records
        ],
        request_id=_request_id(request),
    )
    return RecognitionAttendanceReviewConfirmationRead(
        review_id=outcome.review_id,
        attendance_record_ids=list(outcome.attendance_record_ids),
        confirmed_records=[
            {
                "student_profile_id": student_id,
                "status": status,
            }
            for student_id, status in outcome.confirmed_records
        ],
    )


@router.post(
    "/attendance/attempts/{attempt_id}/confirm",
    response_model=RecognitionAttendanceConfirmationRead,
)
async def confirm_recognition_attendance_attempt(
    attempt_id: uuid.UUID,
    payload: RecognitionAttendanceConfirmationRequest,
    current_user: AdminOrTeacher,
    session: Session,
    request: Request,
) -> RecognitionAttendanceConfirmationRead:
    """Explicitly confirm a single-face proposal (including FOUND)."""
    outcome = await RecognitionAttendanceService(session).confirm_attempt(
        current_user=current_user,
        attempt_id=attempt_id,
        student_profile_id=payload.student_profile_id,
        request_id=_request_id(request),
    )
    return RecognitionAttendanceConfirmationRead(
        attempt_id=outcome.attempt_id,
        decision=outcome.decision,
        confirmed_student_profile_id=outcome.confirmed_student_profile_id,
        attendance_record_id=outcome.attendance_record_id,
    )
