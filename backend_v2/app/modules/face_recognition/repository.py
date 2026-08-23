"""Data access for ``BiometricEmbedding`` — Phase 5 Stage 3.

Same conventions as
``app.modules.biometric_enrollment.repository``: thin, single-aggregate
access; callers own the transaction boundary (``flush()``/``refresh()``
only, never ``commit()``); no lazy-loaded relationship.

**Every read here that feeds matching is scoped by an explicit,
caller-supplied set of student IDs** (``list_active_for_students``) —
there is no method on this repository that returns "every embedding in
the system", which is this module's half of enforcing the Stage 3
brief's "do NOT compare every student in the entire institution by
default" (the other half — actually requiring a non-empty scope before
calling this — is
``app.modules.face_recognition.matching_service.MatchingService``'s
job).
"""

from __future__ import annotations

import builtins
import uuid
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.biometric_enrollment.models import (
    BiometricEnrollment,
    BiometricSample,
    RecognitionProcessingState,
    SampleStatus,
)
from app.modules.face_recognition.domain import MatchStatus
from app.modules.face_recognition.models import (
    BiometricEmbedding,
    RecognitionAttendanceAttempt,
    RecognitionAttendanceReview,
)


class CandidateEmbeddingRow:
    """A plain (non-ORM) row shape: one student's one active embedding.

    Returned by ``list_active_for_students`` instead of a raw SQLAlchemy
    ``Row``/tuple so callers (``MatchingService``) get named attributes
    without importing SQLAlchemy themselves — this repository's only
    export that isn't an ORM model or a UUID/primitive.
    """

    __slots__ = ("embedding_dimension", "embedding_values", "student_profile_id")

    def __init__(
        self,
        *,
        student_profile_id: uuid.UUID,
        embedding_values: list[float],
        embedding_dimension: int,
    ) -> None:
        self.student_profile_id = student_profile_id
        self.embedding_values = embedding_values
        self.embedding_dimension = embedding_dimension


class BiometricEmbeddingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active_for_sample(
        self, biometric_sample_id: uuid.UUID
    ) -> BiometricEmbedding | None:
        stmt = select(BiometricEmbedding).where(
            BiometricEmbedding.biometric_sample_id == biometric_sample_id,
            BiometricEmbedding.is_active.is_(True),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_active(
        self,
        *,
        biometric_sample_id: uuid.UUID,
        provider_name: str,
        model_identifier: str,
        model_version: str,
        embedding_values: builtins.list[float],
        model_artifact_checksum: str | None,
    ) -> BiometricEmbedding:
        """Insert one new active embedding row for a sample.

        Callers are responsible for first superseding any existing
        active row for this sample (see ``supersede_active_for_sample``)
        — this method does not do it implicitly, so the caller's
        transaction boundary controls exactly when the old row stops
        being active relative to when the new one starts.
        """
        embedding = BiometricEmbedding(
            biometric_sample_id=biometric_sample_id,
            provider_name=provider_name,
            model_identifier=model_identifier,
            model_version=model_version,
            embedding_dimension=len(embedding_values),
            embedding_values=embedding_values,
            model_artifact_checksum=model_artifact_checksum,
            is_active=True,
        )
        self._session.add(embedding)
        await self._session.flush()
        await self._session.refresh(embedding)
        return embedding

    async def supersede_active_for_sample(
        self, biometric_sample_id: uuid.UUID, *, superseded_at: datetime
    ) -> None:
        """Mark any existing active embedding for this sample as superseded.

        A no-op if none exists — the normal case for a first-time
        processing attempt (only a retry-after-success/force-reprocess
        path, not yet exposed via any Stage 3 API, would ever find an
        existing active row here).
        """
        existing = await self.get_active_for_sample(biometric_sample_id)
        if existing is None:
            return
        existing.is_active = False
        existing.superseded_at = superseded_at
        await self._session.flush()

    async def list_active_for_students(
        self, student_profile_ids: builtins.list[uuid.UUID]
    ) -> builtins.list[CandidateEmbeddingRow]:
        """Active embeddings for the given students, from live, PROCESSED samples only.

        The three-way join below is the single enforcement point for
        "retired/deleted/quarantined samples must never match" (Stage 3
        brief, instruction 9) and "deletion of biometric samples must
        make their embedding unavailable" (instruction 6): a sample
        that is no longer ``ACTIVE`` (soft-deleted, quarantined, mid-
        replacement, etc.) is excluded here regardless of whether its
        embedding row still physically exists — no separate cleanup
        step is required to make deletion "take effect" for matching
        purposes; see ``app.modules.face_recognition.models``'s module
        docstring.
        """
        if not student_profile_ids:
            return []
        stmt = (
            select(
                BiometricEnrollment.student_profile_id,
                BiometricEmbedding.embedding_values,
                BiometricEmbedding.embedding_dimension,
            )
            .join(BiometricSample, BiometricSample.id == BiometricEmbedding.biometric_sample_id)
            .join(BiometricEnrollment, BiometricEnrollment.id == BiometricSample.enrollment_id)
            .where(
                BiometricEmbedding.is_active.is_(True),
                BiometricSample.status == SampleStatus.ACTIVE,
                BiometricSample.processing_state == RecognitionProcessingState.PROCESSED,
                BiometricEnrollment.student_profile_id.in_(student_profile_ids),
            )
        )
        result = await self._session.execute(stmt)
        return [
            CandidateEmbeddingRow(
                student_profile_id=row.student_profile_id,
                embedding_values=list(row.embedding_values),
                embedding_dimension=row.embedding_dimension,
            )
            for row in result.all()
        ]


class RecognitionAttendanceAttemptRepository:
    """Thin persistence boundary for the Stage 4 attempt lifecycle."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(
        self, attempt_id: uuid.UUID, *, for_update: bool = False
    ) -> RecognitionAttendanceAttempt | None:
        stmt = select(RecognitionAttendanceAttempt).where(
            RecognitionAttendanceAttempt.id == attempt_id
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        actor_user_id: uuid.UUID,
        classroom_id: uuid.UUID,
        subject_id: uuid.UUID,
        attendance_date: date,
        decision: MatchStatus,
        matched_student_profile_id: uuid.UUID | None,
        candidate_student_profile_ids: list[uuid.UUID],
        review_id: uuid.UUID | None = None,
        face_index: int | None = None,
        is_duplicate: bool = False,
    ) -> RecognitionAttendanceAttempt:
        attempt = RecognitionAttendanceAttempt(
            review_id=review_id,
            face_index=face_index,
            is_duplicate=is_duplicate,
            actor_user_id=actor_user_id,
            classroom_id=classroom_id,
            subject_id=subject_id,
            attendance_date=attendance_date,
            decision=decision,
            matched_student_profile_id=matched_student_profile_id,
            candidate_count=len(candidate_student_profile_ids),
            candidate_student_profile_ids=list(candidate_student_profile_ids),
        )
        self._session.add(attempt)
        await self._session.flush()
        await self._session.refresh(attempt)
        return attempt

    async def set_attendance_record(
        self,
        attempt: RecognitionAttendanceAttempt,
        *,
        attendance_record_id: uuid.UUID,
    ) -> RecognitionAttendanceAttempt:
        attempt.attendance_record_id = attendance_record_id
        await self._session.flush()
        await self._session.refresh(attempt)
        return attempt

    async def confirm(
        self,
        attempt: RecognitionAttendanceAttempt,
        *,
        student_profile_id: uuid.UUID,
        confirmed_by_user_id: uuid.UUID,
        confirmed_at: datetime,
        attendance_record_id: uuid.UUID,
    ) -> RecognitionAttendanceAttempt:
        attempt.confirmed_student_profile_id = student_profile_id
        attempt.confirmed_by_user_id = confirmed_by_user_id
        attempt.confirmed_at = confirmed_at
        attempt.attendance_record_id = attendance_record_id
        await self._session.flush()
        await self._session.refresh(attempt)
        return attempt


class RecognitionAttendanceReviewRepository:
    """Persistence boundary for multi-face review and confirmation state."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(
        self, review_id: uuid.UUID, *, for_update: bool = False
    ) -> RecognitionAttendanceReview | None:
        stmt = select(RecognitionAttendanceReview).where(
            RecognitionAttendanceReview.id == review_id
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        actor_user_id: uuid.UUID,
        classroom_id: uuid.UUID,
        subject_id: uuid.UUID,
        attendance_date: date,
        candidate_student_profile_ids: list[uuid.UUID],
        face_count: int,
    ) -> RecognitionAttendanceReview:
        review = RecognitionAttendanceReview(
            actor_user_id=actor_user_id,
            classroom_id=classroom_id,
            subject_id=subject_id,
            attendance_date=attendance_date,
            candidate_count=len(candidate_student_profile_ids),
            candidate_student_profile_ids=list(candidate_student_profile_ids),
            face_count=face_count,
        )
        self._session.add(review)
        await self._session.flush()
        await self._session.refresh(review)
        return review

    async def confirm(
        self,
        review: RecognitionAttendanceReview,
        *,
        confirmed_by_user_id: uuid.UUID,
        confirmed_at: datetime,
        confirmed_records: list[dict[str, str]],
        attendance_record_ids: list[uuid.UUID],
    ) -> RecognitionAttendanceReview:
        review.confirmed_by_user_id = confirmed_by_user_id
        review.confirmed_at = confirmed_at
        review.confirmed_records = confirmed_records
        review.attendance_record_ids = attendance_record_ids
        await self._session.flush()
        await self._session.refresh(review)
        return review


__all__ = [
    "BiometricEmbeddingRepository",
    "CandidateEmbeddingRow",
    "RecognitionAttendanceAttemptRepository",
    "RecognitionAttendanceReviewRepository",
]
