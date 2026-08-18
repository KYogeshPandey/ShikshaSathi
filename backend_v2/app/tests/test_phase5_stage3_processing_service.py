"""DB-backed tests for ``app.modules.face_recognition.processing_service.SampleProcessingService``.

Requires a reachable Postgres test database (see
``app.tests.conftest.db_session`` — skips cleanly otherwise, matching
every other DB-backed test file in this suite). Real Stage 2 HTTP
enrollment endpoints (via ``client_db`` + ``seed_enrollment_scope``/
``upload_sample``) create genuine ``ACTIVE`` samples with real files on
disk; ``app.modules.face_recognition.pipeline.get_detector``/
``get_embedder`` are monkeypatched to ``FakeFaceDetector``/
``FakeFaceEmbedder`` (see ``app.tests.phase5_stage3_helpers``) so no
real model file or real inference is required — only this module's own
lifecycle/transaction logic is under test.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.biometric_enrollment.models import RecognitionProcessingState, SampleStatus
from app.modules.biometric_enrollment.repository import BiometricSampleRepository
from app.modules.face_recognition.errors import SampleNotEligibleForProcessingError
from app.modules.face_recognition.processing_service import (
    REASON_ZERO_FACES,
    SampleProcessingService,
)
from app.modules.face_recognition.repository import BiometricEmbeddingRepository
from app.tests.phase5_stage2_http_helpers import (
    make_jpeg_bytes,
    seed_enrollment_scope,
    upload_sample,
)
from app.tests.phase5_stage3_helpers import (
    FakeFaceDetector,
    FakeFaceEmbedder,
    make_detected_face,
    patch_providers,
    seed_active_sample_direct,
)


async def test_process_sample_transitions_pending_to_processed(
    client_db, db_session: AsyncSession
) -> None:
    scope = await seed_enrollment_scope(client_db, db_session, suffix="proc1")
    upload_response = await upload_sample(
        client_db,
        student_profile_id=scope["student_profile_1"]["id"],
        user=scope["admin"],
        content=make_jpeg_bytes(),
    )
    sample_id = uuid.UUID(upload_response.json()["id"])

    detector = FakeFaceDetector(results=[[make_detected_face()]])
    embedder = FakeFaceEmbedder(seed=1.0)
    service = SampleProcessingService(db_session)

    with patch_providers(detector, embedder):
        result = await service.process_sample(sample_id=sample_id, actor=scope["admin"])

    assert result.succeeded is True
    assert result.reason_code is None

    samples = BiometricSampleRepository(db_session)
    sample = await samples.get_by_id(sample_id)
    assert sample is not None
    assert sample.processing_state is RecognitionProcessingState.PROCESSED
    assert sample.processing_started_at is not None
    assert sample.processing_completed_at is not None
    assert sample.processing_failure_reason_code is None

    embeddings = BiometricEmbeddingRepository(db_session)
    embedding = await embeddings.get_active_for_sample(sample_id)
    assert embedding is not None
    assert embedding.is_active is True
    assert embedding.embedding_dimension == 128
    assert len(embedding.embedding_values) == 128
    assert embedding.provider_name == "dlib_resnet_v1_local"
    assert embedding.model_identifier == "dlib_face_recognition_resnet_model_v1"
    assert embedding.model_version == "v1"
    assert embedding.created_at is not None
    # No FACE_EMBEDDER_MODEL_PATH configured in this test environment ->
    # no checksum to record.
    assert embedding.model_artifact_checksum is None


async def test_process_sample_zero_faces_marks_processing_failed(
    client_db, db_session: AsyncSession
) -> None:
    scope = await seed_enrollment_scope(client_db, db_session, suffix="proc2")
    upload_response = await upload_sample(
        client_db,
        student_profile_id=scope["student_profile_1"]["id"],
        user=scope["admin"],
        content=make_jpeg_bytes(),
    )
    sample_id = uuid.UUID(upload_response.json()["id"])

    detector = FakeFaceDetector(results=[[]])  # zero faces
    embedder = FakeFaceEmbedder()
    service = SampleProcessingService(db_session)

    with patch_providers(detector, embedder):
        result = await service.process_sample(sample_id=sample_id, actor=scope["admin"])

    assert result.succeeded is False
    assert result.reason_code == REASON_ZERO_FACES

    samples = BiometricSampleRepository(db_session)
    sample = await samples.get_by_id(sample_id)
    assert sample is not None
    assert sample.processing_state is RecognitionProcessingState.PROCESSING_FAILED
    assert sample.processing_failure_reason_code == REASON_ZERO_FACES

    embeddings = BiometricEmbeddingRepository(db_session)
    assert await embeddings.get_active_for_sample(sample_id) is None


async def test_retry_sample_after_failure_succeeds(client_db, db_session: AsyncSession) -> None:
    scope = await seed_enrollment_scope(client_db, db_session, suffix="proc3")
    upload_response = await upload_sample(
        client_db,
        student_profile_id=scope["student_profile_1"]["id"],
        user=scope["admin"],
        content=make_jpeg_bytes(),
    )
    sample_id = uuid.UUID(upload_response.json()["id"])
    service = SampleProcessingService(db_session)

    failing_detector = FakeFaceDetector(results=[[]])
    embedder = FakeFaceEmbedder(seed=2.0)
    with patch_providers(failing_detector, embedder):
        first_result = await service.process_sample(sample_id=sample_id, actor=scope["admin"])
    assert first_result.succeeded is False

    working_detector = FakeFaceDetector(results=[[make_detected_face()]])
    with patch_providers(working_detector, embedder):
        retry_result = await service.retry_sample(sample_id=sample_id, actor=scope["admin"])

    assert retry_result.succeeded is True
    samples = BiometricSampleRepository(db_session)
    sample = await samples.get_by_id(sample_id)
    assert sample is not None
    assert sample.processing_state is RecognitionProcessingState.PROCESSED
    assert sample.processing_failure_reason_code is None

    embeddings = BiometricEmbeddingRepository(db_session)
    embedding = await embeddings.get_active_for_sample(sample_id)
    assert embedding is not None


async def test_retry_sample_rejects_non_failed_sample(client_db, db_session: AsyncSession) -> None:
    scope = await seed_enrollment_scope(client_db, db_session, suffix="proc4")
    upload_response = await upload_sample(
        client_db,
        student_profile_id=scope["student_profile_1"]["id"],
        user=scope["admin"],
        content=make_jpeg_bytes(),
    )
    sample_id = uuid.UUID(upload_response.json()["id"])
    service = SampleProcessingService(db_session)

    with pytest.raises(SampleNotEligibleForProcessingError):
        await service.retry_sample(sample_id=sample_id, actor=scope["admin"])


async def test_process_sample_rejects_already_processed_sample(
    client_db, db_session: AsyncSession
) -> None:
    scope = await seed_enrollment_scope(client_db, db_session, suffix="proc5")
    upload_response = await upload_sample(
        client_db,
        student_profile_id=scope["student_profile_1"]["id"],
        user=scope["admin"],
        content=make_jpeg_bytes(),
    )
    sample_id = uuid.UUID(upload_response.json()["id"])
    service = SampleProcessingService(db_session)
    detector = FakeFaceDetector(results=[[make_detected_face()]])
    embedder = FakeFaceEmbedder()

    with patch_providers(detector, embedder):
        await service.process_sample(sample_id=sample_id, actor=scope["admin"])

    with pytest.raises(SampleNotEligibleForProcessingError):
        await service.process_sample(sample_id=sample_id, actor=scope["admin"])


async def test_process_sample_rejects_non_active_sample(
    client_db, db_session: AsyncSession
) -> None:
    """A quarantined/deleted/replacement-pending sample must never be processed."""
    scope = await seed_enrollment_scope(client_db, db_session, suffix="proc6")
    upload_response = await upload_sample(
        client_db,
        student_profile_id=scope["student_profile_1"]["id"],
        user=scope["admin"],
        content=make_jpeg_bytes(),
    )
    sample_id = uuid.UUID(upload_response.json()["id"])

    samples = BiometricSampleRepository(db_session)
    sample = await samples.get_by_id(sample_id)
    assert sample is not None
    await samples.mark_quarantined(sample, quarantined_at=sample.created_at)

    service = SampleProcessingService(db_session)
    with pytest.raises(SampleNotEligibleForProcessingError):
        await service.process_sample(sample_id=sample_id, actor=scope["admin"])


async def test_db_failure_during_persistence_leaves_no_half_active_embedding(
    client_db, db_session: AsyncSession
) -> None:
    """A DB-layer failure while persisting a successful result must not leave
    a committed embedding row, and must not leave the sample marked PROCESSED."""
    scope = await seed_enrollment_scope(client_db, db_session, suffix="proc7")
    upload_response = await upload_sample(
        client_db,
        student_profile_id=scope["student_profile_1"]["id"],
        user=scope["admin"],
        content=make_jpeg_bytes(),
    )
    sample_id = uuid.UUID(upload_response.json()["id"])

    detector = FakeFaceDetector(results=[[make_detected_face()]])
    embedder = FakeFaceEmbedder()
    service = SampleProcessingService(db_session)

    with (
        patch_providers(detector, embedder),
        patch(
            "app.modules.face_recognition.processing_service."
            "BiometricEmbeddingRepository.create_active",
            side_effect=RuntimeError("simulated database failure"),
        ),
        pytest.raises(RuntimeError, match="simulated database failure"),
    ):
        await service.process_sample(sample_id=sample_id, actor=scope["admin"])

    # Query fresh state (the session was rolled back by service_transaction).
    samples = BiometricSampleRepository(db_session)
    sample = await samples.get_by_id(sample_id)
    assert sample is not None
    assert sample.processing_state is not RecognitionProcessingState.PROCESSED

    embeddings = BiometricEmbeddingRepository(db_session)
    assert await embeddings.get_active_for_sample(sample_id) is None


async def test_replacement_sample_does_not_inherit_old_embedding(
    client_db, db_session: AsyncSession
) -> None:
    scope = await seed_enrollment_scope(client_db, db_session, suffix="proc8")
    first_upload = await upload_sample(
        client_db,
        student_profile_id=scope["student_profile_1"]["id"],
        user=scope["admin"],
        content=make_jpeg_bytes(color=(10, 10, 10)),
    )
    first_sample_id = uuid.UUID(first_upload.json()["id"])

    service = SampleProcessingService(db_session)
    detector = FakeFaceDetector(results=[[make_detected_face()]])
    old_embedder = FakeFaceEmbedder(seed=1.0)
    with patch_providers(detector, old_embedder):
        first_result = await service.process_sample(sample_id=first_sample_id, actor=scope["admin"])
    assert first_result.succeeded is True

    embeddings = BiometricEmbeddingRepository(db_session)
    old_embedding = await embeddings.get_active_for_sample(first_sample_id)
    assert old_embedding is not None
    old_values = list(old_embedding.embedding_values)

    replace_response = await upload_sample(
        client_db,
        student_profile_id=scope["student_profile_1"]["id"],
        user=scope["admin"],
        content=make_jpeg_bytes(color=(200, 200, 200)),
        method="put",
    )
    new_sample_id = uuid.UUID(replace_response.json()["new_sample"]["id"])
    assert new_sample_id != first_sample_id

    # The new sample starts fresh: no embedding until it is processed.
    assert await embeddings.get_active_for_sample(new_sample_id) is None

    samples = BiometricSampleRepository(db_session)
    old_sample = await samples.get_by_id(first_sample_id)
    assert old_sample is not None
    assert old_sample.status is SampleStatus.DELETED

    new_embedder = FakeFaceEmbedder(seed=9.0)
    with patch_providers(detector, new_embedder):
        second_result = await service.process_sample(sample_id=new_sample_id, actor=scope["admin"])
    assert second_result.succeeded is True

    new_embedding = await embeddings.get_active_for_sample(new_sample_id)
    assert new_embedding is not None
    assert list(new_embedding.embedding_values) != old_values

    # The old sample's own embedding row is untouched (still is_active on
    # ITS row) — but it is no longer reachable through the
    # candidate-matching query, because its sample is no longer ACTIVE.
    # This IS the "no inheritance/reuse" guarantee: the query only ever
    # returns the live sample's own, freshly-computed embedding for this
    # student, never the retired one.
    candidates = await embeddings.list_active_for_students(
        [uuid.UUID(scope["student_profile_1"]["id"])]
    )
    assert len(candidates) == 1
    assert list(candidates[0].embedding_values) == list(new_embedding.embedding_values)
    assert list(candidates[0].embedding_values) != old_values


async def test_process_pending_batch_is_bounded(client_db, db_session: AsyncSession) -> None:
    scope = await seed_enrollment_scope(client_db, db_session, suffix="proc9")
    student_profile_ids = [scope["student_profile_1"]["id"], scope["student_profile_2"]["id"]]
    # seed_enrollment_scope only creates two students; upload one sample
    # each, giving exactly 2 PENDING_PROCESSING samples to draw from.
    for profile_id in student_profile_ids:
        await upload_sample(
            client_db,
            student_profile_id=profile_id,
            user=scope["admin"],
            content=make_jpeg_bytes(),
        )

    detector = FakeFaceDetector(results=[[make_detected_face()]])
    embedder = FakeFaceEmbedder()
    service = SampleProcessingService(db_session)

    with patch_providers(detector, embedder):
        results = await service.process_pending_batch(actor=scope["admin"], limit=1)

    assert len(results) == 1
    assert results[0].succeeded is True


async def test_process_sample_rejects_failed_sample_and_only_retry_sample_accepts_it(
    client_db, db_session: AsyncSession
) -> None:
    """Stage 3 correction, finding 2: ``process_sample`` must reject a
    ``PROCESSING_FAILED`` sample exactly as firmly as an already-``PROCESSED``
    one — only ``retry_sample`` may act on it. Regression test for the
    Stage 3 audit finding that ``process_sample`` was previously only
    checking for ``processed``, silently letting a ``PROCESSING_FAILED``
    sample straight back through as if it were a fresh attempt.

    Seeds the ACTIVE sample directly via
    ``app.tests.phase5_stage3_helpers.seed_active_sample_direct`` (ORM/
    repository layer only) rather than through Stage 2's real HTTP upload
    endpoint, to keep this Stage 3 regression test independent of the
    pre-existing, out-of-scope Stage 2 ``MissingGreenlet`` defect in
    ``BiometricEnrollmentService.create_sample`` (see this module's
    docstring and ``docs/HANDOVER_PHASE_5_STAGE_3.md``).
    """
    scope = await seed_enrollment_scope(client_db, db_session, suffix="proc10")
    sample_id = await seed_active_sample_direct(
        db_session,
        student_profile_id=uuid.UUID(scope["student_profile_1"]["id"]),
        created_by_user_id=scope["admin"].id,
    )
    service = SampleProcessingService(db_session)

    # Step 1: first attempt fails (zero faces detected) -> PROCESSING_FAILED.
    failing_detector = FakeFaceDetector(results=[[]])
    embedder = FakeFaceEmbedder()
    with patch_providers(failing_detector, embedder):
        first_result = await service.process_sample(sample_id=sample_id, actor=scope["admin"])
    assert first_result.succeeded is False
    assert first_result.reason_code == REASON_ZERO_FACES

    samples = BiometricSampleRepository(db_session)
    sample = await samples.get_by_id(sample_id)
    assert sample is not None
    assert sample.processing_state is RecognitionProcessingState.PROCESSING_FAILED

    # Step 2: process_sample() must reject the now-PROCESSING_FAILED sample,
    # with a reason distinct from "already processed".
    with pytest.raises(SampleNotEligibleForProcessingError) as exc_info:
        await service.process_sample(sample_id=sample_id, actor=scope["admin"])
    assert exc_info.value.details["reason"] == "sample_already_failed_use_retry"

    # Step 3: retry_sample() is the only valid path for a failed sample,
    # and succeeds once the underlying condition is fixed.
    succeeding_detector = FakeFaceDetector(results=[[make_detected_face()]])
    with patch_providers(succeeding_detector, embedder):
        retry_result = await service.retry_sample(sample_id=sample_id, actor=scope["admin"])
    assert retry_result.succeeded is True
    assert retry_result.reason_code is None

    sample_after_retry = await samples.get_by_id(sample_id)
    assert sample_after_retry is not None
    assert sample_after_retry.processing_state is RecognitionProcessingState.PROCESSED

    # And now that it is PROCESSED, process_sample() rejects it for the
    # *other* reason (not conflated with the failed-state rejection above).
    with pytest.raises(SampleNotEligibleForProcessingError) as exc_info_processed:
        await service.process_sample(sample_id=sample_id, actor=scope["admin"])
    assert exc_info_processed.value.details["reason"] == "sample_already_processed"

    # And retry_sample() itself now refuses a PROCESSED (not-failed) sample.
    with pytest.raises(SampleNotEligibleForProcessingError) as exc_info_retry:
        await service.retry_sample(sample_id=sample_id, actor=scope["admin"])
    assert exc_info_retry.value.details["reason"] == "sample_not_in_failed_state"
