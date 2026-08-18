"""Tests for ``app.modules.face_recognition.providers.yunet_detector.YuNetFaceDetector``.

No real ``.onnx`` model file is used anywhere in this file — ``cv2``
itself is real (this sandbox has ``opencv-python-headless`` installed),
but ``cv2.FaceDetectorYN.create`` is monkeypatched to return a small
fake object with the same ``setInputSize``/``detect`` surface, so these
tests exercise this adapter's own logic (model-artifact validation,
row-parsing, clamping, error mapping) deterministically without a real
model artifact. Confirmed patchable directly against the real ``cv2``
module in this sandbox (a native/compiled type) before relying on it
here.
"""

from __future__ import annotations

import hashlib
from unittest.mock import patch

import cv2
import numpy as np
import pytest

from app.modules.face_recognition.domain import ImageDimensions
from app.modules.face_recognition.errors import (
    FaceDetectionFailedError,
    FaceProviderUnavailableError,
    ModelArtifactChecksumMismatchError,
    ModelArtifactMissingError,
)
from app.modules.face_recognition.providers.yunet_detector import YuNetFaceDetector
from app.tests.phase5_stage3_helpers import make_decoded_image


class _SettingsLike:
    def __init__(
        self,
        *,
        model_path: str | None,
        model_sha256: str | None = None,
        input_size: int = 320,
    ) -> None:
        self.FACE_DETECTOR_MODEL_PATH = model_path
        self.FACE_DETECTOR_MODEL_SHA256 = model_sha256
        self.FACE_DETECTOR_INPUT_SIZE_PX = input_size


class _FakeCvDetector:
    """Stands in for ``cv2.FaceDetectorYN`` — returns a pre-set faces array."""

    def __init__(self, faces_array: np.ndarray | None) -> None:
        self._faces = faces_array
        self.set_input_size_calls: list[tuple[int, int]] = []

    def setInputSize(self, size: tuple[int, int]) -> None:
        self.set_input_size_calls.append(size)

    def detect(self, image: np.ndarray) -> tuple[int, np.ndarray | None]:
        return (1, self._faces)


def _make_model_file(tmp_path, content: bytes = b"fake-onnx-model-bytes") -> str:
    path = tmp_path / "yunet.onnx"
    path.write_bytes(content)
    return str(path)


def _yunet_row(
    *, x: float, y: float, w: float, h: float, score: float, landmark_offset: float = 0.0
) -> list[float]:
    """One YuNet detection row: [x, y, w, h, 5x(lx,ly), score] — 15 columns."""
    landmarks = []
    for i in range(5):
        landmarks.extend([x + w * 0.3 + i * 2 + landmark_offset, y + h * 0.3 + i])
    return [x, y, w, h, *landmarks, score]


def test_detect_raises_missing_model_error_when_path_unset() -> None:
    detector = YuNetFaceDetector(_SettingsLike(model_path=None))
    with pytest.raises(FaceProviderUnavailableError):
        detector.detect(make_decoded_image())


def test_detect_raises_missing_model_error_when_file_does_not_exist(tmp_path) -> None:
    missing_path = str(tmp_path / "does-not-exist.onnx")
    detector = YuNetFaceDetector(_SettingsLike(model_path=missing_path))
    with pytest.raises(ModelArtifactMissingError):
        detector.detect(make_decoded_image())


def test_detect_raises_checksum_mismatch_error(tmp_path) -> None:
    model_path = _make_model_file(tmp_path)
    wrong_checksum = "0" * 64
    detector = YuNetFaceDetector(_SettingsLike(model_path=model_path, model_sha256=wrong_checksum))
    with pytest.raises(ModelArtifactChecksumMismatchError):
        detector.detect(make_decoded_image())


def test_detect_succeeds_with_correct_checksum(tmp_path) -> None:
    content = b"fake-onnx-model-bytes"
    model_path = _make_model_file(tmp_path, content)
    correct_checksum = hashlib.sha256(content).hexdigest()
    detector = YuNetFaceDetector(
        _SettingsLike(model_path=model_path, model_sha256=correct_checksum)
    )
    fake_cv = _FakeCvDetector(faces_array=None)
    with patch("cv2.FaceDetectorYN.create", return_value=fake_cv):
        result = detector.detect(make_decoded_image())
    assert result == []


def test_detect_raises_provider_unavailable_on_corrupt_unloadable_model(tmp_path) -> None:
    model_path = _make_model_file(tmp_path)
    detector = YuNetFaceDetector(_SettingsLike(model_path=model_path))

    def _raise_cv_error(*args, **kwargs):
        raise cv2.error("could not parse model")

    with (
        patch("cv2.FaceDetectorYN.create", side_effect=_raise_cv_error),
        pytest.raises(FaceProviderUnavailableError),
    ):
        detector.detect(make_decoded_image())


def test_is_available_returns_false_without_raising_on_missing_model() -> None:
    detector = YuNetFaceDetector(_SettingsLike(model_path=None))
    assert detector.is_available() is False


def test_is_available_returns_true_when_model_loads(tmp_path) -> None:
    model_path = _make_model_file(tmp_path)
    detector = YuNetFaceDetector(_SettingsLike(model_path=model_path))
    with patch("cv2.FaceDetectorYN.create", return_value=_FakeCvDetector(None)):
        assert detector.is_available() is True


