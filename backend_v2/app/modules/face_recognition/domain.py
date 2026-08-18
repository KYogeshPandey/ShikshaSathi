"""Provider-neutral typed value objects for face detection, embedding, and matching.

Every value object here is a plain Pydantic v2 model (``frozen=True``,
``extra="forbid"``), the same convention already used for immutable,
validated shapes elsewhere in this codebase (e.g.
``app.modules.attendance.schemas``). None of these carry provider-specific
types (no OpenCV ``Mat``, no ONNX Runtime session, no numpy array, no
hosted-API response shape) and none reference an ORM model — a
``MatchResult`` identifies a student only by ``uuid.UUID``
(``student_profile_id``), never a ``StudentProfile`` instance, so the
provider layer can never leak ORM state or trigger a lazy load.

**Deliberately dependency-free.** These contracts store image/embedding
data as plain ``bytes``/``tuple[float, ...]`` rather than numpy arrays, so
this module adds zero new third-party dependencies in Stage 1 (see
``docs/adr/0005-face-recognition-provider-pending.md``'s "Consequences" —
``numpy``/``opencv-python-headless``/``onnxruntime`` are Stage 2/3
additions, not Stage 1 ones).

**Confidence/distance semantics are fixed project-wide as similarity,
never distance:** ``MatchCandidate.similarity`` is always "higher is more
alike" (bounded to the ``[-1.0, 1.0]`` cosine-similarity range). A future
provider built around a distance metric (e.g. raw L2 distance, where
*lower* is more alike) must convert to this similarity convention before
constructing a ``MatchCandidate`` — this module never exposes a second,
competing "distance" field that could be mixed up with it.
"""

from __future__ import annotations

import math
import uuid
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.face_recognition.errors import InvalidEmbeddingDimensionError

# Generous sanity bounds — these guard against obviously-malformed input
# (e.g. a zero-sized or absurdly large image), not a real product limit.
# Real enrollment-image size limits are enforced separately, at upload
# time, by ``Settings.MAX_ENROLLMENT_IMAGE_BYTES`` (Stage 2).
_MIN_DIMENSION_PX = 1
_MAX_DIMENSION_PX = 10_000


class ImageDimensions(BaseModel):
    """The width/height, in pixels, of a decoded image or a face crop."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    width_px: int = Field(ge=_MIN_DIMENSION_PX, le=_MAX_DIMENSION_PX)
    height_px: int = Field(ge=_MIN_DIMENSION_PX, le=_MAX_DIMENSION_PX)


class BoundingBox(BaseModel):
    """A face's location within its source image, in pixel coordinates.

    ``x_px``/``y_px`` are the top-left corner; both non-negative.
    ``width_px``/``height_px`` must be strictly positive — a zero-area
    box is not a valid detection. Whether a box actually fits inside a
    *specific* image is checked one level up, by ``DetectedFace`` (a bare
    ``BoundingBox`` does not know which image it belongs to).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    x_px: int = Field(ge=0)
    y_px: int = Field(ge=0)
    width_px: int = Field(gt=0, le=_MAX_DIMENSION_PX)
    height_px: int = Field(gt=0, le=_MAX_DIMENSION_PX)

    @property
    def right_px(self) -> int:
        return self.x_px + self.width_px

    @property
    def bottom_px(self) -> int:
        return self.y_px + self.height_px


class DecodedImage(BaseModel):
    """The input to a ``FaceDetector``: one already-decoded whole image.

    ``pixel_data`` is intentionally opaque ``bytes`` here — this contract
    does not assume, encode, or validate any particular pixel layout
    (RGB/BGR, packed/planar, bit depth). A Stage 3 provider adapter is
    responsible for decoding whatever raw upload it receives into
    whatever concrete format its own detector needs; this value object
    only carries the result of that step plus the dimensions it claims to
    have, so the boundary between "decoding" and "detecting" stays
    provider-neutral.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    dimensions: ImageDimensions
    pixel_data: bytes
    color_format: Literal["rgb", "bgr"] = "rgb"

    @model_validator(mode="after")
    def _reject_empty_pixel_data(self) -> DecodedImage:
        if not self.pixel_data:
            raise ValueError("DecodedImage.pixel_data must not be empty.")
        return self


class FacialLandmark(BaseModel):
    """One named facial landmark point, in the same pixel space as its
    parent ``DetectedFace.source_image_dimensions`` (i.e. whole-image
    pixel coordinates, not face-crop-relative).

    **Added in Phase 5 Stage 3** for YuNet alignment support (Stage 1
    left ``DetectedFace`` landmark-free since no detector was
    implemented yet — see this class's addition in
    ``docs/HANDOVER_PHASE_5_STAGE_3.md``). Coordinates are plain
    ``float`` (not ``int``) because YuNet reports sub-pixel positions;
    ``app.modules.face_recognition.alignment`` is the only code that
    reads these.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    x_px: float
    y_px: float

    @model_validator(mode="after")
    def _reject_non_finite_coordinates(self) -> FacialLandmark:
        if not (math.isfinite(self.x_px) and math.isfinite(self.y_px)):
            raise ValueError("FacialLandmark coordinates must be finite numbers.")
        return self


