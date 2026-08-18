"""Tests for ``app.modules.face_recognition.providers.dlib_embedder.DlibResnetFaceEmbedder``.

No real ``dlib`` package or ``.dat`` model file is required: ``import
dlib`` inside ``_ensure_loaded`` is lazy (see that module's docstring),
so injecting a fake module object into ``sys.modules["dlib"]`` before
the call is enough to exercise this adapter's own logic (artifact
validation, preprocessing, dimension/finiteness checks, L2
normalization, exception mapping) deterministically — the same
technique ``test_face_recognition_yunet_detector.py`` uses for
``cv2.FaceDetectorYN``, just via ``sys.modules`` instead of
``unittest.mock.patch`` since ``dlib`` may not be importable at all in
this environment (unlike ``cv2``, which genuinely is installed here).
"""

from __future__ import annotations

import hashlib
import math
import sys
from types import ModuleType
from unittest.mock import patch

import pytest

from app.modules.face_recognition.errors import (
    FaceEmbeddingFailedError,
    FaceProviderUnavailableError,
    ModelArtifactChecksumMismatchError,
    ModelArtifactMissingError,
)
from app.modules.face_recognition.providers.dlib_embedder import DlibResnetFaceEmbedder
from app.tests.phase5_stage3_helpers import make_normalized_face


class _SettingsLike:
    def __init__(
        self,
        *,
        model_path: str | None,
        model_sha256: str | None = None,
        embedding_dimension: int = 128,
    ) -> None:
        self.FACE_EMBEDDER_MODEL_PATH = model_path
        self.FACE_EMBEDDER_MODEL_SHA256 = model_sha256
        self.FACE_EMBEDDING_DIMENSION = embedding_dimension


class _FakeDlibModel:
    def __init__(self, descriptor: list[float] | None = None, raise_error: Exception | None = None):
        self._descriptor = descriptor if descriptor is not None else [0.01 * i for i in range(128)]
        self._raise_error = raise_error
        self.last_call_kwargs: dict[str, object] | None = None

    def compute_face_descriptor(self, img, num_jitters=1):
        self.last_call_kwargs = {"num_jitters": num_jitters, "shape": getattr(img, "shape", None)}
        if self._raise_error is not None:
            raise self._raise_error
        return self._descriptor


def _install_fake_dlib(model: _FakeDlibModel) -> None:
    fake_module = ModuleType("dlib")
    fake_module.face_recognition_model_v1 = lambda path: model
    sys.modules["dlib"] = fake_module


def _make_model_file(tmp_path, content: bytes = b"fake-dlib-model-bytes") -> str:
    path = tmp_path / "dlib_face_recognition_resnet_model_v1.dat"
    path.write_bytes(content)
    return str(path)


@pytest.fixture(autouse=True)
def _clean_fake_dlib_module():
    sys.modules.pop("dlib", None)
    yield
    sys.modules.pop("dlib", None)


def test_embed_raises_missing_model_error_when_path_unset() -> None:
    embedder = DlibResnetFaceEmbedder(_SettingsLike(model_path=None))
    with pytest.raises(FaceProviderUnavailableError):
        embedder.embed(make_normalized_face())


def test_embed_raises_missing_model_error_when_file_does_not_exist(tmp_path) -> None:
    missing_path = str(tmp_path / "missing.dat")
    embedder = DlibResnetFaceEmbedder(_SettingsLike(model_path=missing_path))
    with pytest.raises(ModelArtifactMissingError):
        embedder.embed(make_normalized_face())


def test_embed_raises_checksum_mismatch_error(tmp_path) -> None:
    model_path = _make_model_file(tmp_path)
    embedder = DlibResnetFaceEmbedder(_SettingsLike(model_path=model_path, model_sha256="0" * 64))
    with pytest.raises(ModelArtifactChecksumMismatchError):
        embedder.embed(make_normalized_face())


