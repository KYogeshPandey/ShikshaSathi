"""Attendance bulk-save orchestration: transaction, authorization, audit.

Phase 4 Stage 2. Builds directly on Stage 1's models/schemas/errors/
repositories (``docs/HANDOVER_PHASE_4_STAGE_1.md``) — nothing in that
checkpoint is modified here.

Two distinct transaction boundaries are used, deliberately never mixed:

1. **The main batch transaction** (``app.db.transaction.service_transaction``,
   bound to ``self._session`` — the caller's request-scoped session).
   Reference/authorization checks, the student-by-student upsert loop, and
   the *success* audit-log write all happen inside this one boundary. Any
   exception anywhere in it — an invalid row, a repository/integrity
   error, or a failure while writing the success audit row — rolls back
   every attendance write made so far in this call, per the Stage 2
   brief's instruction A/B.

2. **The blocked-audit transaction** (``BlockedAuditWriter``, its own
   brand-new ``AsyncSession`` from a factory bound to the caller session's
   current ``AsyncEngine``). A teacher
   attempting to act on a classroom/subject scope they are not assigned
   to must still have that *attempt* durably recorded even though the
   main transaction is about to be rolled back (or, in Stage 2, was never
   written to at all — authorization runs before any attendance write).
   Reusing the main session for this would mean the blocked-audit row
   either gets rolled back along with everything else, or forces an
   early partial-commit that undermines the "one invalid row rolls back
   the whole batch" guarantee. A fully independent session/transaction
   sidesteps both problems.
"""

from __future__ import annotations

import uuid
from datetime import date

import structlog
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.db.transaction import service_transaction
from app.modules.academics.errors import (
    ClassroomNotFoundError,
    InactiveAcademicReferenceError,
    SubjectNotFoundError,
)
from app.modules.academics.models import Classroom, Subject
from app.modules.academics.repository import (
    ClassroomRepository,
    SubjectRepository,
    TeacherAssignmentRepository,
)
from app.modules.attendance.errors import (
    AttendanceBatchTooLargeError,
    AttendanceDuplicateStudentInBatchError,
    AttendanceInactiveStudentError,
    AttendanceRoleNotPermittedError,
    AttendanceScopeNotFoundError,
    AttendanceStudentNotFoundError,
    AttendanceStudentNotInClassroomError,
)
from app.modules.attendance.models import AuditLog, AuditOutcome
from app.modules.attendance.repository import AttendanceRepository, AuditLogRepository
from app.modules.attendance.schemas import (
    MAX_BULK_ATTENDANCE_ROWS,
    AttendanceBulkSaveResult,
    BulkAttendanceRecordIn,
    BulkAttendanceRequest,
)
from app.modules.profiles.repository import StudentProfileRepository, TeacherProfileRepository
from app.modules.users.models import User, UserRole

logger = structlog.get_logger(__name__)

# How many attendance-record IDs a single audit row's ``event_metadata``
# will list verbatim. A 200-row batch's full ID list would still be a
# small JSON payload, but this keeps the column's size bounded and
# independent of the (already-capped) batch size, per instruction B
# ("bounded attendance record IDs").
_AUDIT_MAX_RECORD_IDS = 50

ACTION_ATTENDANCE_BULK_MARK = "attendance.bulk_mark"
_ENTITY_TYPE_ATTENDANCE_BATCH = "attendance_batch"

# Safe, non-identifying reason codes recorded server-side only (in the
# blocked audit row's ``event_metadata``) — never returned to the client,
# which always sees the same concealed ``AttendanceScopeNotFoundError``.
_REASON_TEACHER_PROFILE_INACTIVE_OR_MISSING = "teacher_profile_inactive_or_missing"
_REASON_CLASSROOM_OR_SUBJECT_NOT_FOUND = "classroom_or_subject_not_found"
_REASON_ASSIGNMENT_INACTIVE_OR_MISSING = "teacher_assignment_inactive_or_missing"


def _independent_session_factory(
    session: AsyncSession,
) -> async_sessionmaker[AsyncSession]:
    """Build a fresh-session factory on the caller session's current engine.

    Request sessions and PostgreSQL test sessions are both bound directly to
    an ``AsyncEngine``. Reusing that exact engine keeps the independent audit
    transaction inside the same application/test lifecycle and event loop,
    while still giving the audit write a separate session and DB transaction.
    """
    bind = session.bind
    if not isinstance(bind, AsyncEngine):
        raise RuntimeError("attendance session must be bound to an AsyncEngine")
    return async_sessionmaker(bind=bind, expire_on_commit=False, autoflush=False)


