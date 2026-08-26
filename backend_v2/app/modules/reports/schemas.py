"""Typed response contracts for Phase 8 attendance reports."""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, Field

from app.modules.attendance.models import AttendanceStatus


class ReportPeriodRead(BaseModel):
    month: str | None
    date_from: date
    date_to: date


class AttendanceReportSummary(BaseModel):
    total_count: int
    present_count: int
    absent_count: int
    attendance_percentage: float


class AttendanceReportDetailRow(BaseModel):
    attendance_date: date
    student_profile_id: uuid.UUID
    roll_number: str | None
    full_name: str
    status: AttendanceStatus
    remarks: str | None


class AttendanceReportResponse(BaseModel):
    classroom_id: uuid.UUID
    subject_id: uuid.UUID
    student_profile_id: uuid.UUID | None
    period: ReportPeriodRead
    summary: AttendanceReportSummary
    details: list[AttendanceReportDetailRow]


class StudentAttendanceReportRow(BaseModel):
    student_profile_id: uuid.UUID
    roll_number: str | None
    full_name: str
    total_count: int
    present_count: int
    absent_count: int
    attendance_percentage: float


class DefaultersReportResponse(BaseModel):
    classroom_id: uuid.UUID
    subject_id: uuid.UUID
    period: ReportPeriodRead
    threshold: float = Field(ge=0, le=100)
    zero_attendance_policy: str = "included_as_zero_percent"
    students: list[StudentAttendanceReportRow]


class LeaderboardRow(StudentAttendanceReportRow):
    rank: int = Field(ge=1)


class LeaderboardReportResponse(BaseModel):
    classroom_id: uuid.UUID
    subject_id: uuid.UUID
    period: ReportPeriodRead
    tie_breaking: str = "percentage_desc_roll_number_asc_student_profile_id_asc"
    students: list[LeaderboardRow]
