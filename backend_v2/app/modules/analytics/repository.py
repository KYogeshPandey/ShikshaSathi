"""Set-based aggregation queries for role-aware dashboard analytics."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import Float, and_, cast, func, select
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.modules.academics.models import (
    Classroom,
    Subject,
    TeacherAssignment,
    TimetableEntry,
)
from app.modules.attendance.models import AttendanceRecord, AttendanceStatus
from app.modules.profiles.models import StudentProfile, TeacherProfile
from app.modules.users.models import User, UserRole


@dataclass(frozen=True)
class DailyAttendanceAggregate:
    attendance_date: date
    total_count: int
    present_count: int
    absent_count: int


@dataclass(frozen=True)
class AdminPopulationAggregate:
    active_students: int
    active_teachers: int
    active_classrooms: int
    active_subjects: int


@dataclass(frozen=True)
class TeacherScopeAggregate:
    assigned_classrooms: int
    assigned_subjects: int
    timetable_slots: int


@dataclass(frozen=True)
class ClassroomAttendanceAggregate:
    classroom_name: str
    classroom_code: str
    total_count: int
    present_count: int
    absent_count: int


def _attendance_counts() -> tuple[ColumnElement[int], ColumnElement[int], ColumnElement[int]]:
    total = func.count(AttendanceRecord.id)
    present = func.count(AttendanceRecord.id).filter(
        AttendanceRecord.status == AttendanceStatus.PRESENT
    )
    absent = func.count(AttendanceRecord.id).filter(
        AttendanceRecord.status == AttendanceStatus.ABSENT
    )
    return total, present, absent


def _daily_rows(
    rows: Sequence[Row[tuple[date, int, int, int]]],
) -> list[DailyAttendanceAggregate]:
    return [
        DailyAttendanceAggregate(
            attendance_date=attendance_date,
            total_count=int(total_count),
            present_count=int(present_count),
            absent_count=int(absent_count),
        )
        for attendance_date, total_count, present_count, absent_count in rows
    ]


class AnalyticsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def admin_population(self) -> AdminPopulationAggregate:
        active_students = (
            select(func.count(StudentProfile.id))
            .join(User, User.id == StudentProfile.user_id)
            .where(
                StudentProfile.is_active.is_(True),
                User.is_active.is_(True),
                User.role == UserRole.STUDENT,
            )
            .scalar_subquery()
        )
        active_teachers = (
            select(func.count(TeacherProfile.id))
            .join(User, User.id == TeacherProfile.user_id)
            .where(
                TeacherProfile.is_active.is_(True),
                User.is_active.is_(True),
                User.role == UserRole.TEACHER,
            )
            .scalar_subquery()
        )
        active_classrooms = (
            select(func.count(Classroom.id)).where(Classroom.is_active.is_(True)).scalar_subquery()
        )
        active_subjects = (
            select(func.count(Subject.id)).where(Subject.is_active.is_(True)).scalar_subquery()
        )
        row = (
            await self._session.execute(
                select(
                    active_students.label("active_students"),
                    active_teachers.label("active_teachers"),
                    active_classrooms.label("active_classrooms"),
                    active_subjects.label("active_subjects"),
                )
            )
        ).one()
        return AdminPopulationAggregate(
            active_students=int(row.active_students),
            active_teachers=int(row.active_teachers),
            active_classrooms=int(row.active_classrooms),
            active_subjects=int(row.active_subjects),
        )

    async def teacher_scope(self, teacher_profile_id: uuid.UUID) -> TeacherScopeAggregate:
        assigned_classrooms = (
            select(func.count(func.distinct(TeacherAssignment.classroom_id)))
            .select_from(TeacherAssignment)
            .join(Classroom, Classroom.id == TeacherAssignment.classroom_id)
            .join(Subject, Subject.id == TeacherAssignment.subject_id)
            .where(
                TeacherAssignment.teacher_profile_id == teacher_profile_id,
                TeacherAssignment.is_active.is_(True),
                Classroom.is_active.is_(True),
                Subject.is_active.is_(True),
            )
            .scalar_subquery()
        )
        assigned_subjects = (
            select(func.count(func.distinct(TeacherAssignment.subject_id)))
            .select_from(TeacherAssignment)
            .join(Classroom, Classroom.id == TeacherAssignment.classroom_id)
            .join(Subject, Subject.id == TeacherAssignment.subject_id)
            .where(
                TeacherAssignment.teacher_profile_id == teacher_profile_id,
                TeacherAssignment.is_active.is_(True),
                Classroom.is_active.is_(True),
                Subject.is_active.is_(True),
            )
            .scalar_subquery()
        )
        timetable_slots = (
            select(func.count(func.distinct(TimetableEntry.id)))
            .select_from(TimetableEntry)
            .join(
                TeacherAssignment,
                and_(
                    TeacherAssignment.teacher_profile_id == TimetableEntry.teacher_profile_id,
                    TeacherAssignment.classroom_id == TimetableEntry.classroom_id,
                    TeacherAssignment.subject_id == TimetableEntry.subject_id,
                ),
            )
            .join(Classroom, Classroom.id == TimetableEntry.classroom_id)
            .join(Subject, Subject.id == TimetableEntry.subject_id)
            .where(
                TimetableEntry.teacher_profile_id == teacher_profile_id,
                TimetableEntry.is_active.is_(True),
                TeacherAssignment.is_active.is_(True),
                Classroom.is_active.is_(True),
                Subject.is_active.is_(True),
            )
            .scalar_subquery()
        )
        row = (
            await self._session.execute(
                select(
                    assigned_classrooms.label("assigned_classrooms"),
                    assigned_subjects.label("assigned_subjects"),
                    timetable_slots.label("timetable_slots"),
                )
            )
        ).one()
        return TeacherScopeAggregate(
            assigned_classrooms=int(row.assigned_classrooms),
            assigned_subjects=int(row.assigned_subjects),
            timetable_slots=int(row.timetable_slots),
        )

    async def daily_for_admin(
        self, *, date_from: date, date_to: date
    ) -> list[DailyAttendanceAggregate]:
        total, present, absent = _attendance_counts()
        stmt = (
            select(
                AttendanceRecord.attendance_date,
                total.label("total_count"),
                present.label("present_count"),
                absent.label("absent_count"),
            )
            .select_from(AttendanceRecord)
            .join(StudentProfile, StudentProfile.id == AttendanceRecord.student_profile_id)
            .join(User, User.id == StudentProfile.user_id)
            .join(Classroom, Classroom.id == AttendanceRecord.classroom_id)
            .join(Subject, Subject.id == AttendanceRecord.subject_id)
            .where(
                AttendanceRecord.attendance_date >= date_from,
                AttendanceRecord.attendance_date <= date_to,
                StudentProfile.is_active.is_(True),
                User.is_active.is_(True),
                Classroom.is_active.is_(True),
                Subject.is_active.is_(True),
            )
            .group_by(AttendanceRecord.attendance_date)
            .order_by(AttendanceRecord.attendance_date)
        )
        return _daily_rows(list((await self._session.execute(stmt)).all()))

    async def daily_for_teacher(
        self,
        *,
        teacher_profile_id: uuid.UUID,
        date_from: date,
        date_to: date,
    ) -> list[DailyAttendanceAggregate]:
        total, present, absent = _attendance_counts()
        stmt = (
            select(
                AttendanceRecord.attendance_date,
                total.label("total_count"),
                present.label("present_count"),
                absent.label("absent_count"),
            )
            .select_from(AttendanceRecord)
            .join(
                TeacherAssignment,
                and_(
                    TeacherAssignment.classroom_id == AttendanceRecord.classroom_id,
                    TeacherAssignment.subject_id == AttendanceRecord.subject_id,
                    TeacherAssignment.teacher_profile_id == teacher_profile_id,
                ),
            )
            .join(StudentProfile, StudentProfile.id == AttendanceRecord.student_profile_id)
            .join(User, User.id == StudentProfile.user_id)
            .join(Classroom, Classroom.id == AttendanceRecord.classroom_id)
            .join(Subject, Subject.id == AttendanceRecord.subject_id)
            .where(
                AttendanceRecord.attendance_date >= date_from,
                AttendanceRecord.attendance_date <= date_to,
                TeacherAssignment.is_active.is_(True),
                StudentProfile.is_active.is_(True),
                User.is_active.is_(True),
                Classroom.is_active.is_(True),
                Subject.is_active.is_(True),
            )
            .group_by(AttendanceRecord.attendance_date)
            .order_by(AttendanceRecord.attendance_date)
        )
        return _daily_rows(list((await self._session.execute(stmt)).all()))

    async def daily_for_student(
        self,
        *,
        student_profile_id: uuid.UUID,
        date_from: date,
        date_to: date,
    ) -> list[DailyAttendanceAggregate]:
        total, present, absent = _attendance_counts()
        stmt = (
            select(
                AttendanceRecord.attendance_date,
                total.label("total_count"),
                present.label("present_count"),
                absent.label("absent_count"),
            )
            .where(
                AttendanceRecord.student_profile_id == student_profile_id,
                AttendanceRecord.attendance_date >= date_from,
                AttendanceRecord.attendance_date <= date_to,
            )
            .group_by(AttendanceRecord.attendance_date)
            .order_by(AttendanceRecord.attendance_date)
        )
        return _daily_rows(list((await self._session.execute(stmt)).all()))

    async def lowest_attendance_classrooms(
        self, *, date_from: date, date_to: date, limit: int
    ) -> list[ClassroomAttendanceAggregate]:
        total, present, absent = _attendance_counts()
        rate = cast(present, Float) / func.nullif(total, 0)
        stmt = (
            select(
                Classroom.name.label("classroom_name"),
                Classroom.code.label("classroom_code"),
                total.label("total_count"),
                present.label("present_count"),
                absent.label("absent_count"),
            )
            .select_from(AttendanceRecord)
            .join(StudentProfile, StudentProfile.id == AttendanceRecord.student_profile_id)
            .join(User, User.id == StudentProfile.user_id)
            .join(Classroom, Classroom.id == AttendanceRecord.classroom_id)
            .join(Subject, Subject.id == AttendanceRecord.subject_id)
            .where(
                AttendanceRecord.attendance_date >= date_from,
                AttendanceRecord.attendance_date <= date_to,
                StudentProfile.is_active.is_(True),
                User.is_active.is_(True),
                Classroom.is_active.is_(True),
                Subject.is_active.is_(True),
            )
            .group_by(Classroom.id, Classroom.name, Classroom.code)
            .order_by(rate, Classroom.code)
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            ClassroomAttendanceAggregate(
                classroom_name=classroom_name,
                classroom_code=classroom_code,
                total_count=int(total_count),
                present_count=int(present_count),
                absent_count=int(absent_count),
            )
            for classroom_name, classroom_code, total_count, present_count, absent_count in rows
        ]


__all__ = ["AnalyticsRepository"]