class BlockedAuditWriter:
    """Write one blocked-attempt audit row in a separate transaction."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    @classmethod
    def from_session(cls, session: AsyncSession) -> BlockedAuditWriter:
        """Create a writer that shares the caller's engine lifecycle, not session."""
        return cls(_independent_session_factory(session))

    async def write(
        self,
        *,
        actor_user_id: uuid.UUID,
        action: str,
        entity_type: str,
        classroom_id: uuid.UUID | None,
        subject_id: uuid.UUID | None,
        request_id: str | None,
        reason_code: str,
        attempted_action: str,
    ) -> AuditLog:
        async with self._session_factory() as session:
            log = await AuditLogRepository(session).create(
                actor_user_id=actor_user_id,
                action=action,
                outcome=AuditOutcome.BLOCKED,
                entity_type=entity_type,
                classroom_id=classroom_id,
                subject_id=subject_id,
                request_id=request_id,
                event_metadata={
                    "reason_code": reason_code,
                    "attempted_action": attempted_action,
                },
            )
            await session.commit()
            return log


class AttendanceService:
    """Transaction-owned, authorization-checked attendance bulk-save."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        blocked_audit_writer: BlockedAuditWriter | None = None,
    ) -> None:
        self._session = session
        self._attendance = AttendanceRepository(session)
        self._audit_logs = AuditLogRepository(session)
        self._classrooms = ClassroomRepository(session)
        self._subjects = SubjectRepository(session)
        self._teachers = TeacherProfileRepository(session)
        self._students = StudentProfileRepository(session)
        self._assignments = TeacherAssignmentRepository(session)
        self._blocked_audit_writer = blocked_audit_writer or BlockedAuditWriter.from_session(
            session
        )

    # --- public entry point --------------------------------------------

    async def bulk_save(
        self,
        *,
        current_user: User,
        payload: BulkAttendanceRequest,
        request_id: str | None = None,
    ) -> AttendanceBulkSaveResult:
        """Create/update every record in ``payload`` as one transaction.

        Raises (non-exhaustive; see ``app.modules.attendance.errors``):

        - ``AttendanceBatchTooLargeError`` / ``AttendanceDuplicateStudentInBatchError``
          — defense-in-depth batch-shape checks, before any DB access.
        - ``AttendanceRoleNotPermittedError`` — caller is neither admin nor teacher.
        - ``ClassroomNotFoundError`` / ``SubjectNotFoundError`` — admin caller,
          reference does not exist.
        - ``AttendanceScopeNotFoundError`` — teacher caller, any flavor of
          scope denial (see this module's docstring); a blocked audit row
          is persisted first, independently, before this is raised.
        - ``InactiveAcademicReferenceError`` — classroom/subject exists
          (and, for a teacher, is within their assignment) but is inactive.
        - ``AttendanceStudentNotFoundError`` / ``AttendanceInactiveStudentError``
          / ``AttendanceStudentNotInClassroomError`` — a record's student
          fails validation.

        On any exception, the entire batch (every attendance write made
        so far in this call, and the success-audit write) is rolled back.
        """
        self._validate_batch_shape(payload)
        if current_user.role not in (UserRole.ADMIN, UserRole.TEACHER):
            raise AttendanceRoleNotPermittedError()

        async with service_transaction(self._session):
            classroom = await self._classrooms.get_by_id(payload.classroom_id)
            subject = await self._subjects.get_by_id(payload.subject_id)

            if current_user.role is UserRole.ADMIN:
                if classroom is None:
                    raise ClassroomNotFoundError()
                if subject is None:
                    raise SubjectNotFoundError()
            else:
                await self._authorize_teacher_scope(
                    current_user,
                    classroom=classroom,
                    subject=subject,
                    classroom_id=payload.classroom_id,
                    subject_id=payload.subject_id,
                    request_id=request_id,
                )

            # Authorization above guarantees both are non-None by this
            # point (admin: checked directly; teacher: scope check only
            # returns normally when both were resolved). Checked
            # explicitly (not via ``assert``, which ``python -O`` can
            # strip) since this is a genuine invariant, not a client
            # input to validate.
            if classroom is None or subject is None:  # pragma: no cover - invariant
                raise RuntimeError(
                    "attendance authorization invariant violated: "
                    "classroom/subject resolved as None after authorization succeeded"
                )
            if not classroom.is_active or not subject.is_active:
                raise InactiveAcademicReferenceError()

            await self._validate_students(classroom_id=classroom.id, records=payload.records)

            created_count, updated_count, record_ids = await self._write_attendance_records(
                classroom=classroom,
                subject=subject,
                attendance_date=payload.attendance_date,
                records=payload.records,
                marked_by_user_id=current_user.id,
            )

            await self._write_success_audit(
                current_user=current_user,
                classroom_id=classroom.id,
                subject_id=subject.id,
                attendance_date=payload.attendance_date,
                created_count=created_count,
                updated_count=updated_count,
                total_count=len(payload.records),
                record_ids=record_ids,
                request_id=request_id,
            )

        return AttendanceBulkSaveResult(
            classroom_id=classroom.id,
            subject_id=subject.id,
            attendance_date=payload.attendance_date,
            created_count=created_count,
            updated_count=updated_count,
            total_count=len(payload.records),
            record_ids=record_ids,
        )

    # --- batch-shape validation (defense in depth) ----------------------

    def _validate_batch_shape(self, payload: BulkAttendanceRequest) -> None:
        """Re-check what ``BulkAttendanceRequest`` already validates.

        Normal HTTP callers can never trigger either error here — the
        Pydantic schema already enforces both the 200-row cap and no
        duplicate ``student_profile_id`` at request-parsing time. This
        exists so the service itself never trusts an already-validated
        request object as its only line of defense (instruction A: "never
        trust actor, role, ownership, or marked_by values from request
        data" — extended here to batch shape as well).
        """
        if len(payload.records) > MAX_BULK_ATTENDANCE_ROWS:
            raise AttendanceBatchTooLargeError()
        seen: set[uuid.UUID] = set()
        for record in payload.records:
            if record.student_profile_id in seen:
                raise AttendanceDuplicateStudentInBatchError()
            seen.add(record.student_profile_id)

    # --- authorization ---------------------------------------------------

    async def _authorize_teacher_scope(
        self,
        current_user: User,
        *,
        classroom: Classroom | None,
        subject: Subject | None,
        classroom_id: uuid.UUID,
        subject_id: uuid.UUID,
        request_id: str | None,
    ) -> None:
        """Verify the teacher is actively assigned to (classroom, subject).

        Every denial path — missing/inactive teacher profile, a
        classroom/subject that does not exist, or a missing/inactive
        assignment — funnels into the same concealed
        ``AttendanceScopeNotFoundError``, after a blocked audit row is
        persisted (independently, see ``BlockedAuditWriter``) recording
        the real, safe reason code server-side only.
        """
        teacher_profile = await self._teachers.get_by_user_id(current_user.id)
        reason_code: str
        assigned = False

        if teacher_profile is None or not teacher_profile.is_active:
            reason_code = _REASON_TEACHER_PROFILE_INACTIVE_OR_MISSING
        elif classroom is None or subject is None:
            reason_code = _REASON_CLASSROOM_OR_SUBJECT_NOT_FOUND
        else:
            assigned = await self._assignments.exists(
                teacher_profile_id=teacher_profile.id,
                classroom_id=classroom.id,
                subject_id=subject.id,
                active_only=True,
            )
            reason_code = _REASON_ASSIGNMENT_INACTIVE_OR_MISSING

        if assigned:
            return

        try:
            await self._blocked_audit_writer.write(
                actor_user_id=current_user.id,
                action=ACTION_ATTENDANCE_BULK_MARK,
                entity_type=_ENTITY_TYPE_ATTENDANCE_BATCH,
                classroom_id=classroom_id,
                subject_id=subject_id,
                request_id=request_id,
                reason_code=reason_code,
                attempted_action=ACTION_ATTENDANCE_BULK_MARK,
            )
        except Exception as exc:
            # The blocked-audit write deliberately uses its own independent
            # session/transaction (BlockedAuditWriter) so that a failure
            # here is possible without touching the main transaction at
            # all. That failure must never replace or suppress the
            # original ownership-denial error the caller is about to
            # raise below — the request is still rejected either way,
            # just without a durable audit row this one time. Only the
            # exception's type is logged, never its message (no stack
            # trace, no driver detail — matching app/db/session.py's
            # ``require_database_ready`` convention for the same reason).
            logger.error(
                "blocked_audit_write_failed",
                reason_code=reason_code,
                request_id=request_id,
                exc_type=type(exc).__name__,
            )
        else:
            logger.warning(
                "attendance_scope_blocked",
                reason_code=reason_code,
                request_id=request_id,
            )
        raise AttendanceScopeNotFoundError()

    # --- student validation -----------------------------------------------

    async def _validate_students(
        self, *, classroom_id: uuid.UUID, records: list[BulkAttendanceRecordIn]
    ) -> None:
        """Every record's student must exist, be active, and be in ``classroom_id``.

        Raises on the first invalid record encountered. Runs entirely
        before any attendance row is written, so an invalid record never
        leaves a partial batch to roll back — it simply never starts.
        """
        for record in records:
            profile = await self._students.get_by_id(record.student_profile_id)
            if profile is None:
                raise AttendanceStudentNotFoundError()
            if not profile.is_active:
                raise AttendanceInactiveStudentError()
            if profile.classroom_id != classroom_id:
                raise AttendanceStudentNotInClassroomError()

    # --- writes ------------------------------------------------------------

    async def _write_attendance_records(
        self,
        *,
        classroom: Classroom,
        subject: Subject,
        attendance_date: date,
        records: list[BulkAttendanceRecordIn],
        marked_by_user_id: uuid.UUID,
    ) -> tuple[int, int, list[uuid.UUID]]:
        """Create missing rows, update existing ones. Never trusts ``marked_by``.

        ``marked_by_user_id`` always comes from the authenticated caller
        (the parameter above) — no field on ``BulkAttendanceRecordIn``
        carries an actor/marked-by value at all, so there is nothing from
        client input to accidentally trust here.
        """
        created_count = 0
        updated_count = 0
        record_ids: list[uuid.UUID] = []

        for record in records:
            student_profile_id = record.student_profile_id
            status = record.status
            remarks = record.remarks

            existing = await self._attendance.get_by_unique_key(
                student_profile_id=student_profile_id,
                classroom_id=classroom.id,
                subject_id=subject.id,
                attendance_date=attendance_date,
            )
            if existing is None:
                saved = await self._attendance.create(
                    student_profile_id=student_profile_id,
                    classroom_id=classroom.id,
                    subject_id=subject.id,
                    attendance_date=attendance_date,
                    status=status,
                    remarks=remarks,
                    marked_by_user_id=marked_by_user_id,
                )
                created_count += 1
            else:
                saved = await self._attendance.update(
                    existing,
                    status=status,
                    remarks=remarks,
                    marked_by_user_id=marked_by_user_id,
                )
                updated_count += 1
            record_ids.append(saved.id)

        return created_count, updated_count, record_ids

    async def _write_success_audit(
        self,
        *,
        current_user: User,
        classroom_id: uuid.UUID,
        subject_id: uuid.UUID,
        attendance_date: date,
        created_count: int,
        updated_count: int,
        total_count: int,
        record_ids: list[uuid.UUID],
        request_id: str | None,
    ) -> AuditLog:
        """Append one success audit row, in the same (still-open) transaction.

        Bounded, safe metadata only — never raw remarks, request bodies,
        tokens, cookies, passwords, or stack traces (instruction B). If
        this write itself fails (e.g. a forced/simulated error), the
        exception propagates out of the surrounding ``service_transaction``
        block and rolls back every attendance write made above.
        """
        bounded_ids = [str(record_id) for record_id in record_ids[:_AUDIT_MAX_RECORD_IDS]]
        event_metadata: dict[str, object] = {
            "attendance_date": attendance_date.isoformat(),
            "created_count": created_count,
            "updated_count": updated_count,
            "total_count": total_count,
            "record_ids": bounded_ids,
            "record_ids_truncated": len(record_ids) > _AUDIT_MAX_RECORD_IDS,
        }
        return await self._audit_logs.create(
            actor_user_id=current_user.id,
            action=ACTION_ATTENDANCE_BULK_MARK,
            outcome=AuditOutcome.SUCCESS,
            entity_type=_ENTITY_TYPE_ATTENDANCE_BATCH,
            entity_id=None,
            classroom_id=classroom_id,
            subject_id=subject_id,
            request_id=request_id,
            event_metadata=event_metadata,
        )


__all__ = [
    "ACTION_ATTENDANCE_BULK_MARK",
    "AttendanceService",
    "BlockedAuditWriter",
]
