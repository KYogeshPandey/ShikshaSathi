"""Role dispatch and bounded analytics calculations."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analytics.repository import (
    AnalyticsRepository,
    ClassroomAttendanceAggregate,
    DailyAttendanceAggregate,
)
from app.modules.analytics.schemas import (
    AdminPopulationRead,
    AnalyticsOverviewResponse,
    AnalyticsPeriodRead,
    AnalyticsWindowDays,
    AttendanceComparisonRead,
    AttendanceMetricRead,
    AttendanceTrendPointRead,
    ClassroomAttentionRead,
    StudentContextRead,
    TeacherScopeRead,
)
from app.modules.attendance.calculations import attendance_percentage
from app.modules.profiles.errors import (
    StudentProfileNotFoundError,
    TeacherProfileNotFoundError,
)
from app.modules.profiles.repository import (
    StudentProfileRepository,
    TeacherProfileRepository,
)
from app.modules.users.models import User, UserRole


def _metric(rows: list[DailyAttendanceAggregate]) -> AttendanceMetricRead:
    total = sum(row.total_count for row in rows)
    present = sum(row.present_count for row in rows)
    absent = sum(row.absent_count for row in rows)
    return AttendanceMetricRead(
        total_count=total,
        present_count=present,
        absent_count=absent,
        attendance_percentage=attendance_percentage(present, total),
    )


def _trend(
    rows: list[DailyAttendanceAggregate], period: AnalyticsPeriodRead
) -> list[AttendanceTrendPointRead]:
    by_date = {row.attendance_date: row for row in rows}
    points: list[AttendanceTrendPointRead] = []
    for offset in range(period.days):
        attendance_date = period.date_from + timedelta(days=offset)
        row = by_date.get(attendance_date)
        total = row.total_count if row else 0
        present = row.present_count if row else 0
        absent = row.absent_count if row else 0
        points.append(
            AttendanceTrendPointRead(
                attendance_date=attendance_date,
                total_count=total,
                present_count=present,
                absent_count=absent,
                attendance_percentage=attendance_percentage(present, total),
            )
        )
    return points


def _attention(row: ClassroomAttendanceAggregate) -> ClassroomAttentionRead:
    return ClassroomAttentionRead(
        classroom_name=row.classroom_name,
        classroom_code=row.classroom_code,
        total_count=row.total_count,
        present_count=row.present_count,
        absent_count=row.absent_count,
        attendance_percentage=attendance_percentage(row.present_count, row.total_count),
    )


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self._analytics = AnalyticsRepository(session)
        self._teachers = TeacherProfileRepository(session)
        self._students = StudentProfileRepository(session)

    async def overview(
        self,
        current_user: User,
        *,
        days: AnalyticsWindowDays,
        date_to: date,
    ) -> AnalyticsOverviewResponse:
        current_period = AnalyticsPeriodRead(
            days=days,
            date_from=date_to - timedelta(days=days - 1),
            date_to=date_to,
        )
        previous_to = current_period.date_from - timedelta(days=1)
        previous_period = AnalyticsPeriodRead(
            days=days,
            date_from=previous_to - timedelta(days=days - 1),
            date_to=previous_to,
        )

        admin_population: AdminPopulationRead | None = None
        teacher_scope: TeacherScopeRead | None = None
        student_context: StudentContextRead | None = None
        attention_classrooms: list[ClassroomAttentionRead] = []

        if current_user.role is UserRole.ADMIN:
            rows = await self._analytics.daily_for_admin(
                date_from=previous_period.date_from,
                date_to=current_period.date_to,
            )
            population = await self._analytics.admin_population()
            admin_population = AdminPopulationRead(**asdict(population))
            attention_rows = await self._analytics.lowest_attendance_classrooms(
                date_from=current_period.date_from,
                date_to=current_period.date_to,
                limit=3,
            )
            attention_classrooms = [_attention(row) for row in attention_rows]
        elif current_user.role is UserRole.TEACHER:
            teacher_profile = await self._teachers.get_by_user_id(current_user.id)
            if teacher_profile is None or not teacher_profile.is_active:
                raise TeacherProfileNotFoundError()
            rows = await self._analytics.daily_for_teacher(
                teacher_profile_id=teacher_profile.id,
                date_from=previous_period.date_from,
                date_to=current_period.date_to,
            )
            scope = await self._analytics.teacher_scope(teacher_profile.id)
            teacher_scope = TeacherScopeRead(**asdict(scope))
        else:
            student_profile = await self._students.get_by_user_id(current_user.id)
            if student_profile is None or not student_profile.is_active:
                raise StudentProfileNotFoundError()
            rows = await self._analytics.daily_for_student(
                student_profile_id=student_profile.id,
                date_from=previous_period.date_from,
                date_to=current_period.date_to,
            )
            student_context = StudentContextRead(roll_number=student_profile.roll_number)

        current_rows = [row for row in rows if current_period.date_from <= row.attendance_date]
        previous_rows = [row for row in rows if row.attendance_date <= previous_period.date_to]
        current_metric = _metric(current_rows)
        previous_metric = _metric(previous_rows)
        percentage_point_change = (
            round(
                current_metric.attendance_percentage - previous_metric.attendance_percentage,
                2,
            )
            if current_metric.total_count > 0 and previous_metric.total_count > 0
            else None
        )

        return AnalyticsOverviewResponse(
            role=current_user.role,
            period=current_period,
            attendance=current_metric,
            comparison=AttendanceComparisonRead(
                period=previous_period,
                attendance=previous_metric,
                percentage_point_change=percentage_point_change,
            ),
            trend=_trend(current_rows, current_period),
            admin_population=admin_population,
            teacher_scope=teacher_scope,
            student_context=student_context,
            attention_classrooms=attention_classrooms,
        )


__all__ = ["AnalyticsService"]
