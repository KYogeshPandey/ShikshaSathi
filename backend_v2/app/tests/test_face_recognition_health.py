"""Tests for ``app.modules.face_recognition.health.get_face_recognition_health``.

Uses fake detector/embedder objects (via monkeypatching
``app.modules.face_recognition.health.get_detector``/``get_embedder``)
so no real model file or real ``cv2``/``dlib`` load is required — only
this module's own aggregation logic (overall status derivation, safe
reason codes, no path/exception leakage) is under test here.
"""

from __future__ import annotations

from unittest.mock import patch

from app.core.config import FaceRecognitionProvider
from app.modules.face_recognition.domain import ProviderStatus
from app.modules.face_recognition.health import get_face_recognition_health


class _SettingsLike:
    def __init__(
        self,
        *,
        provider: FaceRecognitionProvider = FaceRecognitionProvider.SERVER_SIDE_LOCAL,
        detector_model_path: str | None = "/some/detector.onnx",
        embedder_model_path: str | None = "/some/embedder.dat",
    ) -> None:
        self.FACE_RECOGNITION_PROVIDER = provider
        self.FACE_DETECTOR_MODEL_PATH = detector_model_path
        self.FACE_EMBEDDER_MODEL_PATH = embedder_model_path


class _FakeProvider:
    def __init__(self, available: bool) -> None:
        self._available = available

    def is_available(self) -> bool:
        return self._available


def test_health_when_provider_disabled_reports_not_configured() -> None:
    settings = _SettingsLike(provider=FaceRecognitionProvider.NONE)
    health = get_face_recognition_health(settings)
    assert health.overall_status is ProviderStatus.NOT_CONFIGURED
    assert health.detector.status is ProviderStatus.NOT_CONFIGURED
    assert health.embedder.status is ProviderStatus.NOT_CONFIGURED


def test_health_when_both_providers_ready() -> None:
    settings = _SettingsLike()
    with (
        patch(
            "app.modules.face_recognition.health.get_detector",
            return_value=_FakeProvider(True),
        ),
        patch(
            "app.modules.face_recognition.health.get_embedder",
            return_value=_FakeProvider(True),
        ),
    ):
        health = get_face_recognition_health(settings)

    assert health.overall_status is ProviderStatus.READY
    assert health.detector.status is ProviderStatus.READY
    assert health.embedder.status is ProviderStatus.READY


def test_health_when_detector_model_missing_path_is_not_configured() -> None:
    settings = _SettingsLike(detector_model_path=None)
    with patch(
        "app.modules.face_recognition.health.get_embedder",
        return_value=_FakeProvider(True),
    ):
        health = get_face_recognition_health(settings)

    assert health.detector.status is ProviderStatus.NOT_CONFIGURED
    assert health.overall_status is ProviderStatus.NOT_CONFIGURED


def test_health_when_embedder_unavailable_reports_unavailable() -> None:
    settings = _SettingsLike()
    with (
        patch(
            "app.modules.face_recognition.health.get_detector",
            return_value=_FakeProvider(True),
        ),
        patch(
            "app.modules.face_recognition.health.get_embedder",
            return_value=_FakeProvider(False),
        ),
    ):
        health = get_face_recognition_health(settings)

    assert health.embedder.status is ProviderStatus.UNAVAILABLE
    assert health.overall_status is ProviderStatus.UNAVAILABLE


def test_detector_checksum_mismatch_is_a_normal_unavailable_health_result() -> None:
    """From this module's perspective, "checksum mismatch" and "any other
    load failure" both collapse to `is_available() -> False` — a
    checksum-specific status is not distinguished at this layer (that
    detail lives server-side in structured logs only, never surfaced
    here)."""
    settings = _SettingsLike()
    with (
        patch(
            "app.modules.face_recognition.health.get_detector",
            return_value=_FakeProvider(False),
        ),
        patch(
            "app.modules.face_recognition.health.get_embedder",
            return_value=_FakeProvider(True),
        ),
    ):
        health = get_face_recognition_health(settings)

    assert health.detector.status is ProviderStatus.UNAVAILABLE
    assert health.overall_status is ProviderStatus.UNAVAILABLE


def test_health_details_never_contain_a_filesystem_path() -> None:
    settings = _SettingsLike(
        detector_model_path="/etc/shikshasathi/models/very-secret-directory/yunet.onnx"
    )
    with (
        patch(
            "app.modules.face_recognition.health.get_detector",
            return_value=_FakeProvider(False),
        ),
        patch(
            "app.modules.face_recognition.health.get_embedder",
            return_value=_FakeProvider(False),
        ),
    ):
        health = get_face_recognition_health(settings)

    for provider_health in (health.detector, health.embedder):
        if provider_health.detail:
            assert "/etc/shikshasathi" not in provider_health.detail
            assert "very-secret-directory" not in provider_health.detail


def test_health_never_runs_recognition_it_only_checks_availability() -> None:
    """A health check must call only `is_available()` — never `.detect()`
    or `.embed()` — on either provider (Stage 3 brief §12)."""

    class _StrictFakeProvider:
        def is_available(self) -> bool:
            return True

        def detect(self, *args, **kwargs):  # pragma: no cover - must never be called
            raise AssertionError("health check must never call detect()")

        def embed(self, *args, **kwargs):  # pragma: no cover - must never be called
            raise AssertionError("health check must never call embed()")

    settings = _SettingsLike()
    with (
        patch(
            "app.modules.face_recognition.health.get_detector",
            return_value=_StrictFakeProvider(),
        ),
        patch(
            "app.modules.face_recognition.health.get_embedder",
            return_value=_StrictFakeProvider(),
        ),
    ):
        health = get_face_recognition_health(settings)

    assert health.overall_status is ProviderStatus.READY
