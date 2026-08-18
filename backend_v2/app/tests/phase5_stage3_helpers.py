"""Shared fakes/builders for Phase 5 Stage 3 tests.

Every test file under ``test_face_recognition_*``/``test_phase5_stage3_*``
that needs a detector/embedder without a real ``.onnx``/``.dat`` model
file, or a quick ``DetectedFace``/``EmbeddingVector`` to construct,
imports from here — matching
``app.tests.phase5_stage2_http_helpers``'s established pattern of one
shared helpers module per stage rather than duplicating fixture setup
per test file.

**Fakes, not mocks:** ``FakeFaceDetector``/``FakeFaceEmbedder`` are
small, real classes implementing the actual
``app.modules.face_recognition.protocols`` Protocols end-to-end (not
``unittest.mock.Mock`` stand-ins) — this is what the Stage 3 brief's
"use deterministic fake providers for normal unit/integration tests
where possible" means in this codebase's own idiom.
"""

from __future__ import annotations

import hashlib
import io
import math
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.biometric_enrollment.models import EnrollmentStatus
from app.modules.biometric_enrollment.repository import (
    BiometricEnrollmentRepository,
    BiometricSampleRepository,
)
from app.modules.biometric_enrollment.storage import PrivateBiometricStorage
from app.modules.face_recognition.domain import (
    BoundingBox,
    CandidateEmbedding,
    DecodedImage,
    DetectedFace,
    EmbeddingVector,
    FacialLandmark,
    ImageDimensions,
    NormalizedFaceInput,
)

DEFAULT_DIMENSIONS = ImageDimensions(width_px=400, height_px=400)


def make_decoded_image(
    *, dimensions: ImageDimensions = DEFAULT_DIMENSIONS, color_format: str = "rgb"
) -> DecodedImage:
    """A minimal, valid ``DecodedImage`` — solid-color pixel data, content never inspected
    by any fake provider in this module (only real cv2/dlib adapters read actual pixels)."""
    size = dimensions.width_px * dimensions.height_px * 3
    return DecodedImage(
        dimensions=dimensions, pixel_data=bytes([120]) * size, color_format=color_format
    )


def make_landmarks(
    *, dimensions: ImageDimensions = DEFAULT_DIMENSIONS
) -> tuple[FacialLandmark, ...]:
    """Five plausible YuNet-order landmarks (right eye, left eye, nose, mouth corners)
    positioned inside ``dimensions``, forming a valid (non-degenerate) upright face."""
    cx, cy = dimensions.width_px / 2, dimensions.height_px / 2
    return (
        FacialLandmark(x_px=cx - 20, y_px=cy - 10),  # right eye
        FacialLandmark(x_px=cx + 20, y_px=cy - 10),  # left eye
        FacialLandmark(x_px=cx, y_px=cy + 5),  # nose tip
        FacialLandmark(x_px=cx - 15, y_px=cy + 30),  # right mouth corner
        FacialLandmark(x_px=cx + 15, y_px=cy + 30),  # left mouth corner
    )


def make_detected_face(
    *,
    dimensions: ImageDimensions = DEFAULT_DIMENSIONS,
    with_landmarks: bool = True,
    confidence: float = 0.95,
) -> DetectedFace:
    box = BoundingBox(
        x_px=int(dimensions.width_px * 0.25),
        y_px=int(dimensions.height_px * 0.2),
        width_px=int(dimensions.width_px * 0.5),
        height_px=int(dimensions.height_px * 0.6),
    )
    return DetectedFace(
        bounding_box=box,
        source_image_dimensions=dimensions,
        confidence=confidence,
        landmarks=make_landmarks(dimensions=dimensions) if with_landmarks else None,
    )


def make_normalized_face(*, size_px: int = 150) -> NormalizedFaceInput:
    dims = ImageDimensions(width_px=size_px, height_px=size_px)
    return NormalizedFaceInput(
        dimensions=dims, pixel_data=bytes([100]) * (size_px * size_px * 3), color_format="rgb"
    )