class DetectedFace(BaseModel):
    """One face detection result: a bounding box plus a confidence score.

    ``confidence`` is bounded to ``[0.0, 1.0]`` — a detector's own
    per-detection confidence, distinct from a *matcher's* similarity
    score (``MatchCandidate.similarity``); the two are never the same
    number and this module never conflates them.

    ``landmarks`` is optional and, when present, is a fixed-length
    5-point tuple in YuNet's own published order — right eye, left eye,
    nose tip, right mouth corner, left mouth corner (see
    ``app.modules.face_recognition.providers.yunet_detector``) — chosen
    because that is the only landmark scheme this codebase's one Stage 3
    detector adapter ever produces. A detector that cannot supply
    landmarks (or a future, different provider) may leave this ``None``;
    ``app.modules.face_recognition.alignment`` treats a ``None`` or
    wrong-length ``landmarks`` as "alignment not possible" and raises a
    typed error rather than guessing.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    bounding_box: BoundingBox
    source_image_dimensions: ImageDimensions
    confidence: float = Field(ge=0.0, le=1.0)
    landmarks: tuple[FacialLandmark, ...] | None = Field(default=None)

    @field_validator("confidence")
    @classmethod
    def _reject_non_finite_confidence(cls, value: float) -> float:
        # Field(ge=0.0, le=1.0) already rejects NaN/±inf via comparison
        # semantics, but that rejection is incidental to how Python
        # compares NaN, not a stated intent. This makes the "confidence
        # must be finite" requirement explicit and independent of that
        # comparison behavior, matching EmbeddingVector's explicit
        # ``math.isfinite`` check above.
        if not math.isfinite(value):
            raise ValueError("DetectedFace.confidence must be a finite number.")
        return value

    @field_validator("landmarks")
    @classmethod
    def _reject_wrong_landmark_count(
        cls, value: tuple[FacialLandmark, ...] | None
    ) -> tuple[FacialLandmark, ...] | None:
        # A bare structural sanity check (any provider that supplies
        # landmarks at all must supply a plausible small fixed set) —
        # the *exact* "must be 5, in YuNet order" requirement is
        # alignment.py's concern, not this domain object's, since a
        # hypothetical future non-5-point provider is still a
        # structurally valid DetectedFace even though today's one
        # alignment implementation would reject it.
        if value is not None and not (1 <= len(value) <= 68):
            raise ValueError("DetectedFace.landmarks must contain between 1 and 68 points.")
        return value

    @model_validator(mode="after")
    def _reject_out_of_bounds_box(self) -> DetectedFace:
        box = self.bounding_box
        dims = self.source_image_dimensions
        if box.right_px > dims.width_px or box.bottom_px > dims.height_px:
            raise ValueError(
                "DetectedFace.bounding_box must fit entirely within source_image_dimensions."
            )
        return self


class NormalizedFaceInput(BaseModel):
    """The input to a ``FaceEmbedder``: one already-cropped, aligned face.

    Distinct from ``DecodedImage`` deliberately: by the time a face
    reaches an embedder it has already been detected, cropped, and (in a
    real Stage 3 provider) geometrically aligned — a different pipeline
    stage with different preconditions, not "the same image type reused".
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    dimensions: ImageDimensions
    pixel_data: bytes
    color_format: Literal["rgb", "bgr"] = "rgb"

    @model_validator(mode="after")
    def _reject_empty_pixel_data(self) -> NormalizedFaceInput:
        if not self.pixel_data:
            raise ValueError("NormalizedFaceInput.pixel_data must not be empty.")
        return self


