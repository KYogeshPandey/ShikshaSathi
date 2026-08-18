"""Attendance read/statistics/export authorization and query orchestration.

Phase 4 Stage 3. Builds on Stage 1's repositories and Stage 2's
``BlockedAuditWriter`` (both unmodified here — see
``docs/HANDOVER_PHASE_4_STAGE_1.md`` / ``_STAGE_2.md``) without touching
``AttendanceService.bulk_save`` or its private
``_authorize_teacher_scope`` at all.

Every general (non-self-service) attendance read/export endpoint —
detail, daily, statistics, CSV export — shares **one** authorization
method, ``AttendanceReadService.authorize_scope``, which deliberately
mirrors Stage 2's write-scope authorization shape exactly:

- **Admin**: the classroom/subject must exist (``ClassroomNotFoundError``
  / ``SubjectNotFoundError``, 404) and both must be active
  (``InactiveAcademicReferenceError``, 409) — "may read active
  attendance scopes", per the Stage 3 brief. An admin does not get a
  broader "read anything, active or not" allowance; this keeps read and
  write authorization symmetrical and avoids inventing a second,
  undocumented admin-only rule.
- **Teacher**: the exact same concealed-authorization outcome as
  ``bulk_save``'s ``_authorize_teacher_scope`` — missing/inactive
  teacher profile, a classroom/subject that does not exist, or a
  missing/inactive assignment all funnel into the same
  ``AttendanceScopeNotFoundError`` (404), with a blocked audit row
  persisted first via ``BlockedAuditWriter`` (imported directly from
  ``app.modules.attendance.service``, not reimplemented).

This module intentionally does **not** call Stage 2's private
``_authorize_teacher_scope`` — that method belongs to
``AttendanceService`` and is reserved for the ``bulk_save`` write path
(``docs/HANDOVER_PHASE_4_STAGE_2.md``'s "Must NOT be redone" list).
Instead, ``authorize_scope`` here is a fresh, single implementation that
every read/export endpoint calls — never duplicated per-route — which
satisfies the Stage 3 brief's "do not duplicate authorization logic
independently in every endpoint" at this module's own boundary.

No success audit is written for reads or exports — only Stage 2's
``bulk_save`` writes a success audit row. The Stage 3 brief only calls
for *blocked* read/export attempts to be audited; adding a success audit
for every read would be unrequested scope beyond what either brief asks
for and would make read-heavy traffic the dominant audit-log write
source for no stated benefit.
"""

from __future__ import annotations

import uuid
from datetime import date

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.modules.attendance.calculations import attendance_percentage
from app.modules.attendance.errors import (
    AttendanceInvalidDateRangeError,
    AttendanceRoleNotPermittedError,
    AttendanceScopeNotFoundError,
)
from app.modules.attendance.models import AttendanceStatus
from app.modules.attendance.repository import (
    AttendanceExportRow,
    AttendanceRepository,
    AuditLogRepository,
)
from app.modules.attendance.schemas import (
    AttendanceRecordRead,
    AttendanceRosterStudentRead,
    AttendanceStatsByClassroom,
    AttendanceStatsByStudent,
    AttendanceStatsGrouping,
    AttendanceStatsOverall,
    AttendanceStatsResponse,
    DailyAttendanceResponse,
    StudentSelfStatsResponse,
)
from app.modules.attendance.service import BlockedAuditWriter
from app.modules.profiles.errors import StudentProfileNotFoundError
from app.modules.profiles.models import StudentProfile
from app.modules.profiles.repository import StudentProfileRepository, TeacherProfileRepository
from app.modules.users.models import User, UserRole
from app.schemas.pagination import Page

logger = structlog.get_logger(__name__)

ACTION_ATTENDANCE_READ_DETAIL = "attendance.read_detail"
ACTION_ATTENDANCE_READ_DAILY = "attendance.read_daily"
ACTION_ATTENDANCE_READ_ROSTER = "attendance.read_roster"
ACTION_ATTENDANCE_READ_STATS = "attendance.read_stats"
ACTION_ATTENDANCE_EXPORT = "attendance.export"

_ENTITY_TYPE_ATTENDANCE_SCOPE = "attendance_scope"

# Safe, non-identifying reason codes recorded server-side only, in the
# blocked audit row's ``event_metadata`` — never returned to the client,
# which always sees the same concealed ``AttendanceScopeNotFoundError``.
# Deliberately distinct constants from Stage 2's (also-private) write-path
# reason codes in ``app.modules.attendance.service``, since that module is
# not imported here for anything beyond ``BlockedAuditWriter``.
_REASON_TEACHER_PROFILE_INACTIVE_OR_MISSING = "teacher_profile_inactive_or_missing"
_REASON_CLASSROOM_OR_SUBJECT_NOT_FOUND = "classroom_or_subject_not_found"
_REASON_ASSIGNMENT_INACTIVE_OR_MISSING = "teacher_assignment_inactive_or_missing"


