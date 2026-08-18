"""Provider/model health reporting — Phase 5 Stage 3.

Implements the Stage 3 brief's "provider health" requirement using the
Stage 1 ``ProviderHealth``/``ProviderStatus`` contracts
(``app.modules.face_recognition.domain`` — unchanged from Stage 1,
already safe-metadata-only by construction).

**A health check never runs recognition against a student's biometric
image** (Stage 3 brief, instruction 12): the readiness probes below
(``YuNetFaceDetector.is_available``/``DlibResnetFaceEmbedder.is_available``)
only validate that a model *file* is present (and checksum-correct, if
configured) and that the underlying library can load it into memory —
no image, real or synthetic, is ever passed through either provider
here.

**Never returned:** filesystem absolute paths, embeddings, raw
exceptions, secrets — every ``ProviderHealth.detail`` value below is a
short, fixed, pre-written string, never an f-string interpolating
anything path- or exception-derived.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.core.config import FaceRecognitionProvider, Settings
from app.modules.face_recognition.domain import ProviderHealth, ProviderStatus
from app.modules.face_recognition.provider_factory import get_detector, get_embedder


class FaceRecognitionHealth(BaseModel):
    """Combined detector + embedder health, plus one overall status."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    overall_status: ProviderStatus
    detector: ProviderHealth
    embedder: ProviderHealth


def get_face_recognition_health(settings: Settings) -> FaceRecognitionHealth:
    if settings.FACE_RECOGNITION_PROVIDER is FaceRecognitionProvider.NONE:
        not_configured = ProviderHealth(
            provider_name="face_recognition",
            status=ProviderStatus.NOT_CONFIGURED,
            detail="Face recognition is not enabled for this deployment.",
        )
        return FaceRecognitionHealth(
            overall_status=ProviderStatus.NOT_CONFIGURED,
            detector=not_configured,
            embedder=not_configured,
        )

    detector_health = _detector_health(settings)
    embedder_health = _embedder_health(settings)

    if (
        detector_health.status is ProviderStatus.READY
        and embedder_health.status is ProviderStatus.READY
    ):
        overall = ProviderStatus.READY
    elif (
        detector_health.status is ProviderStatus.NOT_CONFIGURED
        or embedder_health.status is ProviderStatus.NOT_CONFIGURED
    ):
        overall = ProviderStatus.NOT_CONFIGURED
    else:
        overall = ProviderStatus.UNAVAILABLE

    return FaceRecognitionHealth(
        overall_status=overall, detector=detector_health, embedder=embedder_health
    )


def _detector_health(settings: Settings) -> ProviderHealth:
    model_path = (settings.FACE_DETECTOR_MODEL_PATH or "").strip()
    if not model_path:
        return ProviderHealth(
            provider_name="yunet_opencv_local",
            status=ProviderStatus.NOT_CONFIGURED,
            detail="No detector model path is configured.",
        )
    detector = get_detector(settings)
    if detector.is_available():
        return ProviderHealth(provider_name="yunet_opencv_local", status=ProviderStatus.READY)
    return ProviderHealth(
        provider_name="yunet_opencv_local",
        status=ProviderStatus.UNAVAILABLE,
        detail="Detector model could not be loaded.",
    )


def _embedder_health(settings: Settings) -> ProviderHealth:
    model_path = (settings.FACE_EMBEDDER_MODEL_PATH or "").strip()
    if not model_path:
        return ProviderHealth(
            provider_name="dlib_resnet_v1_local",
            status=ProviderStatus.NOT_CONFIGURED,
            detail="No embedder model path is configured.",
        )
    embedder = get_embedder(settings)
    if embedder.is_available():
        return ProviderHealth(provider_name="dlib_resnet_v1_local", status=ProviderStatus.READY)
    return ProviderHealth(
        provider_name="dlib_resnet_v1_local",
        status=ProviderStatus.UNAVAILABLE,
        detail="Embedder model could not be loaded.",
    )
