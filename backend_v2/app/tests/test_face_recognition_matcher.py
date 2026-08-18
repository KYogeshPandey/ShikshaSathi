"""Tests for the face-recognition cosine-similarity matcher.

Pure-logic tests: no database, no HTTP, real cosine-similarity math only
(numpy-free — the matcher itself uses plain Python floats). A tiny
``_SettingsLike`` stand-in supplies just the two attributes the matcher
reads, so these tests do not need a real ``Settings`` instance.
"""

from __future__ import annotations

import math
import uuid

import pytest

from app.modules.face_recognition.domain import CandidateEmbedding, MatchStatus
from app.modules.face_recognition.errors import CandidateEmbeddingDimensionMismatchError
from app.modules.face_recognition.providers.similarity_matcher import CosineSimilarityFaceMatcher
from app.tests.phase5_stage3_helpers import (
    make_candidate,
    make_unit_embedding_vector,
    nudge_unit_vector,
)


class _SettingsLike:
    def __init__(self, *, threshold: float = 0.8, ambiguous_margin: float = 0.05) -> None:
        self.FACE_MATCH_THRESHOLD = threshold
        self.FACE_MATCH_AMBIGUOUS_MARGIN = ambiguous_margin


def _matcher(**kwargs: float) -> CosineSimilarityFaceMatcher:
    return CosineSimilarityFaceMatcher(_SettingsLike(**kwargs))


def test_match_with_no_candidates_returns_unknown() -> None:
    matcher = _matcher()
    probe = make_unit_embedding_vector(seed=1.0)

    result = matcher.match(probe, [])

    assert result.status is MatchStatus.UNKNOWN
    assert result.matched_student_profile_id is None
    assert result.best_candidate is None


def test_match_below_threshold_returns_unknown_but_reports_best_candidate() -> None:
    matcher = _matcher(threshold=0.999)
    probe = make_unit_embedding_vector(seed=1.0)
    # Deliberately close but NOT identical (~0.9988 similarity — see
    # nudge_unit_vector's calibration) and NOT close enough for 0.999.
    near_miss = nudge_unit_vector(probe, epsilon=0.05)
    candidate = make_candidate(seed=1.0)
    candidate = candidate.model_copy(update={"embedding": near_miss})

    result = matcher.match(probe, [candidate])

    assert result.status is MatchStatus.UNKNOWN
    assert result.matched_student_profile_id is None
    assert result.best_candidate is not None
    assert result.best_candidate.student_profile_id == candidate.student_profile_id
    assert result.best_candidate.similarity < 0.999


def test_match_with_single_clear_candidate_returns_found() -> None:
    matcher = _matcher(threshold=0.5, ambiguous_margin=0.05)
    probe = make_unit_embedding_vector(seed=1.0)
    same_student_id = uuid.uuid4()
    candidate = CandidateEmbedding(
        student_profile_id=same_student_id, embedding=make_unit_embedding_vector(seed=1.0)
    )

    result = matcher.match(probe, [candidate])

    assert result.status is MatchStatus.FOUND
    assert result.matched_student_profile_id == same_student_id
    assert result.best_candidate is not None
    assert math.isclose(result.best_candidate.similarity, 1.0, abs_tol=1e-9)
    assert result.runner_up_candidate is None


def test_match_with_two_close_candidates_returns_ambiguous() -> None:
    matcher = _matcher(threshold=0.1, ambiguous_margin=0.05)
    probe = make_unit_embedding_vector(seed=1.0)
    candidate_a = make_candidate(seed=1.0)  # identical to probe -> similarity 1.0
    candidate_a = candidate_a.model_copy(update={"embedding": probe})
    # ~0.961 similarity to probe (see nudge_unit_vector calibration) —
    # gap to candidate_a's 1.0 is ~0.039, inside the 0.05 margin.
    close_embedding = nudge_unit_vector(probe, epsilon=0.3)
    candidate_b = make_candidate(seed=2.0)
    candidate_b = candidate_b.model_copy(update={"embedding": close_embedding})

    result = matcher.match(probe, [candidate_a, candidate_b])

    assert result.status is MatchStatus.AMBIGUOUS
    assert result.matched_student_profile_id is None
    assert result.best_candidate is not None
    assert result.runner_up_candidate is not None
    assert (result.best_candidate.similarity - result.runner_up_candidate.similarity) < 0.05


