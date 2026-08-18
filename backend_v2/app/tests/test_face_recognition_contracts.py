"""Tests for the Phase 5 Stage 1 face-recognition contracts and protocols.

No detector/embedder/matcher *implementation* exists in this file (see
``app/modules/face_recognition/providers/`` for the real Stage 3
adapters); every test here exercises only the typed value objects
(``app.modules.face_recognition.domain``) and the ``Protocol``
interfaces (``app.modules.face_recognition.protocols``) directly.
Nothing in this file requires a model file, GPU, camera, or network
access — the fakes defined below are deterministic, in-memory test
doubles used only for protocol-conformance testing (Stage 1 brief,
instruction 4), not a preview of Stage 3's real provider math.

**Stage 3 note:** ``_FakeLookupFaceMatcher.match`` below takes a
``candidates`` parameter, matching the Stage 3 refinement to
``FaceMatcher.match`` (see ``protocols.py``'s own docstring on why this
was an additive, not a breaking, change to a contract Stage 1 left
deliberately open). This file was originally written against Stage 1's
one-argument signature and is updated here to keep exercising the
*current* protocol, not a stale one.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Sequence

import pytest
from pydantic import ValidationError

from app.modules.face_recognition.domain import (
    BoundingBox,
    CandidateEmbedding,
    DecodedImage,
    DetectedFace,
    EmbeddingVector,
    ImageDimensions,
    MatchCandidate,
    MatchResult,
    MatchStatus,
    NormalizedFaceInput,
    ProviderHealth,
    ProviderStatus,
    validate_embedding_dimension,
)
from app.modules.face_recognition.errors import InvalidEmbeddingDimensionError
from app.modules.face_recognition.protocols import FaceDetector, FaceEmbedder, FaceMatcher

# ---------------------------------------------------------------------------
# ImageDimensions
# ---------------------------------------------------------------------------


def test_valid_image_dimensions_are_accepted() -> None:
    dimensions = ImageDimensions(width_px=640, height_px=480)
    assert dimensions.width_px == 640
    assert dimensions.height_px == 480


@pytest.mark.parametrize(
    ("width_px", "height_px"),
    [(0, 480), (640, 0), (-1, 480), (640, -1), (10_001, 480), (640, 10_001)],
)
def test_invalid_image_dimensions_are_rejected(width_px: int, height_px: int) -> None:
    with pytest.raises(ValidationError):
        ImageDimensions(width_px=width_px, height_px=height_px)


# ---------------------------------------------------------------------------
# BoundingBox and DetectedFace (out-of-range boxes)
# ---------------------------------------------------------------------------


def test_valid_bounding_box_is_accepted() -> None:
    box = BoundingBox(x_px=10, y_px=20, width_px=100, height_px=120)
    assert box.right_px == 110
    assert box.bottom_px == 140


@pytest.mark.parametrize(
    ("x_px", "y_px", "width_px", "height_px"),
    [
        (-1, 0, 100, 100),  # negative x
        (0, -1, 100, 100),  # negative y
        (0, 0, 0, 100),  # zero width
        (0, 0, 100, 0),  # zero height
        (0, 0, -5, 100),  # negative width
        (0, 0, 100, -5),  # negative height
    ],
)
def test_invalid_bounding_box_is_rejected(
    x_px: int, y_px: int, width_px: int, height_px: int
) -> None:
    with pytest.raises(ValidationError):
        BoundingBox(x_px=x_px, y_px=y_px, width_px=width_px, height_px=height_px)


def test_detected_face_with_box_inside_image_is_accepted() -> None:
    dims = ImageDimensions(width_px=640, height_px=480)
    box = BoundingBox(x_px=100, y_px=100, width_px=200, height_px=200)
    face = DetectedFace(bounding_box=box, source_image_dimensions=dims, confidence=0.95)
    assert face.confidence == 0.95


def test_detected_face_with_out_of_range_box_is_rejected() -> None:
    dims = ImageDimensions(width_px=640, height_px=480)
    # Box extends past the right edge of the image (100 + 600 = 700 > 640).
    box = BoundingBox(x_px=100, y_px=100, width_px=600, height_px=200)
    with pytest.raises(ValidationError):
        DetectedFace(bounding_box=box, source_image_dimensions=dims, confidence=0.9)


def test_detected_face_with_box_exceeding_bottom_edge_is_rejected() -> None:
    dims = ImageDimensions(width_px=640, height_px=480)
    box = BoundingBox(x_px=0, y_px=400, width_px=100, height_px=200)
    with pytest.raises(ValidationError):
        DetectedFace(bounding_box=box, source_image_dimensions=dims, confidence=0.9)


@pytest.mark.parametrize("confidence", [-0.01, 1.01, -1.0, 2.0])
def test_detected_face_confidence_outside_zero_one_is_rejected(confidence: float) -> None:
    dims = ImageDimensions(width_px=640, height_px=480)
    box = BoundingBox(x_px=0, y_px=0, width_px=100, height_px=100)
    with pytest.raises(ValidationError):
        DetectedFace(bounding_box=box, source_image_dimensions=dims, confidence=confidence)


@pytest.mark.parametrize("confidence", [math.nan, math.inf, -math.inf])
def test_detected_face_confidence_rejects_non_finite_values(confidence: float) -> None:
    dims = ImageDimensions(width_px=640, height_px=480)
    box = BoundingBox(x_px=0, y_px=0, width_px=100, height_px=100)
    with pytest.raises(ValidationError):
        DetectedFace(bounding_box=box, source_image_dimensions=dims, confidence=confidence)


# ---------------------------------------------------------------------------
# DecodedImage / NormalizedFaceInput
# ---------------------------------------------------------------------------


def test_decoded_image_rejects_empty_pixel_data() -> None:
    dims = ImageDimensions(width_px=64, height_px=64)
    with pytest.raises(ValidationError):
        DecodedImage(dimensions=dims, pixel_data=b"")


def test_normalized_face_input_rejects_empty_pixel_data() -> None:
    dims = ImageDimensions(width_px=112, height_px=112)
    with pytest.raises(ValidationError):
        NormalizedFaceInput(dimensions=dims, pixel_data=b"")


def test_normalized_face_input_accepts_nonempty_pixel_data() -> None:
    dims = ImageDimensions(width_px=112, height_px=112)
    face_input = NormalizedFaceInput(dimensions=dims, pixel_data=b"\x00" * 16)
    assert face_input.dimensions.width_px == 112


# ---------------------------------------------------------------------------
# EmbeddingVector
# ---------------------------------------------------------------------------


def test_valid_embedding_vector_is_accepted() -> None:
    vector = EmbeddingVector(values=(0.1, 0.2, -0.3))
    assert vector.dimension == 3


def test_empty_embedding_vector_is_rejected() -> None:
    with pytest.raises(ValidationError):
        EmbeddingVector(values=())


def test_embedding_vector_with_nan_is_rejected() -> None:
    with pytest.raises(ValidationError):
        EmbeddingVector(values=(0.1, math.nan, 0.3))


def test_embedding_vector_with_infinity_is_rejected() -> None:
    with pytest.raises(ValidationError):
        EmbeddingVector(values=(0.1, math.inf, 0.3))
    with pytest.raises(ValidationError):
        EmbeddingVector(values=(0.1, -math.inf, 0.3))


def test_validate_embedding_dimension_passes_through_on_match() -> None:
    vector = EmbeddingVector(values=(1.0, 2.0, 3.0))
    result = validate_embedding_dimension(vector, expected_dimension=3)
    assert result is vector


def test_validate_embedding_dimension_raises_on_mismatch() -> None:
    vector = EmbeddingVector(values=(1.0, 2.0, 3.0))
    with pytest.raises(InvalidEmbeddingDimensionError) as exc_info:
        validate_embedding_dimension(vector, expected_dimension=128)
    assert exc_info.value.code == "FACE_EMBEDDING_DIMENSION_MISMATCH"


# ---------------------------------------------------------------------------
# MatchCandidate — confidence/distance (similarity) semantics
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("similarity", [-1.0, 0.0, 0.5, 1.0])
def test_valid_match_candidate_similarity_is_accepted(similarity: float) -> None:
    candidate = MatchCandidate(student_profile_id=uuid.uuid4(), similarity=similarity)
    assert candidate.similarity == similarity


@pytest.mark.parametrize("similarity", [-1.01, 1.01, 2.0, -5.0])
def test_match_candidate_similarity_outside_range_is_rejected(similarity: float) -> None:
    with pytest.raises(ValidationError):
        MatchCandidate(student_profile_id=uuid.uuid4(), similarity=similarity)


@pytest.mark.parametrize("similarity", [math.nan, math.inf, -math.inf])
def test_match_candidate_similarity_rejects_non_finite_values(similarity: float) -> None:
    with pytest.raises(ValidationError):
        MatchCandidate(student_profile_id=uuid.uuid4(), similarity=similarity)


# ---------------------------------------------------------------------------
# MatchResult — found / unknown / ambiguous
# ---------------------------------------------------------------------------


def test_match_result_found_is_valid_and_carries_the_matched_student() -> None:
    student_id = uuid.uuid4()
    candidate = MatchCandidate(student_profile_id=student_id, similarity=0.97)
    result = MatchResult.found(candidate)
    assert result.status is MatchStatus.FOUND
    assert result.matched_student_profile_id == student_id
    assert result.best_candidate is not None
    assert result.best_candidate.student_profile_id == student_id


def test_match_result_unknown_carries_no_matched_student() -> None:
    result = MatchResult.unknown()
    assert result.status is MatchStatus.UNKNOWN
    assert result.matched_student_profile_id is None
    assert result.runner_up_candidate is None


def test_match_result_unknown_may_carry_best_candidate_as_audit_context() -> None:
    below_threshold = MatchCandidate(student_profile_id=uuid.uuid4(), similarity=0.4)
    result = MatchResult.unknown(best_candidate=below_threshold)
    assert result.status is MatchStatus.UNKNOWN
    assert result.matched_student_profile_id is None
    assert result.best_candidate is below_threshold


def test_match_result_ambiguous_is_distinct_from_unknown_and_found() -> None:
    best = MatchCandidate(student_profile_id=uuid.uuid4(), similarity=0.92)
    runner_up = MatchCandidate(student_profile_id=uuid.uuid4(), similarity=0.905)
    result = MatchResult.ambiguous(best_candidate=best, runner_up_candidate=runner_up)
    assert result.status is MatchStatus.AMBIGUOUS
    assert result.status is not MatchStatus.UNKNOWN
    assert result.status is not MatchStatus.FOUND
    assert result.matched_student_profile_id is None
    assert result.best_candidate is best
    assert result.runner_up_candidate is runner_up


def test_match_result_found_requires_matched_student_and_best_candidate() -> None:
    with pytest.raises(ValidationError):
        MatchResult(status=MatchStatus.FOUND)


def test_match_result_found_matched_id_must_equal_best_candidate_id() -> None:
    candidate = MatchCandidate(student_profile_id=uuid.uuid4(), similarity=0.9)
    with pytest.raises(ValidationError):
        MatchResult(
            status=MatchStatus.FOUND,
            matched_student_profile_id=uuid.uuid4(),  # deliberately mismatched
            best_candidate=candidate,
        )


def test_match_result_non_found_must_not_set_matched_student() -> None:
    with pytest.raises(ValidationError):
        MatchResult(status=MatchStatus.UNKNOWN, matched_student_profile_id=uuid.uuid4())


def test_match_result_ambiguous_requires_both_candidates() -> None:
    best = MatchCandidate(student_profile_id=uuid.uuid4(), similarity=0.9)
    with pytest.raises(ValidationError):
        MatchResult(status=MatchStatus.AMBIGUOUS, best_candidate=best)


def test_match_result_unknown_must_not_set_runner_up() -> None:
    best = MatchCandidate(student_profile_id=uuid.uuid4(), similarity=0.4)
    runner_up = MatchCandidate(student_profile_id=uuid.uuid4(), similarity=0.39)
    with pytest.raises(ValidationError):
        MatchResult(status=MatchStatus.UNKNOWN, best_candidate=best, runner_up_candidate=runner_up)


def test_match_result_found_must_not_set_runner_up_candidate() -> None:
    student_id = uuid.uuid4()
    candidate = MatchCandidate(student_profile_id=student_id, similarity=0.97)
    other = MatchCandidate(student_profile_id=uuid.uuid4(), similarity=0.5)
    with pytest.raises(ValidationError):
        MatchResult(
            status=MatchStatus.FOUND,
            matched_student_profile_id=student_id,
            best_candidate=candidate,
            runner_up_candidate=other,
        )


def test_match_result_ambiguous_candidates_must_reference_different_students() -> None:
    same_student = uuid.uuid4()
    best = MatchCandidate(student_profile_id=same_student, similarity=0.92)
    runner_up = MatchCandidate(student_profile_id=same_student, similarity=0.90)
    with pytest.raises(ValidationError):
        MatchResult(
            status=MatchStatus.AMBIGUOUS, best_candidate=best, runner_up_candidate=runner_up
        )


def test_match_result_ambiguous_runner_up_must_not_outscore_best() -> None:
    best = MatchCandidate(student_profile_id=uuid.uuid4(), similarity=0.80)
    runner_up = MatchCandidate(student_profile_id=uuid.uuid4(), similarity=0.90)
    with pytest.raises(ValidationError):
        MatchResult(
            status=MatchStatus.AMBIGUOUS, best_candidate=best, runner_up_candidate=runner_up
        )


def test_match_result_ambiguous_accepts_equal_similarity_scores() -> None:
    # best_candidate.similarity must be >= runner_up_candidate.similarity;
    # equal scores are a valid (if maximally ambiguous) boundary case.
    best = MatchCandidate(student_profile_id=uuid.uuid4(), similarity=0.85)
    runner_up = MatchCandidate(student_profile_id=uuid.uuid4(), similarity=0.85)
    result = MatchResult.ambiguous(best_candidate=best, runner_up_candidate=runner_up)
    assert result.status is MatchStatus.AMBIGUOUS


# ---------------------------------------------------------------------------
# ProviderHealth
# ---------------------------------------------------------------------------


def test_provider_health_valid_states() -> None:
    for status in (ProviderStatus.READY, ProviderStatus.UNAVAILABLE, ProviderStatus.NOT_CONFIGURED):
        health = ProviderHealth(provider_name="server_side_local", status=status)
        assert health.status is status


def test_provider_health_rejects_blank_provider_name() -> None:
    with pytest.raises(ValidationError):
        ProviderHealth(provider_name="", status=ProviderStatus.READY)


def test_provider_health_rejects_whitespace_only_provider_name() -> None:
    with pytest.raises(ValidationError):
        ProviderHealth(provider_name="   \t  ", status=ProviderStatus.READY)


def test_provider_health_strips_surrounding_whitespace_from_provider_name() -> None:
    health = ProviderHealth(provider_name="  server_side_local  ", status=ProviderStatus.READY)
    assert health.provider_name == "server_side_local"


def test_provider_health_rejects_overlong_detail() -> None:
    with pytest.raises(ValidationError):
        ProviderHealth(
            provider_name="server_side_local",
            status=ProviderStatus.UNAVAILABLE,
            detail="x" * 201,
        )


# ---------------------------------------------------------------------------
# Protocol conformance — deterministic fakes, contract testing only
#
# These fakes are NOT a preview of Stage 3's real provider. They exist
# only to prove the Protocol boundary is usable and that a
# protocol-compatible object never needs to return an ORM instance
# (Stage 1 brief, instruction 9: "no provider contract returns ORM
# models"). Neither fake performs any real image analysis; both are
# fully deterministic and require no model file, GPU, camera, or network
# access.
# ---------------------------------------------------------------------------


class _FakeFixedFaceDetector:
    """Always reports exactly one face filling most of the image."""

    def detect(self, image: DecodedImage) -> list[DetectedFace]:
        box = BoundingBox(
            x_px=0,
            y_px=0,
            width_px=image.dimensions.width_px,
            height_px=image.dimensions.height_px,
        )
        face = DetectedFace(
            bounding_box=box, source_image_dimensions=image.dimensions, confidence=1.0
        )
        return [face]


class _FakeZeroFaceDetector:
    """Always reports no faces — a normal, valid detection result."""

    def detect(self, image: DecodedImage) -> list[DetectedFace]:
        return []


class _FakeConstantFaceEmbedder:
    """Always returns the same fixed-dimension embedding."""

    def __init__(self, *, dimension: int = 4) -> None:
        self._dimension = dimension

    def embed(self, face: NormalizedFaceInput) -> EmbeddingVector:
        vector = EmbeddingVector(values=tuple(1.0 for _ in range(self._dimension)))
        return validate_embedding_dimension(vector, expected_dimension=self._dimension)


class _FakeLookupFaceMatcher:
    """Matches against a caller-supplied candidate list, keyed by a known student ID.

    Deliberately simple (dimension check + "is the known student among
    the candidates" check) — this fake exists to prove protocol
    conformance and candidate-scoping shape, not to demonstrate real
    similarity math (see ``test_face_recognition_matcher.py`` for the
    real ``CosineSimilarityFaceMatcher`` under test with real numbers).
    """

    def __init__(self, *, known_student_id: uuid.UUID) -> None:
        self._known_student_id = known_student_id

    def match(
        self, embedding: EmbeddingVector, candidates: Sequence[CandidateEmbedding]
    ) -> MatchResult:
        known_candidate_present = any(
            candidate.student_profile_id == self._known_student_id for candidate in candidates
        )
        if embedding.dimension == 4 and known_candidate_present:
            candidate = MatchCandidate(student_profile_id=self._known_student_id, similarity=0.99)
            return MatchResult.found(candidate)
        return MatchResult.unknown()


def test_fake_detector_satisfies_the_face_detector_protocol() -> None:
    detector = _FakeFixedFaceDetector()
    assert isinstance(detector, FaceDetector)
    dims = ImageDimensions(width_px=100, height_px=100)
    image = DecodedImage(dimensions=dims, pixel_data=b"\x00")
    faces = detector.detect(image)
    assert len(faces) == 1
    assert faces[0].confidence == 1.0


def test_fake_zero_face_detector_returns_empty_list_not_an_error() -> None:
    detector = _FakeZeroFaceDetector()
    assert isinstance(detector, FaceDetector)
    dims = ImageDimensions(width_px=100, height_px=100)
    image = DecodedImage(dimensions=dims, pixel_data=b"\x00")
    assert detector.detect(image) == []


def test_fake_embedder_satisfies_the_face_embedder_protocol() -> None:
    embedder = _FakeConstantFaceEmbedder(dimension=4)
    assert isinstance(embedder, FaceEmbedder)
    face_input = NormalizedFaceInput(
        dimensions=ImageDimensions(width_px=112, height_px=112), pixel_data=b"\x00"
    )
    vector = embedder.embed(face_input)
    assert vector.dimension == 4


def test_fake_matcher_satisfies_the_face_matcher_protocol() -> None:
    known_id = uuid.uuid4()
    matcher = _FakeLookupFaceMatcher(known_student_id=known_id)
    assert isinstance(matcher, FaceMatcher)

    known_candidates = [
        CandidateEmbedding(
            student_profile_id=known_id, embedding=EmbeddingVector(values=(1.0, 1.0, 1.0, 1.0))
        )
    ]
    found = matcher.match(EmbeddingVector(values=(1.0, 1.0, 1.0, 1.0)), known_candidates)
    assert found.status is MatchStatus.FOUND
    assert found.matched_student_profile_id == known_id

    unknown = matcher.match(EmbeddingVector(values=(1.0, 1.0)), known_candidates)
    assert unknown.status is MatchStatus.UNKNOWN
    assert unknown.matched_student_profile_id is None

    # An empty candidate list must also resolve to UNKNOWN — this fake's
    # own "is the known student among the candidates" check makes that
    # true here the same way the real matcher's "no candidates ->
    # UNKNOWN" contract does (see test_face_recognition_matcher.py).
    no_candidates: list[CandidateEmbedding] = []
    empty_scope = matcher.match(EmbeddingVector(values=(1.0, 1.0, 1.0, 1.0)), no_candidates)
    assert empty_scope.status is MatchStatus.UNKNOWN


def test_end_to_end_fake_pipeline_never_returns_an_orm_model() -> None:
    """Detect -> embed -> match, entirely with fakes, proving the boundary.

    Asserts every object crossing the detect/embed/match boundary is one
    of this module's own value objects (or a plain ``uuid.UUID``) —
    never a SQLAlchemy model instance. This is a structural, not a
    tautological, assertion: it would fail if any fake here were changed
    to return, say, an ``app.modules.profiles.models.StudentProfile``.
    """

    known_id = uuid.uuid4()
    detector = _FakeFixedFaceDetector()
    embedder = _FakeConstantFaceEmbedder(dimension=4)
    matcher = _FakeLookupFaceMatcher(known_student_id=known_id)

    dims = ImageDimensions(width_px=200, height_px=200)
    image = DecodedImage(dimensions=dims, pixel_data=b"\x00")
    faces = detector.detect(image)
    assert all(isinstance(face, DetectedFace) for face in faces)

    face_dims = faces[0].source_image_dimensions
    face_input = NormalizedFaceInput(dimensions=face_dims, pixel_data=b"\x00")
    embedding = embedder.embed(face_input)
    assert isinstance(embedding, EmbeddingVector)

    candidates = [
        CandidateEmbedding(student_profile_id=known_id, embedding=embedding),
    ]
    result = matcher.match(embedding, candidates)
    assert isinstance(result, MatchResult)
    assert result.matched_student_profile_id is None or isinstance(
        result.matched_student_profile_id, uuid.UUID
    )

    # No provider-layer object anywhere above is, or wraps, an ORM model:
    # every field on MatchResult/DetectedFace/EmbeddingVector is a
    # Pydantic-native type (UUID/float/int/bytes/tuple/nested Pydantic
    # model) — never `app.modules.profiles.models.StudentProfile` or any
    # other `app.db.base.Base` subclass.
    for model_cls in (DetectedFace, EmbeddingVector, MatchResult, MatchCandidate):
        for field_info in model_cls.model_fields.values():
            annotation = str(field_info.annotation)
            assert "profiles.models" not in annotation
            assert "StudentProfile" not in annotation
            assert "db.base" not in annotation
