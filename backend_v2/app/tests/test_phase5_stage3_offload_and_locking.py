"""Tests for Stage 3 correction finding 3: event-loop offload + provider serialization.

Three things are asserted, matching the correction brief exactly:

1. ``SampleProcessingService.process_sample`` (and, by extension,
   ``retry_sample``, which shares ``_run_pipeline``) runs detect -> align ->
   embed via ``asyncio.to_thread`` — never directly on the event-loop thread.
2. ``router.match_probe`` runs decoded-content validation + detect -> align ->
   embed via ``asyncio.to_thread`` too, and ``router.get_health`` offloads
   provider-health model loading.
3. The cached ``YuNetFaceDetector``/``DlibResnetFaceEmbedder`` provider
   adapters serialize concurrent lazy-loading/inference on the *same*
   instance via their own per-instance ``threading.RLock`` — proven directly
   against those classes (not through the full async stack), since that is
   where the actual serialization guarantee lives.

Thread-offload proof strategy: a fake detector/embedder records
``threading.get_ident()`` from inside its own ``detect``/``embed`` call and
the test compares that to the ident of the thread the test coroutine itself
is running on (``asyncio.to_thread`` genuinely dispatches to a worker thread
from the default executor, so these are reliably different when offload is
actually happening, and would be equal if a regression reverted to a direct
call).
"""

from __future__ import annotations

import threading
import time
import types
import uuid
from unittest.mock import patch

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.face_recognition import router as router_module
from app.modules.face_recognition.processing_service import SampleProcessingService
from app.modules.face_recognition.providers.dlib_embedder import DlibResnetFaceEmbedder
from app.modules.face_recognition.providers.yunet_detector import YuNetFaceDetector
from app.tests.phase5_stage2_http_helpers import seed_enrollment_scope
from app.tests.phase5_stage3_helpers import (
    DEFAULT_DIMENSIONS,
    make_decoded_image,
    make_detected_face,
    make_normalized_face,
    make_real_jpeg_bytes,
    patch_providers,
    seed_active_sample_direct,
)


class _ThreadRecordingDetector:
    """A ``FaceDetector`` that records which OS thread called ``detect()``."""

    provider_name = "fake_detector"

    def __init__(self, faces: list) -> None:
        self._faces = faces
        self.detect_thread_ident: int | None = None

    def is_available(self) -> bool:
        return True

    def detect(self, image):
        self.detect_thread_ident = threading.get_ident()
        return list(self._faces)


class _ThreadRecordingEmbedder:
    """A ``FaceEmbedder`` that records which OS thread called ``embed()``."""

    provider_name = "fake_embedder"
    model_identifier = "fake_embedder_model"

    def __init__(self, *, dimension: int = 128) -> None:
        from app.tests.phase5_stage3_helpers import make_unit_embedding_vector

        self._dimension = dimension
        self._make_vector = make_unit_embedding_vector
        self.embed_thread_ident: int | None = None

    def is_available(self) -> bool:
        return True

    def embed(self, face):
        self.embed_thread_ident = threading.get_ident()
        return self._make_vector(dimension=self._dimension, seed=1.0)


class _FakeUploadFile:
    """Minimal duck-typed stand-in for Starlette's ``UploadFile`` — only the
    ``content_type`` attribute and ``read``/``close`` coroutines that
    ``router.match_probe`` actually uses."""

    def __init__(self, data: bytes, *, content_type: str = "image/jpeg") -> None:
        self._data = data
        self.content_type = content_type
        self.closed = False

    async def read(self, size: int = -1) -> bytes:
        return self._data

    async def close(self) -> None:
        self.closed = True


def _fake_request(request_id: str) -> types.SimpleNamespace:
    return types.SimpleNamespace(state=types.SimpleNamespace(request_id=request_id))


# --- 1. sample processing pipeline offload -----------------------------------


