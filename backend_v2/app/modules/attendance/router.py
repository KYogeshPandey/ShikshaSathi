"""Versioned attendance API: bulk-mark, detail/daily/stats reads, CSV export,
and student self-service.

Phase 4 Stage 3. Thin routers only — parse the request, resolve
``request.state.request_id``, and delegate to
``app.modules.attendance.service.AttendanceService`` (bulk-mark, built in
Stage 2) or ``app.modules.attendance.read_service.AttendanceReadService``
(every read/export endpoint, built in this stage). No authorization
logic lives here — see those two modules for the actual admin/teacher/
student rules.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.attendance.csv_export import build_attendance_csv, build_export_filename
from app.modules.attendance.models import AttendanceStatus
from app.modules.attendance.planner_schemas import (
    AttendanceRecoveryPlanRead,
    AttendanceRecoveryPlanRequest,
)
from app.modules.attendance.planner_service import AttendanceRecoveryPlannerService
from app.modules.attendance.read_service import AttendanceReadService
from app.modules.attendance.schemas import (
    AttendanceBulkSaveResult,
    AttendanceRecordRead,
    AttendanceRosterStudentRead,
    AttendanceStatsGrouping,
    AttendanceStatsResponse,
    BulkAttendanceRequest,
    DailyAttendanceResponse,
    StudentSelfStatsResponse,
)
from app.modules.attendance.service import AttendanceService
from app.modules.auth.dependencies import require_roles
from app.modules.users.models import User, UserRole
from app.schemas.pagination import Page

router = APIRouter(prefix="/attendance", tags=["attendance"])

AdminOrTeacher = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.TEACHER))]
StudentUser = Annotated[User, Depends(require_roles(UserRole.STUDENT))]
Session = Annotated[AsyncSession, Depends(get_db_session)]

_LimitQuery = Annotated[int, Query(ge=1, le=100)]
_OffsetQuery = Annotated[int, Query(ge=0)]


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


@router.post("/bulk", response_model=AttendanceBulkSaveResult, status_code=status.HTTP_200_OK)
async def bulk_save_attendance(
    payload: BulkAttendanceRequest,
    current_user: AdminOrTeacher,
    session: Session,
    request: Request,
) -> AttendanceBulkSaveResult:
    """Create/update one classroom/subject/date batch of attendance records.

    ``actor``/``marked_by`` are always the authenticated caller — no
    field on ``BulkAttendanceRequest`` accepts either, so there is
    nothing for a client to spoof here (see
    ``app.modules.attendance.schemas.BulkAttendanceRecordIn``).
    """
    return await AttendanceService(session).bulk_save(
        current_user=current_user,
        payload=payload,
        request_id=_request_id(request),
    )


@router.get("/roster", response_model=list[AttendanceRosterStudentRead])
async def get_attendance_roster(
    current_user: AdminOrTeacher,
    session: Session,
    request: Request,
    classroom_id: uuid.UUID,
    subject_id: uuid.UUID,
) -> list[AttendanceRosterStudentRead]:
    """Return only active students from an authorized classroom/subject scope."""
    return await AttendanceReadService(session).get_roster(
        current_user,
        classroom_id=classroom_id,
        subject_id=subject_id,
        request_id=_request_id(request),
    )


@router.get("/detail", response_model=Page[AttendanceRecordRead])
async def get_attendance_detail(
    current_user: AdminOrTeacher,
    session: Session,
    request: Request,
    classroom_id: uuid.UUID,
    subject_id: uuid.UUID,
    student_profile_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    status_filter: Annotated[AttendanceStatus | None, Query(alias="status")] = None,
    limit: _LimitQuery = 50,
    offset: _OffsetQuery = 0,
) -> Page[AttendanceRecordRead]:
    """Bounded, filtered, deterministically ordered attendance detail.

    ``classroom_id``/``subject_id`` are required — a teacher's assignment
    is scoped to an exact (classroom, subject) pair, so every read/export
    endpoint shares that same exact-scope shape (see
    ``app.modules.attendance.read_service.AttendanceReadService
    .authorize_scope``). An unrelated or inactive teacher scope is
    concealed as the same 404 used by ``bulk_save``, with an independent
    blocked-audit row.
    """
    return await AttendanceReadService(session).get_detail(
        current_user,
        classroom_id=classroom_id,
        subject_id=subject_id,
        student_profile_id=student_profile_id,
        date_from=date_from,
        date_to=date_to,
        status=status_filter,
        limit=limit,
        offset=offset,
        request_id=_request_id(request),
    )


@router.get("/daily", response_model=DailyAttendanceResponse)
async def get_attendance_daily(
    current_user: AdminOrTeacher,
    session: Session,
    request: Request,
    classroom_id: uuid.UUID,
    subject_id: uuid.UUID,
    attendance_date: date,
) -> DailyAttendanceResponse:
    """The exact (classroom, subject, date) daily-attendance scope.

    Returns a typed empty ``records`` list (never an error) when nothing
    has been marked yet for this scope.
    """
    return await AttendanceReadService(session).get_daily(
        current_user,
        classroom_id=classroom_id,
        subject_id=subject_id,
        attendance_date=attendance_date,
        request_id=_request_id(request),
    )


@router.get("/stats", response_model=AttendanceStatsResponse)
async def get_attendance_stats(
    current_user: AdminOrTeacher,
    session: Session,
    request: Request,
    classroom_id: uuid.UUID,
    subject_id: uuid.UUID,
    student_profile_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    status_filter: Annotated[AttendanceStatus | None, Query(alias="status")] = None,
    grouping: AttendanceStatsGrouping = AttendanceStatsGrouping.OVERALL,
) -> AttendanceStatsResponse:
    """Raw, explainable attendance counts only — no ranking, no dashboard.

    Zero matching records returns ``attendance_percentage=0.0``;
    otherwise it is ``round(present / total * 100, 2)``, and
    ``present_count + absent_count`` always equals ``total_count``.
    """
    return await AttendanceReadService(session).get_stats(
        current_user,
        classroom_id=classroom_id,
        subject_id=subject_id,
        student_profile_id=student_profile_id,
        date_from=date_from,
        date_to=date_to,
        status=status_filter,
        grouping=grouping,
        request_id=_request_id(request),
    )


@router.get("/export")
async def export_attendance_csv(
    current_user: AdminOrTeacher,
    session: Session,
    request: Request,
    classroom_id: uuid.UUID,
    subject_id: uuid.UUID,
    student_profile_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    status_filter: Annotated[AttendanceStatus | None, Query(alias="status")] = None,
) -> Response:
    """In-memory CSV export — same authorization as ``GET /attendance/detail``.

    Never writes a temporary file (see
    ``app.modules.attendance.csv_export``). The filename is built
    exclusively from the already-authorized classroom/subject codes —
    never from client input. An empty result still returns a valid CSV
    containing only the header row.
    """
    classroom, subject, rows = await AttendanceReadService(session).export(
        current_user,
        classroom_id=classroom_id,
        subject_id=subject_id,
        student_profile_id=student_profile_id,
        date_from=date_from,
        date_to=date_to,
        status=status_filter,
        request_id=_request_id(request),
    )
    csv_body = build_attendance_csv(classroom=classroom, subject=subject, rows=rows)
    filename = build_export_filename(classroom=classroom, subject=subject)
    return Response(
        content=csv_body.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/me/detail", response_model=Page[AttendanceRecordRead])
async def get_my_attendance_detail(
    current_user: StudentUser,
    session: Session,
    classroom_id: uuid.UUID | None = None,
    subject_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    status_filter: Annotated[AttendanceStatus | None, Query(alias="status")] = None,
    limit: _LimitQuery = 50,
    offset: _OffsetQuery = 0,
) -> Page[AttendanceRecordRead]:
    """The caller's own attendance only. No ``student_profile_id`` parameter exists."""
    return await AttendanceReadService(session).get_self_detail(
        current_user,
        classroom_id=classroom_id,
        subject_id=subject_id,
        date_from=date_from,
        date_to=date_to,
        status=status_filter,
        limit=limit,
        offset=offset,
    )


@router.get("/me/stats", response_model=StudentSelfStatsResponse)
async def get_my_attendance_stats(
    current_user: StudentUser,
    session: Session,
    classroom_id: uuid.UUID | None = None,
    subject_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> StudentSelfStatsResponse:
    """The caller's own raw attendance statistics only."""
    return await AttendanceReadService(session).get_self_stats(
        current_user,
        classroom_id=classroom_id,
        subject_id=subject_id,
        date_from=date_from,
        date_to=date_to,
    )


@router.post("/me/recovery-plan", response_model=AttendanceRecoveryPlanRead)
async def build_my_attendance_recovery_plan(
    payload: AttendanceRecoveryPlanRequest,
    current_user: StudentUser,
    session: Session,
) -> AttendanceRecoveryPlanRead:
    """Build a timetable-aware plan for the authenticated student only."""
    return await AttendanceRecoveryPlannerService(session).build_plan(current_user, payload)
