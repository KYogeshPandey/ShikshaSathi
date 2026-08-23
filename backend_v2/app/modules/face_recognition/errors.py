"""Application-defined errors for the face-recognition domain.

Same ``AppError`` contract as every other module (e.g.
``app.modules.attendance.errors``) — handled by the existing centralized
exception handler (``app/core/exceptions.py``), so a future router never
needs a local ``try/except`` block to keep the standard envelope.

**Stage 1 scope note (historical):** at Stage 1, nothing in this module
was reachable over HTTP — no router existed. That changed in Stage 3:
``app.modules.face_recognition.router`` now raises the errors below
(including the Stage 3 and Stage 4 additions further down this file)
through real endpoints.
Every message below is deliberately generic and contains no model name,
file path, vendor response body, or other provider-internal detail —
see ``docs/BIOMETRIC_DATA_POLICY.md``'s "model/provider diagnostics
restrictions".
"""

from __future__ import annotations

from fastapi import status

from app.core.exceptions import AppError


class FaceRecognitionError(AppError):
    """Base class for every face-recognition-domain error.

    Not raised directly — always one of the specific subclasses below.
    """

    code = "FACE_RECOGNITION_ERROR"
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class FaceProviderUnavailableError(FaceRecognitionError):
    """The configured provider cannot serve a request right now.

    Covers every flavor of provider-level failure a Stage 3
    implementation might hit: an unreadable/missing model file, a
    misconfigured device, or a hosted API being unreachable. Deliberately
    carries no diagnostic detail in the client-facing message — the real
    cause belongs in the server-side structured log only, exactly like
    ``app.core.exceptions.DatabaseUnavailableError``.
    """

    code = "FACE_PROVIDER_UNAVAILABLE"
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    def __init__(self) -> None:
        super().__init__("The face-recognition provider is temporarily unavailable.")


class FaceDetectionFailedError(FaceRecognitionError):
    """A ``FaceDetector`` implementation could not process the given image.

    E.g. a corrupt or unreadable image payload — not "zero faces found",
    which is a normal, valid detection result (an empty list), not an
    error.
    """

    code = "FACE_DETECTION_FAILED"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__("The provided image could not be processed for face detection.")


class FaceEmbeddingFailedError(FaceRecognitionError):
    """A ``FaceEmbedder`` implementation could not embed a detected face."""

    code = "FACE_EMBEDDING_FAILED"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__("The detected face could not be converted into a usable embedding.")


class InvalidEmbeddingDimensionError(FaceRecognitionError):
    """Raised when an embedding's dimension does not match what is configured.

    Used by ``app.modules.face_recognition.domain.validate_embedding_dimension``
    so every embedder implementation validates its own output shape
    against ``Settings.FACE_EMBEDDING_DIMENSION`` the same way, rather than
    each provider re-implementing this check with its own error type.
    """

    code = "FACE_EMBEDDING_DIMENSION_MISMATCH"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self, *, expected: int, actual: int) -> None:
        super().__init__(f"Embedding dimension mismatch: expected {expected}, got {actual}.")


# ---------------------------------------------------------------------------
# Phase 5 Stage 3: alignment, model-artifact, and enrollment-sample-
# processing errors. Everything below is new in this checkpoint — Stage 1/2
# defined no alignment step, no model artifact, and no sample-processing
# pipeline (see docs/HANDOVER_PHASE_5_STAGE_3.md).
# ---------------------------------------------------------------------------


class FaceLandmarksUnavailableError(FaceRecognitionError):
    """A ``DetectedFace`` has no usable landmarks for alignment.

    Covers both "no landmarks at all" (``landmarks is None``) and
    "landmarks present but not the 5-point YuNet layout this codebase's
    one alignment implementation understands" — see
    ``app.modules.face_recognition.alignment``.
    """

    code = "FACE_LANDMARKS_UNAVAILABLE"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__("The detected face has no usable landmarks for alignment.")


class FaceAlignmentFailedError(FaceRecognitionError):
    """Alignment could not produce a usable normalized face crop.

    E.g. degenerate landmark geometry (eye points coincide, so no scale/
    rotation can be estimated) — distinct from
    ``FaceLandmarksUnavailableError`` (landmarks missing/wrong shape
    entirely) in that here landmarks exist in the right shape but their
    *values* make alignment impossible.
    """

    code = "FACE_ALIGNMENT_FAILED"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__("The detected face could not be aligned into a usable crop.")


class EnrollmentSampleNoFaceDetectedError(FaceRecognitionError):
    """Stage 3's enrollment-processing policy: zero faces is a processing failure.

    Distinct from ``FaceDetectionFailedError`` (the image itself could
    not be processed at all) — here detection succeeded and legitimately
    found no face, which for an enrollment sample is still not usable.
    """

    code = "ENROLLMENT_SAMPLE_NO_FACE_DETECTED"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__("No face was detected in this enrollment sample.")


