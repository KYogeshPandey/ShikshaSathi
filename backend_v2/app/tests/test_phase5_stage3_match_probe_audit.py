"""Tests for Stage 3 correction finding 4: safe ``/match-probe`` auditing.

``MatchingService.match_probe`` now requires ``actor``/``request_id`` and
writes exactly one audit row per call (``SUCCESS`` on a completed match
attempt, ``BLOCKED`` on an empty candidate scope) — see that module's
docstring. Every seeded sample here goes through
``app.tests.phase5_stage3_helpers.seed_active_sample_direct`` (ORM/
repository layer) plus ``SampleProcessingService.process_sample`` with fake
providers — never Stage 2's real HTTP upload endpoint — so these tests are
independent of the pre-existing, out-of-scope Stage 2 ``MissingGreenlet``
defect (see ``seed_active_sample_direct``'s own docstring and
``docs/HANDOVER_PHASE_5_STAGE_3.md``).
"""

from __future__ import annotations

import types
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.attendance.models import AttendanceRecord, AuditOutcome
from app.modules.attendance.repository import AuditLogRepository
from app.modules.face_recognition import router as router_module
from app.modules.face_recognition.domain import MatchStatus
from app.modules.face_recognition.errors import CandidateScopeRequiredError
from app.modules.face_recognition.matching_service import ACTION_MATCH_PROBE, MatchingService
from app.modules.face_recognition.processing_service import SampleProcessingService
from app.tests.phase5_stage2_http_helpers import seed_enrollment_scope
from app.tests.phase5_stage3_helpers import (
    FakeFaceDetector,
    FakeFaceEmbedder,
    make_detected_face,
    make_unit_embedding_vector,
    patch_providers,
    seed_active_sample_direct,
)


class _SettingsLike:
    def __init__(
        self, *, threshold: float = 0.5, ambiguous_margin: float = 0.05, dimension: int = 128
    ) -> None:
        self.FACE_MATCH_THRESHOLD = threshold
        self.FACE_MATCH_AMBIGUOUS_MARGIN = ambiguous_margin
        self.FACE_EMBEDDING_DIMENSION = dimension


async def _seed_one_processed_student(client_db, db_session: AsyncSession, *, suffix: str):
    """One admin + one classroom + one student with an ACTIVE, PROCESSED
    sample/embedding — built entirely through ORM seeding + fake providers,
    per this module's docstring."""
    scope = await seed_enrollment_scope(client_db, db_session, suffix=suffix)
    sample_id = await seed_active_sample_direct(
        db_session,
        student_profile_id=uuid.UUID(scope["student_profile_1"]["id"]),
        created_by_user_id=scope["admin"].id,
    )
    processing_service = SampleProcessingService(db_session)
    detector = FakeFaceDetector(results=[[make_detected_face()]])
    embedder = FakeFaceEmbedder(seed=1.0)
    with patch_providers(detector, embedder):
        result = await processing_service.process_sample(sample_id=sample_id, actor=scope["admin"])
    assert result.succeeded is True
    return scope