async def test_process_sample_runs_detect_align_embed_off_the_event_loop_thread(
    client_db, db_session: AsyncSession
) -> None:
    scope = await seed_enrollment_scope(client_db, db_session, suffix="offload1")
    sample_id = await seed_active_sample_direct(
        db_session,
        student_profile_id=uuid.UUID(scope["student_profile_1"]["id"]),
        created_by_user_id=scope["admin"].id,
    )
    service = SampleProcessingService(db_session)
    detector = _ThreadRecordingDetector([make_detected_face()])
    embedder = _ThreadRecordingEmbedder()
    calling_thread_ident = threading.get_ident()

    with patch_providers(detector, embedder):
        result = await service.process_sample(sample_id=sample_id, actor=scope["admin"])

    assert result.succeeded is True
    assert detector.detect_thread_ident is not None
    assert embedder.embed_thread_ident is not None
    # Ran off the event-loop/test-coroutine thread...
    assert detector.detect_thread_ident != calling_thread_ident
    # ...and detect+embed happened on the very same worker thread as each
    # other, confirming they were dispatched via a single asyncio.to_thread
    # call (one synchronous function doing both), not two separate hops.
    assert detector.detect_thread_ident == embedder.embed_thread_ident


async def test_retry_sample_also_runs_off_the_event_loop_thread(
    client_db, db_session: AsyncSession
) -> None:
    """``retry_sample`` shares ``_run_pipeline`` with ``process_sample`` — a
    quick confirmation it is not a second, un-offloaded code path."""
    scope = await seed_enrollment_scope(client_db, db_session, suffix="offload1b")
    sample_id = await seed_active_sample_direct(
        db_session,
        student_profile_id=uuid.UUID(scope["student_profile_1"]["id"]),
        created_by_user_id=scope["admin"].id,
    )
    service = SampleProcessingService(db_session)
    calling_thread_ident = threading.get_ident()

    with patch_providers(_ThreadRecordingDetector([]), _ThreadRecordingEmbedder()):
        first = await service.process_sample(sample_id=sample_id, actor=scope["admin"])
    assert first.succeeded is False  # zero faces -> PROCESSING_FAILED

    retry_detector = _ThreadRecordingDetector([make_detected_face()])
    retry_embedder = _ThreadRecordingEmbedder()
    with patch_providers(retry_detector, retry_embedder):
        retry_result = await service.retry_sample(sample_id=sample_id, actor=scope["admin"])

    assert retry_result.succeeded is True
    assert retry_detector.detect_thread_ident is not None
    assert retry_detector.detect_thread_ident != calling_thread_ident


# --- 2. match-probe offload (router-level) -----------------------------------


async def test_match_probe_runs_validation_and_inference_off_the_event_loop_thread(
    client_db, db_session: AsyncSession
) -> None:
    """Calls ``router.match_probe`` directly as a plain coroutine function —
    the ``@router.post(...)`` decorator does not wrap/replace it, so this
    reaches the exact same code the real endpoint runs, without needing a
    full ASGI/TestClient round trip (which would obscure which thread ran
    what)."""
    scope = await seed_enrollment_scope(client_db, db_session, suffix="offload2")
    student_id = uuid.UUID(scope["student_profile_1"]["id"])
    detector = _ThreadRecordingDetector([make_detected_face()])
    embedder = _ThreadRecordingEmbedder()
    calling_thread_ident = threading.get_ident()

    with patch_providers(detector, embedder):
        result = await router_module.match_probe(
            admin=scope["admin"],
            session=db_session,
            request=_fake_request("req-offload-2"),
            file=_FakeUploadFile(make_real_jpeg_bytes()),
            candidate_student_profile_ids=[student_id],
        )

    assert result is not None
    assert detector.detect_thread_ident is not None
    assert detector.detect_thread_ident != calling_thread_ident
    assert embedder.embed_thread_ident == detector.detect_thread_ident


async def test_get_health_offloads_provider_readiness_loading(client_db) -> None:
    """``get_face_recognition_health`` can perform blocking model-file I/O via
    each provider's ``is_available()`` — this proves ``router.get_health``
    dispatches it via ``asyncio.to_thread`` rather than calling it directly."""
    calling_thread_ident = threading.get_ident()
    recorded_thread_ident: list[int] = []

    def fake_health(settings):
        recorded_thread_ident.append(threading.get_ident())
        from app.modules.face_recognition.domain import ProviderHealth, ProviderStatus
        from app.modules.face_recognition.health import FaceRecognitionHealth

        health = ProviderHealth(
            provider_name="fake", status=ProviderStatus.NOT_CONFIGURED, detail="fake"
        )
        return FaceRecognitionHealth(
            overall_status=ProviderStatus.NOT_CONFIGURED, detector=health, embedder=health
        )

    admin = types.SimpleNamespace(id=uuid.uuid4())
    with patch.object(router_module, "get_face_recognition_health", fake_health):
        await router_module.get_health(admin)

    assert recorded_thread_ident, "get_face_recognition_health was never called"
    assert recorded_thread_ident[0] != calling_thread_ident


