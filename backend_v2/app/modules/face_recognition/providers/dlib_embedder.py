"""dlib ResNet ``FaceEmbedder`` provider adapter — Phase 5 Stage 3.

Implements ``app.modules.face_recognition.protocols.FaceEmbedder``
using dlib's ``dlib_face_recognition_resnet_model_v1`` — see
``docs/HANDOVER_PHASE_5_STAGE_3.md`` for the full model-selection
writeup (source, exact version, license, and why the two other
candidates compared — OpenCV Zoo's SFace and InsightFace's
buffalo_l/ArcFace family — were rejected). Summary repeated here
because it directly explains this adapter's shape:

- **Model:** ``dlib_face_recognition_resnet_model_v1.dat`` — a 29-conv-
  layer ResNet-34-derived network, 128-D output, published by Davis
  King (dlib's maintainer) at
  ``http://dlib.net/files/dlib_face_recognition_resnet_model_v1.dat.bz2``.
- **License:** released into the public domain by its author — see
  ``dlib``'s own ``dnn_face_recognition_ex.cpp`` example ("The contents
  of this file are in the public domain") and the maintainer's blog
  post announcing the model ("the pretrained model used by this
  example program is in the public domain. So you can use it for
  anything you want."). This is the confirmed-permissive candidate that
  resolves ADR 0005's Stage 1 blocker (SFace's unresolved licensing —
  still unresolved and still not selected; InsightFace's buffalo_l/
  ArcFace family independently confirmed here as non-commercial-
  research-only, i.e. a second, equally clear rejection, not merely an
  unexamined alternative).
- **No official ONNX export.** Unlike the YuNet detector (loaded
  through OpenCV's own ONNX importer, no ``onnxruntime`` needed), dlib
  ships its own native ``.dat`` weight format and its own C++/Python
  inference engine — this adapter therefore depends on the ``dlib``
  Python package directly, not ``onnxruntime``. This is a deliberate,
  documented trade-off against ADR 0005's stated "onnxruntime only if
  genuinely needed" preference: the licensing gate is treated as the
  harder constraint (Stage 3 brief, instruction 4: "Do not use a model
  whose license or redistribution rights remain unclear"), and no
  clearly-licensed ONNX-native alternative was found — see the
  handover doc's comparison table.
- **Similarity metric:** this codebase's domain contract
  (``app.modules.face_recognition.domain``) fixes cosine similarity,
  never distance, project-wide — but dlib's own official guidance
  recommends comparing raw 128-D descriptors by Euclidean distance
  (same person if distance < ~0.6). Rather than introduce a second,
  competing distance-based code path, this adapter **L2-normalizes**
  every embedding it produces to a unit vector before returning it. For
  unit vectors, cosine similarity and Euclidean distance carry the same
  ranking information (``cosine_similarity = 1 - (euclidean_distance^2)/2``),
  so normalizing here lets
  ``app.modules.face_recognition.providers.similarity_matcher`` use a
  single, consistent cosine-similarity computation for every candidate,
  matching this codebase's fixed domain convention exactly. This means
  ``Settings.FACE_MATCH_THRESHOLD``'s effective meaning is "cosine
  similarity of L2-normalized dlib descriptors", not dlib's own
  Euclidean-distance convention — a real, documented calibration
  difference, not an oversight (see the handover doc's "Calibration
  status: pending").
"""

from __future__ import annotations

import math
import threading
from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar, Protocol, cast

import numpy as np
import structlog

from app.core.config import Settings
from app.modules.face_recognition.domain import (
    EmbeddingVector,
    NormalizedFaceInput,
    validate_embedding_dimension,
)
from app.modules.face_recognition.errors import (
    FaceEmbeddingFailedError,
    FaceProviderUnavailableError,
)
from app.modules.face_recognition.image_codec import normalized_face_input_to_ndarray, to_rgb
from app.modules.face_recognition.model_artifacts import verify_model_artifact

logger = structlog.get_logger(__name__)

_EXPECTED_RAW_DIMENSION = 128


class _DlibEmbeddingModel(Protocol):
    def compute_face_descriptor(self, image: object, *, num_jitters: int) -> Iterable[float]: ...


