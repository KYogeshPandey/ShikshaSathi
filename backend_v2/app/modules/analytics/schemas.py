"""Typed contracts for truthful, role-aware dashboard analytics."""

from __future__ import annotations

from datetime import date
from enum import IntEnum
from typing import Literal

from pydantic import BaseModel, Field

from app.modules.users.models import UserRole


class AnalyticsWindowDays(IntEnum):
    SEVEN = 7
    THIRTY = 30


class AnalyticsPeriodRead(BaseModel):
    days: AnalyticsWindowDays
    date_from: date
    date_to: date


class AttendanceMetricRead(BaseModel):
    total_count: int
    present_count: int
    absent_count: int
    attendance_percentage: float


class AttendanceTrendPointRead(AttendanceMetricRead):
    attendance_date: date


class AttendanceComparisonRead(BaseModel):
    period: AnalyticsPeriodRead
    attendance: AttendanceMetricRead
    percentage_point_change: float | None


class AdminPopulationRead(BaseModel):
    active_students: int
    active_teachers: int
    active_classrooms: int
    active_subjects: int


class TeacherScopeRead(BaseModel):
    assigned_classrooms: int
    assigned_subjects: int
    timetable_slots: int


class StudentContextRead(BaseModel):
    roll_number: str | None


class ClassroomAttentionRead(AttendanceMetricRead):
    classroom_name: str
    classroom_code: str


class AnalyticsOverviewResponse(BaseModel):
    role: UserRole
    period: AnalyticsPeriodRead
    attendance: AttendanceMetricRead
    comparison: AttendanceComparisonRead
    trend: list[AttendanceTrendPointRead]
    attendance_definition: Literal["present_marked_records_divided_by_all_marked_records"] = (
        "present_marked_records_divided_by_all_marked_records"
    )
    missing_records_policy: Literal["excluded_unmarked"] = "excluded_unmarked"
    admin_population: AdminPopulationRead | None = None
    teacher_scope: TeacherScopeRead | None = None
    student_context: StudentContextRead | None = None
    attention_classrooms: list[ClassroomAttentionRead] = Field(default_factory=list)


__all__ = [
    "AnalyticsOverviewResponse",
    "AnalyticsWindowDays",
]