# --- 3. cached-provider serialization (unit-level, no real model files) ------


class _YuNetSettingsLike:
    def __init__(self, *, model_path: str = "/fake/yunet.onnx", input_size: int = 320) -> None:
        self.FACE_DETECTOR_MODEL_PATH = model_path
        self.FACE_DETECTOR_MODEL_SHA256 = None
        self.FACE_DETECTOR_INPUT_SIZE_PX = input_size


class _DlibSettingsLike:
    def __init__(
        self, *, model_path: str = "/fake/dlib.dat", embedding_dimension: int = 128
    ) -> None:
        self.FACE_EMBEDDER_MODEL_PATH = model_path
        self.FACE_EMBEDDER_MODEL_SHA256 = None
        self.FACE_EMBEDDING_DIMENSION = embedding_dimension


def test_yunet_detector_serializes_concurrent_lazy_load_and_detect(monkeypatch) -> None:
    """Five threads all calling ``detect()`` for the first time on one shared,
    cached ``YuNetFaceDetector`` instance must (a) trigger the underlying
    ``cv2.FaceDetectorYN.create`` exactly once, and (b) never have two
    threads inside the fake detector's own ``detect`` at the same time."""
    guard = threading.Lock()
    state = {"load_calls": 0, "concurrent": 0, "max_concurrent": 0}

    class _FakeCvDetector:
        def setInputSize(self, size) -> None:
            pass

        def detect(self, image: np.ndarray):
            with guard:
                state["concurrent"] += 1
                state["max_concurrent"] = max(state["max_concurrent"], state["concurrent"])
            time.sleep(0.05)
            with guard:
                state["concurrent"] -= 1
            return (1, np.zeros((0, 15), dtype=np.float32))

    def fake_create(*_args, **_kwargs):
        with guard:
            state["load_calls"] += 1
        time.sleep(0.05)
        return _FakeCvDetector()

    monkeypatch.setattr(
        "app.modules.face_recognition.providers.yunet_detector.verify_model_artifact",
        lambda *a, **k: None,
    )

    detector_adapter = YuNetFaceDetector(_YuNetSettingsLike())
    image = make_decoded_image(dimensions=DEFAULT_DIMENSIONS)

    with patch("cv2.FaceDetectorYN.create", side_effect=fake_create):
        threads = [
            threading.Thread(target=lambda: detector_adapter.detect(image)) for _ in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert state["load_calls"] == 1, (
        "lazy load must happen exactly once despite 5 concurrent callers"
    )
    assert state["max_concurrent"] == 1, "detect() calls on the same instance must never overlap"


def test_dlib_embedder_serializes_concurrent_lazy_load_and_embed(monkeypatch) -> None:
    """Mirrors the YuNet test above for ``DlibResnetFaceEmbedder``, using the
    same ``sys.modules["dlib"]`` fake-injection technique
    ``test_face_recognition_dlib_embedder.py`` already establishes for this
    adapter (real ``dlib`` package is not required/available here)."""
    import sys
    from types import ModuleType

    guard = threading.Lock()
    state = {"load_calls": 0, "concurrent": 0, "max_concurrent": 0}

    class _FakeDlibModel:
        def compute_face_descriptor(self, _img, num_jitters: int = 1):
            with guard:
                state["concurrent"] += 1
                state["max_concurrent"] = max(state["max_concurrent"], state["concurrent"])
            time.sleep(0.05)
            with guard:
                state["concurrent"] -= 1
            return [0.01 * i for i in range(128)]

    def fake_load(_path: str):
        with guard:
            state["load_calls"] += 1
        time.sleep(0.05)
        return _FakeDlibModel()

    monkeypatch.setattr(
        "app.modules.face_recognition.providers.dlib_embedder.verify_model_artifact",
        lambda *a, **k: None,
    )
    fake_module = ModuleType("dlib")
    fake_module.face_recognition_model_v1 = fake_load  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "dlib", fake_module)

    embedder_adapter = DlibResnetFaceEmbedder(_DlibSettingsLike())
    face = make_normalized_face()

    threads = [threading.Thread(target=lambda: embedder_adapter.embed(face)) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert state["load_calls"] == 1, (
        "lazy load must happen exactly once despite 5 concurrent callers"
    )
    assert state["max_concurrent"] == 1, "embed() calls on the same instance must never overlap"