class EmbeddingVector(BaseModel):
    """A validated face embedding: a non-empty tuple of finite floats.

    Dimension is derived (``len(values)``), never a separately-settable
    field that could drift from the actual data — see ``dimension``
    below. Whether this dimension matches what the application currently
    *expects* (``Settings.FACE_EMBEDDING_DIMENSION``) is a separate,
    explicit check — ``validate_embedding_dimension`` — not something
    this model can enforce on its own, since the expected dimension is a
    runtime configuration value, not a property of the vector itself.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    values: tuple[float, ...]

    @model_validator(mode="after")
    def _validate_values(self) -> EmbeddingVector:
        if not self.values:
            raise ValueError("EmbeddingVector.values must not be empty.")
        if any(not math.isfinite(value) for value in self.values):
            raise ValueError("EmbeddingVector.values must contain only finite numbers.")
        return self

    @property
    def dimension(self) -> int:
        return len(self.values)


def validate_embedding_dimension(
    vector: EmbeddingVector, *, expected_dimension: int
) -> EmbeddingVector:
    """Confirm ``vector`` has exactly ``expected_dimension`` components.

    Returns ``vector`` unchanged on success (so this composes into a
    pipeline: ``validate_embedding_dimension(embedder.embed(face),
    expected_dimension=settings.FACE_EMBEDDING_DIMENSION)``); raises
    ``InvalidEmbeddingDimensionError`` otherwise. Every Stage 3 embedder
    adapter is expected to call this on its own output rather than
    re-implementing the comparison, so the error code/message is
    consistent regardless of which provider produced the mismatch.
    """

    if vector.dimension != expected_dimension:
        raise InvalidEmbeddingDimensionError(expected=expected_dimension, actual=vector.dimension)
    return vector


class CandidateEmbedding(BaseModel):
    """One enrolled student's embedding, offered to a ``FaceMatcher`` as a
    candidate to compare against.

    **Added in Phase 5 Stage 3.** This is the concrete shape behind the
    Stage 3 brief's "candidate-scoped matching" requirement: a
    ``FaceMatcher`` never queries a repository or reaches into the
    database on its own (see ``protocols.py``'s updated ``FaceMatcher``
    docstring) — the *caller* (an already-authorized service) resolves
    exactly which students are in scope, fetches their active,
    processed embeddings, and passes a list of these value objects in.
    An empty list is a normal, valid input (see
    ``app.modules.face_recognition.protocols.FaceMatcher.match``'s
    "no candidates -> UNKNOWN" contract) — never itself an error.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    student_profile_id: uuid.UUID
    embedding: EmbeddingVector


class MatchStatus(StrEnum):
    """The three, mutually exclusive shapes a ``MatchResult`` can take."""

    FOUND = "found"
    UNKNOWN = "unknown"
    AMBIGUOUS = "ambiguous"


