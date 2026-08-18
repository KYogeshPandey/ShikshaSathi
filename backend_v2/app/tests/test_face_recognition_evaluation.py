"""Tests for ``app.modules.face_recognition.evaluation`` (Phase 5 Stage 3).

Pure math, deterministic synthetic data only — no real embeddings, no
real biometric data, no accuracy claim asserted about this project's
actual deployment (see that module's own docstring).
"""

from __future__ import annotations

import pytest

from app.modules.face_recognition.evaluation import (
    EvaluationPair,
    ambiguity_rate,
    compute_far_frr,
    threshold_sweep,
)


def _synthetic_pairs() -> list[EvaluationPair]:
    # Genuine pairs: mostly high similarity (0.7-0.95). Impostor pairs:
    # mostly low similarity (-0.2-0.4). Deliberately includes some
    # overlap near 0.5 so a threshold sweep shows real trade-offs rather
    # than a trivial perfect separator.
    genuine = [
        EvaluationPair(is_genuine=True, similarity=s)
        for s in (0.95, 0.9, 0.85, 0.8, 0.75, 0.7, 0.55, 0.4)
    ]
    impostor = [
        EvaluationPair(is_genuine=False, similarity=s)
        for s in (0.3, 0.25, 0.2, 0.1, 0.0, -0.1, -0.2, 0.6)
    ]
    return genuine + impostor


def test_evaluation_pair_rejects_out_of_range_similarity() -> None:
    with pytest.raises(ValueError):
        EvaluationPair(is_genuine=True, similarity=1.5)
    with pytest.raises(ValueError):
        EvaluationPair(is_genuine=False, similarity=-1.5)


def test_evaluation_pair_rejects_non_finite_similarity() -> None:
    with pytest.raises(ValueError):
        EvaluationPair(is_genuine=True, similarity=float("nan"))


def test_compute_far_frr_at_generous_threshold_accepts_everything() -> None:
    pairs = _synthetic_pairs()
    result = compute_far_frr(pairs, threshold=-1.0)
    assert result.false_reject_rate == 0.0
    assert result.false_accept_rate == 1.0  # every impostor also >= -1.0


def test_compute_far_frr_at_strict_threshold_rejects_everything() -> None:
    pairs = _synthetic_pairs()
    result = compute_far_frr(pairs, threshold=1.01)
    assert result.false_reject_rate == 1.0  # nothing reaches 1.01
    assert result.false_accept_rate == 0.0


def test_compute_far_frr_counts_match_hand_derived_values() -> None:
    pairs = _synthetic_pairs()
    threshold = 0.5
    result = compute_far_frr(pairs, threshold=threshold)

    genuine_values = [0.95, 0.9, 0.85, 0.8, 0.75, 0.7, 0.55, 0.4]
    impostor_values = [0.3, 0.25, 0.2, 0.1, 0.0, -0.1, -0.2, 0.6]
    expected_false_rejects = sum(1 for v in genuine_values if v < threshold)
    expected_false_accepts = sum(1 for v in impostor_values if v >= threshold)

    assert result.genuine_pair_count == len(genuine_values)
    assert result.impostor_pair_count == len(impostor_values)
    assert result.false_reject_rate == expected_false_rejects / len(genuine_values)
    assert result.false_accept_rate == expected_false_accepts / len(impostor_values)


def test_compute_far_frr_handles_empty_class_without_dividing_by_zero() -> None:
    only_genuine = [EvaluationPair(is_genuine=True, similarity=0.9)]
    result = compute_far_frr(only_genuine, threshold=0.5)
    assert result.impostor_pair_count == 0
    assert result.false_accept_rate == 0.0


def test_threshold_sweep_returns_one_result_per_threshold_in_order() -> None:
    pairs = _synthetic_pairs()
    thresholds = [0.0, 0.3, 0.5, 0.7, 0.9]

    results = threshold_sweep(pairs, thresholds=thresholds)

    assert [r.threshold for r in results] == thresholds
    # FRR is monotonically non-decreasing as threshold rises (stricter
    # threshold rejects at least as many genuine pairs).
    frr_values = [r.false_reject_rate for r in results]
    assert frr_values == sorted(frr_values)
    # FAR is monotonically non-increasing as threshold rises.
    far_values = [r.false_accept_rate for r in results]
    assert far_values == sorted(far_values, reverse=True)


def test_ambiguity_rate_computes_fraction_below_margin() -> None:
    top_similarities = [(0.9, 0.85), (0.9, 0.5), (0.8, 0.79), (0.7, 0.1)]
    rate = ambiguity_rate(top_similarities, ambiguous_margin=0.1)
    # The first and third pairs are below the 0.1 margin; the others are not.
    assert rate == 2 / 4


def test_ambiguity_rate_of_empty_input_is_zero() -> None:
    assert ambiguity_rate([], ambiguous_margin=0.05) == 0.0


def test_evaluation_module_never_asserts_a_real_accuracy_claim() -> None:
    """Structural guard: this module's docstring states no benchmark
    number is presented as this project's actual calibrated accuracy —
    assert that no such constant exists in this module's public surface."""
    import app.modules.face_recognition.evaluation as evaluation_module

    forbidden_names = {"PRODUCTION_ACCURACY", "CALIBRATED_THRESHOLD", "BENCHMARK_ACCURACY"}
    assert forbidden_names.isdisjoint(dir(evaluation_module))