async def test_successful_match_probe_persists_success_audit_with_safe_metadata(
    client_db, db_session: AsyncSession
) -> None:
    scope = await _seed_one_processed_student(client_db, db_session, suffix="audit1")
    student_id = uuid.UUID(scope["student_profile_1"]["id"])
    service = MatchingService(db_session, settings=_SettingsLike(threshold=0.5))

    outcome = await service.match_probe(
        probe_embedding=make_unit_embedding_vector(seed=1.0),
        candidate_student_profile_ids=[student_id],
        actor=scope["admin"],
        request_id="req-audit-1",
    )
    assert outcome.status is MatchStatus.FOUND

    rows = await AuditLogRepository(db_session).list(
        action=ACTION_MATCH_PROBE, outcome=AuditOutcome.SUCCESS
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.actor_user_id == scope["admin"].id
    assert row.request_id == "req-audit-1"
    assert row.entity_id is None
    assert row.event_metadata == {
        "candidate_count": 1,
        "match_status": "found",
        "matched_student_profile_id": str(student_id),
    }


async def test_match_probe_with_no_match_persists_success_audit_without_matched_id(
    client_db, db_session: AsyncSession
) -> None:
    scope = await _seed_one_processed_student(client_db, db_session, suffix="audit2")
    student_id = uuid.UUID(scope["student_profile_1"]["id"])
    # An unrelated, very different embedding and a strict threshold so this
    # deterministically misses rather than depending on a borderline score.
    service = MatchingService(db_session, settings=_SettingsLike(threshold=0.99))

    outcome = await service.match_probe(
        probe_embedding=make_unit_embedding_vector(seed=999.0),
        candidate_student_profile_ids=[student_id],
        actor=scope["admin"],
        request_id="req-audit-2",
    )
    assert outcome.status is MatchStatus.UNKNOWN

    rows = await AuditLogRepository(db_session).list(
        action=ACTION_MATCH_PROBE, outcome=AuditOutcome.SUCCESS
    )
    assert len(rows) == 1
    assert rows[0].event_metadata["match_status"] == "unknown"
    assert rows[0].event_metadata["matched_student_profile_id"] is None
    assert rows[0].event_metadata["candidate_count"] == 1


async def test_empty_candidate_scope_persists_blocked_audit_before_raising(
    client_db, db_session: AsyncSession
) -> None:
    scope = await seed_enrollment_scope(client_db, db_session, suffix="audit3")
    service = MatchingService(db_session, settings=_SettingsLike())

    with pytest.raises(CandidateScopeRequiredError):
        await service.match_probe(
            probe_embedding=make_unit_embedding_vector(seed=1.0),
            candidate_student_profile_ids=[],
            actor=scope["admin"],
            request_id="req-audit-3",
        )

    rows = await AuditLogRepository(db_session).list(
        action=ACTION_MATCH_PROBE, outcome=AuditOutcome.BLOCKED
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.actor_user_id == scope["admin"].id
    assert row.request_id == "req-audit-3"
    assert row.entity_id is None
    assert row.event_metadata == {"reason_code": "candidate_scope_required"}

    # And no SUCCESS row was also written for the same blocked attempt.
    success_rows = await AuditLogRepository(db_session).list(
        action=ACTION_MATCH_PROBE, outcome=AuditOutcome.SUCCESS
    )
    assert success_rows == []


async def test_match_probe_audit_metadata_never_leaks_embeddings_or_paths(
    client_db, db_session: AsyncSession
) -> None:
    """Sanitization guard: the only keys ever written are the three safe,
    documented ones, and none of their values is embedding/path/exception
    shaped — regardless of match outcome (FOUND here; UNKNOWN/BLOCKED are
    covered, with their own exact-dict assertions, by the tests above)."""
    scope = await _seed_one_processed_student(client_db, db_session, suffix="audit4")
    student_id = uuid.UUID(scope["student_profile_1"]["id"])
    service = MatchingService(db_session, settings=_SettingsLike(threshold=0.5))

    await service.match_probe(
        probe_embedding=make_unit_embedding_vector(seed=1.0),
        candidate_student_profile_ids=[student_id],
        actor=scope["admin"],
        request_id="req-audit-4",
    )

    rows = await AuditLogRepository(db_session).list(
        action=ACTION_MATCH_PROBE, outcome=AuditOutcome.SUCCESS
    )
    assert len(rows) == 1
    metadata = rows[0].event_metadata

    assert set(metadata.keys()) == {"candidate_count", "match_status", "matched_student_profile_id"}
    serialized = str(metadata)
    # No embedding vector (a long run of numeric-looking floats), no image
    # bytes, no absolute filesystem/model path, no raw exception text.
    assert "0.0" not in serialized and "array(" not in serialized
    assert "/" not in serialized.replace("candidate_count", "").replace("match_status", "").replace(
        "matched_student_profile_id", ""
    )
    assert "Traceback" not in serialized
    assert isinstance(metadata["candidate_count"], int)
    assert isinstance(metadata["match_status"], str)


async def test_match_probe_never_writes_an_attendance_record(
    client_db, db_session: AsyncSession
) -> None:
    """Stage-boundary regression guard: a match-probe — audited or not —
    must never create or touch ``AttendanceRecord`` rows. ``MatchingService``
    has no ``AttendanceService``/``AttendanceRepository`` dependency at all
    (see its constructor); this asserts the end-to-end effect too."""
    scope = await _seed_one_processed_student(client_db, db_session, suffix="audit5")
    student_id = uuid.UUID(scope["student_profile_1"]["id"])
    service = MatchingService(db_session, settings=_SettingsLike(threshold=0.5))

    await service.match_probe(
        probe_embedding=make_unit_embedding_vector(seed=1.0),
        candidate_student_profile_ids=[student_id],
        actor=scope["admin"],
        request_id="req-audit-5",
    )

    result = await db_session.execute(select(AttendanceRecord))
    assert result.scalars().all() == []


# --- Stage 3 v3 correction: HTTP empty-scope BLOCKED audit -----------------


class _AssertNeverReadUploadFile:
    """A duck-typed stand-in for ``UploadFile`` that raises if ``read()`` is
    ever called — used to prove an empty candidate scope short-circuits
    before any file I/O (and therefore before any decoded-content
    validation or detect/align/embed inference) happens."""

    content_type = "image/jpeg"

    async def read(self, size: int = -1) -> bytes:
        raise AssertionError("file.read() must never be called for an empty candidate scope")

    async def close(self) -> None:
        pass


def _fake_request(request_id: str) -> types.SimpleNamespace:
    return types.SimpleNamespace(state=types.SimpleNamespace(request_id=request_id))


async def test_ensure_candidate_scope_persists_blocked_audit_for_empty_scope(
    client_db, db_session: AsyncSession
) -> None:
    """Direct, service-level regression test for the extracted
    ``MatchingService.ensure_candidate_scope`` helper: an empty scope writes
    the ``BLOCKED`` audit row before raising, independent of whether the
    caller is ``match_probe`` itself or ``router.match_probe`` (see the test
    below for the HTTP-shaped path)."""
    scope = await seed_enrollment_scope(client_db, db_session, suffix="audit6")
    service = MatchingService(db_session, settings=_SettingsLike())

    with pytest.raises(CandidateScopeRequiredError):
        await service.ensure_candidate_scope(
            candidate_student_profile_ids=[], actor=scope["admin"], request_id="req-audit-6"
        )

    rows = await AuditLogRepository(db_session).list(
        action=ACTION_MATCH_PROBE, outcome=AuditOutcome.BLOCKED
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.actor_user_id == scope["admin"].id
    assert row.request_id == "req-audit-6"
    assert row.entity_id is None
    # Sanitization: exactly the one documented, safe key — never an
    # embedding, image bytes, a path, or raw exception text.
    assert row.event_metadata == {"reason_code": "candidate_scope_required"}


async def test_ensure_candidate_scope_is_a_noop_for_non_empty_scope(
    client_db, db_session: AsyncSession
) -> None:
    """``ensure_candidate_scope`` is called twice in the real request flow
    (once by ``router.match_probe`` before file I/O, once again inside
    ``match_probe`` itself) — this proves the second call is a true no-op
    for an already-non-empty scope: no audit row of any kind is written,
    so the two calls never double-audit."""
    scope = await seed_enrollment_scope(client_db, db_session, suffix="audit7")
    service = MatchingService(db_session, settings=_SettingsLike())
    student_id = uuid.UUID(scope["student_profile_1"]["id"])

    await service.ensure_candidate_scope(
        candidate_student_profile_ids=[student_id],
        actor=scope["admin"],
        request_id="req-audit-7",
    )

    rows = await AuditLogRepository(db_session).list(action=ACTION_MATCH_PROBE)
    assert rows == []


async def test_http_empty_candidate_scope_persists_blocked_audit_and_skips_file_io(
    client_db, db_session: AsyncSession
) -> None:
    """Stage 3 v3 correction regression test — the actual bug fixed here.

    Calls ``router.match_probe`` directly as a plain coroutine function
    (the ``@router.post(...)`` decorator does not wrap/replace it — see
    ``test_phase5_stage3_offload_and_locking.py`` for the same pattern used
    for the thread-offload tests), with an empty candidate scope. Before
    this fix, the router had its own separate, unaudited
    ``if not candidate_student_profile_ids: raise ...`` pre-check that ran
    before a ``MatchingService`` was even constructed, so this exact,
    realistic HTTP-shaped call never wrote a ``BLOCKED`` audit row despite
    ``MatchingService.match_probe`` having one built in. Also proves no file
    I/O happens for the empty-scope case: the fake upload file's ``read()``
    raises if ever called.
    """
    scope = await seed_enrollment_scope(client_db, db_session, suffix="audit8")

    with pytest.raises(CandidateScopeRequiredError):
        await router_module.match_probe(
            admin=scope["admin"],
            session=db_session,
            request=_fake_request("req-audit-8"),
            file=_AssertNeverReadUploadFile(),
            candidate_student_profile_ids=[],
        )

    rows = await AuditLogRepository(db_session).list(
        action=ACTION_MATCH_PROBE, outcome=AuditOutcome.BLOCKED
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.actor_user_id == scope["admin"].id
    assert row.request_id == "req-audit-8"
    assert row.event_metadata == {"reason_code": "candidate_scope_required"}

    # And no SUCCESS row either — the empty scope never reached matching.
    success_rows = await AuditLogRepository(db_session).list(
        action=ACTION_MATCH_PROBE, outcome=AuditOutcome.SUCCESS
    )
    assert success_rows == []