def test_embed_returns_128d_finite_l2_normalized_vector(tmp_path) -> None:
    model_path = _make_model_file(tmp_path)
    correct_checksum = hashlib.sha256(
        (tmp_path / "dlib_face_recognition_resnet_model_v1.dat").read_bytes()
    ).hexdigest()
    embedder = DlibResnetFaceEmbedder(
        _SettingsLike(model_path=model_path, model_sha256=correct_checksum)
    )
    raw_descriptor = [float(i) - 64.0 for i in range(128)]  # arbitrary, non-degenerate
    _install_fake_dlib(_FakeDlibModel(descriptor=raw_descriptor))

    vector = embedder.embed(make_normalized_face())

    assert vector.dimension == 128
    assert all(math.isfinite(v) for v in vector.values)
    norm = math.sqrt(sum(v * v for v in vector.values))
    assert math.isclose(norm, 1.0, abs_tol=1e-9)


def test_embed_passes_expected_preprocessing_shape_and_jitter(tmp_path) -> None:
    model_path = _make_model_file(tmp_path)
    embedder = DlibResnetFaceEmbedder(_SettingsLike(model_path=model_path))
    fake_model = _FakeDlibModel()
    _install_fake_dlib(fake_model)

    embedder.embed(make_normalized_face(size_px=150))

    assert fake_model.last_call_kwargs is not None
    assert fake_model.last_call_kwargs["num_jitters"] == 1
    assert fake_model.last_call_kwargs["shape"] == (150, 150, 3)


def test_embed_rejects_wrong_length_descriptor(tmp_path) -> None:
    model_path = _make_model_file(tmp_path)
    embedder = DlibResnetFaceEmbedder(_SettingsLike(model_path=model_path))
    _install_fake_dlib(_FakeDlibModel(descriptor=[0.1] * 64))  # wrong dimension

    with pytest.raises(FaceEmbeddingFailedError):
        embedder.embed(make_normalized_face())


def test_embed_rejects_non_finite_descriptor(tmp_path) -> None:
    model_path = _make_model_file(tmp_path)
    embedder = DlibResnetFaceEmbedder(_SettingsLike(model_path=model_path))
    bad_descriptor = [0.1] * 127 + [float("nan")]
    _install_fake_dlib(_FakeDlibModel(descriptor=bad_descriptor))

    with pytest.raises(FaceEmbeddingFailedError):
        embedder.embed(make_normalized_face())


def test_embed_rejects_all_zero_descriptor() -> None:
    """A zero vector has no defined direction to L2-normalize to."""
    _install_fake_dlib(_FakeDlibModel(descriptor=[0.0] * 128))
    embedder = DlibResnetFaceEmbedder(_SettingsLike(model_path="/irrelevant/because/mocked"))
    with (
        patch(
            "app.modules.face_recognition.providers.dlib_embedder.verify_model_artifact",
            return_value=None,
        ),
        pytest.raises(FaceEmbeddingFailedError),
    ):
        embedder.embed(make_normalized_face())


def test_embed_sanitizes_raw_inference_exception(tmp_path) -> None:
    """A raw dlib/runtime exception must never propagate as-is — only the
    provider-neutral FaceEmbeddingFailedError, with a fixed, generic message
    (no exception text, no model name, no path)."""
    model_path = _make_model_file(tmp_path)
    embedder = DlibResnetFaceEmbedder(_SettingsLike(model_path=model_path))
    _install_fake_dlib(
        _FakeDlibModel(raise_error=RuntimeError("some internal dlib C++ stack trace detail"))
    )

    with pytest.raises(FaceEmbeddingFailedError) as excinfo:
        embedder.embed(make_normalized_face())

    assert "some internal dlib C++ stack trace detail" not in str(excinfo.value)
    assert model_path not in str(excinfo.value)


def test_is_available_false_when_dlib_import_fails(tmp_path) -> None:
    model_path = _make_model_file(tmp_path)
    embedder = DlibResnetFaceEmbedder(_SettingsLike(model_path=model_path))
    # dlib genuinely absent from sys.modules and not importable in this
    # sandbox — is_available() must return False, never raise.
    assert embedder.is_available() is False


def test_is_available_true_when_model_loads(tmp_path) -> None:
    model_path = _make_model_file(tmp_path)
    embedder = DlibResnetFaceEmbedder(_SettingsLike(model_path=model_path))
    _install_fake_dlib(_FakeDlibModel())
    assert embedder.is_available() is True