def make_embedding_vector(*, dimension: int = 128, seed: float = 1.0) -> EmbeddingVector:
    """A deterministic, non-degenerate embedding vector of the given dimension.

    ``seed`` shifts every component so two calls with different seeds
    produce genuinely different (but still deterministic, still finite)
    vectors — enough for matcher/aggregation tests without needing real
    inference. Uses a classic sine-based pseudo-random hash (not modular
    arithmetic on ``seed * i``) specifically because integer/near-integer
    seeds under simple modular arithmetic can alias — e.g.
    ``99 * (i + 1) % 7 == 1 * (i + 1) % 7`` for every integer ``i`` (since
    ``99 % 7 == 1``), which would make two "different" seeds silently
    produce the same vector and quietly defeat any test relying on them
    being distinguishable.
    """
    values = tuple(
        math.sin((i + 1) * seed * 12.9898) * 43758.5453 % 1.0 * 2.0 - 1.0 for i in range(dimension)
    )
    return EmbeddingVector(values=values)


def make_unit_embedding_vector(*, dimension: int = 128, seed: float = 1.0) -> EmbeddingVector:
    """Same as ``make_embedding_vector`` but L2-normalized to a unit vector —
    matches what ``DlibResnetFaceEmbedder`` actually returns (see that module)."""
    raw = make_embedding_vector(dimension=dimension, seed=seed)
    norm = sum(v * v for v in raw.values) ** 0.5
    return EmbeddingVector(values=tuple(v / norm for v in raw.values))


def nudge_unit_vector(vector: EmbeddingVector, *, epsilon: float) -> EmbeddingVector:
    """Perturb ``vector`` (assumed already a unit vector) by ``epsilon`` in its
    first component, then re-normalize — produces a new unit vector whose
    cosine similarity to the original is close to, but strictly less than,
    1.0, with the gap growing monotonically as ``epsilon`` grows. Used for
    "near-identical but not exactly the same" test fixtures (a smooth,
    predictable alternative to picking a second, unrelated ``seed`` — see
    ``make_embedding_vector``'s own docstring on why two arbitrary seeds
    can be much closer, or much farther apart, than intended)."""
    values = list(vector.values)
    values[0] = values[0] + epsilon
    norm = sum(v * v for v in values) ** 0.5
    return EmbeddingVector(values=tuple(v / norm for v in values))


def make_candidate(
    *, student_profile_id: uuid.UUID | None = None, dimension: int = 128, seed: float = 1.0
) -> CandidateEmbedding:
    return CandidateEmbedding(
        student_profile_id=student_profile_id or uuid.uuid4(),
        embedding=make_unit_embedding_vector(dimension=dimension, seed=seed),
    )


class FakeFaceDetector:
    """A ``FaceDetector`` returning a pre-programmed, per-call result.

    ``results`` is consumed in order, one entry per ``detect()`` call;
    the last entry repeats once exhausted (so a test that calls
    ``detect()`` more times than it explicitly programmed still gets a
    predictable, non-crashing result rather than an ``IndexError``).
    """

    provider_name = "fake_detector"

    def __init__(self, results: list[list[DetectedFace]] | None = None) -> None:
        self._results = results if results is not None else [[make_detected_face()]]
        self._call_count = 0
        self.available = True

    def is_available(self) -> bool:
        return self.available

    def detect(self, image: DecodedImage) -> list[DetectedFace]:
        index = min(self._call_count, len(self._results) - 1)
        self._call_count += 1
        return list(self._results[index])


class FakeFaceEmbedder:
    """A ``FaceEmbedder`` returning a pre-programmed, per-call embedding (or raising)."""

    provider_name = "fake_embedder"
    model_identifier = "fake_embedder_model"

    def __init__(
        self,
        *,
        dimension: int = 128,
        seed: float = 1.0,
        raise_error: Exception | None = None,
    ) -> None:
        self._dimension = dimension
        self._seed = seed
        self._raise_error = raise_error
        self.available = True

    def is_available(self) -> bool:
        return self.available

    def embed(self, face: NormalizedFaceInput) -> EmbeddingVector:
        if self._raise_error is not None:
            raise self._raise_error
        return make_unit_embedding_vector(dimension=self._dimension, seed=self._seed)


@contextmanager
def patch_providers(detector: FakeFaceDetector, embedder: FakeFaceEmbedder):
    """Patch both ``app.modules.face_recognition.pipeline.get_detector``/
    ``get_embedder`` at once, for the duration of the ``with`` block.

    One combined context manager (rather than two separate ``patch(...)``
    calls a caller has to chain with a comma) so every test file that
    needs a fake detector+embedder pair — the detect -> align -> embed
    pipeline always needs both together — writes one short ``with``
    line instead of repeating the same two-patch boilerplate.
    """
    with (
        patch("app.modules.face_recognition.pipeline.get_detector", return_value=detector),
        patch("app.modules.face_recognition.pipeline.get_embedder", return_value=embedder),
    ):
        yield