class EnrollmentSampleMultipleFacesDetectedError(FaceRecognitionError):
    """Stage 3's enrollment-processing policy: more than one face is a processing failure.

    This codebase never silently picks one face out of a multi-face
    enrollment photo (Stage 3 brief, instruction 3) — the sample must be
    replaced with a cleaner image instead.
    """

    code = "ENROLLMENT_SAMPLE_MULTIPLE_FACES_DETECTED"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__(
            "More than one face was detected in this enrollment sample; "
            "exactly one face is required."
        )


class SampleNotEligibleForProcessingError(FaceRecognitionError):
    """Raised when ``process_sample``/``retry_sample`` is called on a sample
    that is not in a state eligible for that operation.

    E.g. the sample is not ``ACTIVE`` (still ``PENDING``, or already
    ``DELETION_PENDING``/``QUARANTINED``/``DELETED``), or
    ``process_sample`` is called on a sample that is already
    ``PROCESSED`` (use ``retry_sample`` — and only on a
    ``PROCESSING_FAILED`` sample — instead).
    """

    code = "SAMPLE_NOT_ELIGIBLE_FOR_PROCESSING"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self, reason: str) -> None:
        super().__init__(
            "This biometric sample is not eligible for that processing operation.",
            details={"reason": reason},
        )


class ModelArtifactMissingError(FaceRecognitionError):
    """A configured model file does not exist on disk.

    Never includes the configured path in the client-facing message —
    see this module's docstring on provider-diagnostics restrictions.
    """

    code = "FACE_MODEL_ARTIFACT_MISSING"
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    def __init__(self) -> None:
        super().__init__("A required face-recognition model artifact is not available.")


class ModelArtifactChecksumMismatchError(FaceRecognitionError):
    """A configured model file exists but its SHA-256 does not match.

    Never includes either the expected or actual checksum in the
    client-facing message (server-side structured log only).
    """

    code = "FACE_MODEL_ARTIFACT_CHECKSUM_MISMATCH"
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    def __init__(self) -> None:
        super().__init__("A face-recognition model artifact failed integrity verification.")


class CandidateEmbeddingDimensionMismatchError(FaceRecognitionError):
    """A candidate embedding offered to a matcher has the wrong dimension.

    A real configuration/data inconsistency (e.g. a leftover embedding
    from a since-changed embedding model) — fails loudly rather than
    silently skipping the candidate, since that would silently shrink
    the search space without telling anyone.
    """

    code = "FACE_CANDIDATE_EMBEDDING_DIMENSION_MISMATCH"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self, *, expected: int, actual: int) -> None:
        super().__init__(
            f"Candidate embedding dimension mismatch: expected {expected}, got {actual}."
        )


class CandidateScopeRequiredError(FaceRecognitionError):
    """Raised when a match is attempted with no explicit candidate scope.

    The direct enforcement point for the Stage 3 brief's "global
    unscoped matching rejected" requirement: a caller must supply a
    non-empty, explicit list of student IDs (or a resolved roster) —
    there is no code path that matches against "everyone".
    """

    code = "FACE_MATCH_CANDIDATE_SCOPE_REQUIRED"
    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self) -> None:
        super().__init__("A match request must supply an explicit, non-empty candidate scope.")


class SampleStorageFileMissingError(FaceRecognitionError):
    """The stored image file for a sample being processed could not be found.

    An infrastructure-drift condition (see
    ``app.modules.biometric_enrollment.reconciliation``'s own similarly-
    named concern) rather than a client input problem — still modeled
    as an ``AppError`` (unlike genuine disk-full/permission-denied
    failures elsewhere in this codebase) because it is a well-understood,
    specifically-anticipated failure mode of one specific operation
    (processing a sample), not an arbitrary infrastructure fault.
    """

    code = "FACE_SAMPLE_STORAGE_FILE_MISSING"
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    def __init__(self) -> None:
        super().__init__("The stored image for this sample could not be found.")


class SampleImageDecodeFailedError(FaceRecognitionError):
    """A sample's stored file could not be decoded as an image during processing.

    Should be rare in practice — Stage 2's ``image_validation.py``
    already rejected undecodable uploads at enrollment time — but
    Stage 3 decodes independently (a stored file could theoretically be
    corrupted at rest between enrollment and processing) and must fail
    predictably rather than raising a raw Pillow exception.
    """

    code = "FACE_SAMPLE_IMAGE_DECODE_FAILED"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__("The stored image for this sample could not be decoded.")


# --- match-probe image validation (Stage 3 correction) ----------------------
#
# Provider-neutral errors for the in-memory ``/match-probe`` upload path.
# Deliberately named ``MatchProbeImage*`` rather than reusing
# ``app.modules.biometric_enrollment.errors.Enrollment*`` — a probe image is
# never staged, never persisted, and has nothing to do with enrollment, so
# leaking the ``ENROLLMENT_IMAGE_*`` error codes through this API would be
# misleading to a client and would wrongly couple the two modules' public
# contracts. See ``app.modules.face_recognition.match_probe_validation``,
# which shares its actual decode/bomb/format/dimension/animated checks with
# Stage 2's ``image_validation.py`` (same protection class, translated to
# these error types instead).