def test_match_ties_are_broken_deterministically_by_student_id() -> None:
    """Two candidates with the identical embedding (identical similarity) —
    the winner must always be the lexicographically smaller UUID string,
    on every run, regardless of input list order."""
    shared_embedding = make_unit_embedding_vector(seed=1.0)
    id_low = uuid.UUID("00000000-0000-0000-0000-000000000001")
    id_high = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    candidate_low = CandidateEmbedding(student_profile_id=id_low, embedding=shared_embedding)
    candidate_high = CandidateEmbedding(student_profile_id=id_high, embedding=shared_embedding)
    matcher = _matcher(threshold=0.0, ambiguous_margin=0.0)
    probe = shared_embedding

    result_forward = matcher.match(probe, [candidate_low, candidate_high])
    result_reversed = matcher.match(probe, [candidate_high, candidate_low])

    assert result_forward.matched_student_profile_id == id_low
    assert result_reversed.matched_student_profile_id == id_low


def test_match_rejects_dimension_mismatched_candidate() -> None:
    matcher = _matcher()
    probe = make_unit_embedding_vector(dimension=128, seed=1.0)
    mismatched = make_candidate(dimension=64, seed=1.0)

    with pytest.raises(CandidateEmbeddingDimensionMismatchError):
        matcher.match(probe, [mismatched])


def test_match_excludes_out_of_scope_students_implicitly() -> None:
    """The matcher only ever sees what its caller supplies — there is no
    way for a student outside the given `candidates` list to affect the
    result (the real scope-enforcement lives in
    app.modules.face_recognition.matching_service, tested separately)."""
    matcher = _matcher(threshold=0.5, ambiguous_margin=0.05)
    probe = make_unit_embedding_vector(seed=1.0)
    in_scope = uuid.uuid4()
    candidate = CandidateEmbedding(
        student_profile_id=in_scope, embedding=make_unit_embedding_vector(seed=1.0)
    )

    result = matcher.match(probe, [candidate])

    assert result.matched_student_profile_id == in_scope


def test_match_aggregates_multiple_samples_per_student_using_best_sample() -> None:
    """Same student appears twice: one poor sample, one excellent sample —
    the matcher must use the BEST one (max similarity), not average them
    or let the poor sample drag the result below threshold."""
    matcher = _matcher(threshold=0.9, ambiguous_margin=0.01)
    probe = make_unit_embedding_vector(seed=1.0)
    student_id = uuid.uuid4()
    good_sample = CandidateEmbedding(
        student_profile_id=student_id, embedding=make_unit_embedding_vector(seed=1.0)
    )
    poor_sample = CandidateEmbedding(
        student_profile_id=student_id, embedding=make_unit_embedding_vector(seed=99.0)
    )

    result = matcher.match(probe, [poor_sample, good_sample])

    assert result.status is MatchStatus.FOUND
    assert result.matched_student_profile_id == student_id
    assert result.best_candidate is not None
    assert math.isclose(result.best_candidate.similarity, 1.0, abs_tol=1e-9)


def test_match_two_samples_of_same_student_never_produce_self_ambiguity() -> None:
    """A student's own two samples must never trigger AMBIGUOUS against
    themselves — aggregation collapses them into one score per student
    before the ambiguity-margin comparison ever runs."""
    matcher = _matcher(threshold=0.5, ambiguous_margin=0.9)
    probe = make_unit_embedding_vector(seed=1.0)
    student_id = uuid.uuid4()
    sample_one = CandidateEmbedding(
        student_profile_id=student_id, embedding=make_unit_embedding_vector(seed=1.0)
    )
    sample_two = CandidateEmbedding(
        student_profile_id=student_id, embedding=make_unit_embedding_vector(seed=1.01)
    )

    result = matcher.match(probe, [sample_one, sample_two])

    assert result.status is MatchStatus.FOUND
    assert result.matched_student_profile_id == student_id
