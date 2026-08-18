"""Offline threshold-evaluation utility — Phase 5 Stage 3.

Pure, deterministic math over already-computed similarity scores — no
image decoding, no detector/embedder/matcher provider, no I/O. Exists
so ``Settings.FACE_MATCH_THRESHOLD``/``FACE_MATCH_AMBIGUOUS_MARGIN`` can
eventually be *calibrated* against a real labeled dataset, once one
exists, using the exact same FAR/FRR/threshold-sweep math this module
already implements and already tests (with synthetic data — see
``app/tests/test_face_recognition_evaluation.py``).

**No real evaluation dataset is included anywhere in this checkpoint,
and no accuracy/FAR/FRR number in this codebase is asserted as this
project's actual, calibrated performance** (Stage 3 brief, instruction
10: "Do not fabricate benchmark numbers"). Every number this module's
own tests compute is derived from synthetic, seeded-random test data
that exists only to prove the *math* is correct — never real student
biometric data (which this repository must never contain at all — see
``docs/BIOMETRIC_DATA_POLICY.md``). Calibration against this project's
own real classroom data is explicitly documented as **pending** — see
``docs/HANDOVER_PHASE_5_STAGE_3.md``, "Calibration status".
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class EvaluationPair:
    """One scored comparison: is this pair the same person, and how similar
    did the matcher's similarity metric say they were?

    ``is_genuine=True`` means both embeddings came from the same
    identity (a "genuine pair"); ``False`` means they came from two
    different identities (an "impostor pair"). ``similarity`` uses this
    codebase's fixed cosine-similarity convention
    (``app.modules.face_recognition.domain``), the same metric
    ``app.modules.face_recognition.providers.similarity_matcher``
    computes at match time.
    """

    is_genuine: bool
    similarity: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.similarity):
            raise ValueError("EvaluationPair.similarity must be a finite number.")
        if not (-1.0 <= self.similarity <= 1.0):
            raise ValueError("EvaluationPair.similarity must be within [-1.0, 1.0].")


@dataclass(frozen=True)
class ThresholdEvaluation:
    """FAR/FRR at one specific threshold, plus the counts they were computed from."""

    threshold: float
    false_accept_rate: float
    false_reject_rate: float
    genuine_pair_count: int
    impostor_pair_count: int


def compute_far_frr(pairs: Sequence[EvaluationPair], *, threshold: float) -> ThresholdEvaluation:
    """False Accept Rate / False Reject Rate at a single ``threshold``.

    - **False accept**: an impostor pair (``is_genuine=False``) whose
      similarity is ``>= threshold`` (the matcher would have called
      this a match — wrongly).
    - **False reject**: a genuine pair (``is_genuine=True``) whose
      similarity is ``< threshold`` (the matcher would have missed a
      real match).

    Returns ``0.0`` for either rate if there are zero pairs of that
    class (never raises a division-by-zero) — a caller comparing
    multiple thresholds should check ``genuine_pair_count``/
    ``impostor_pair_count`` before trusting a rate computed from an
    empty class.
    """
    genuine = [pair for pair in pairs if pair.is_genuine]
    impostors = [pair for pair in pairs if not pair.is_genuine]

    false_rejects = sum(1 for pair in genuine if pair.similarity < threshold)
    false_accepts = sum(1 for pair in impostors if pair.similarity >= threshold)

    frr = (false_rejects / len(genuine)) if genuine else 0.0
    far = (false_accepts / len(impostors)) if impostors else 0.0

    return ThresholdEvaluation(
        threshold=threshold,
        false_accept_rate=far,
        false_reject_rate=frr,
        genuine_pair_count=len(genuine),
        impostor_pair_count=len(impostors),
    )


def threshold_sweep(
    pairs: Sequence[EvaluationPair], *, thresholds: Sequence[float]
) -> list[ThresholdEvaluation]:
    """``compute_far_frr`` at every threshold in ``thresholds``, in the given order."""
    return [compute_far_frr(pairs, threshold=threshold) for threshold in thresholds]


def ambiguity_rate(
    top_similarities: Sequence[tuple[float, float]], *, ambiguous_margin: float
) -> float:
    """Fraction of probe attempts whose best/runner-up gap is below ``ambiguous_margin``.

    ``top_similarities`` is a sequence of ``(best, runner_up)`` pairs —
    one per probe attempt, already computed by whatever produced the
    evaluation data (e.g. a candidate-scoped match over synthetic
    embeddings). Returns ``0.0`` for an empty input.
    """
    if not top_similarities:
        return 0.0
    ambiguous_count = sum(
        1 for best, runner_up in top_similarities if (best - runner_up) < ambiguous_margin
    )
    return ambiguous_count / len(top_similarities)