class MatchProbeImageEmptyError(FaceRecognitionError):
    code = "FACE_MATCH_PROBE_IMAGE_EMPTY"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__("The uploaded probe image is empty.")


class MatchProbeImageTooLargeError(FaceRecognitionError):
    """Encoded byte size exceeds the probe upload cap.

    Distinct from ``MatchProbeImageDimensionsTooLargeError``, which is a
    *decoded-content* rejection (pixel count/width/height/decompression
    bomb) — this one fires before any decoding happens at all, from the
    raw encoded byte count alone.
    """

    code = "FACE_MATCH_PROBE_IMAGE_TOO_LARGE"
    status_code = status.HTTP_413_CONTENT_TOO_LARGE

    def __init__(self, max_bytes: int) -> None:
        super().__init__(
            f"The uploaded probe image exceeds the {max_bytes}-byte limit.",
            details={"max_bytes": max_bytes},
        )


class MatchProbeImageDecodeError(FaceRecognitionError):
    code = "FACE_MATCH_PROBE_IMAGE_DECODE_FAILED"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__("The uploaded probe image is not a valid, decodable image.")


class MatchProbeImageFormatNotAllowedError(FaceRecognitionError):
    code = "FACE_MATCH_PROBE_IMAGE_FORMAT_NOT_ALLOWED"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self, allowed: frozenset[str]) -> None:
        super().__init__(
            "The uploaded probe image format is not allowed.",
            details={"allowed_formats": sorted(allowed)},
        )


class MatchProbeImageDimensionsInvalidError(FaceRecognitionError):
    code = "FACE_MATCH_PROBE_IMAGE_DIMENSIONS_INVALID"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__("The uploaded probe image has invalid (non-positive) dimensions.")


class MatchProbeImageDimensionsTooLargeError(FaceRecognitionError):
    code = "FACE_MATCH_PROBE_IMAGE_DIMENSIONS_TOO_LARGE"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__(
            "The uploaded probe image's dimensions exceed the maximum allowed "
            "(this also guards against decompression-bomb-style images)."
        )


class MatchProbeImageAnimatedNotAllowedError(FaceRecognitionError):
    code = "FACE_MATCH_PROBE_IMAGE_ANIMATED_NOT_ALLOWED"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__("Animated/multi-frame images are not allowed for a match probe.")


class MatchProbeImageMimeMismatchError(FaceRecognitionError):
    code = "FACE_MATCH_PROBE_IMAGE_MIME_MISMATCH"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__(
            "The declared content type does not match the probe image's actual, decoded format."
        )


# --- Stage 4 recognition-attendance lifecycle ------------------------------


class RecognitionAttendanceRosterEmptyError(FaceRecognitionError):
    code = "RECOGNITION_ATTENDANCE_ROSTER_EMPTY"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self) -> None:
        super().__init__("The authorized classroom has no active students to recognize.")


class RecognitionAttendanceTooManyFacesError(FaceRecognitionError):
    code = "RECOGNITION_ATTENDANCE_TOO_MANY_FACES"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self, max_faces: int) -> None:
        super().__init__(
            "The attendance image contains more faces than this review allows.",
            details={"max_faces": max_faces},
        )


class RecognitionAttendanceReviewNotFoundError(FaceRecognitionError):
    code = "RECOGNITION_ATTENDANCE_REVIEW_NOT_FOUND"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self) -> None:
        super().__init__("Recognition attendance review not found.")


class RecognitionAttendanceReviewConfirmationConflictError(FaceRecognitionError):
    code = "RECOGNITION_ATTENDANCE_REVIEW_CONFIRMATION_CONFLICT"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self) -> None:
        super().__init__("This review was already confirmed with different attendance statuses.")


class RecognitionAttendanceAttemptNotFoundError(FaceRecognitionError):
    code = "RECOGNITION_ATTENDANCE_ATTEMPT_NOT_FOUND"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self) -> None:
        super().__init__("Recognition attendance attempt not found.")


class RecognitionAttendanceConfirmationNotAllowedError(FaceRecognitionError):
    code = "RECOGNITION_ATTENDANCE_CONFIRMATION_NOT_ALLOWED"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self) -> None:
        super().__init__("This recognition decision does not allow manual confirmation.")


class RecognitionAttendanceConfirmationConflictError(FaceRecognitionError):
    code = "RECOGNITION_ATTENDANCE_CONFIRMATION_CONFLICT"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self) -> None:
        super().__init__("This recognition attempt was already confirmed for another student.")


class RecognitionAttendanceStudentNotInRosterError(FaceRecognitionError):
    code = "RECOGNITION_ATTENDANCE_STUDENT_NOT_IN_ROSTER"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__("The selected student is not in the authorized classroom roster.")


class RecognitionAttendanceMatchOutsideRosterError(FaceRecognitionError):
    code = "RECOGNITION_ATTENDANCE_MATCH_OUTSIDE_ROSTER"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self) -> None:
        super().__init__("The recognition result is not valid for the authorized roster.")
