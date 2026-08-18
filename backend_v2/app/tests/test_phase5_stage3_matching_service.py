"""DB-backed tests for ``app.modules.face_recognition.matching_service.MatchingService``.

Same DB-backed conventions as
``app.tests.test_phase5_stage3_processing_service`` (real Stage 2 HTTP
enrollment + fake detector/embedder providers, skips cleanly without a
reachable Postgres test database). Seeds real, processed embeddings via
``SampleProcessingService`` (already covered by its own test file) so
these tests exercise ``MatchingService``'s own orchestration —
candidate-scope enforcement and the repository's live-sample filtering
— against real persisted rows, not synthetic candidate lists.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.biometric_enrollment.repository import BiometricSampleRepository
from app.modules.face_recognition.domain import MatchStatus
from app.modules.face_recognition.errors import CandidateScopeRequiredError
from app.modules.face_recognition.matching_service import MatchingService
from app.modules.face_recognition.processing_service import SampleProcessingService
from app.tests.phase5_stage2_http_helpers import (
    make_jpeg_bytes,
    seed_enrollment_scope,
    upload_sample,
)
from app.tests.phase5_stage3_helpers import (
    FakeFaceDetector,
    FakeFaceEmbedder,
    make_detected_face,
    make_unit_embedding_vector,
    patch_providers,
)


class _SettingsLike:
    def __init__(
        self, *, threshold: float = 0.5, ambiguous_margin: float = 0.05, dimension: int = 128
    ) -> None:
        self.FACE_MATCH_THRESHOLD = threshold
        self.FACE_MATCH_AMBIGUOUS_MARGIN = ambiguous_margin
        self.FACE_EMBEDDING_DIMENSION = dimension


async def _seed_two_processed_students(client_db, db_session: AsyncSession, *, suffix: str):
    """Two students, each with one ACTIVE, PROCESSED sample with a distinct embedding."""
    scope = await seed_enrollment_scope(client_db, db_session, suffix=suffix)
    processing_service = SampleProcessingService(db_session)
    detector = FakeFaceDetector(results=[[make_detected_face()]])

    upload_1 = await upload_sample(
        client_db,
        student_profile_id=scope["student_profile_1"]["id"],
        user=scope["admin"],
        content=make_jpeg_bytes(color=(1, 1, 1)),
    )
    sample_1_id = uuid.UUID(upload_1.json()["id"])
    embedder_1 = FakeFaceEmbedder(seed=1.0)
    with patch_providers(detector, embedder_1):
        result_1 = await processing_service.process_sample(
            sample_id=sample_1_id, actor=scope["admin"]
        )
    assert result_1.succeeded is True

    upload_2 = await upload_sample(
        client_db,
        student_profile_id=scope["student_profile_2"]["id"],
        user=scope["admin"],
        content=make_jpeg_bytes(color=(2, 2, 2)),
    )
    sample_2_id = uuid.UUID(upload_2.json()["id"])
    embedder_2 = FakeFaceEmbedder(seed=50.0)
    with patch_providers(detector, embedder_2):
        result_2 = await processing_service.process_sample(
            sample_id=sample_2_id, actor=scope["admin"]
        )
    assert result_2.succeeded is True

    return scope, sample_1_id, sample_2_id


async def test_match_probe_requires_non_empty_candidate_scope(
    client_db, db_session: AsyncSession
) -> None:
    scope, _sample_1_id, _sample_2_id = await _seed_two_processed_students(
        client_db, db_session, suffix="match1"
    )
    service = MatchingService(db_session, settings=_SettingsLike())
    probe = make_unit_embedding_vector(seed=1.0)

    with pytest.raises(CandidateScopeRequiredError):
        await service.match_probe(
            probe_embedding=probe, candidate_student_profile_ids=[], actor=scope["admin"]
        )


async def test_match_probe_finds_matching_student_within_scope(
    client_db, db_session: AsyncSession
) -> None:
    scope, _sample_1_id, _sample_2_id = await _seed_two_processed_students(
        client_db, db_session, suffix="match2"
    )
    service = MatchingService(db_session, settings=_SettingsLike(threshold=0.5))
    probe = make_unit_embedding_vector(seed=1.0)  # matches student 1's embedding exactly

    outcome = await service.match_probe(
        probe_embedding=probe,
        candidate_student_profile_ids=[uuid.UUID(scope["student_profile_1"]["id"])],
        actor=scope["admin"],
    )

    assert outcome.status is MatchStatus.FOUND
    assert outcome.matched_student_profile_id == uuid.UUID(scope["student_profile_1"]["id"])


async def test_match_probe_excludes_students_outside_supplied_scope(
    client_db, db_session: AsyncSession
) -> None:
    """Student 1's embedding matches the probe exactly, but only student 2 is
    in scope — the result must reflect only student 2, never student 1."""
    scope, _sample_1_id, _sample_2_id = await _seed_two_processed_students(
        client_db, db_session, suffix="match3"
    )
    service = MatchingService(db_session, settings=_SettingsLike(threshold=0.9))
    probe = make_unit_embedding_vector(seed=1.0)  # would match student 1 exactly

    outcome = await service.match_probe(
        probe_embedding=probe,
        candidate_student_profile_ids=[uuid.UUID(scope["student_profile_2"]["id"])],
        actor=scope["admin"],
    )

    assert outcome.matched_student_profile_id != uuid.UUID(scope["student_profile_1"]["id"])
    # Student 2's embedding (seed=50.0) is unrelated to the probe -> below
    # a 0.9 threshold, so this resolves to UNKNOWN, never a false FOUND
    # against the out-of-scope student.
    assert outcome.status is MatchStatus.UNKNOWN


async def test_match_probe_excludes_quarantined_sample_embedding(
    client_db, db_session: AsyncSession
) -> None:
    scope, sample_1_id, _sample_2_id = await _seed_two_processed_students(
        client_db, db_session, suffix="match4"
    )
    samples = BiometricSampleRepository(db_session)
    sample_1 = await samples.get_by_id(sample_1_id)
    assert sample_1 is not None
    await samples.mark_quarantined(sample_1, quarantined_at=sample_1.created_at)

    service = MatchingService(db_session, settings=_SettingsLike(threshold=0.5))
    probe = make_unit_embedding_vector(seed=1.0)  # matches student 1's (now quarantined) embedding

    outcome = await service.match_probe(
        probe_embedding=probe,
        candidate_student_profile_ids=[uuid.UUID(scope["student_profile_1"]["id"])],
        actor=scope["admin"],
    )

    assert outcome.status is MatchStatus.UNKNOWN
    assert outcome.matched_student_profile_id is None


async def test_match_probe_only_uses_active_processed_embeddings(
    client_db, db_session: AsyncSession
) -> None:
    """A student with an ACTIVE sample that has NOT yet been processed
    contributes no candidate at all — not an error, just zero candidates
    for that student."""
    scope = await seed_enrollment_scope(client_db, db_session, suffix="match5")
    await upload_sample(
        client_db,
        student_profile_id=scope["student_profile_1"]["id"],
        user=scope["admin"],
        content=make_jpeg_bytes(),
    )  # uploaded but never processed -> PENDING_PROCESSING

    service = MatchingService(db_session, settings=_SettingsLike(threshold=0.0))
    probe = make_unit_embedding_vector(seed=1.0)

    outcome = await service.match_probe(
        probe_embedding=probe,
        candidate_student_profile_ids=[uuid.UUID(scope["student_profile_1"]["id"])],
        actor=scope["admin"],
    )

    assert outcome.status is MatchStatus.UNKNOWN
    assert outcome.best_similarity is None


async def test_match_probe_reports_ambiguous_between_two_in_scope_close_students(
    client_db, db_session: AsyncSession
) -> None:
    scope = await seed_enrollment_scope(client_db, db_session, suffix="match6")
    processing_service = SampleProcessingService(db_session)
    detector = FakeFaceDetector(results=[[make_detected_face()]])

    upload_1 = await upload_sample(
        client_db,
        student_profile_id=scope["student_profile_1"]["id"],
        user=scope["admin"],
        content=make_jpeg_bytes(color=(1, 1, 1)),
    )
    embedder_1 = FakeFaceEmbedder(seed=1.0)
    with patch_providers(detector, embedder_1):
        await processing_service.process_sample(
            sample_id=uuid.UUID(upload_1.json()["id"]), actor=scope["admin"]
        )

    upload_2 = await upload_sample(
        client_db,
        student_profile_id=scope["student_profile_2"]["id"],
        user=scope["admin"],
        content=make_jpeg_bytes(color=(2, 2, 2)),
    )
    # A second embedder that returns the SAME seed -> same vector -> ties
    # with student 1's embedding exactly, guaranteeing an ambiguous gap
    # of 0.0 regardless of the hash function's specific numeric output.
    embedder_2 = FakeFaceEmbedder(seed=1.0)
    with patch_providers(detector, embedder_2):
        await processing_service.process_sample(
            sample_id=uuid.UUID(upload_2.json()["id"]), actor=scope["admin"]
        )

    service = MatchingService(
        db_session, settings=_SettingsLike(threshold=0.5, ambiguous_margin=0.01)
    )
    probe = make_unit_embedding_vector(seed=1.0)

    outcome = await service.match_probe(
        probe_embedding=probe,
        candidate_student_profile_ids=[
            uuid.UUID(scope["student_profile_1"]["id"]),
            uuid.UUID(scope["student_profile_2"]["id"]),
        ],
        actor=scope["admin"],
    )

    assert outcome.status is MatchStatus.AMBIGUOUS
    assert outcome.matched_student_profile_id is None
    assert outcome.best_similarity is not None
    assert outcome.runner_up_similarity is not None
