"""Tests for ``app.modules.face_recognition.alignment`` (Phase 5 Stage 3).

Pure-logic tests: no database, no HTTP, no real detector/embedder model
file. Uses real OpenCV geometric-transform code
(``cv2.estimateAffinePartial2D``/``cv2.warpAffine`` — no DNN/ONNX model
involved, so no model artifact is needed) against hand-built
``DecodedImage``/``DetectedFace`` fixtures from
``app.tests.phase5_stage3_helpers``.
"""

from __future__ import annotations

import pytest

from app.modules.face_recognition.alignment import ALIGNED_FACE_SIZE_PX, align_face
from app.modules.face_recognition.domain import FacialLandmark, ImageDimensions
from app.modules.face_recognition.errors import (
    FaceAlignmentFailedError,
    FaceLandmarksUnavailableError,
)
from app.modules.face_recognition.image_codec import normalized_face_input_to_ndarray
from app.tests.phase5_stage3_helpers import make_decoded_image, make_detected_face


def test_align_face_with_valid_landmarks_produces_fixed_size_rgb_chip() -> None:
    image = make_decoded_image()
    face = make_detected_face(with_landmarks=True)

    result = align_face(image, face)

    assert result.dimensions.width_px == ALIGNED_FACE_SIZE_PX
    assert result.dimensions.height_px == ALIGNED_FACE_SIZE_PX
    assert result.color_format == image.color_format == "rgb"

    array = normalized_face_input_to_ndarray(result)
    assert array.shape == (ALIGNED_FACE_SIZE_PX, ALIGNED_FACE_SIZE_PX, 3)
    assert array.dtype.name == "uint8"


def test_align_face_output_shape_is_deterministic_across_calls() -> None:
    image = make_decoded_image()
    face = make_detected_face(with_landmarks=True)

    first = align_face(image, face)
    second = align_face(image, face)

    # Same input geometry -> byte-identical output (no randomness anywhere
    # in the alignment pipeline).
    assert first.pixel_data == second.pixel_data
    assert first.dimensions == second.dimensions


def test_align_face_preserves_bgr_color_format_without_conversion() -> None:
    image = make_decoded_image(color_format="bgr")
    face = make_detected_face(with_landmarks=True)

    result = align_face(image, face)

    assert result.color_format == "bgr"


def test_align_face_raises_when_landmarks_missing() -> None:
    image = make_decoded_image()
    face = make_detected_face(with_landmarks=False)

    with pytest.raises(FaceLandmarksUnavailableError):
        align_face(image, face)


def test_align_face_raises_when_landmark_count_is_wrong() -> None:
    image = make_decoded_image()
    face = make_detected_face(with_landmarks=True)
    # Rebuild with only 3 landmarks (still passes DetectedFace's own
    # 1..68 structural bound, but is not YuNet's 5-point layout).
    truncated = face.model_copy(update={"landmarks": face.landmarks[:3]})

    with pytest.raises(FaceLandmarksUnavailableError):
        align_face(image, truncated)


def test_align_face_raises_on_degenerate_landmark_geometry() -> None:
    """All 5 landmarks coincident -> no scale/rotation can be estimated."""
    image = make_decoded_image()
    face = make_detected_face(with_landmarks=True)
    coincident = tuple(FacialLandmark(x_px=200.0, y_px=200.0) for _ in range(5))
    degenerate = face.model_copy(update={"landmarks": coincident})

    with pytest.raises(FaceAlignmentFailedError):
        align_face(image, degenerate)


def test_align_face_handles_landmarks_near_source_image_edge() -> None:
    """A face near the image border should still produce a full-size chip
    (out-of-bounds source pixels become black padding, not a crash) —
    see alignment.py's "Crop padding / clipping at image edges" policy."""
    dims = ImageDimensions(width_px=100, height_px=100)
    image = make_decoded_image(dimensions=dims)
    landmarks = (
        FacialLandmark(x_px=5.0, y_px=5.0),
        FacialLandmark(x_px=25.0, y_px=5.0),
        FacialLandmark(x_px=15.0, y_px=15.0),
        FacialLandmark(x_px=8.0, y_px=25.0),
        FacialLandmark(x_px=22.0, y_px=25.0),
    )
    face = make_detected_face(dimensions=dims, with_landmarks=True).model_copy(
        update={"landmarks": landmarks, "source_image_dimensions": dims}
    )

    result = align_face(image, face)

    assert result.dimensions.width_px == ALIGNED_FACE_SIZE_PX
    assert result.dimensions.height_px == ALIGNED_FACE_SIZE_PX
