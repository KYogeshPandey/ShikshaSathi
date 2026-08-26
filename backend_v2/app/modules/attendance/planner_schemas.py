"""Typed request and response contracts for student attendance recovery planning."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.attendance.planner import AttendancePlanStatus, SubjectAttendanceStatus


class AttendanceRecoveryPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_percentage: Decimal = Field(default=Decimal("75"), gt=0, le=100)
    deadline: date
    subject_id: uuid.UUID | None = None


class AttendanceCountsRead(BaseModel):
    attended: int
    held: int
    absent: int
    percentage: float


class SubjectAttendanceSummaryRead(AttendanceCountsRead):
    subject_id: uuid.UUID
    subject_name: str
    subject_code: str
    status: SubjectAttendanceStatus


class AttendanceRecoveryPlanRead(BaseModel):
    scope: Literal["overall", "subject"]
    subject_id: uuid.UUID | None
    subject_name: str | None
    target_percentage: float
    deadline: date
    current: AttendanceCountsRead
    overall: AttendanceCountsRead
    overall_status: SubjectAttendanceStatus
    subjects: list[SubjectAttendanceSummaryRead]
    status: AttendancePlanStatus
    reachable: bool
    classes_required: int | None
    scheduled_classes_remaining: int
    scheduled_teaching_days_remaining: int
    teaching_days_required: int | None
    recovery_date: date | None
    projected_attendance_percentage: float
    projected_max_percentage: float
    attendance_buffer_classes: int
    schedule_assumption: str


__all__ = [
    "AttendanceCountsRead",
    "AttendanceRecoveryPlanRead",
    "AttendanceRecoveryPlanRequest",
    "SubjectAttendanceSummaryRead",
]
