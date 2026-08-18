"""Admin/teacher-only, exact-scope Phase 8 attendance report endpoints."""

from __future__ import annotations

import calendar
import uuid
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.auth.dependencies import require_roles
from app.modules.reports.csv_export import build_report_csv, build_report_filename
from app.modules.reports.errors import (
    ReportInvalidPeriodError,
    ReportPeriodConflictError,
    ReportPeriodRequiredError,
)
from app.modules.reports.pdf_export import build_report_pdf
from app.modules.reports.schemas import (
    AttendanceReportResponse,
    DefaultersReportResponse,
    LeaderboardReportResponse,
    ReportPeriodRead,
)
from app.modules.reports.service import (
    ACTION_REPORT_ATTENDANCE_CSV,
    ACTION_REPORT_ATTENDANCE_PDF,
    ReportsService,
)
from app.modules.users.models import User, UserRole

router = APIRouter(prefix="/reports", tags=["reports"])

AdminOrTeacher = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.TEACHER))]
Session = Annotated[AsyncSession, Depends(get_db_session)]
ThresholdQuery = Annotated[float, Query(ge=0, le=100)]

_MAX_PERIOD_DAYS = 366


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _resolve_period(
    *, month: str | None, date_from: date | None, date_to: date | None
) -> ReportPeriodRead:
    if month is not None and (date_from is not None or date_to is not None):
        raise ReportPeriodConflictError()
    if month is not None:
        try:
            month_start = datetime.strptime(month, "%Y-%m").date()
        except ValueError as exc:
            raise ReportInvalidPeriodError() from exc
        if month_start.strftime("%Y-%m") != month:
            raise ReportInvalidPeriodError()
        month_end = date(
            month_start.year,
            month_start.month,
            calendar.monthrange(month_start.year, month_start.month)[1],
        )
        return ReportPeriodRead(month=month, date_from=month_start, date_to=month_end)
    if date_from is None or date_to is None:
        raise ReportPeriodRequiredError()
    if date_from > date_to or (date_to - date_from).days >= _MAX_PERIOD_DAYS:
        raise ReportInvalidPeriodError()
    return ReportPeriodRead(month=None, date_from=date_from, date_to=date_to)


@router.get("/attendance", response_model=AttendanceReportResponse)
async def get_attendance_report(
    current_user: AdminOrTeacher,
    session: Session,
    request: Request,
    classroom_id: uuid.UUID,
    subject_id: uuid.UUID,
    month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    student_profile_id: uuid.UUID | None = None,
) -> AttendanceReportResponse:
    report, _, _ = await ReportsService(session).get_attendance_report(
        current_user,
        classroom_id=classroom_id,
        subject_id=subject_id,
        period=_resolve_period(month=month, date_from=date_from, date_to=date_to),
        student_profile_id=student_profile_id,
        request_id=_request_id(request),
    )
    return report


@router.get("/defaulters", response_model=DefaultersReportResponse)
async def get_defaulters_report(
    current_user: AdminOrTeacher,
    session: Session,
    request: Request,
    classroom_id: uuid.UUID,
    subject_id: uuid.UUID,
    month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    threshold: ThresholdQuery = 75,
) -> DefaultersReportResponse:
    return await ReportsService(session).get_defaulters_report(
        current_user,
        classroom_id=classroom_id,
        subject_id=subject_id,
        period=_resolve_period(month=month, date_from=date_from, date_to=date_to),
        threshold=threshold,
        request_id=_request_id(request),
    )


@router.get("/leaderboard", response_model=LeaderboardReportResponse)
async def get_leaderboard_report(
    current_user: AdminOrTeacher,
    session: Session,
    request: Request,
    classroom_id: uuid.UUID,
    subject_id: uuid.UUID,
    month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> LeaderboardReportResponse:
    return await ReportsService(session).get_leaderboard_report(
        current_user,
        classroom_id=classroom_id,
        subject_id=subject_id,
        period=_resolve_period(month=month, date_from=date_from, date_to=date_to),
        request_id=_request_id(request),
    )


@router.get("/attendance/export.csv")
async def export_attendance_report_csv(
    current_user: AdminOrTeacher,
    session: Session,
    request: Request,
    classroom_id: uuid.UUID,
    subject_id: uuid.UUID,
    month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    student_profile_id: uuid.UUID | None = None,
) -> Response:
    report, classroom, subject = await ReportsService(session).get_attendance_report(
        current_user,
        classroom_id=classroom_id,
        subject_id=subject_id,
        period=_resolve_period(month=month, date_from=date_from, date_to=date_to),
        student_profile_id=student_profile_id,
        request_id=_request_id(request),
        action=ACTION_REPORT_ATTENDANCE_CSV,
    )
    filename = build_report_filename(
        classroom=classroom, subject=subject, report=report, suffix="csv"
    )
    return Response(
        content=build_report_csv(report).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/attendance/export.pdf")
async def export_attendance_report_pdf(
    current_user: AdminOrTeacher,
    session: Session,
    request: Request,
    classroom_id: uuid.UUID,
    subject_id: uuid.UUID,
    month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    student_profile_id: uuid.UUID | None = None,
) -> Response:
    report, classroom, subject = await ReportsService(session).get_attendance_report(
        current_user,
        classroom_id=classroom_id,
        subject_id=subject_id,
        period=_resolve_period(month=month, date_from=date_from, date_to=date_to),
        student_profile_id=student_profile_id,
        request_id=_request_id(request),
        action=ACTION_REPORT_ATTENDANCE_PDF,
    )
    filename = build_report_filename(
        classroom=classroom, subject=subject, report=report, suffix="pdf"
    )
    return Response(
        content=build_report_pdf(report=report, classroom=classroom, subject=subject),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


__all__ = ["router"]