def test_detect_returns_empty_list_for_zero_faces(tmp_path) -> None:
    model_path = _make_model_file(tmp_path)
    detector = YuNetFaceDetector(_SettingsLike(model_path=model_path))
    with patch("cv2.FaceDetectorYN.create", return_value=_FakeCvDetector(np.zeros((0, 15)))):
        result = detector.detect(make_decoded_image())
    assert result == []


def test_detect_returns_one_detected_face_with_landmarks(tmp_path) -> None:
    model_path = _make_model_file(tmp_path)
    detector = YuNetFaceDetector(_SettingsLike(model_path=model_path))
    row = _yunet_row(x=50, y=60, w=100, h=120, score=0.88)
    faces_array = np.array([row], dtype=np.float32)
    with patch("cv2.FaceDetectorYN.create", return_value=_FakeCvDetector(faces_array)):
        result = detector.detect(make_decoded_image())

    assert len(result) == 1
    face = result[0]
    assert face.landmarks is not None
    assert len(face.landmarks) == 5
    assert 0.0 <= face.confidence <= 1.0
    assert abs(face.confidence - 0.88) < 1e-4
    assert face.bounding_box.x_px == 50
    assert face.bounding_box.y_px == 60


def test_detect_returns_multiple_distinguishable_faces(tmp_path) -> None:
    model_path = _make_model_file(tmp_path)
    detector = YuNetFaceDetector(_SettingsLike(model_path=model_path))
    row_a = _yunet_row(x=10, y=10, w=50, h=60, score=0.9)
    row_b = _yunet_row(x=200, y=200, w=50, h=60, score=0.7, landmark_offset=5.0)
    faces_array = np.array([row_a, row_b], dtype=np.float32)
    with patch("cv2.FaceDetectorYN.create", return_value=_FakeCvDetector(faces_array)):
        result = detector.detect(make_decoded_image())

    assert len(result) == 2
    assert result[0].bounding_box.x_px != result[1].bounding_box.x_px
    assert result[0].confidence != result[1].confidence


def test_detect_clips_bounding_box_that_extends_past_image_edge(tmp_path) -> None:
    model_path = _make_model_file(tmp_path)
    detector = YuNetFaceDetector(_SettingsLike(model_path=model_path))
    dims = ImageDimensions(width_px=100, height_px=100)
    # A box that would extend to x=90+30=120, past the 100px-wide image.
    row = _yunet_row(x=90, y=90, w=30, h=30, score=0.8)
    faces_array = np.array([row], dtype=np.float32)
    with patch("cv2.FaceDetectorYN.create", return_value=_FakeCvDetector(faces_array)):
        result = detector.detect(make_decoded_image(dimensions=dims))

    assert len(result) == 1
    box = result[0].bounding_box
    assert box.x_px + box.width_px <= dims.width_px
    assert box.y_px + box.height_px <= dims.height_px


def test_detect_clamps_out_of_range_confidence(tmp_path) -> None:
    model_path = _make_model_file(tmp_path)
    detector = YuNetFaceDetector(_SettingsLike(model_path=model_path))
    # A score slightly above 1.0 (floating point artifact) must be
    # clamped, never raise/propagate an invalid DetectedFace.confidence.
    row = _yunet_row(x=10, y=10, w=40, h=40, score=1.0001)
    faces_array = np.array([row], dtype=np.float32)
    with patch("cv2.FaceDetectorYN.create", return_value=_FakeCvDetector(faces_array)):
        result = detector.detect(make_decoded_image())

    assert result[0].confidence <= 1.0


def test_detect_raises_on_decode_or_inference_failure(tmp_path) -> None:
    model_path = _make_model_file(tmp_path)
    detector = YuNetFaceDetector(_SettingsLike(model_path=model_path))

    class _RaisingCvDetector(_FakeCvDetector):
        def detect(self, image: np.ndarray) -> tuple[int, np.ndarray | None]:
            raise cv2.error("bad input")

    with (
        patch("cv2.FaceDetectorYN.create", return_value=_RaisingCvDetector(None)),
        pytest.raises(FaceDetectionFailedError),
    ):
        detector.detect(make_decoded_image())


def test_detect_result_type_is_pure_domain_object_no_opencv_leak(tmp_path) -> None:
    """No cv2/numpy type crosses back out of the adapter — every returned
    field is a plain Python int/float, and the DetectedFace/BoundingBox/
    FacialLandmark objects are this codebase's own domain types."""
    model_path = _make_model_file(tmp_path)
    detector = YuNetFaceDetector(_SettingsLike(model_path=model_path))
    row = _yunet_row(x=10, y=10, w=40, h=40, score=0.9)
    faces_array = np.array([row], dtype=np.float32)
    with patch("cv2.FaceDetectorYN.create", return_value=_FakeCvDetector(faces_array)):
        result = detector.detect(make_decoded_image())

    face = result[0]
    assert type(face.confidence) is float
    assert type(face.bounding_box.x_px) is int
    assert not isinstance(face.confidence, np.floating)
    assert all(type(lm.x_px) is float for lm in face.landmarks)
