"""Phase 5 Stage 4 recognition-to-attendance orchestration.

This is the only face-recognition application layer that may request an
attendance mutation, and it does so exclusively through Phase 4's
``AttendanceService``. It never imports ``AttendanceRepository`` or constructs
an ``AttendanceRecord``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.db.transaction import service_transaction
from app.modules.attendance.models import AttendanceStatus, AuditOutcome
from app.modules.attendance.read_service import AttendanceReadService
from app.modules.attendance.repository import AuditLogRepository
from app.modules.attendance.schemas import BulkAttendanceRecordIn, BulkAttendanceRequest
from app.modules.attendance.service import AttendanceService
from app.modules.face_recognition.domain import EmbeddingVector, MatchStatus
from app.modules.face_recognition.errors import (
    RecognitionAttendanceAttemptNotFoundError,
    RecognitionAttendanceConfirmationConflictError,
    RecognitionAttendanceMatchOutsideRosterError,
    RecognitionAttendanceReviewConfirmationConflictError,
    RecognitionAttendanceReviewNotFoundError,
    RecognitionAttendanceRosterEmptyError,
    RecognitionAttendanceStudentNotInRosterError,
)
from app.modules.face_recognition.matching_service import MatchingService
from app.modules.face_recognition.repository import (
    RecognitionAttendanceAttemptRepository,
    RecognitionAttendanceReviewRepository,
)
from app.modules.profiles.repository import StudentProfileRepository
from app.modules.users.models import User

logger = structlog.get_logger(__name__)

ACTION_RECOGNITION_ATTENDANCE_ATTEMPT = "face_recognition.attendance_attempt"
ACTION_RECOGNITION_ATTENDANCE_DECISION = "face_recognition.attendance_decision"
ACTION_RECOGNITION_ATTENDANCE_CONFIRMATION = "face_recognition.attendance_confirmation"
_ENTITY_TYPE_RECOGNITION_ATTEMPT = "recognition_attendance_attempt"

_REASON_AUTHORIZED_ROSTER_EMPTY = "authorized_roster_empty"
_REASON_ATTEMPT_NOT_FOUND = "attempt_not_found"
_REASON_ALREADY_CONFIRMED_DIFFERENT_STUDENT = "already_confirmed_different_student"
_REASON_STUDENT_NOT_IN_AUTHORIZED_ROSTER = "student_not_in_authorized_roster"
_REASON_MATCH_OUTSIDE_AUTHORIZED_ROSTER = "match_outside_authorized_roster"


@dataclass(frozen=True)
class AuthorizedRecognitionScope:
    classroom_id: uuid.UUID
    subject_id: uuid.UUID
    attendance_date: date
    candidate_student_profile_ids: tuple[uuid.UUID, ...]


@dataclass(frozen=True)
class RecognitionAttemptOutcome:
    attempt_id: uuid.UUID
    classroom_id: uuid.UUID
    subject_id: uuid.UUID
    attendance_date: date
    decision: MatchStatus
    matched_student_profile_id: uuid.UUID | None
    attendance_record_id: uuid.UUID | None


@dataclass(frozen=True)
class RecognitionConfirmationOutcome:
    attempt_id: uuid.UUID
    decision: MatchStatus
    confirmed_student_profile_id: uuid.UUID
    attendance_record_id: uuid.UUID


@dataclass(frozen=True)
class RecognitionReviewProposalOutcome:
    attempt_id: uuid.UUID
    face_index: int
    decision: MatchStatus
    matched_student_profile_id: uuid.UUID | None
    best_similarity: float | None
    is_duplicate: bool


@dataclass(frozen=True)
class RecognitionReviewOutcome:
    review_id: uuid.UUID
    classroom_id: uuid.UUID
    subject_id: uuid.UUID
    attendance_date: date
    face_count: int
    proposals: tuple[RecognitionReviewProposalOutcome, ...]


@dataclass(frozen=True)
class RecognitionReviewConfirmationOutcome:
    review_id: uuid.UUID
    attendance_record_ids: tuple[uuid.UUID, ...]
    confirmed_records: tuple[tuple[uuid.UUID, AttendanceStatus], ...]


def _independent_session_factory(
    session: AsyncSession,
) -> async_sessionmaker[AsyncSession]:
    bind = session.bind
    if not isinstance(bind, AsyncEngine):
        raise RuntimeError("recognition attendance session must be bound to an AsyncEngine")
    return async_sessionmaker(bind=bind, expire_on_commit=False, autoflush=False)


class RecognitionAttendanceService:
    def __init__(self, session: AsyncSession, *, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._attempts = RecognitionAttendanceAttemptRepository(session)
        self._reviews = RecognitionAttendanceReviewRepository(session)
        self._audit_logs = AuditLogRepository(session)
        self._students = StudentProfileRepository(session)

    async def resolve_authorized_scope(
        self,
        *,
        current_user: User,
        classroom_id: uuid.UUID,
        subject_id: uuid.UUID,
        attendance_date: date,
        request_id: str | None = None,
    ) -> AuthorizedRecognitionScope:
        """Authorize before image access and derive the active classroom roster."""
        async with service_transaction(self._session):
            await AttendanceReadService(self._session).authorize_scope(
                current_user,
                classroom_id=classroom_id,
                subject_id=subject_id,
                request_id=request_id,
                action=ACTION_RECOGNITION_ATTENDANCE_ATTEMPT,
            )
            profiles = await self._students.list_by_classroom(classroom_id)
            candidate_ids = tuple(
                sorted(
                    (profile.id for profile in profiles if profile.is_active),
                    key=str,
                )
            )

        if not candidate_ids:
            await self._write_blocked_audit(
                actor_user_id=current_user.id,
                action=ACTION_RECOGNITION_ATTENDANCE_ATTEMPT,
                entity_id=None,
                classroom_id=classroom_id,
                subject_id=subject_id,
                request_id=request_id,
                event_metadata={"reason_code": _REASON_AUTHORIZED_ROSTER_EMPTY},
            )
            raise RecognitionAttendanceRosterEmptyError()

        return AuthorizedRecognitionScope(
            classroom_id=classroom_id,
            subject_id=subject_id,
            attendance_date=attendance_date,
            candidate_student_profile_ids=candidate_ids,
        )

    async def create_attempt(
        self,
        *,
        current_user: User,
        scope: AuthorizedRecognitionScope,
        probe_embedding: EmbeddingVector,
        request_id: str | None = None,
    ) -> RecognitionAttemptOutcome:
        """Match within ``scope`` and persist a proposal without attendance writes."""
        roster = list(scope.candidate_student_profile_ids)
        outcome = await MatchingService(self._session, settings=self._settings).match_probe(
            probe_embedding=probe_embedding,
            candidate_student_profile_ids=roster,
            actor=current_user,
            request_id=request_id,
        )

        matched_id = outcome.matched_student_profile_id
        if (
            outcome.status is MatchStatus.FOUND
            and matched_id not in scope.candidate_student_profile_ids
        ):
            await self._write_blocked_audit(
                actor_user_id=current_user.id,
                action=ACTION_RECOGNITION_ATTENDANCE_DECISION,
                entity_id=None,
                classroom_id=scope.classroom_id,
                subject_id=scope.subject_id,
                request_id=request_id,
                event_metadata={
                    "reason_code": _REASON_MATCH_OUTSIDE_AUTHORIZED_ROSTER,
                    "recognition_decision": outcome.status.value,
                },
            )
            raise RecognitionAttendanceMatchOutsideRosterError()

        async with service_transaction(self._session):
            attempt = await self._attempts.create(
                actor_user_id=current_user.id,
                classroom_id=scope.classroom_id,
                subject_id=scope.subject_id,
                attendance_date=scope.attendance_date,
                decision=outcome.status,
                matched_student_profile_id=matched_id,
                candidate_student_profile_ids=roster,
            )
            await self._audit_logs.create(
                actor_user_id=current_user.id,
                action=ACTION_RECOGNITION_ATTENDANCE_DECISION,
                outcome=AuditOutcome.SUCCESS,
                entity_type=_ENTITY_TYPE_RECOGNITION_ATTEMPT,
                entity_id=attempt.id,
                classroom_id=scope.classroom_id,
                subject_id=scope.subject_id,
                request_id=request_id,
                event_metadata={
                    "recognition_attempt_id": str(attempt.id),
                    "recognition_decision": outcome.status.value,
                    "matched_student_profile_id": str(matched_id) if matched_id else None,
                    "candidate_count": len(roster),
                },
            )

        return RecognitionAttemptOutcome(
            attempt_id=attempt.id,
            classroom_id=scope.classroom_id,
            subject_id=scope.subject_id,
            attendance_date=scope.attendance_date,
            decision=outcome.status,
            matched_student_profile_id=matched_id,
            attendance_record_id=None,
        )

    async def create_review(
        self,
        *,
        current_user: User,
        scope: AuthorizedRecognitionScope,
        probe_embeddings: list[EmbeddingVector],
        request_id: str | None = None,
    ) -> RecognitionReviewOutcome:
        """Create one review and one non-writing proposal per detected face."""
        roster = list(scope.candidate_student_profile_ids)
        matches = []
        for embedding in probe_embeddings:
            matches.append(
                await MatchingService(self._session, settings=self._settings).match_probe(
                    probe_embedding=embedding,
                    candidate_student_profile_ids=roster,
                    actor=current_user,
                    request_id=request_id,
                )
            )

        seen_students: set[uuid.UUID] = set()
        proposals: list[RecognitionReviewProposalOutcome] = []
        async with service_transaction(self._session):
            review = await self._reviews.create(
                actor_user_id=current_user.id,
                classroom_id=scope.classroom_id,
                subject_id=scope.subject_id,
                attendance_date=scope.attendance_date,
                candidate_student_profile_ids=roster,
                face_count=len(matches),
            )
            for face_index, outcome in enumerate(matches):
                matched_id = outcome.matched_student_profile_id
                if outcome.status is MatchStatus.FOUND and matched_id not in roster:
                    raise RecognitionAttendanceMatchOutsideRosterError()
                is_duplicate = matched_id is not None and matched_id in seen_students
                if matched_id is not None:
                    seen_students.add(matched_id)
                attempt = await self._attempts.create(
                    review_id=review.id,
                    face_index=face_index,
                    is_duplicate=is_duplicate,
                    actor_user_id=current_user.id,
                    classroom_id=scope.classroom_id,
                    subject_id=scope.subject_id,
                    attendance_date=scope.attendance_date,
                    decision=outcome.status,
                    matched_student_profile_id=matched_id,
                    candidate_student_profile_ids=roster,
                )
                await self._audit_logs.create(
                    actor_user_id=current_user.id,
                    action=ACTION_RECOGNITION_ATTENDANCE_DECISION,
                    outcome=AuditOutcome.SUCCESS,
                    entity_type=_ENTITY_TYPE_RECOGNITION_ATTEMPT,
                    entity_id=attempt.id,
                    classroom_id=scope.classroom_id,
                    subject_id=scope.subject_id,
                    request_id=request_id,
                    event_metadata={
                        "recognition_attempt_id": str(attempt.id),
                        "recognition_review_id": str(review.id),
                        "recognition_decision": outcome.status.value,
                        "matched_student_profile_id": str(matched_id) if matched_id else None,
                        "face_index": face_index,
                        "is_duplicate": is_duplicate,
                        "candidate_count": len(roster),
                    },
                )
                proposals.append(
                    RecognitionReviewProposalOutcome(
                        attempt_id=attempt.id,
                        face_index=face_index,
                        decision=outcome.status,
                        matched_student_profile_id=matched_id,
                        best_similarity=outcome.best_similarity,
                        is_duplicate=is_duplicate,
                    )
                )

        return RecognitionReviewOutcome(
            review_id=review.id,
            classroom_id=scope.classroom_id,
            subject_id=scope.subject_id,
            attendance_date=scope.attendance_date,
            face_count=len(matches),
            proposals=tuple(proposals),
        )

    async def confirm_review(
        self,
        *,
        current_user: User,
        review_id: uuid.UUID,
        records: list[BulkAttendanceRecordIn],
        request_id: str | None = None,
    ) -> RecognitionReviewConfirmationOutcome:
        """Persist only the teacher-reviewed statuses through AttendanceService."""
        normalized = sorted(
            ((record.student_profile_id, record.status) for record in records),
            key=lambda item: str(item[0]),
        )
        serialized = [
            {"student_profile_id": str(student_id), "status": status.value}
            for student_id, status in normalized
        ]
        async with service_transaction(self._session):
            review = await self._reviews.get_by_id(review_id, for_update=True)
            if review is None:
                raise RecognitionAttendanceReviewNotFoundError()
            await AttendanceReadService(self._session).authorize_scope(
                current_user,
                classroom_id=review.classroom_id,
                subject_id=review.subject_id,
                request_id=request_id,
                action=ACTION_RECOGNITION_ATTENDANCE_CONFIRMATION,
            )
            current_profiles = await self._students.list_by_classroom(review.classroom_id)
            current_roster = {profile.id for profile in current_profiles if profile.is_active}
            original_roster = set(review.candidate_student_profile_ids)
            if any(
                student_id not in current_roster or student_id not in original_roster
                for student_id, _ in normalized
            ):
                raise RecognitionAttendanceStudentNotInRosterError()

            if review.confirmed_at is not None:
                if review.confirmed_records != serialized:
                    raise RecognitionAttendanceReviewConfirmationConflictError()
                return RecognitionReviewConfirmationOutcome(
                    review_id=review.id,
                    attendance_record_ids=tuple(review.attendance_record_ids or []),
                    confirmed_records=tuple(normalized),
                )

            session_factory = _independent_session_factory(self._session)
            async with session_factory() as attendance_session:
                result = await AttendanceService(attendance_session).bulk_save(
                    current_user=current_user,
                    payload=BulkAttendanceRequest(
                        classroom_id=review.classroom_id,
                        subject_id=review.subject_id,
                        attendance_date=review.attendance_date,
                        records=records,
                    ),
                    request_id=request_id,
                )

            await self._reviews.confirm(
                review,
                confirmed_by_user_id=current_user.id,
                confirmed_at=datetime.now(UTC),
                confirmed_records=serialized,
                attendance_record_ids=result.record_ids,
            )
            await self._audit_logs.create(
                actor_user_id=current_user.id,
                action=ACTION_RECOGNITION_ATTENDANCE_CONFIRMATION,
                outcome=AuditOutcome.SUCCESS,
                entity_type="recognition_attendance_review",
                entity_id=review.id,
                classroom_id=review.classroom_id,
                subject_id=review.subject_id,
                request_id=request_id,
                event_metadata={
                    "recognition_review_id": str(review.id),
                    "confirmed_record_count": len(records),
                },
            )
            return RecognitionReviewConfirmationOutcome(
                review_id=review.id,
                attendance_record_ids=tuple(result.record_ids),
                confirmed_records=tuple(normalized),
            )

    async def confirm_attempt(
        self,
        *,
        current_user: User,
        attempt_id: uuid.UUID,
        student_profile_id: uuid.UUID,
        request_id: str | None = None,
    ) -> RecognitionConfirmationOutcome:
        """Explicitly confirm any proposal under a locked, re-authorized attempt."""
        async with service_transaction(self._session):
            attempt = await self._attempts.get_by_id(attempt_id, for_update=True)
            if attempt is None:
                await self._audit_invalid_confirmation(
                    current_user=current_user,
                    attempt_id=attempt_id,
                    classroom_id=None,
                    subject_id=None,
                    selected_student_profile_id=student_profile_id,
                    request_id=request_id,
                    reason_code=_REASON_ATTEMPT_NOT_FOUND,
                )
                raise RecognitionAttendanceAttemptNotFoundError()

            await AttendanceReadService(self._session).authorize_scope(
                current_user,
                classroom_id=attempt.classroom_id,
                subject_id=attempt.subject_id,
                request_id=request_id,
                action=ACTION_RECOGNITION_ATTENDANCE_CONFIRMATION,
            )

            current_profiles = await self._students.list_by_classroom(attempt.classroom_id)
            current_roster = {profile.id for profile in current_profiles if profile.is_active}
            original_roster = set(attempt.candidate_student_profile_ids)
            if (
                student_profile_id not in original_roster
                or student_profile_id not in current_roster
            ):
                await self._audit_invalid_confirmation(
                    current_user=current_user,
                    attempt_id=attempt.id,
                    classroom_id=attempt.classroom_id,
                    subject_id=attempt.subject_id,
                    selected_student_profile_id=student_profile_id,
                    request_id=request_id,
                    reason_code=_REASON_STUDENT_NOT_IN_AUTHORIZED_ROSTER,
                )
                raise RecognitionAttendanceStudentNotInRosterError()

            if attempt.confirmed_student_profile_id is not None:
                if attempt.confirmed_student_profile_id != student_profile_id:
                    await self._audit_invalid_confirmation(
                        current_user=current_user,
                        attempt_id=attempt.id,
                        classroom_id=attempt.classroom_id,
                        subject_id=attempt.subject_id,
                        selected_student_profile_id=student_profile_id,
                        request_id=request_id,
                        reason_code=_REASON_ALREADY_CONFIRMED_DIFFERENT_STUDENT,
                    )
                    raise RecognitionAttendanceConfirmationConflictError()
                if attempt.attendance_record_id is None:  # pragma: no cover - DB invariant
                    raise RuntimeError("confirmed recognition attempt has no attendance record")
                return RecognitionConfirmationOutcome(
                    attempt_id=attempt.id,
                    decision=attempt.decision,
                    confirmed_student_profile_id=student_profile_id,
                    attendance_record_id=attempt.attendance_record_id,
                )

            # Keep the attempt row locked in this session while Phase 4 owns the
            # attendance transaction in a separate session. Concurrent confirmations
            # serialize on this lock; a crash after attendance commit is safe because
            # retrying uses AttendanceService's existing upsert/unique-key behavior.
            session_factory = _independent_session_factory(self._session)
            async with session_factory() as attendance_session:
                attendance_record_id = await self._mark_present(
                    session=attendance_session,
                    current_user=current_user,
                    classroom_id=attempt.classroom_id,
                    subject_id=attempt.subject_id,
                    attendance_date=attempt.attendance_date,
                    student_profile_id=student_profile_id,
                    request_id=request_id,
                )

            await self._attempts.confirm(
                attempt,
                student_profile_id=student_profile_id,
                confirmed_by_user_id=current_user.id,
                confirmed_at=datetime.now(UTC),
                attendance_record_id=attendance_record_id,
            )
            await self._audit_logs.create(
                actor_user_id=current_user.id,
                action=ACTION_RECOGNITION_ATTENDANCE_CONFIRMATION,
                outcome=AuditOutcome.SUCCESS,
                entity_type=_ENTITY_TYPE_RECOGNITION_ATTEMPT,
                entity_id=attempt.id,
                classroom_id=attempt.classroom_id,
                subject_id=attempt.subject_id,
                request_id=request_id,
                event_metadata={
                    "recognition_attempt_id": str(attempt.id),
                    "recognition_decision": attempt.decision.value,
                    "confirmed_student_profile_id": str(student_profile_id),
                },
            )

            return RecognitionConfirmationOutcome(
                attempt_id=attempt.id,
                decision=attempt.decision,
                confirmed_student_profile_id=student_profile_id,
                attendance_record_id=attendance_record_id,
            )

    async def _mark_present(
        self,
        *,
        session: AsyncSession,
        current_user: User,
        classroom_id: uuid.UUID,
        subject_id: uuid.UUID,
        attendance_date: date,
        student_profile_id: uuid.UUID,
        request_id: str | None,
    ) -> uuid.UUID:
        result = await AttendanceService(session).bulk_save(
            current_user=current_user,
            payload=BulkAttendanceRequest(
                classroom_id=classroom_id,
                subject_id=subject_id,
                attendance_date=attendance_date,
                records=[
                    BulkAttendanceRecordIn(
                        student_profile_id=student_profile_id,
                        status=AttendanceStatus.PRESENT,
                    )
                ],
            ),
            request_id=request_id,
        )
        return result.record_ids[0]

    async def _audit_invalid_confirmation(
        self,
        *,
        current_user: User,
        attempt_id: uuid.UUID,
        classroom_id: uuid.UUID | None,
        subject_id: uuid.UUID | None,
        selected_student_profile_id: uuid.UUID,
        request_id: str | None,
        reason_code: str,
    ) -> None:
        await self._write_blocked_audit(
            actor_user_id=current_user.id,
            action=ACTION_RECOGNITION_ATTENDANCE_CONFIRMATION,
            entity_id=attempt_id,
            classroom_id=classroom_id,
            subject_id=subject_id,
            request_id=request_id,
            event_metadata={
                "recognition_attempt_id": str(attempt_id),
                "selected_student_profile_id": str(selected_student_profile_id),
                "reason_code": reason_code,
            },
        )

    async def _write_blocked_audit(
        self,
        *,
        actor_user_id: uuid.UUID,
        action: str,
        entity_id: uuid.UUID | None,
        classroom_id: uuid.UUID | None,
        subject_id: uuid.UUID | None,
        request_id: str | None,
        event_metadata: dict[str, object],
    ) -> None:
        try:
            session_factory = _independent_session_factory(self._session)
            async with session_factory() as session:
                await AuditLogRepository(session).create(
                    actor_user_id=actor_user_id,
                    action=action,
                    outcome=AuditOutcome.BLOCKED,
                    entity_type=_ENTITY_TYPE_RECOGNITION_ATTEMPT,
                    entity_id=entity_id,
                    classroom_id=classroom_id,
                    subject_id=subject_id,
                    request_id=request_id,
                    event_metadata=event_metadata,
                )
                await session.commit()
        except Exception as exc:
            logger.error(
                "recognition_attendance_blocked_audit_write_failed",
                action=action,
                request_id=request_id,
                exc_type=type(exc).__name__,
            )


__all__ = [
    "ACTION_RECOGNITION_ATTENDANCE_ATTEMPT",
    "ACTION_RECOGNITION_ATTENDANCE_CONFIRMATION",
    "ACTION_RECOGNITION_ATTENDANCE_DECISION",
    "AuthorizedRecognitionScope",
    "RecognitionAttemptOutcome",
    "RecognitionAttendanceService",
    "RecognitionConfirmationOutcome",
    "RecognitionReviewConfirmationOutcome",
    "RecognitionReviewOutcome",
    "RecognitionReviewProposalOutcome",
]
