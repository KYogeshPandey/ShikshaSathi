"""Shared detect -> require-exactly-one-face -> align -> embed pipeline step.

Factored out so both
``app.modules.face_recognition.processing_service`` (processing a
stored Stage 2 enrollment sample) and
``app.modules.face_recognition.router``'s optional match-probe
endpoint (embedding an ad hoc uploaded probe image, to validate the
matching pipeline — Stage 3 brief §14) run the *exact* same detection/
alignment/embedding logic and enforce the *exact* same "exactly one
face" policy, rather than two call sites drifting apart over time.

Raises exactly the typed errors documented on
``app.modules.face_recognition.errors``:
``EnrollmentSampleNoFaceDetectedError``/
``EnrollmentSampleMultipleFacesDetectedError`` for the face-count
policy (the name is Stage-2-sample-flavored, but the same "exactly one
face" policy applies equally to a probe image — Stage 3 brief
instruction 3 does not distinguish the two), plus whatever
``FaceDetectionFailedError``/``FaceLandmarksUnavailableError``/
``FaceAlignmentFailedError``/``FaceEmbeddingFailedError`` the
individual stages raise.
"""

from __future__ import annotations

from app.core.config import Settings
from app.modules.face_recognition.alignment import align_face
from app.modules.face_recognition.domain import (
    DecodedImage,
    EmbeddingVector,
    validate_embedding_dimension,
)
from app.modules.face_recognition.errors import (
    EnrollmentSampleMultipleFacesDetectedError,
    EnrollmentSampleNoFaceDetectedError,
    RecognitionAttendanceTooManyFacesError,
)
from app.modules.face_recognition.provider_factory import get_detector, get_embedder


def detect_align_embed(image: DecodedImage, *, settings: Settings) -> EmbeddingVector:
    """Run the full detect -> align -> embed pipeline against one decoded image.

    Requires exactly one detected face — zero or multiple both raise
    (see this module's docstring) rather than picking one.
    """
    detector = get_detector(settings)
    faces = detector.detect(image)

    if len(faces) == 0:
        raise EnrollmentSampleNoFaceDetectedError()
    if len(faces) > 1:
        raise EnrollmentSampleMultipleFacesDetectedError()

    normalized_face = align_face(image, faces[0])

    embedder = get_embedder(settings)
    embedding = embedder.embed(normalized_face)
    return validate_embedding_dimension(
        embedding, expected_dimension=settings.FACE_EMBEDDING_DIMENSION
    )


def detect_align_embed_many(
    image: DecodedImage,
    *,
    settings: Settings,
) -> list[EmbeddingVector]:
    """Embed every detected attendance face, preserving detector order.

    Unlike enrollment and diagnostic probes, zero faces is a valid review
    outcome. The configured upper bound prevents unbounded CPU work.
    """
    detector = get_detector(settings)
    faces = detector.detect(image)
    if len(faces) > settings.MAX_ATTENDANCE_FACES_PER_IMAGE:
        raise RecognitionAttendanceTooManyFacesError(settings.MAX_ATTENDANCE_FACES_PER_IMAGE)

    embedder = get_embedder(settings)
    embeddings: list[EmbeddingVector] = []
    for face in faces:
        normalized_face = align_face(image, face)
        embeddings.append(
            validate_embedding_dimension(
                embedder.embed(normalized_face),
                expected_dimension=settings.FACE_EMBEDDING_DIMENSION,
            )
        )
    return embeddings
