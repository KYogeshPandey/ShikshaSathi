"""Builds and caches the active Stage 3 provider instances from ``Settings``.

One place decides "which concrete detector/embedder/matcher
implementation backs the ``FaceDetector``/``FaceEmbedder``/
``FaceMatcher`` protocols right now" — every service/router/health
module depends on *this* factory, never on
``app.modules.face_recognition.providers.yunet_detector``/
``dlib_embedder``/``similarity_matcher`` directly, so a future
alternate provider (Stage 5+, or a hosted-API adapter — see ADR 0005's
own "Provider swapability" comparison row) is a change in this one
file, not a search-and-replace across the codebase.

Instances are cached per ``Settings`` object (``lru_cache``-free,
explicit dict keyed by ``id(settings)`` — ``Settings`` is not hashable
in a way this module wants to rely on, and test suites construct many
short-lived ``Settings`` instances that must never share a cached
provider across tests). Each provider adapter still lazily loads its
own underlying model on first real use (see each adapter's own
docstring) — caching the *adapter object* here just avoids re-creating
that lazy-loading wrapper (and re-running its own cheap bookkeeping) on
every request.
"""

from __future__ import annotations

import threading

from app.core.config import Settings
from app.modules.face_recognition.protocols import FaceMatcher
from app.modules.face_recognition.providers.dlib_embedder import DlibResnetFaceEmbedder
from app.modules.face_recognition.providers.similarity_matcher import CosineSimilarityFaceMatcher
from app.modules.face_recognition.providers.yunet_detector import YuNetFaceDetector

_detector_cache: dict[int, YuNetFaceDetector] = {}
_embedder_cache: dict[int, DlibResnetFaceEmbedder] = {}

# Stage 3 correction (finding 3): guards only this module's two cache
# dicts' get-or-create step (a tiny, fast critical section) — not the
# provider instances' own, much longer-held locks (see
# ``YuNetFaceDetector._lock``/``DlibResnetFaceEmbedder._lock``), and not
# shared across the two dicts' *providers* in any way that would let one
# provider's work block the other's. Without this, two concurrent
# first-ever calls for the same ``settings`` could each see an empty
# cache slot and construct/cache two different adapter instances, one of
# which then silently drops out of the cache (still usable by whichever
# caller got it, just no longer the *shared* instance the per-instance
# locks above are meant to serialize).
_cache_lock = threading.Lock()


def get_detector(settings: Settings) -> YuNetFaceDetector:
    """Returns the cached ``YuNetFaceDetector`` for ``settings``.

    Typed concretely (not as the ``FaceDetector`` Protocol) so callers
    that need the extra, non-Protocol ``is_available()`` readiness
    probe (``app.modules.face_recognition.health``) get it without a
    cast; every other caller (the processing/matching services) only
    ever calls ``.detect(...)``, which is also on the Protocol, so
    depending on the concrete type here costs those callers nothing.
    """
    key = id(settings)
    with _cache_lock:
        detector = _detector_cache.get(key)
        if detector is None:
            detector = YuNetFaceDetector(settings)
            _detector_cache[key] = detector
        return detector


def get_embedder(settings: Settings) -> DlibResnetFaceEmbedder:
    """Returns the cached ``DlibResnetFaceEmbedder`` for ``settings`` — see ``get_detector``."""
    key = id(settings)
    with _cache_lock:
        embedder = _embedder_cache.get(key)
        if embedder is None:
            embedder = DlibResnetFaceEmbedder(settings)
            _embedder_cache[key] = embedder
        return embedder


def get_matcher(settings: Settings) -> FaceMatcher:
    # The matcher provider is stateless/cheap to construct (holds only
    # two float settings, loads no model) — no caching benefit, so a
    # fresh instance every call keeps this function trivially correct
    # even if a caller mutates threshold-related settings between
    # calls in a test.
    return CosineSimilarityFaceMatcher(settings)


def reset_provider_cache() -> None:
    """Test-only: clears cached provider instances between test modules."""
    _detector_cache.clear()
    _embedder_cache.clear()