class MatchCandidate(BaseModel):
    """One candidate student and how similar the query embedding was to them.

    ``similarity`` uses this module's fixed similarity convention (higher
    is more alike), bounded to the cosine-similarity range
    ``[-1.0, 1.0]`` — see this module's docstring.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    student_profile_id: uuid.UUID
    similarity: float = Field(ge=-1.0, le=1.0)

    @field_validator("similarity")
    @classmethod
    def _reject_non_finite_similarity(cls, value: float) -> float:
        # See DetectedFace._reject_non_finite_confidence for why this is
        # explicit rather than left to Field(ge=..., le=...) alone.
        if not math.isfinite(value):
            raise ValueError("MatchCandidate.similarity must be a finite number.")
        return value


class MatchResult(BaseModel):
    """The outcome of a ``FaceMatcher.match(...)`` call.

    Exactly one of the three ``MatchStatus`` shapes — never a bare
    boolean "matched or not". ``UNKNOWN`` and ``AMBIGUOUS`` are distinct
    on purpose (Stage 1 brief, instruction 5): ``UNKNOWN`` means no
    candidate was similar enough to consider at all; ``AMBIGUOUS`` means
    two or more candidates were both plausible and too close together to
    tell apart safely (within ``Settings.FACE_MATCH_AMBIGUOUS_MARGIN`` of
    each other) — the caller must not silently pick the higher-scoring
    one, per ``docs/BIOMETRIC_DATA_POLICY.md``'s "low-confidence/ambiguous
    results require confirmation".

    Construct via ``.found(...)``/``.unknown()``/``.ambiguous(...)``
    rather than the constructor directly, so every call site is
    guaranteed to build a result the ``_validate_shape`` check below
    would also accept.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: MatchStatus
    matched_student_profile_id: uuid.UUID | None = None
    best_candidate: MatchCandidate | None = None
    runner_up_candidate: MatchCandidate | None = None

    @model_validator(mode="after")
    def _validate_shape(self) -> MatchResult:
        if self.status is MatchStatus.FOUND:
            if self.matched_student_profile_id is None or self.best_candidate is None:
                raise ValueError(
                    "A FOUND MatchResult must set matched_student_profile_id and best_candidate."
                )
            if self.matched_student_profile_id != self.best_candidate.student_profile_id:
                raise ValueError(
                    "A FOUND MatchResult's matched_student_profile_id must equal "
                    "best_candidate.student_profile_id."
                )
            if self.runner_up_candidate is not None:
                raise ValueError("A FOUND MatchResult must not set runner_up_candidate.")
        else:
            if self.matched_student_profile_id is not None:
                raise ValueError("Only a FOUND MatchResult may set matched_student_profile_id.")

        if self.status is MatchStatus.AMBIGUOUS:
            if self.best_candidate is None or self.runner_up_candidate is None:
                raise ValueError(
                    "An AMBIGUOUS MatchResult must include both best_candidate and "
                    "runner_up_candidate, for audit context."
                )
            best_id = self.best_candidate.student_profile_id
            runner_up_id = self.runner_up_candidate.student_profile_id
            if best_id == runner_up_id:
                raise ValueError(
                    "An AMBIGUOUS MatchResult's best_candidate and runner_up_candidate "
                    "must reference different students."
                )
            if self.best_candidate.similarity < self.runner_up_candidate.similarity:
                raise ValueError(
                    "An AMBIGUOUS MatchResult's best_candidate.similarity must be >= "
                    "runner_up_candidate.similarity."
                )

        if self.status is MatchStatus.UNKNOWN and self.runner_up_candidate is not None:
            raise ValueError("An UNKNOWN MatchResult must not set runner_up_candidate.")

        return self

    @classmethod
    def found(cls, candidate: MatchCandidate) -> MatchResult:
        return cls(
            status=MatchStatus.FOUND,
            matched_student_profile_id=candidate.student_profile_id,
            best_candidate=candidate,
        )

    @classmethod
    def unknown(cls, *, best_candidate: MatchCandidate | None = None) -> MatchResult:
        """No candidate was similar enough to consider a match at all.

        ``best_candidate`` is optional context (the closest candidate
        found, even though it fell below the match threshold) — useful
        for audit logging in Stage 4, never treated as a match.
        """

        return cls(status=MatchStatus.UNKNOWN, best_candidate=best_candidate)

    @classmethod
    def ambiguous(
        cls, *, best_candidate: MatchCandidate, runner_up_candidate: MatchCandidate
    ) -> MatchResult:
        return cls(
            status=MatchStatus.AMBIGUOUS,
            best_candidate=best_candidate,
            runner_up_candidate=runner_up_candidate,
        )


class ProviderStatus(StrEnum):
    """A coarse, client-safe health state for a face-recognition provider."""

    READY = "ready"
    UNAVAILABLE = "unavailable"
    NOT_CONFIGURED = "not_configured"


class ProviderHealth(BaseModel):
    """A provider's own health/status, safe to surface without leaking internals.

    ``detail`` is short and human-readable by construction (``max_length``
    below) — it must never carry a stack trace, file path, or raw
    vendor-response body (``docs/BIOMETRIC_DATA_POLICY.md``'s
    "model/provider diagnostics restrictions"); enforcing that fully is a
    Stage 3 code-review concern, not something a length cap alone can
    guarantee, but the cap at least rules out pasting a full traceback in.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider_name: str = Field(max_length=100)
    status: ProviderStatus
    detail: str | None = Field(default=None, max_length=200)

    @field_validator("provider_name")
    @classmethod
    def _strip_and_reject_blank_provider_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("ProviderHealth.provider_name must not be blank.")
        return stripped
