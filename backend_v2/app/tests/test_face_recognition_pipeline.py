"""Tests for ``app.modules.face_recognition.pipeline.detect_align_embed``.

Covers the "exactly one face" enrollment-processing policy (Stage 3
brief §3/§8) at the one place it is enforced, using
``FakeFaceDetector``/``FakeFaceEmbedder`` (see
``app.tests.phase5_stage3_helpers``) so no real model file is needed.
"""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.modules.face_recognition.errors import (
    EnrollmentSampleMultipleFacesDetectedError,
    EnrollmentSampleNoFaceDetectedError,
)
from app.modules.face_recognition.pipeline import detect_align_embed
from app.tests.phase5_stage3_helpers import (
    FakeFaceDetector,
    FakeFaceEmbedder,
    make_decoded_image,
    make_detected_face,
    patch_providers,
)


def test_detect_align_embed_succeeds_with_exactly_one_face() -> None:
    detector = FakeFaceDetector(results=[[make_detected_face()]])
    embedder = FakeFaceEmbedder()
    with patch_providers(detector, embedder):
        embedding = detect_align_embed(make_decoded_image(), settings=get_settings())
    assert embedding.dimension == 128


def test_detect_align_embed_rejects_zero_faces() -> None:
    detector = FakeFaceDetector(results=[[]])
    embedder = FakeFaceEmbedder()
    with patch_providers(detector, embedder), pytest.raises(EnrollmentSampleNoFaceDetectedError):
        detect_align_embed(make_decoded_image(), settings=get_settings())


def test_detect_align_embed_rejects_multiple_faces_without_picking_one() -> None:
    detector = FakeFaceDetector(results=[[make_detected_face(), make_detected_face()]])
    embedder = FakeFaceEmbedder()
    with (
        patch_providers(detector, embedder),
        pytest.raises(EnrollmentSampleMultipleFacesDetectedError),
    ):
        detect_align_embed(make_decoded_image(), settings=get_settings())