def _validate_date_range(date_from: date | None, date_to: date | None) -> None:
    if date_from is not None and date_to is not None and date_from > date_to:
        raise AttendanceInvalidDateRangeError()


class AttendanceReadService:
    """Read-scope authorization plus detail/daily/stats/export/self-service queries."""

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

    # --- shared scope authorization (detail/daily/stats/export) -----------

    async def authorize_scope(
        self,
        current_user: User,
        *,
        classroom_id: uuid.UUID,
        subject_id: uuid.UUID,
        request_id: str | None,
        action: str,
    ) -> tuple[Classroom, Subject]:
        """The one authorization method every read/export endpoint calls.

        Raises ``AttendanceRoleNotPermittedError`` (403) for any role
        other than admin/teacher — a defense-in-depth backstop behind
        the router's own ``require_roles`` dependency, mirroring
        ``bulk_save``'s same pattern. Raises ``ClassroomNotFoundError``/
        ``SubjectNotFoundError`` (404) or ``InactiveAcademicReferenceError``
        (409) for admin; ``AttendanceScopeNotFoundError`` (404, concealed)
        for any teacher-scope denial.
        """
        if current_user.role not in (UserRole.ADMIN, UserRole.TEACHER):
            raise AttendanceRoleNotPermittedError()

        classroom = await self._classrooms.get_by_id(classroom_id)
        subject = await self._subjects.get_by_id(subject_id)

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
                classroom_id=classroom_id,
                subject_id=subject_id,
                request_id=request_id,
                action=action,
            )

        # Authorization above guarantees both are non-None by this point
        # (admin: checked directly; teacher: the scope check only returns
        # normally when both were resolved). Checked explicitly (not via
        # ``assert``, which ``python -O`` strips) since this is a genuine
        # invariant, not client input — mirrors ``bulk_save``'s identical
        # guard.
        if classroom is None or subject is None:  # pragma: no cover - invariant
            raise RuntimeError(
                "attendance read-scope authorization invariant violated: "
                "classroom/subject resolved as None after authorization succeeded"
            )
        if not classroom.is_active or not subject.is_active:
            raise InactiveAcademicReferenceError()

        return classroom, subject

    async def _authorize_teacher_scope(
        self,
        current_user: User,
        *,
        classroom: Classroom | None,
        subject: Subject | None,
        classroom_id: uuid.UUID,
        subject_id: uuid.UUID,
        request_id: str | None,
        action: str,
    ) -> None:
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
                action=action,
                entity_type=_ENTITY_TYPE_ATTENDANCE_SCOPE,
                classroom_id=classroom_id,
                subject_id=subject_id,
                request_id=request_id,
                reason_code=reason_code,
                attempted_action=action,
            )
        except Exception as exc:
            # Never let a blocked-audit write failure replace or suppress
            # the original concealed ownership error — only the exception
            # type is logged (no message, no stack trace), mirroring
            # ``app.modules.attendance.service``'s identical convention.
            logger.error(
                "blocked_read_audit_write_failed",
                reason_code=reason_code,
                request_id=request_id,
                action=action,
                exc_type=type(exc).__name__,
            )
        else:
            logger.warning(
                "attendance_read_scope_blocked",
                reason_code=reason_code,
                request_id=request_id,
                action=action,
            )
        raise AttendanceScopeNotFoundError()

    # --- classroom roster -------------------------------------------------

    async def get_roster(
        self,
        current_user: User,
        *,
        classroom_id: uuid.UUID,
        subject_id: uuid.UUID,
        request_id: str | None,
    ) -> list[AttendanceRosterStudentRead]:
        """Return the active server-derived roster for one authorized scope."""
        await self.authorize_scope(
            current_user,
            classroom_id=classroom_id,
            subject_id=subject_id,
            request_id=request_id,
            action=ACTION_ATTENDANCE_READ_ROSTER,
        )
        profiles = await self._students.list_by_classroom(classroom_id)
        active_profiles = sorted(
            (profile for profile in profiles if profile.is_active),
            key=lambda profile: (
                profile.roll_number is None,
                profile.roll_number or "",
                str(profile.id),
            ),
        )
        return [
            AttendanceRosterStudentRead(
                student_profile_id=profile.id,
                roll_number=profile.roll_number,
            )
            for profile in active_profiles
        ]

    # --- detail -------------------------------------------------------------

    async def get_detail(
        self,
        current_user: User,
        *,
        classroom_id: uuid.UUID,
        subject_id: uuid.UUID,
        student_profile_id: uuid.UUID | None,
        date_from: date | None,
        date_to: date | None,
        status: AttendanceStatus | None,
        limit: int,
        offset: int,
        request_id: str | None,
    ) -> Page[AttendanceRecordRead]:
        _validate_date_range(date_from, date_to)
        await self.authorize_scope(
            current_user,
            classroom_id=classroom_id,
            subject_id=subject_id,
            request_id=request_id,
            action=ACTION_ATTENDANCE_READ_DETAIL,
        )
        rows = await self._attendance.list(
            classroom_id=classroom_id,
            subject_id=subject_id,
            student_profile_id=student_profile_id,
            date_from=date_from,
            date_to=date_to,
            status=status,
            limit=limit,
            offset=offset,
        )
        total = await self._attendance.count(
            classroom_id=classroom_id,
            subject_id=subject_id,
            student_profile_id=student_profile_id,
            date_from=date_from,
            date_to=date_to,
            status=status,
        )
        return Page[AttendanceRecordRead](
            items=[AttendanceRecordRead.model_validate(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    # --- daily ----------------------------------------------------------

    async def get_daily(
        self,
        current_user: User,
        *,
        classroom_id: uuid.UUID,
        subject_id: uuid.UUID,
        attendance_date: date,
        request_id: str | None,
    ) -> DailyAttendanceResponse:
        await self.authorize_scope(
            current_user,
            classroom_id=classroom_id,
            subject_id=subject_id,
            request_id=request_id,
            action=ACTION_ATTENDANCE_READ_DAILY,
        )
        rows = await self._attendance.list_daily(
            classroom_id=classroom_id,
            subject_id=subject_id,
            attendance_date=attendance_date,
        )
        return DailyAttendanceResponse(
            classroom_id=classroom_id,
            subject_id=subject_id,
            attendance_date=attendance_date,
            records=[AttendanceRecordRead.model_validate(row) for row in rows],
        )

    # --- statistics -------------------------------------------------------

    async def get_stats(
        self,
        current_user: User,
        *,
        classroom_id: uuid.UUID,
        subject_id: uuid.UUID,
        student_profile_id: uuid.UUID | None,
        date_from: date | None,
        date_to: date | None,
        status: AttendanceStatus | None,
        grouping: AttendanceStatsGrouping,
        request_id: str | None,
    ) -> AttendanceStatsResponse:
        _validate_date_range(date_from, date_to)
        await self.authorize_scope(
            current_user,
            classroom_id=classroom_id,
            subject_id=subject_id,
            request_id=request_id,
            action=ACTION_ATTENDANCE_READ_STATS,
        )

        if grouping is AttendanceStatsGrouping.STUDENT:
            aggregates = await self._attendance.aggregate_by_student(
                classroom_id=classroom_id,
                subject_id=subject_id,
                student_profile_id=student_profile_id,
                date_from=date_from,
                date_to=date_to,
                status=status,
            )
            return AttendanceStatsResponse(
                grouping=grouping,
                classroom_id=classroom_id,
                subject_id=subject_id,
                by_student=[
                    AttendanceStatsByStudent(
                        student_profile_id=agg.student_profile_id,
                        total_count=agg.total_count,
                        present_count=agg.present_count,
                        absent_count=agg.absent_count,
                        attendance_percentage=attendance_percentage(
                            agg.present_count, agg.total_count
                        ),
                    )
                    for agg in aggregates
                ],
            )

        if grouping is AttendanceStatsGrouping.CLASSROOM:
            classroom_aggregates = await self._attendance.aggregate_by_classroom(
                classroom_id=classroom_id,
                subject_id=subject_id,
                student_profile_id=student_profile_id,
                date_from=date_from,
                date_to=date_to,
                status=status,
            )
            return AttendanceStatsResponse(
                grouping=grouping,
                classroom_id=classroom_id,
                subject_id=subject_id,
                by_classroom=[
                    AttendanceStatsByClassroom(
                        classroom_id=agg.classroom_id,
                        total_count=agg.total_count,
                        present_count=agg.present_count,
                        absent_count=agg.absent_count,
                        attendance_percentage=attendance_percentage(
                            agg.present_count, agg.total_count
                        ),
                    )
                    for agg in classroom_aggregates
                ],
            )

        total, present, absent = await self._attendance.aggregate_counts(
            classroom_id=classroom_id,
            subject_id=subject_id,
            student_profile_id=student_profile_id,
            date_from=date_from,
            date_to=date_to,
            status=status,
        )
        return AttendanceStatsResponse(
            grouping=grouping,
            classroom_id=classroom_id,
            subject_id=subject_id,
            overall=AttendanceStatsOverall(
                total_count=total,
                present_count=present,
                absent_count=absent,
                attendance_percentage=attendance_percentage(present, total),
            ),
        )

    # --- CSV export ---------------------------------------------------------

    async def export(
        self,
        current_user: User,
        *,
        classroom_id: uuid.UUID,
        subject_id: uuid.UUID,
        student_profile_id: uuid.UUID | None,
        date_from: date | None,
        date_to: date | None,
        status: AttendanceStatus | None,
        request_id: str | None,
    ) -> tuple[Classroom, Subject, list[AttendanceExportRow]]:
        """Authorize, then return ``(classroom, subject, rows)`` for CSV building.

        Returning the already-authorized ``Classroom``/``Subject``
        (rather than just the rows) lets the router's CSV builder use
        their ``code`` values directly, without a second lookup or a
        per-row join (see ``app.modules.attendance.repository.
        AttendanceExportRow``'s docstring).
        """
        _validate_date_range(date_from, date_to)
        classroom, subject = await self.authorize_scope(
            current_user,
            classroom_id=classroom_id,
            subject_id=subject_id,
            request_id=request_id,
            action=ACTION_ATTENDANCE_EXPORT,
        )
        rows = await self._attendance.list_for_export(
            classroom_id=classroom_id,
            subject_id=subject_id,
            student_profile_id=student_profile_id,
            date_from=date_from,
            date_to=date_to,
            status=status,
        )
        return classroom, subject, rows

    # --- student self-service ------------------------------------------

    async def _resolve_own_student_profile(self, current_user: User) -> StudentProfile:
        """Identity-derived own ``StudentProfile`` — never a client-supplied ID.

        Raises ``AttendanceRoleNotPermittedError`` (403) for any non-student
        caller (defense in depth behind the router's own
        ``require_roles(UserRole.STUDENT)``), or ``StudentProfileNotFoundError``
        (404) for a missing/inactive own profile — the same self-profile
        error convention already established in
        ``app.modules.profiles.student_service.StudentProfileService.get_for_user``.
        """
        if current_user.role is not UserRole.STUDENT:
            raise AttendanceRoleNotPermittedError()
        profile = await self._students.get_by_user_id(current_user.id)
        if profile is None or not profile.is_active:
            raise StudentProfileNotFoundError()
        return profile

    async def get_self_detail(
        self,
        current_user: User,
        *,
        classroom_id: uuid.UUID | None,
        subject_id: uuid.UUID | None,
        date_from: date | None,
        date_to: date | None,
        status: AttendanceStatus | None,
        limit: int,
        offset: int,
    ) -> Page[AttendanceRecordRead]:
        """The caller's own attendance only. ``student_profile_id`` is never accepted."""
        _validate_date_range(date_from, date_to)
        profile = await self._resolve_own_student_profile(current_user)
        rows = await self._attendance.list(
            classroom_id=classroom_id,
            subject_id=subject_id,
            student_profile_id=profile.id,
            date_from=date_from,
            date_to=date_to,
            status=status,
            limit=limit,
            offset=offset,
        )
        total = await self._attendance.count(
            classroom_id=classroom_id,
            subject_id=subject_id,
            student_profile_id=profile.id,
            date_from=date_from,
            date_to=date_to,
            status=status,
        )
        return Page[AttendanceRecordRead](
            items=[AttendanceRecordRead.model_validate(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_self_stats(
        self,
        current_user: User,
        *,
        classroom_id: uuid.UUID | None,
        subject_id: uuid.UUID | None,
        date_from: date | None,
        date_to: date | None,
    ) -> StudentSelfStatsResponse:
        _validate_date_range(date_from, date_to)
        profile = await self._resolve_own_student_profile(current_user)
        total, present, absent = await self._attendance.aggregate_counts(
            classroom_id=classroom_id,
            subject_id=subject_id,
            student_profile_id=profile.id,
            date_from=date_from,
            date_to=date_to,
        )
        return StudentSelfStatsResponse(
            student_profile_id=profile.id,
            total_count=total,
            present_count=present,
            absent_count=absent,
            attendance_percentage=attendance_percentage(present, total),
        )


__all__ = [
    "ACTION_ATTENDANCE_EXPORT",
    "ACTION_ATTENDANCE_READ_DAILY",
    "ACTION_ATTENDANCE_READ_DETAIL",
    "ACTION_ATTENDANCE_READ_STATS",
    "AttendanceReadService",
]
