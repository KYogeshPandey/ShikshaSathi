"""Provider-neutral ``Protocol`` interfaces for detect/embed/match.

These are the exact three interfaces required by
``docs/ARCHITECTURE.md`` §9 and ``docs/adr/0005-face-recognition-provider-pending.md``:
``detect``, ``embed``, ``match``. No provider-specific type (OpenCV,
ONNX Runtime, TensorFlow, a hosted-API SDK client) appears anywhere in
this file — only the value objects from
``app.modules.face_recognition.domain``.

**No implementation exists here.** These are structural (``Protocol``)
interfaces, not abstract base classes to inherit from — any object with
matching method signatures satisfies them, including a deterministic
test double defined only in a test module (Stage 1 brief, instruction 4:
"A test double may exist only in tests or as an explicitly named fake
used for contract testing"). ``runtime_checkable`` is set so tests can
assert ``isinstance(fake, FaceDetector)`` etc. as a structural
conformance check.

**Deliberately synchronous.** Face detection/embedding/matching are
CPU-bound, blocking operations by nature (unlike this codebase's
I/O-bound async database/HTTP work) — an ``async def`` signature here
would just be a coroutine that still blocks the event loop for however
long real inference takes. A Stage 3+ service layer calling a real
provider is expected to run it off the event loop (e.g.
``asyncio.to_thread`` or a worker/process pool), not to make the
provider interface itself ``async`` and hope that alone helps.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from app.modules.face_recognition.domain import (
    CandidateEmbedding,
    DecodedImage,
    DetectedFace,
    EmbeddingVector,
    MatchResult,
    NormalizedFaceInput,
)


@runtime_checkable
class FaceDetector(Protocol):
    """Detects zero or more faces within one decoded image."""

    def detect(self, image: DecodedImage) -> list[DetectedFace]:
        """Return every face detected in ``image``.

        An empty list is a normal, valid result ("no face found") — not
        an error. Raise ``app.modules.face_recognition.errors.
        FaceDetectionFailedError`` only when ``image`` itself could not
        be processed at all (e.g. corrupt data), never for "zero faces".
        """
        ...


@runtime_checkable
class FaceEmbedder(Protocol):
    """Converts one normalized (cropped, aligned) face into an embedding."""

    def embed(self, face: NormalizedFaceInput) -> EmbeddingVector:
        """Return a validated embedding for ``face``.

        Implementations must validate their own output's dimension via
        ``app.modules.face_recognition.domain.validate_embedding_dimension``
        before returning, so every provider fails the same way on a
        shape mismatch.
        """
        ...


@runtime_checkable
class FaceMatcher(Protocol):
    """Matches one embedding against an explicit, caller-supplied candidate set.

    **Signature changed in Phase 5 Stage 3** from Stage 1's
    ``match(self, embedding)`` to ``match(self, embedding, candidates)``
    — see ``docs/HANDOVER_PHASE_5_STAGE_3.md`` for why this is a
    deliberate, additive refinement rather than a Stage 1/2 rewrite:
    Stage 1 defined the *shape* of matching (``embedding -> MatchResult``)
    but explicitly left "what a matcher is scoped against" undecided (no
    implementation existed to constrain it). Stage 3's brief requires
    candidate-scoped matching — "do NOT compare every student in the
    entire institution by default" — which is only enforceable if the
    candidate set is an explicit parameter the matcher cannot bypass by
    reaching into a repository on its own.

    A ``FaceMatcher`` implementation MUST be a pure function of its two
    arguments: it never queries a database, never reads
    ``app.modules.biometric_enrollment`` state itself, and never
    remembers a previous call's candidates. Resolving *which* students
    are in scope (an explicit student-ID list, or a classroom/teacher-
    derived roster) and fetching their embeddings is the caller's job —
    see ``app.modules.face_recognition.matching_service.MatchingService``
    — precisely so that authorization/ownership scoping happens once, in
    an already-authorized service layer, and can never be silently
    widened by a provider implementation.
    """

    def match(
        self, embedding: EmbeddingVector, candidates: Sequence[CandidateEmbedding]
    ) -> MatchResult:
        """Return a provider-neutral, typed match outcome for ``embedding``.

        ``candidates`` is the complete, explicit search space for this
        call — an empty sequence is a normal, valid input (not an error)
        and must produce ``MatchResult.unknown()``. Must return a
        ``MatchResult`` built via ``.found(...)``, ``.unknown()``, or
        ``.ambiguous(...)`` — never a raw student ORM object, never a
        bare boolean, and never the caller's own pre-existing session
        data.
        """
        ...
