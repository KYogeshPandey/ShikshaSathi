"""Candidate-scoped cosine-similarity ``FaceMatcher`` — Phase 5 Stage 3.

Implements the Stage 3 ``app.modules.face_recognition.protocols.FaceMatcher``
contract (``match(embedding, candidates)``). This class is a **pure
function of its two arguments** — see ``protocols.py``'s updated
``FaceMatcher`` docstring: it never queries a database, never knows
about ``app.modules.biometric_enrollment``, and never remembers state
between calls. Resolving which students are in scope and fetching
their active, ``PROCESSED`` embeddings is
``app.modules.face_recognition.matching_service.MatchingService``'s
job, not this class's.

**Similarity metric:** plain cosine similarity
(``dot(a, b) / (|a| * |b|)``, clamped to ``[-1.0, 1.0]`` to absorb
floating-point rounding). This works correctly whether or not a
candidate's stored embedding happens to already be a unit vector —
this class does not assume its caller's embedder pre-normalized
anything, even though the one embedder this project ships
(``app.modules.face_recognition.providers.dlib_embedder``) always
does; see that module's docstring for why L2-normalized dlib
descriptors were chosen specifically to make cosine similarity the
correct, single metric this whole pipeline uses.

**Multi-sample aggregation rule — best sample per student (Stage 3
brief, instruction 9):** a student may have more than one
``CandidateEmbedding`` in the ``candidates`` sequence (Stage 2 allows a
history of samples; more than one may reach ``PROCESSED`` over time —
see ``docs/HANDOVER_PHASE_5_STAGE_3.md``'s "Embedding storage" section
for exactly which samples the caller is expected to supply). This
matcher aggregates multiple candidates for the same
``student_profile_id`` by taking the **maximum** similarity among
them ("best sample per student"), not the mean. Chosen over averaging
because: (a) it matches the common 1:N face-recognition convention of
treating enrollment as "a gallery of templates per identity, compare
against the closest one" rather than a single blended template: (b) it
avoids a genuinely good match being dragged down by one poor-quality
older sample; (c) it needs no extra configuration (a mean-based
approach would need a documented minimum-sample-count policy to avoid
one sample dominating an average of two). The trade-off (documented,
not hidden) is a mild optimism bias versus averaging — mitigated by
this project's separate, configurable ambiguity margin.

**Deterministic tie-breaking:** after aggregation, candidates are
sorted by ``(-similarity, str(student_profile_id))`` — highest
similarity first, ties broken by the candidate's UUID string form.
This guarantees the exact same ``MatchResult`` for the exact same
input on every run, on every machine, regardless of dict/set
iteration order upstream.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Sequence

from app.core.config import Settings
from app.modules.face_recognition.domain import (
    CandidateEmbedding,
    EmbeddingVector,
    MatchCandidate,
    MatchResult,
)
from app.modules.face_recognition.errors import CandidateEmbeddingDimensionMismatchError


class CosineSimilarityFaceMatcher:
    """Threshold/ambiguity-margin-driven candidate-scoped matcher."""

    provider_name = "cosine_similarity_local"

    def __init__(self, settings: Settings) -> None:
        self._threshold = settings.FACE_MATCH_THRESHOLD
        self._ambiguous_margin = settings.FACE_MATCH_AMBIGUOUS_MARGIN

    def match(
        self, embedding: EmbeddingVector, candidates: Sequence[CandidateEmbedding]
    ) -> MatchResult:
        if not candidates:
            return MatchResult.unknown()

        per_student_best: dict[uuid.UUID, float] = {}
        for candidate in candidates:
            if candidate.embedding.dimension != embedding.dimension:
                raise CandidateEmbeddingDimensionMismatchError(
                    expected=embedding.dimension, actual=candidate.embedding.dimension
                )
            similarity = _cosine_similarity(embedding, candidate.embedding)
            existing = per_student_best.get(candidate.student_profile_id)
            if existing is None or similarity > existing:
                per_student_best[candidate.student_profile_id] = similarity

        ranked = sorted(
            per_student_best.items(),
            key=lambda item: (-item[1], str(item[0])),
        )

        best_student_id, best_similarity = ranked[0]
        best_candidate = MatchCandidate(
            student_profile_id=best_student_id, similarity=best_similarity
        )

        if best_similarity < self._threshold:
            return MatchResult.unknown(best_candidate=best_candidate)

        if len(ranked) > 1:
            runner_up_student_id, runner_up_similarity = ranked[1]
            gap = best_similarity - runner_up_similarity
            if gap < self._ambiguous_margin:
                runner_up_candidate = MatchCandidate(
                    student_profile_id=runner_up_student_id, similarity=runner_up_similarity
                )
                return MatchResult.ambiguous(
                    best_candidate=best_candidate, runner_up_candidate=runner_up_candidate
                )

        return MatchResult.found(best_candidate)


def _cosine_similarity(a: EmbeddingVector, b: EmbeddingVector) -> float:
    dot = sum(x * y for x, y in zip(a.values, b.values, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a.values))
    norm_b = math.sqrt(sum(y * y for y in b.values))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    similarity = dot / (norm_a * norm_b)
    return max(-1.0, min(1.0, similarity))
