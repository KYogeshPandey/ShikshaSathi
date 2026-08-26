"""Authorization and orchestration for bounded Phase 8 attendance reports."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.academics.models import Classroom, Subject
from app.modules.attendance.calculations import attendance_percentage
from app.modules.attendance.read_service import AttendanceReadService
from app.modules.reports.errors import ReportStudentNotInScopeError, ReportTooLargeError
from app.modules.reports.repository import ReportsRepository, RosterAttendanceAggregate
from app.modules.reports.schemas import (
    AttendanceReportDetailRow,
    AttendanceReportResponse,
    AttendanceReportSummary,
    DefaultersReportResponse,
    LeaderboardReportResponse,
    LeaderboardRow,
    ReportPeriodRead,
    StudentAttendanceReportRow,
)
from app.modules.users.models import User

ACTION_REPORT_ATTENDANCE = "reports.attendance"
ACTION_REPORT_DEFAULTERS = "reports.defaulters"
ACTION_REPORT_LEADERBOARD = "reports.leaderboard"
ACTION_REPORT_ATTENDANCE_CSV = "reports.attendance_export_csv"
ACTION_REPORT_ATTENDANCE_PDF = "reports.attendance_export_pdf"

MAX_REPORT_ROWS = 5_000
MAX_REPORT_STUDENTS = 1_000


class ReportsService:
    """Build report responses after the existing exact-scope authorization gate."""

    def __init__(self, session: AsyncSession) -> None:
        self._read_service = AttendanceReadService(session)
        self._reports = ReportsRepository(session)

    async def get_attendance_report(
        self,
        current_user: User,
        *,
        classroom_id: uuid.UUID,
        subject_id: uuid.UUID,
        period: ReportPeriodRead,
        student_profile_id: uuid.UUID | None,
        request_id: str | None,
        action: str = ACTION_REPORT_ATTENDANCE,
    ) -> tuple[AttendanceReportResponse, Classroom, Subject]:
        classroom, subject = await self._read_service.authorize_scope(
            current_user,
            classroom_id=classroom_id,
            subject_id=subject_id,
            request_id=request_id,
            action=action,
        )
        if student_profile_id is not None and not await self._reports.is_active_roster_student(
            classroom_id=classroom_id,
            student_profile_id=student_profile_id,
        ):
            raise ReportStudentNotInScopeError()

        total_count, present_count, absent_count = await self._reports.aggregate_summary(
            classroom_id=classroom_id,
            subject_id=subject_id,
            date_from=period.date_from,
            date_to=period.date_to,
            student_profile_id=student_profile_id,
        )
        if total_count > MAX_REPORT_ROWS:
            raise ReportTooLargeError()

        details = await self._reports.list_details(
            classroom_id=classroom_id,
            subject_id=subject_id,
            date_from=period.date_from,
            date_to=period.date_to,
            student_profile_id=student_profile_id,
            limit=MAX_REPORT_ROWS + 1,
        )
        if len(details) > MAX_REPORT_ROWS:  # pragma: no cover - guarded by aggregate
            raise ReportTooLargeError()

        response = AttendanceReportResponse(
            classroom_id=classroom_id,
            subject_id=subject_id,
            student_profile_id=student_profile_id,
            period=period,
            summary=AttendanceReportSummary(
                total_count=total_count,
                present_count=present_count,
                absent_count=absent_count,
                attendance_percentage=attendance_percentage(present_count, total_count),
            ),
            details=[
                AttendanceReportDetailRow(
                    attendance_date=row.attendance_date,
                    student_profile_id=row.student_profile_id,
                    roll_number=row.roll_number,
                    full_name=row.full_name,
                    status=row.status,
                    remarks=row.remarks,
                )
                for row in details
            ],
        )
        return response, classroom, subject

    async def get_defaulters_report(
        self,
        current_user: User,
        *,
        classroom_id: uuid.UUID,
        subject_id: uuid.UUID,
        period: ReportPeriodRead,
        threshold: float,
        request_id: str | None,
    ) -> DefaultersReportResponse:
        await self._read_service.authorize_scope(
            current_user,
            classroom_id=classroom_id,
            subject_id=subject_id,
            request_id=request_id,
            action=ACTION_REPORT_DEFAULTERS,
        )
        aggregates = await self._active_roster_aggregates(
            classroom_id=classroom_id,
            subject_id=subject_id,
            period=period,
        )
        students = [self._student_row(row) for row in aggregates]
        students = [row for row in students if row.attendance_percentage < threshold]
        students.sort(key=self._defaulter_sort_key)
        return DefaultersReportResponse(
            classroom_id=classroom_id,
            subject_id=subject_id,
            period=period,
            threshold=threshold,
            students=students,
        )

    async def get_leaderboard_report(
        self,
        current_user: User,
        *,
        classroom_id: uuid.UUID,
        subject_id: uuid.UUID,
        period: ReportPeriodRead,
        request_id: str | None,
    ) -> LeaderboardReportResponse:
        await self._read_service.authorize_scope(
            current_user,
            classroom_id=classroom_id,
            subject_id=subject_id,
            request_id=request_id,
            action=ACTION_REPORT_LEADERBOARD,
        )
        aggregates = await self._active_roster_aggregates(
            classroom_id=classroom_id,
            subject_id=subject_id,
            period=period,
        )
        students = [self._student_row(row) for row in aggregates]
        students.sort(key=self._leaderboard_sort_key)
        ranked = [
            LeaderboardRow(rank=index, **row.model_dump()) for index, row in enumerate(students, 1)
        ]
        return LeaderboardReportResponse(
            classroom_id=classroom_id,
            subject_id=subject_id,
            period=period,
            students=ranked,
        )

    async def _active_roster_aggregates(
        self,
        *,
        classroom_id: uuid.UUID,
        subject_id: uuid.UUID,
        period: ReportPeriodRead,
    ) -> list[RosterAttendanceAggregate]:
        rows = await self._reports.aggregate_active_roster(
            classroom_id=classroom_id,
            subject_id=subject_id,
            date_from=period.date_from,
            date_to=period.date_to,
            limit=MAX_REPORT_STUDENTS + 1,
        )
        if len(rows) > MAX_REPORT_STUDENTS:
            raise ReportTooLargeError()
        return rows

    @staticmethod
    def _student_row(row: RosterAttendanceAggregate) -> StudentAttendanceReportRow:
        return StudentAttendanceReportRow(
            student_profile_id=row.student_profile_id,
            roll_number=row.roll_number,
            full_name=row.full_name,
            total_count=row.total_count,
            present_count=row.present_count,
            absent_count=row.absent_count,
            attendance_percentage=attendance_percentage(row.present_count, row.total_count),
        )

    @staticmethod
    def _defaulter_sort_key(row: StudentAttendanceReportRow) -> tuple[float, bool, str, str]:
        return (
            row.attendance_percentage,
            row.roll_number is None,
            (row.roll_number or "").casefold(),
            str(row.student_profile_id),
        )

    @staticmethod
    def _leaderboard_sort_key(row: StudentAttendanceReportRow) -> tuple[float, bool, str, str]:
        return (
            -row.attendance_percentage,
            row.roll_number is None,
            (row.roll_number or "").casefold(),
            str(row.student_profile_id),
        )


__all__ = [
    "ACTION_REPORT_ATTENDANCE_CSV",
    "ACTION_REPORT_ATTENDANCE_PDF",
    "MAX_REPORT_ROWS",
    "MAX_REPORT_STUDENTS",
    "ReportsService",
]
