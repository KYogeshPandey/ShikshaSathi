"""YuNet ``FaceDetector`` provider adapter — Phase 5 Stage 3.

Implements ``app.modules.face_recognition.protocols.FaceDetector``
using OpenCV's ``cv2.FaceDetectorYN`` (per ADR 0005's accepted
decision: YuNet, loaded via OpenCV's own DNN/ONNX importer,
``opencv-python-headless`` only — no separate ``onnxruntime``
dependency for detection). No OpenCV type (``cv2.Mat``, the raw
``numpy.ndarray`` returned by ``detect()``) ever crosses back out of
this module — every public method returns only
``app.modules.face_recognition.domain`` value objects or raises this
module's typed errors.

**Lazy loading (Stage 3 brief, instruction 2):** the underlying
``cv2.FaceDetectorYN`` instance is created on first use, not at import
time or construction time of this adapter — see ``_ensure_loaded``.
This keeps importing this module (e.g. for a health check that only
wants to verify the model *file* exists) cheap, and keeps a missing/
corrupt model file a predictable, catchable failure at first real use
rather than a crash during application startup for deployments that
never actually enable face recognition
(``Settings.FACE_RECOGNITION_PROVIDER == "none"``).

**Model artifact validation** (existence + optional SHA-256) happens
via ``app.modules.face_recognition.model_artifacts.verify_model_artifact``
before ``cv2.FaceDetectorYN.create`` is ever called — a missing or
tampered model file fails predictably with a typed, provider-neutral
error (``ModelArtifactMissingError`` / ``ModelArtifactChecksumMismatchError``)
rather than whatever internal error OpenCV itself would raise.

**Bounding-box/landmark clipping:** YuNet can report a box or landmark
point marginally outside the source image due to floating-point
rounding near an edge. Every value returned here is clamped into
``[0, width)``/``[0, height)`` (landmarks) or shrunk so the box fits
entirely within the image (bounding box) *before* constructing a
``DetectedFace`` — ``DetectedFace``'s own validator
(``app.modules.face_recognition.domain``) would otherwise reject an
out-of-bounds box outright, which is not the right failure mode for a
one-pixel rounding artifact from the detector itself.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import ClassVar

import cv2
import numpy as np
import structlog

from app.core.config import Settings
from app.modules.face_recognition.domain import (
    BoundingBox,
    DecodedImage,
    DetectedFace,
    FacialLandmark,
    ImageDimensions,
)
from app.modules.face_recognition.errors import (
    FaceDetectionFailedError,
    FaceProviderUnavailableError,
)
from app.modules.face_recognition.image_codec import decoded_image_to_ndarray, to_bgr
from app.modules.face_recognition.model_artifacts import verify_model_artifact

logger = structlog.get_logger(__name__)

#: YuNet's own fixed output column layout — see this module's docstring
#: and ``cv2.FaceDetectorYN.detect``'s own documentation.
_LANDMARK_COLUMN_PAIRS: tuple[tuple[int, int], ...] = (
    (4, 5),  # right eye
    (6, 7),  # left eye
    (8, 9),  # nose tip
    (10, 11),  # right mouth corner
    (12, 13),  # left mouth corner
)

# Conservative, documented (not tuned against this project's own data —
# see ADR 0005's "Accuracy: explicitly not claimed") defaults for the
# two YuNet-specific knobs this adapter does not currently expose as
# Settings fields, since Stage 3's brief lists only input size, model
# path/checksum, threshold, and batch limit as the fields to add.
_NMS_THRESHOLD = 0.3
_TOP_K = 500
# YuNet's own score is already a reasonable per-detection confidence in
# [0, 1]; a permissive score_threshold here (rather than 0) lets this
# adapter surface every plausible detection and leaves the "is this
# confident enough" decision to callers (e.g. Stage 3's sample-
# processing service, or a future Stage 4 caller), consistent with
# this module never conflating detector confidence with matcher
# similarity (see ``DetectedFace.confidence``'s own docstring).
_SCORE_THRESHOLD = 0.5


class YuNetFaceDetector:
    """Loads a YuNet ``.onnx`` model lazily and detects faces via OpenCV.

    One instance is safe to reuse across many ``detect()`` calls (the
    underlying model is loaded once); it is not safe to share across
    threads calling ``detect()`` concurrently, matching OpenCV's own
    documented thread-safety posture for a single ``cv2.dnn``-backed
    object.

    **Stage 3 correction (finding 3):** callers on the FastAPI request
    path (``processing_service.py``, ``router.py``'s ``match_probe``)
    run this adapter's work off the event loop via ``asyncio.to_thread``
    — but ``asyncio.to_thread`` dispatches to a shared thread pool, so
    two concurrent requests can still land on two different worker
    threads and call into the *same cached* ``YuNetFaceDetector``
    instance (provider instances are cached per
    ``app.modules.face_recognition.provider_factory``) at the same
    time. ``self._lock`` (a process-local, per-instance
    ``threading.RLock``, not a global lock shared with unrelated
    providers) serializes every entry into ``_ensure_loaded``/
    ``detect`` on *this* instance so that never happens — an ``RLock``
    (not a plain ``Lock``) because ``detect`` itself calls
    ``_ensure_loaded`` while already holding the lock.
    """

    provider_name: ClassVar[str] = "yunet_opencv_local"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._detector: cv2.FaceDetectorYN | None = None
        self._loaded_input_size: tuple[int, int] | None = None
        self._lock = threading.RLock()

    def _ensure_loaded(self) -> cv2.FaceDetectorYN:
        with self._lock:
            if self._detector is not None:
                return self._detector

            model_path = (self._settings.FACE_DETECTOR_MODEL_PATH or "").strip()
            if not model_path:
                raise FaceProviderUnavailableError()

            # Raises ModelArtifactMissingError / ModelArtifactChecksumMismatchError
            # (both FaceRecognitionError subclasses) on a bad artifact.
            verify_model_artifact(
                Path(model_path), expected_sha256=self._settings.FACE_DETECTOR_MODEL_SHA256
            )

            input_size = (
                self._settings.FACE_DETECTOR_INPUT_SIZE_PX,
                self._settings.FACE_DETECTOR_INPUT_SIZE_PX,
            )
            try:
                detector = cv2.FaceDetectorYN.create(
                    model_path,
                    "",
                    input_size,
                    _SCORE_THRESHOLD,
                    _NMS_THRESHOLD,
                    _TOP_K,
                )
            except cv2.error as exc:
                logger.error("yunet_detector_load_failed", exc_type=type(exc).__name__)
                raise FaceProviderUnavailableError() from exc

            self._detector = detector
            self._loaded_input_size = input_size
            return detector

    def is_available(self) -> bool:
        """Cheap readiness probe used by health reporting.

        Attempts the same lazy load ``detect()`` would, but performs no
        inference against any image — see
        ``app.modules.face_recognition.health``'s own docstring on why
        a health check must not run recognition against real biometric
        data. Returns ``False`` (never raises) so a caller can build a
        ``ProviderHealth`` from this without its own try/except.

        This still performs blocking model-file I/O (via
        ``_ensure_loaded``) — callers on the FastAPI request path must
        run it via ``asyncio.to_thread`` (see
        ``app.modules.face_recognition.health.get_face_recognition_health``).
        """
        try:
            self._ensure_loaded()
        except Exception:
            return False
        return True

    def detect(self, image: DecodedImage) -> list[DetectedFace]:
        with self._lock:
            detector = self._ensure_loaded()

            width, height = image.dimensions.width_px, image.dimensions.height_px
            if (width, height) != self._loaded_input_size:
                detector.setInputSize((width, height))
                self._loaded_input_size = (width, height)

            try:
                source_array = decoded_image_to_ndarray(image)
                bgr = to_bgr(source_array, color_format=image.color_format)
                _retval, raw_faces = detector.detect(bgr)
            except (cv2.error, ValueError) as exc:
                raise FaceDetectionFailedError() from exc

        if raw_faces is None:
            return []

        detections: list[DetectedFace] = []
        for row in np.asarray(raw_faces, dtype=np.float64):
            detections.append(self._row_to_detected_face(row, dimensions=image.dimensions))
        return detections

    def _row_to_detected_face(
        self, row: np.ndarray, *, dimensions: ImageDimensions
    ) -> DetectedFace:
        x, y, w, h = (float(value) for value in row[0:4])
        raw_score = float(row[14])

        x0 = _clamp(x, 0.0, float(dimensions.width_px))
        y0 = _clamp(y, 0.0, float(dimensions.height_px))
        x1 = _clamp(x + w, 0.0, float(dimensions.width_px))
        y1 = _clamp(y + h, 0.0, float(dimensions.height_px))

        # Clamped to a minimum 1x1 rather than dropped: at this single
        # row's level there is no reliable way to distinguish "YuNet
        # found a genuinely tiny face right at the image's edge" from
        # "this box is a rounding artifact" — returning a minimal valid
        # box (never a zero-area one, which BoundingBox's own validator
        # would reject outright) lets alignment's own landmark-geometry
        # check be the actual arbiter of whether this detection is
        # usable, rather than silently discarding a row here.
        clipped_width = max(1, round(x1 - x0))
        clipped_height = max(1, round(y1 - y0))
        int_x0 = min(round(x0), dimensions.width_px - clipped_width)
        int_y0 = min(round(y0), dimensions.height_px - clipped_height)
        int_x0 = max(0, int_x0)
        int_y0 = max(0, int_y0)

        bounding_box = BoundingBox(
            x_px=int_x0, y_px=int_y0, width_px=clipped_width, height_px=clipped_height
        )

        landmarks = tuple(
            FacialLandmark(
                x_px=_clamp(float(row[col_x]), 0.0, float(dimensions.width_px - 1)),
                y_px=_clamp(float(row[col_y]), 0.0, float(dimensions.height_px - 1)),
            )
            for col_x, col_y in _LANDMARK_COLUMN_PAIRS
        )

        confidence = _clamp(raw_score, 0.0, 1.0)
        if not np.isfinite(confidence):
            confidence = 0.0

        return DetectedFace(
            bounding_box=bounding_box,
            source_image_dimensions=dimensions,
            confidence=confidence,
            landmarks=landmarks,
        )


def _clamp(value: float, low: float, high: float) -> float:
    if not np.isfinite(value):
        return low
    return max(low, min(high, value))
