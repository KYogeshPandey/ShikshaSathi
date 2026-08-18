"""Candidate-scoped matching orchestration — Phase 5 Stage 3.

This is the **only** authorized entrypoint into
``app.modules.face_recognition.providers.similarity_matcher`` in this
checkpoint. Its entire purpose is enforcing the two things a bare
``FaceMatcher`` provider deliberately cannot enforce on its own (see
``protocols.py``'s ``FaceMatcher`` docstring):

1. **An explicit, non-empty candidate scope is required.** ``match_probe``
   takes a caller-supplied ``candidate_student_profile_ids`` list and
   raises ``CandidateScopeRequiredError`` if it is empty — there is no
   "match against everyone" code path anywhere in this application.
2. **Only active, ``PROCESSED`` embeddings from live samples are ever
   candidates** — enforced by delegating the actual fetch to
   ``app.modules.face_recognition.repository.BiometricEmbeddingRepository
   .list_active_for_students``,
   which already joins through ``BiometricSample.status``/
   ``processing_state`` (see that method's own docstring).

**Authorization boundary (Stage 3 brief §13):** this service does not
itself decide *which* students an admin/teacher may query — that is
the router's job (``require_roles`` plus, for a future teacher-facing
caller, an ownership/roster check reusing Phase 2's dependency — not
added in Stage 3, since no teacher-facing endpoint exists yet; see
``docs/HANDOVER_PHASE_5_STAGE_3.md``, "Stage 4 starting point").
``MatchingService`` trusts the ``candidate_student_profile_ids`` it is
given were already authorized by its caller — matching this
codebase's existing "role/ownership checks happen once, in an
already-authorized service/router layer" convention.

**Never returns an embedding value** — ``MatchOutcome`` below carries
only a status, an optional matched student ID, and optional similarity
scores (floats, not vectors).

**Stage 3 correction (finding 4): every call is audited.** Reuses the
same ``app.db.transaction.service_transaction`` +
``app.modules.attendance.repository.AuditLogRepository`` pattern as
``processing_service.py`` (see that module's docstring). A successful,
authorized probe writes a ``SUCCESS`` audit row carrying only safe
metadata (candidate count, match status, and the matched student's ID
if any — the same fields already returned to the caller in
``MatchProbeResult``, so this adds no new exposure). An empty candidate
scope — the one way a request can be rejected *after* reaching this
service boundary — writes a ``BLOCKED`` row before raising
``CandidateScopeRequiredError``. Nothing here ever audits an embedding
vector, raw image bytes, a filesystem/model path, or a raw exception
message — see ``app.modules.face_recognition.errors``'s module
docstring on why every error message in this domain is already
generic.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.transaction import service_transaction
from app.modules.attendance.models import AuditOutcome
from app.modules.attendance.repository import AuditLogRepository
from app.modules.face_recognition.domain import (
    CandidateEmbedding,
    EmbeddingVector,
    MatchStatus,
    validate_embedding_dimension,
)
from app.modules.face_recognition.errors import CandidateScopeRequiredError
from app.modules.face_recognition.provider_factory import get_matcher
from app.modules.face_recognition.repository import BiometricEmbeddingRepository
from app.modules.users.models import User

ACTION_MATCH_PROBE = "face_recognition.match_probe"
_ENTITY_TYPE_MATCH_PROBE = "face_match_probe"

# Safe, generic reason codes for a BLOCKED match-probe audit row — never
# a raw exception message, matching the reason-code vocabulary already
# established in ``processing_service.py``.
REASON_CANDIDATE_SCOPE_REQUIRED = "candidate_scope_required"


@dataclass(frozen=True)
class MatchOutcome:
    """Safe, client-returnable result of one candidate-scoped match attempt."""

    status: MatchStatus
    matched_student_profile_id: uuid.UUID | None
    best_similarity: float | None
    runner_up_similarity: float | None


class MatchingService:
    def __init__(self, session: AsyncSession, *, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._embeddings = BiometricEmbeddingRepository(session)
        self._audit_logs = AuditLogRepository(session)

    async def ensure_candidate_scope(
        self,
        *,
        candidate_student_profile_ids: list[uuid.UUID],
        actor: User,
        request_id: str | None = None,
    ) -> None:
        """Raise ``CandidateScopeRequiredError`` if ``candidate_student_profile_ids``
        is empty — after first persisting a ``BLOCKED`` audit row for the attempt.

        Stage 3 v3 correction: this check (and its audit write) used to live
        only inline at the top of ``match_probe`` below, which is exactly
        right for a caller that reaches this service directly — but
        ``router.match_probe`` had its **own**, separate empty-scope check
        that ran *before* ever constructing a ``MatchingService`` or calling
        into it, so a real HTTP request with an empty scope never reached
        this audit write at all; the audit-writing code existed but was
        dead for the one caller that actually mattered. Factored out here
        so ``router.match_probe`` can call this exact check — and get the
        exact same ``BLOCKED`` audit — *before* it does any file
        reading/validation/inference for an empty scope, without
        duplicating the audit-writing logic: this is the only place that
        writes it. ``match_probe`` below also calls this as its own first
        step, so it remains independently safe to call directly (e.g. from
        a future, non-HTTP Stage 4 caller, or a test) without relying on a
        caller to have already checked.
        """
        if not candidate_student_profile_ids:
            await self._persist_blocked(
                actor=actor,
                request_id=request_id,
                reason_code=REASON_CANDIDATE_SCOPE_REQUIRED,
            )
            raise CandidateScopeRequiredError()

    async def match_probe(
        self,
        *,
        probe_embedding: EmbeddingVector,
        candidate_student_profile_ids: list[uuid.UUID],
        actor: User,
        request_id: str | None = None,
    ) -> MatchOutcome:
        """Match ``probe_embedding`` against exactly the given students' active embeddings.

        Raises ``CandidateScopeRequiredError`` if
        ``candidate_student_profile_ids`` is empty — see
        ``ensure_candidate_scope`` and this module's docstring. This is the
        sole enforcement point for "global unscoped matching rejected"
        (Stage 3 brief §9/§16): every other code path that could reach the
        matcher provider goes through this method.

        ``actor``/``request_id`` are required (not optional) as of the
        Stage 3 correction patch: every call through this method is now
        audited, so there is no code path that can reach the matcher
        without an attributable actor.
        """
        await self.ensure_candidate_scope(
            candidate_student_profile_ids=candidate_student_profile_ids,
            actor=actor,
            request_id=request_id,
        )

        probe_embedding = validate_embedding_dimension(
            probe_embedding, expected_dimension=self._settings.FACE_EMBEDDING_DIMENSION
        )

        rows = await self._embeddings.list_active_for_students(candidate_student_profile_ids)
        candidates = [
            CandidateEmbedding(
                student_profile_id=row.student_profile_id,
                embedding=EmbeddingVector(values=tuple(row.embedding_values)),
            )
            for row in rows
        ]

        matcher = get_matcher(self._settings)
        result = matcher.match(probe_embedding, candidates)

        best_similarity = result.best_candidate.similarity if result.best_candidate else None
        runner_up_similarity = (
            result.runner_up_candidate.similarity if result.runner_up_candidate else None
        )

        await self._persist_success(
            actor=actor,
            request_id=request_id,
            candidate_count=len(candidates),
            status=result.status,
            matched_student_profile_id=result.matched_student_profile_id,
        )

        return MatchOutcome(
            status=result.status,
            matched_student_profile_id=result.matched_student_profile_id,
            best_similarity=best_similarity,
            runner_up_similarity=runner_up_similarity,
        )

    async def _persist_success(
        self,
        *,
        actor: User,
        request_id: str | None,
        candidate_count: int,
        status: MatchStatus,
        matched_student_profile_id: uuid.UUID | None,
    ) -> None:
        async with service_transaction(self._session):
            await self._audit_logs.create(
                actor_user_id=actor.id,
                action=ACTION_MATCH_PROBE,
                outcome=AuditOutcome.SUCCESS,
                entity_type=_ENTITY_TYPE_MATCH_PROBE,
                entity_id=None,
                request_id=request_id,
                event_metadata={
                    "candidate_count": candidate_count,
                    "match_status": status.value,
                    "matched_student_profile_id": (
                        str(matched_student_profile_id) if matched_student_profile_id else None
                    ),
                },
            )

    async def _persist_blocked(
        self, *, actor: User, request_id: str | None, reason_code: str
    ) -> None:
        async with service_transaction(self._session):
            await self._audit_logs.create(
                actor_user_id=actor.id,
                action=ACTION_MATCH_PROBE,
                outcome=AuditOutcome.BLOCKED,
                entity_type=_ENTITY_TYPE_MATCH_PROBE,
                entity_id=None,
                request_id=request_id,
                event_metadata={"reason_code": reason_code},
            )