class FakeFaceMatcher:
    """A trivial ``FaceMatcher`` stand-in, used only where a test needs to assert
    *that* the matcher was invoked with a given candidate list, not its real math
    (real-math coverage lives in ``test_face_recognition_matcher.py`` against the
    actual ``CosineSimilarityFaceMatcher``)."""

    def __init__(self, result: Any) -> None:
        self._result = result
        self.last_candidates: list[CandidateEmbedding] | None = None

    def match(self, embedding: EmbeddingVector, candidates: list[CandidateEmbedding]) -> Any:
        self.last_candidates = list(candidates)
        return self._result


def make_real_jpeg_bytes(
    *, size: tuple[int, int] = (200, 200), color: tuple[int, int, int] = (10, 20, 30)
) -> bytes:
    """A real, fully-decodable JPEG — for direct-seeded samples that
    ``SampleProcessingService._load_decoded_image`` will actually open with
    Pillow (unlike the pixel-data-only ``DecodedImage``/``NormalizedFaceInput``
    builders above, which never touch a real codec)."""
    buffer = io.BytesIO()
    Image.new("RGB", size, color=color).save(buffer, format="JPEG")
    return buffer.getvalue()


async def seed_active_sample_direct(
    db_session: AsyncSession,
    *,
    student_profile_id: uuid.UUID,
    created_by_user_id: uuid.UUID,
    content: bytes | None = None,
    write_file: bool = True,
) -> uuid.UUID:
    """Create an ``ACTIVE`` ``BiometricEnrollment`` + ``BiometricSample`` row
    directly through the repository/ORM layer, and (unless ``write_file`` is
    False) place a real file in the active storage zone — without going
    through ``app.modules.biometric_enrollment.service.create_sample``'s
    HTTP path.

    Stage 3 test files that need an ``ACTIVE`` sample as a setup precondition
    historically drove Stage 2's real HTTP upload endpoint
    (``phase5_stage2_http_helpers.upload_sample``) to get one. That endpoint
    has a confirmed, pre-existing Stage 2 defect (a ``MissingGreenlet``
    error inside ``BiometricEnrollmentService.create_sample`` when
    serializing its Pydantic response after a committed transaction — see
    ``docs/HANDOVER_PHASE_5_STAGE_3.md``'s "Known external blocker") that
    only surfaces against a real database, and is explicitly out of scope
    for this Stage 3 correction patch. This helper reaches the same
    end state (one ACTIVE sample, ready for
    ``SampleProcessingService``) without calling any Stage 2 *service*
    code, so Stage 3 processing/matching/audit/offload behavior can be
    verified against a real PostgreSQL database independently of that
    Stage 2 bug. Only Stage 2 *repository*/*storage* primitives are used
    here (the same ones Stage 2's own service calls) — no Stage 2
    application logic is bypassed or weakened, only its response
    serialization step, which Stage 3 processing never touches anyway.
    """
    settings = get_settings()
    storage = PrivateBiometricStorage(settings)
    enrollments = BiometricEnrollmentRepository(db_session)
    samples = BiometricSampleRepository(db_session)

    enrollment = await enrollments.create(
        student_profile_id=student_profile_id, created_by_user_id=created_by_user_id
    )
    await enrollments.set_status(enrollment, status=EnrollmentStatus.ACTIVE)

    payload = content if content is not None else make_real_jpeg_bytes()
    sha256_hash = hashlib.sha256(payload).hexdigest()
    width_px, height_px = 200, 200
    if write_file:
        with Image.open(io.BytesIO(payload)) as image:
            width_px, height_px = image.size

    key = storage.new_key()
    sample = await samples.create_pending(
        enrollment_id=enrollment.id,
        storage_key=key,
        original_filename="direct-seed.jpg",
        content_type="image/jpeg",
        file_size_bytes=len(payload),
        width_px=width_px,
        height_px=height_px,
        sha256_hash=sha256_hash,
        created_by_user_id=created_by_user_id,
    )
    if write_file:
        storage.active_path(key).write_bytes(payload)

    await samples.mark_active(sample, promoted_at=datetime.now(UTC))
    await db_session.commit()
    await db_session.refresh(sample)
    return sample.id
