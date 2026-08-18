"""Set-based PostgreSQL queries for Phase 8 reports.

The active classroom roster is the left side of grouped report queries, so
zero-record students are represented without running one query per student.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.attendance.models import AttendanceRecord, AttendanceStatus
from app.modules.profiles.models import StudentProfile


@dataclass(frozen=True)
class ReportDetailRow:
    attendance_date: date
    student_profile_id: uuid.UUID
    roll_number: str | None
    status: AttendanceStatus
    remarks: str | None


@dataclass(frozen=True)
class RosterAttendanceAggregate:
    student_profile_id: uuid.UUID
    roll_number: str | None
    total_count: int
    present_count: int
    absent_count: int


class ReportsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def is_active_roster_student(
        self, *, classroom_id: uuid.UUID, student_profile_id: uuid.UUID
    ) -> bool:
        stmt = select(StudentProfile.id).where(
            StudentProfile.id == student_profile_id,
            StudentProfile.classroom_id == classroom_id,
            StudentProfile.is_active.is_(True),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def aggregate_summary(
        self,
        *,
        classroom_id: uuid.UUID,
        subject_id: uuid.UUID,
        date_from: date,
        date_to: date,
        student_profile_id: uuid.UUID | None,
    ) -> tuple[int, int, int]:
        stmt = (
            select(
                func.count(AttendanceRecord.id).label("total"),
                func.count(AttendanceRecord.id)
                .filter(AttendanceRecord.status == AttendanceStatus.PRESENT)
                .label("present_count"),
                func.count(AttendanceRecord.id)
                .filter(AttendanceRecord.status == AttendanceStatus.ABSENT)
                .label("absent_count"),
            )
            .select_from(AttendanceRecord)
            .join(StudentProfile, StudentProfile.id == AttendanceRecord.student_profile_id)
            .where(
                AttendanceRecord.classroom_id == classroom_id,
                AttendanceRecord.subject_id == subject_id,
                AttendanceRecord.attendance_date >= date_from,
                AttendanceRecord.attendance_date <= date_to,
                StudentProfile.classroom_id == classroom_id,
                StudentProfile.is_active.is_(True),
            )
        )
        if student_profile_id is not None:
            stmt = stmt.where(AttendanceRecord.student_profile_id == student_profile_id)
        row = (await self._session.execute(stmt)).one()
        return int(row.total), int(row.present_count), int(row.absent_count)

    async def list_details(
        self,
        *,
        classroom_id: uuid.UUID,
        subject_id: uuid.UUID,
        date_from: date,
        date_to: date,
        student_profile_id: uuid.UUID | None,
        limit: int,
    ) -> list[ReportDetailRow]:
        stmt = (
            select(
                AttendanceRecord.attendance_date,
                AttendanceRecord.student_profile_id,
                StudentProfile.roll_number,
                AttendanceRecord.status,
                AttendanceRecord.remarks,
            )
            .select_from(AttendanceRecord)
            .join(StudentProfile, StudentProfile.id == AttendanceRecord.student_profile_id)
            .where(
                AttendanceRecord.classroom_id == classroom_id,
                AttendanceRecord.subject_id == subject_id,
                AttendanceRecord.attendance_date >= date_from,
                AttendanceRecord.attendance_date <= date_to,
                StudentProfile.classroom_id == classroom_id,
                StudentProfile.is_active.is_(True),
            )
        )
        if student_profile_id is not None:
            stmt = stmt.where(AttendanceRecord.student_profile_id == student_profile_id)
        stmt = stmt.order_by(
            AttendanceRecord.attendance_date,
            StudentProfile.roll_number.asc().nulls_last(),
            AttendanceRecord.student_profile_id,
            AttendanceRecord.id,
        ).limit(limit)
        rows = (await self._session.execute(stmt)).all()
        return [
            ReportDetailRow(
                attendance_date=row.attendance_date,
                student_profile_id=row.student_profile_id,
                roll_number=row.roll_number,
                status=row.status,
                remarks=row.remarks,
            )
            for row in rows
        ]

    async def aggregate_active_roster(
        self,
        *,
        classroom_id: uuid.UUID,
        subject_id: uuid.UUID,
        date_from: date,
        date_to: date,
        limit: int,
    ) -> list[RosterAttendanceAggregate]:
        attendance_scope = and_(
            AttendanceRecord.student_profile_id == StudentProfile.id,
            AttendanceRecord.classroom_id == classroom_id,
            AttendanceRecord.subject_id == subject_id,
            AttendanceRecord.attendance_date >= date_from,
            AttendanceRecord.attendance_date <= date_to,
        )
        stmt = (
            select(
                StudentProfile.id.label("student_profile_id"),
                StudentProfile.roll_number,
                func.count(AttendanceRecord.id).label("total"),
                func.count(AttendanceRecord.id)
                .filter(AttendanceRecord.status == AttendanceStatus.PRESENT)
                .label("present_count"),
                func.count(AttendanceRecord.id)
                .filter(AttendanceRecord.status == AttendanceStatus.ABSENT)
                .label("absent_count"),
            )
            .select_from(StudentProfile)
            .outerjoin(AttendanceRecord, attendance_scope)
            .where(
                StudentProfile.classroom_id == classroom_id,
                StudentProfile.is_active.is_(True),
            )
            .group_by(StudentProfile.id, StudentProfile.roll_number)
            .order_by(
                StudentProfile.roll_number.asc().nulls_last(),
                StudentProfile.id,
            )
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            RosterAttendanceAggregate(
                student_profile_id=row.student_profile_id,
                roll_number=row.roll_number,
                total_count=int(row.total),
                present_count=int(row.present_count),
                absent_count=int(row.absent_count),
            )
            for row in rows
        ]
