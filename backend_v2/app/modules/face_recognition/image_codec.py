"""Internal ``numpy.ndarray`` <-> domain-object conversion helpers.

**New in Phase 5 Stage 3.** ``app.modules.face_recognition.domain``
deliberately stores image/face pixel data as opaque ``bytes`` (see that
module's docstring: "Deliberately dependency-free" — Stage 1 added zero
new dependencies). Once real detection/alignment/embedding code exists,
*something* has to turn those bytes into a numeric array a real
provider (OpenCV, dlib) can operate on, and back again. This module is
that one place: every Stage 3 provider adapter and ``alignment.py``
imports from here rather than each re-implementing its own packing
convention, so the on-the-wire byte layout used by ``DecodedImage``/
``NormalizedFaceInput`` stays consistent project-wide.

**Convention:** ``pixel_data`` is always a C-contiguous, row-major
``(height, width, 3)`` ``uint8`` array's raw bytes (``array.tobytes()``),
channel order given by ``color_format`` ("rgb" or "bgr"). No alpha
channel, no float dtype, no planar layout — this application never
needs any of those for face detection/alignment/embedding, so
supporting them would just be unexercised complexity.

This module raises no ``AppError`` of its own: a malformed
``pixel_data`` (wrong byte length for its claimed dimensions) is a
programming-error-shaped bug in whichever internal caller constructed
the ``DecodedImage``/``NormalizedFaceInput`` in the first place — for
example ``app.modules.face_recognition.processing_service`` decoding a
stored file — never something reachable from external/client input, so
a plain ``ValueError`` (not a client-facing ``AppError``) is
appropriate here.
"""

from __future__ import annotations

from typing import Literal

import numpy as np

from app.modules.face_recognition.domain import (
    DecodedImage,
    ImageDimensions,
    NormalizedFaceInput,
)

_CHANNELS = 3


def ndarray_to_decoded_image(
    array: np.ndarray, *, color_format: Literal["rgb", "bgr"] = "rgb"
) -> DecodedImage:
    """Pack an ``(H, W, 3)`` ``uint8`` array into a ``DecodedImage``."""

    normalized = _normalize_array(array)
    height, width, _ = normalized.shape
    return DecodedImage(
        dimensions=ImageDimensions(width_px=width, height_px=height),
        pixel_data=normalized.tobytes(),
        color_format=color_format,
    )


def decoded_image_to_ndarray(image: DecodedImage) -> np.ndarray:
    """Unpack a ``DecodedImage`` back into an ``(H, W, 3)`` ``uint8`` array.

    The returned array's channel order matches ``image.color_format``
    exactly — this function never silently converts RGB<->BGR; callers
    that need a specific order (e.g. OpenCV's BGR) must convert
    explicitly via ``to_bgr``/``to_rgb`` below.
    """

    return _unpack(
        image.pixel_data, width=image.dimensions.width_px, height=image.dimensions.height_px
    )


def ndarray_to_normalized_face_input(
    array: np.ndarray, *, color_format: Literal["rgb", "bgr"] = "rgb"
) -> NormalizedFaceInput:
    """Pack an ``(H, W, 3)`` ``uint8`` array into a ``NormalizedFaceInput``."""

    normalized = _normalize_array(array)
    height, width, _ = normalized.shape
    return NormalizedFaceInput(
        dimensions=ImageDimensions(width_px=width, height_px=height),
        pixel_data=normalized.tobytes(),
        color_format=color_format,
    )


def normalized_face_input_to_ndarray(face: NormalizedFaceInput) -> np.ndarray:
    """Unpack a ``NormalizedFaceInput`` back into an ``(H, W, 3)`` ``uint8`` array."""

    return _unpack(
        face.pixel_data, width=face.dimensions.width_px, height=face.dimensions.height_px
    )


def to_bgr(array: np.ndarray, *, color_format: Literal["rgb", "bgr"]) -> np.ndarray:
    """Return an OpenCV-ready BGR view/copy of ``array``, converting only if needed."""

    if color_format == "bgr":
        return array
    return array[:, :, ::-1]


def to_rgb(array: np.ndarray, *, color_format: Literal["rgb", "bgr"]) -> np.ndarray:
    """Return an RGB view/copy of ``array`` (dlib's expected order), converting only if needed."""

    if color_format == "rgb":
        return array
    return array[:, :, ::-1]


def _normalize_array(array: np.ndarray) -> np.ndarray:
    if array.ndim != 3 or array.shape[2] != _CHANNELS:
        raise ValueError(f"expected an (H, W, {_CHANNELS}) array, got shape {array.shape!r}")
    if array.dtype != np.uint8:
        raise ValueError(f"expected a uint8 array, got dtype {array.dtype!r}")
    return np.ascontiguousarray(array)


def _unpack(pixel_data: bytes, *, width: int, height: int) -> np.ndarray:
    expected_length = width * height * _CHANNELS
    if len(pixel_data) != expected_length:
        raise ValueError(
            f"pixel_data length {len(pixel_data)} does not match "
            f"{width}x{height}x{_CHANNELS}={expected_length}"
        )
    array = np.frombuffer(pixel_data, dtype=np.uint8)
    return array.reshape((height, width, _CHANNELS))
