"""Self-only orchestration for schedule-aware attendance recovery plans."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.academics.models import DayOfWeek
from app.modules.academics.repository import (
    ClassroomRepository,
    SubjectRepository,
    TimetableRepository,
)
from app.modules.attendance.calculations import attendance_percentage
from app.modules.attendance.errors import (
    AttendancePlannerClassroomRequiredError,
    AttendancePlannerInvalidDeadlineError,
    AttendancePlannerSubjectNotFoundError,
)
from app.modules.attendance.planner import (
    TimetableSlot,
    calculate_recovery,
    expand_timetable,
    subject_attendance_status,
)
from app.modules.attendance.planner_schemas import (
    AttendanceCountsRead,
    AttendanceRecoveryPlanRead,
    AttendanceRecoveryPlanRequest,
    SubjectAttendanceSummaryRead,
)
from app.modules.attendance.read_service import AttendanceReadService
from app.modules.attendance.repository import AttendanceRepository, SubjectAttendanceAggregate
from app.modules.users.models import User

_MAX_PLANNING_DAYS = 366
_MAX_CLASSROOM_SUBJECTS = 1_000
_SCHEDULE_ASSUMPTION = (
    "Projection uses recurring active timetable classes from today through the deadline. "
    "Institutional holidays, cancellations, and timetable changes are not modeled."
)
_WEEKDAY_INDEX = {
    DayOfWeek.MONDAY: 0,
    DayOfWeek.TUESDAY: 1,
    DayOfWeek.WEDNESDAY: 2,
    DayOfWeek.THURSDAY: 3,
    DayOfWeek.FRIDAY: 4,
    DayOfWeek.SATURDAY: 5,
    DayOfWeek.SUNDAY: 6,
}


def _counts(*, total: int, present: int, absent: int) -> AttendanceCountsRead:
    return AttendanceCountsRead(
        attended=present,
        held=total,
        absent=absent,
        percentage=attendance_percentage(present, total),
    )


class AttendanceRecoveryPlannerService:
    def __init__(self, session: AsyncSession) -> None:
        self._attendance = AttendanceRepository(session)
        self._attendance_reads = AttendanceReadService(session)
        self._classrooms = ClassroomRepository(session)
        self._subjects = SubjectRepository(session)
        self._timetable = TimetableRepository(session)

    async def build_plan(
        self,
        current_user: User,
        payload: AttendanceRecoveryPlanRequest,
        *,
        today: date | None = None,
    ) -> AttendanceRecoveryPlanRead:
        planning_date = today or date.today()
        planning_days = (payload.deadline - planning_date).days
        if planning_days < 0 or planning_days > _MAX_PLANNING_DAYS:
            raise AttendancePlannerInvalidDeadlineError()

        profile = await self._attendance_reads.resolve_own_student_profile(current_user)
        classroom = (
            await self._classrooms.get_by_id(profile.classroom_id)
            if profile.classroom_id is not None
            else None
        )
        if classroom is None or not classroom.is_active:
            raise AttendancePlannerClassroomRequiredError()

        subjects = await self._subjects.list_for_classroom(
            classroom.id,
            limit=_MAX_CLASSROOM_SUBJECTS,
            offset=0,
        )
        subjects_by_id = {subject.id: subject for subject in subjects}
        if payload.subject_id is not None and payload.subject_id not in subjects_by_id:
            raise AttendancePlannerSubjectNotFoundError()

        aggregates = await self._attendance.aggregate_by_subject(
            classroom_id=classroom.id,
            student_profile_id=profile.id,
        )
        aggregates_by_subject = {row.subject_id: row for row in aggregates}
        overall_total = sum(row.total_count for row in aggregates)
        overall_present = sum(row.present_count for row in aggregates)
        overall_absent = sum(row.absent_count for row in aggregates)
        overall = _counts(
            total=overall_total,
            present=overall_present,
            absent=overall_absent,
        )

        subject_summaries = [
            self._subject_summary(
                subject_id=subject.id,
                subject_name=subject.name,
                subject_code=subject.code,
                aggregate=aggregates_by_subject.get(subject.id),
                target_percentage=payload.target_percentage,
            )
            for subject in subjects
        ]

        selected_subject = (
            subjects_by_id[payload.subject_id] if payload.subject_id is not None else None
        )
        selected_aggregate = (
            aggregates_by_subject.get(payload.subject_id)
            if payload.subject_id is not None
            else None
        )
        current = (
            _counts(
                total=selected_aggregate.total_count if selected_aggregate else 0,
                present=selected_aggregate.present_count if selected_aggregate else 0,
                absent=selected_aggregate.absent_count if selected_aggregate else 0,
            )
            if selected_subject is not None
            else overall
        )

        timetable_entries = await self._timetable.list_by_classroom(
            classroom.id,
            limit=None,
            offset=0,
        )
        timetable_slots = tuple(
            TimetableSlot(
                timetable_entry_id=entry.id,
                subject_id=entry.subject_id,
                weekday=_WEEKDAY_INDEX[entry.day_of_week],
                start_time=entry.start_time,
            )
            for entry in timetable_entries
        )
        scheduled_classes = expand_timetable(
            timetable_slots,
            start_date=planning_date,
            deadline=payload.deadline,
            subject_id=payload.subject_id,
        )
        calculation = calculate_recovery(
            attended=current.attended,
            held=current.held,
            target_percentage=payload.target_percentage,
            scheduled_classes=scheduled_classes,
        )

        return AttendanceRecoveryPlanRead(
            scope="subject" if selected_subject is not None else "overall",
            subject_id=selected_subject.id if selected_subject is not None else None,
            subject_name=selected_subject.name if selected_subject is not None else None,
            target_percentage=float(payload.target_percentage),
            deadline=payload.deadline,
            current=current,
            overall=overall,
            overall_status=subject_attendance_status(
                attended=overall.attended,
                held=overall.held,
                target_percentage=payload.target_percentage,
            ),
            subjects=subject_summaries,
            status=calculation.status,
            reachable=calculation.reachable,
            classes_required=calculation.classes_required,
            scheduled_classes_remaining=calculation.scheduled_classes_remaining,
            scheduled_teaching_days_remaining=calculation.scheduled_teaching_days_remaining,
            teaching_days_required=calculation.teaching_days_required,
            recovery_date=calculation.recovery_date,
            projected_attendance_percentage=calculation.projected_attendance_percentage,
            projected_max_percentage=calculation.projected_max_percentage,
            attendance_buffer_classes=calculation.attendance_buffer_classes,
            schedule_assumption=_SCHEDULE_ASSUMPTION,
        )

    @staticmethod
    def _subject_summary(
        *,
        subject_id: uuid.UUID,
        subject_name: str,
        subject_code: str,
        aggregate: SubjectAttendanceAggregate | None,
        target_percentage: Decimal,
    ) -> SubjectAttendanceSummaryRead:
        total = aggregate.total_count if aggregate else 0
        present = aggregate.present_count if aggregate else 0
        absent = aggregate.absent_count if aggregate else 0
        counts = _counts(total=total, present=present, absent=absent)
        return SubjectAttendanceSummaryRead(
            subject_id=subject_id,
            subject_name=subject_name,
            subject_code=subject_code,
            attended=counts.attended,
            held=counts.held,
            absent=counts.absent,
            percentage=counts.percentage,
            status=subject_attendance_status(
                attended=present,
                held=total,
                target_percentage=target_percentage,
            ),
        )


__all__ = ["AttendanceRecoveryPlannerService"]