class DlibResnetFaceEmbedder:
    """Loads the dlib ResNet embedding model lazily and embeds aligned face chips.

    Like ``YuNetFaceDetector``, the underlying dlib model object is
    created on first use (see ``_ensure_loaded``), never at import or
    construction time — a deployment with
    ``Settings.FACE_RECOGNITION_PROVIDER == "none"`` never touches the
    ``dlib`` package at all.

    **Stage 3 correction (finding 3):** ``self._lock`` (a process-local,
    per-instance ``threading.RLock``) serializes loading and inference
    on *this* cached instance exactly like
    ``YuNetFaceDetector._lock`` — see that class's docstring for the
    full rationale (cached provider instance + a shared
    ``asyncio.to_thread`` pool means two concurrent requests can
    otherwise land on the same instance at once).
    """

    provider_name: ClassVar[str] = "dlib_resnet_v1_local"
    model_identifier: ClassVar[str] = "dlib_face_recognition_resnet_model_v1"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model: _DlibEmbeddingModel | None = None
        self._lock = threading.RLock()

    def _ensure_loaded(self) -> _DlibEmbeddingModel:
        with self._lock:
            if self._model is not None:
                return self._model

            model_path = (self._settings.FACE_EMBEDDER_MODEL_PATH or "").strip()
            if not model_path:
                raise FaceProviderUnavailableError()

            verify_model_artifact(
                Path(model_path), expected_sha256=self._settings.FACE_EMBEDDER_MODEL_SHA256
            )

            try:
                # Imported lazily (not at module import time): a deployment
                # that never enables face recognition should not need the
                # `dlib` package installed/importable at all just to import
                # this module (e.g. from a health-check-only code path that
                # never reaches this branch). See this class's docstring.
                import dlib
            except ImportError as exc:  # pragma: no cover - environment-dependent
                logger.error("dlib_import_failed")
                raise FaceProviderUnavailableError() from exc

            try:
                model = cast(_DlibEmbeddingModel, dlib.face_recognition_model_v1(model_path))
            except Exception as exc:
                logger.error("dlib_model_load_failed", exc_type=type(exc).__name__)
                raise FaceProviderUnavailableError() from exc

            self._model = model
            return model

    def is_available(self) -> bool:
        """Cheap readiness probe used by health reporting.

        See ``YuNetFaceDetector.is_available`` — including the same
        "this performs blocking model I/O, callers must offload it"
        note.
        """
        try:
            self._ensure_loaded()
        except Exception:
            return False
        return True

    def embed(self, face: NormalizedFaceInput) -> EmbeddingVector:
        with self._lock:
            model = self._ensure_loaded()

            try:
                source_array = normalized_face_input_to_ndarray(face)
                rgb = np.ascontiguousarray(to_rgb(source_array, color_format=face.color_format))
                raw_descriptor = model.compute_face_descriptor(rgb, num_jitters=1)
            except FaceProviderUnavailableError:
                raise
            except Exception as exc:
                logger.error("dlib_embedding_inference_failed", exc_type=type(exc).__name__)
                raise FaceEmbeddingFailedError() from exc

        raw_values = tuple(float(component) for component in raw_descriptor)
        if len(raw_values) != _EXPECTED_RAW_DIMENSION:
            raise FaceEmbeddingFailedError()
        if any(not math.isfinite(value) for value in raw_values):
            raise FaceEmbeddingFailedError()

        normalized_values = _l2_normalize(raw_values)

        vector = EmbeddingVector(values=normalized_values)
        return validate_embedding_dimension(
            vector, expected_dimension=self._settings.FACE_EMBEDDING_DIMENSION
        )


def _l2_normalize(values: tuple[float, ...]) -> tuple[float, ...]:
    """L2-normalize a raw embedding to a unit vector — see this module's docstring.

    Raises ``FaceEmbeddingFailedError`` on a (practically unreachable
    for a real face descriptor, but defensively checked) all-zero
    vector, since a zero vector has no defined direction to normalize
    to and would otherwise propagate a ``ZeroDivisionError``/``nan``.
    """
    norm = math.sqrt(sum(component * component for component in values))
    if not math.isfinite(norm) or norm == 0.0:
        raise FaceEmbeddingFailedError()
    return tuple(component / norm for component in values)
